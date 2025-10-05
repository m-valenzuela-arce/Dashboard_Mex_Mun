import json
from pathlib import Path

import geopandas as gpd
import pandas as pd
import plotly.graph_objects as go
import streamlit as st
from shapely.geometry import Polygon, MultiPolygon
from shapely.ops import unary_union

# -------------------------------
# Configuración básica
# -------------------------------
st.set_page_config(page_title="Mapa de México (Estados y Municipios)", layout="wide")
st.title("Mapa interactivo de México: Estados y Municipios")
st.caption("Selecciona un estado y un municipio para resaltarlos en el mapa. Coloca los GeoJSON en ./data (se aceptan nombres: 'mx_estados.geojson'/'mx_municipios.geojson' o 'states.geojson'/'municipalities.geojson') o súbelos en la barra lateral.")

DATA_DIR = Path("data")
# Acepta nombres comunes: mx_estados.geojson / mx_municipios.geojson o states.geojson / municipalities.geojson
ESTADOS_CANDIDATES = [
    DATA_DIR / "mx_estados.geojson",
    DATA_DIR / "states.geojson",
]
MUNS_CANDIDATES = [
    DATA_DIR / "mx_municipios.geojson",
    DATA_DIR / "municipalities.geojson",
]

def first_existing(paths):
    for p in paths:
        if p.exists():
            return p
    return None

ESTADOS_FILE_DEFAULT = first_existing(ESTADOS_CANDIDATES)
MUNS_FILE_DEFAULT = first_existing(MUNS_CANDIDATES)

# -------------------------------
# Utilidades
# -------------------------------

@st.cache_data(show_spinner=False)
def load_geojson(path: Path) -> gpd.GeoDataFrame:
    gdf = gpd.read_file(path)
    # Asegurar WGS84
    if gdf.crs is None:
        # Si no trae CRS, asumimos WGS84
        gdf.set_crs(4326, inplace=True)
    else:
        gdf = gdf.to_crs(4326)
    return gdf


def guess_name_column(gdf: gpd.GeoDataFrame, candidates=(
    "NOMGEO", "NOM_ENT", "NOM_MUN", "nomgeo", "name", "NOMBRE", "Estado", "Municipio", "estado", "municipio",
)) -> str:
    """Intenta adivinar la columna de nombre más adecuada.
    Retorna la primera candidata que exista; si no hay, intenta la primera columna de texto que no sea geometry.
    """
    for c in candidates:
        if c in gdf.columns:
            return c
    # fallback: primera columna de tipo object con strings
    for c in gdf.columns:
        if c == "geometry":
            continue
        if pd.api.types.is_object_dtype(gdf[c]) or pd.api.types.is_string_dtype(gdf[c]):
            return c
    # última opción
    return gdf.columns[0]


def ensure_data():
    """Obtiene rutas de archivos desde defaults o de uploads en la barra lateral."""
    st.sidebar.subheader("Datos (GeoJSON)")

    # Carga por defecto si existen
    estados_path = ESTADOS_FILE_DEFAULT if ESTADOS_FILE_DEFAULT.exists() else None
    muns_path = MUNS_FILE_DEFAULT if MUNS_FILE_DEFAULT.exists() else None

    up_estados = st.sidebar.file_uploader("Subir GeoJSON de Estados", type=["json", "geojson"], key="estados")
    up_muns = st.sidebar.file_uploader("Subir GeoJSON de Municipios", type=["json", "geojson"], key="muns")

    if up_estados is not None:
        estados_path = Path(st.session_state.get("_tmp_estados_path", "_estados_uploaded.geojson"))
        with open(estados_path, "wb") as f:
            f.write(up_estados.getvalue())
        st.session_state["_tmp_estados_path"] = str(estados_path)

    if up_muns is not None:
        muns_path = Path(st.session_state.get("_tmp_muns_path", "_muns_uploaded.geojson"))
        with open(muns_path, "wb") as f:
            f.write(up_muns.getvalue())
        st.session_state["_tmp_muns_path"] = str(muns_path)

    if estados_path is None or muns_path is None:
        with st.sidebar.expander("Instrucciones de datos", expanded=False):
            st.markdown(
                "- **Opción A (recomendada):** coloca `mx_estados.geojson` y `mx_municipios.geojson` dentro de la carpeta `./data` antes de ejecutar la app.\n"
                "- **Opción B:** sube tus propios archivos GeoJSON arriba.\n"
                "\nLos archivos deben estar en **WGS84 (EPSG:4326)** o tener CRS para reproyectar.")

    return estados_path, muns_path


def explode_exterior_coords(geom: Polygon | MultiPolygon):
    """Devuelve listas de (lon, lat) para dibujar contornos con Scattermapbox.
    Inserta `None` como separador entre anillos.
    """
    def _poly_coords(poly: Polygon):
        x, y = poly.exterior.coords.xy
        return list(x), list(y)

    lons: list[float | None] = []
    lats: list[float | None] = []

    if isinstance(geom, Polygon):
        xs, ys = _poly_coords(geom)
        lons += xs + [None]
        lats += ys + [None]
    elif isinstance(geom, MultiPolygon):
        for p in geom.geoms:
            xs, ys = _poly_coords(p)
            lons += xs + [None]
            lats += ys + [None]
    return lons, lats


# -------------------------------
# Carga de datos
# -------------------------------
estados_path, muns_path = ensure_data()

if not estados_path or not muns_path or (not Path(estados_path).exists()) or (not Path(muns_path).exists()):
    st.warning("⚠️ No se encontraron archivos GeoJSON. Coloca `mx_estados.geojson` y `mx_municipios.geojson` en ./data o súbelos en la barra lateral.")
    st.stop()

with st.spinner("Cargando estados y municipios..."):
    gdf_estados = load_geojson(Path(estados_path))
    gdf_muns = load_geojson(Path(muns_path))

# -------------------------------
# Diagnóstico rápido de archivos
# -------------------------------
st.sidebar.markdown("---")
st.sidebar.subheader("Diagnóstico de archivos")
with st.sidebar.expander("Ver diagnóstico", expanded=False):
    def file_info(p: Path):
        try:
            size = p.stat().st_size if p.exists() else 0
        except Exception:
            size = 0
        return {"ruta": str(p), "existe": p.exists(), "tam_bytes": size}

    st.json({
        "estados": file_info(Path(estados_path)),
        "municipios": file_info(Path(muns_path)),
    })

    def gdf_summary(name: str, gdf: gpd.GeoDataFrame):
        try:
            geom_types = gdf.geometry.geom_type.value_counts().to_dict()
            bounds = list(gdf.total_bounds)  # [minx, miny, maxx, maxy]
            st.markdown(f"**{name}**")
            st.write({
                "CRS": str(gdf.crs),
                "filas": len(gdf),
                "columnas": list(gdf.columns),
                "geom_types": geom_types,
                "bounds[minx,miny,maxx,maxy]": bounds,
            })
            st.dataframe(gdf.head(5))
        except Exception as e:
            st.error(f"No se pudo resumir {name}: {e}")

    gdf_summary("Estados", gdf_estados)
    gdf_summary("Municipios", gdf_muns)

    st.caption("Si descargaste desde GitHub, asegúrate de guardar el **Raw** del GeoJSON, no el HTML de la página.")

# Columnas de nombre
estado_col = guess_name_column(gdf_estados, ("state_name", "NOM_ENT", "NOMGEO", "name", "Estado", "estado"))
mun_col = guess_name_column(gdf_muns, ("mun_name", "NOM_MUN", "NOMGEO", "name", "Municipio", "municipio"))

# -------------------------------
# UI: selectores
# -------------------------------
left, right = st.columns([0.6, 0.4])
with right:
    st.header("Selecciona")
    estados_sorted = sorted(gdf_estados[estado_col].astype(str).unique())
    estado_sel = st.selectbox("Estado", estados_sorted, index=estados_sorted.index("Sonora") if "Sonora" in estados_sorted else 0)
    # Filtrar municipios por estado preferentemente por atributo (state_code) y si no, por sjoin
    gdf_estado_sel = gdf_estados[gdf_estados[estado_col] == estado_sel]
    gdf_muns_in = None
    if "state_code" in gdf_estados.columns and "state_code" in gdf_muns.columns and len(gdf_estado_sel) > 0:
        try:
            state_code_sel = int(pd.to_numeric(gdf_estado_sel["state_code"].iloc[0], errors="coerce"))
            gdf_muns_in = gdf_muns[pd.to_numeric(gdf_muns["state_code"], errors="coerce").astype("Int64") == state_code_sel]
        except Exception:
            gdf_muns_in = None
    if gdf_muns_in is None or len(gdf_muns_in) == 0:
        # Fallback geográfico
        estado_geom = gdf_estado_sel.geometry.unary_union
        try:
            gdf_muns_in = gpd.sjoin(gdf_muns, gpd.GeoDataFrame(geometry=[estado_geom], crs=4326), predicate="intersects")
        except Exception:
            # Fallback por bbox
            gdf_muns_in = gdf_muns[gdf_muns.geometry.bounds.apply(
                lambda r: estado_geom.bounds[0] <= r.minx <= estado_geom.bounds[2] and estado_geom.bounds[1] <= r.miny <= estado_geom.bounds[3],
                axis=1,
            )]

    muns_sorted = sorted(gdf_muns_in[mun_col].astype(str).unique())
    if len(muns_sorted) == 0:
        st.error("No encontré municipios en el estado seleccionado. Revisa tus GeoJSON.")
        st.stop()

    mun_sel = st.selectbox("Municipio", muns_sorted)

    # Controles de estilo
    st.markdown("---")
    st.subheader("Estilo de resaltado")
    estado_outline_width = st.slider("Grosor de contorno del estado", 1, 12, 5)
    muni_line_width = st.slider("Grosor del municipio", 1, 12, 6)
    muni_opacity = st.slider("Opacidad del municipio", 0.1, 1.0, 0.75)

with left:
    st.header("Mapa")

    # Construcción de capas para el mapa
    gdf_estado_sel = gdf_estados[gdf_estados[estado_col] == estado_sel]
    gdf_muni_sel = gdf_muns_in[gdf_muns_in[mun_col] == mun_sel]

    # Centro y zoom aproximado
    centroid = gdf_muni_sel.geometry.unary_union.centroid if not gdf_muni_sel.empty else gdf_estado_sel.geometry.unary_union.centroid
    center = {"lat": centroid.y, "lon": centroid.x}

        # Preparar identificadores estables para Plotly (featureidkey)
    def as_str(s):
        try:
            return s.astype("Int64").astype(str)
        except Exception:
            return s.astype(str)

    gdf_muns_in = gdf_muns_in.copy()
    gdf_muni_sel = gdf_muni_sel.copy()

    # loc_id = state_code-mun_code (único por municipio en todo MX)
    if "state_code" in gdf_muns_in.columns and "mun_code" in gdf_muns_in.columns:
        gdf_muns_in["loc_id"] = as_str(gdf_muns_in["state_code"]) + "-" + as_str(gdf_muns_in["mun_code"]) 
    else:
        # fallback: usa índice (menos robusto)
        gdf_muns_in["loc_id"] = gdf_muns_in.index.astype(str)

    if "state_code" in gdf_muni_sel.columns and "mun_code" in gdf_muni_sel.columns:
        gdf_muni_sel["loc_id"] = as_str(gdf_muni_sel["state_code"]) + "-" + as_str(gdf_muni_sel["mun_code"]) 
    else:
        gdf_muni_sel["loc_id"] = gdf_muni_sel.index.astype(str)

    # GeoJSON (municipios del estado)
    gj_muns = json.loads(gdf_muns_in.to_json())
    gj_muni_sel = json.loads(gdf_muni_sel.to_json())

    # Figura base: todos los municipios (suave)
    fig = go.Figure()
    fig.add_trace(
        go.Choroplethmapbox(
            geojson=gj_muns,
            locations=gdf_muns_in["loc_id"],
            z=[1] * len(gdf_muns_in),
            featureidkey="properties.loc_id",
            colorscale=[[0, "#e6e6e6"], [1, "#e6e6e6"]],
            marker_line_width=0.5,
            marker_line_color="#a3a3a3",
            showscale=False,
            hovertemplate=f"Municipio: %{{customdata[0]}}<extra></extra>",
            customdata=gdf_muns_in[[mun_col]].astype(str).values,
            opacity=0.6,
        )
    )

    # Capa de municipio seleccionado (resaltado)
    fig.add_trace(
        go.Choroplethmapbox(
            geojson=gj_muni_sel,
            locations=gdf_muni_sel["loc_id"],
            z=[1] * len(gdf_muni_sel),
            featureidkey="properties.loc_id",
            colorscale=[[0, "#ffcc00"], [1, "#ffcc00"]],
            marker_line_width=muni_line_width,
            marker_line_color="#000000",
            showscale=False,
            hovertemplate=f"Municipio seleccionado: %{{customdata[0]}}<extra></extra>",
            customdata=gdf_muni_sel[[mun_col]].astype(str).values,
            opacity=muni_opacity,
        )
    )

    # Contorno del estado
    estado_union = unary_union(gdf_estado_sel.geometry)
    lons, lats = explode_exterior_coords(estado_union)
    fig.add_trace(
        go.Scattermapbox(
            lon=lons,
            lat=lats,
            mode="lines",
            line=dict(width=estado_outline_width, color="#111111"),
            name="Contorno estado",
            hoverinfo="skip",
        )
    )

    fig.update_layout(
        mapbox_style="carto-positron",
        mapbox_zoom=7.2,
        mapbox_center=center,
        margin=dict(l=0, r=0, t=0, b=0),
        height=720,
    )

    st.plotly_chart(fig, use_container_width=True)

# -------------------------------
# Notas/ayuda
# -------------------------------
with st.expander("Ayuda y notas"):
    st.markdown(
        """
        **Formato esperado de los datos**
        - GeoJSON de **estados** y **municipios** en **EPSG:4326 (WGS84)**.
        - La app intenta detectar automáticamente las columnas de **nombre** (por ejemplo `NOM_ENT` para estados y `NOM_MUN` para municipios). Si tus archivos usan otros nombres, igual intentará adivinar; si no, renombra esas columnas.

        **Cómo preparar los datos**
        1. Crea una carpeta `data/` junto a este archivo.
        2. Coloca ahí `mx_estados.geojson` y `mx_municipios.geojson` (o usa el cargador de archivos en la barra lateral).

        **Personalización visual**
        - En la derecha puedes ajustar el grosor del contorno del estado y del municipio, así como la opacidad del municipio seleccionado.

        **Tip**
        - Si el *spatial join* falla por topología en tus datos, el código usa un *fallback* por *bounding box* para no romper la app. Idealmente, usa geometrías válidas y limpias.
        """
    )
