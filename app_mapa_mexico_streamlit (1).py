# -*- coding: utf-8 -*-
import os
import json
import unicodedata
import streamlit as st
import geopandas as gpd
import pandas as pd
import numpy as np
import plotly.graph_objects as go
from shapely.ops import unary_union

st.set_page_config(page_title="Mapa interactivo México (Estados y Municipios)", layout="wide")

# ---------------------------
# Utilidades
# ---------------------------
DATA_DIR = "data"

def strip_accents(s: str) -> str:
    if s is None:
        return ""
    return "".join(c for c in unicodedata.normalize("NFD", s)
                   if unicodedata.category(c) != "Mn")

def simplify_name(s: str) -> str:
    s = (s or "").strip()
    s = s.replace("_", " ").replace("-", " ")
    s = strip_accents(s).lower()
    s = " ".join(s.split())
    return s

# Nombres "cortos" → oficiales
OFFICIAL_NAME_MAP = {
    "mexico": "estado de mexico",
    "estado de mexico": "estado de mexico",
    "veracruz": "veracruz de ignacio de la llave",
    "michoacan": "michoacan de ocampo",
    "coahuila": "coahuila de zaragoza",
    "nuevo leon": "nuevo leon",
    "ciudad de mexico": "ciudad de mexico",
    "cdmx": "ciudad de mexico",
    "distrito federal": "ciudad de mexico",
}

# Columnas candidatas para nombre de municipio
MUN_NAME_CANDIDATES = [
    "NOMGEO", "mun_name", "MUN_NAME", "MUNICIPIO",
    "NOM_MUN", "nom_mun", "NOM_MPIO", "NOM_MUNI", "NOM_LOC"
]

@st.cache_data(show_spinner=False)
def list_state_files():
    """Lista archivos por-estado .json/.geojson presentes en ./data."""
    if not os.path.isdir(DATA_DIR):
        return {}
    files = [f for f in os.listdir(DATA_DIR)
             if f.lower().endswith(".json") or f.lower().endswith(".geojson")]
    mapping = {}
    for f in files:
        base = os.path.splitext(f)[0]  # sin extensión
        norm = simplify_name(base)
        mapping[norm] = os.path.join(DATA_DIR, f)
    return mapping

def match_state_to_file(user_choice: str, available_map: dict) -> str:
    """Encuentra la mejor coincidencia de archivo para el nombre de estado seleccionado."""
    if not user_choice:
        return None
    key = simplify_name(user_choice)
    key = OFFICIAL_NAME_MAP.get(key, key)  # normaliza alias
    if key in available_map:
        return available_map[key]
    for k, path in available_map.items():
        if key == k:
            return path
    for k, path in available_map.items():
        if key in k or k in key:
            return path
    return None

def fix_gdf(gdf: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    """Repara CRS, geometrías y deduplica columnas."""
    try:
        if gdf.crs is None:
            gdf = gdf.set_crs(4326, allow_override=True)
        elif gdf.crs.to_epsg() != 4326:
            gdf = gdf.to_crs(epsg=4326)
    except Exception:
        gdf = gdf.set_crs(4326, allow_override=True)

    # Repara geometrías inválidas
    try:
        invalid = ~gdf.geometry.is_valid
        if invalid.any():
            gdf.loc[invalid, gdf.geometry.name] = gdf.loc[invalid, gdf.geometry.name].buffer(0)
    except Exception:
        pass

    # Dedup de columnas
    gdf = gdf.copy()
    seen = {}
    new_cols = []
    for c in gdf.columns:
        if c in seen:
            seen[c] += 1
            new_cols.append(f"{c}__{seen[c]}")
        else:
            seen[c] = 0
            new_cols.append(c)
    gdf.columns = new_cols
    return gdf

def find_mun_name_col(gdf: gpd.GeoDataFrame) -> str:
    cols_lower = {c.lower(): c for c in gdf.columns}
    for cand in MUN_NAME_CANDIDATES:
        if cand.lower() in cols_lower:
            return cols_lower[cand.lower()]
    textish = [c for c in gdf.columns if gdf[c].dtype == object]
    for c in textish:
        cl = c.lower()
        if "mun" in cl or "nom" in cl or "geo" in cl:
            return c
    return textish[0] if textish else None

def dissolve_state_outline(gdf: gpd.GeoDataFrame):
    """Crea un contorno del estado a partir del dissolve de todos los municipios."""
    try:
        geom = unary_union(gdf.geometry)
        return gpd.GeoSeries([geom], crs=gdf.crs)
    except Exception:
        return None

def gdf_to_featurecollection_minimal(gdf: gpd.GeoDataFrame, key_col: str):
    """
    GeoJSON mínimo: geometry + key_col + __loc__ (en properties).
    """
    keep = [c for c in [key_col, "__loc__", gdf.geometry.name] if c in gdf.columns]
    gdf2 = gdf[keep].copy()
    return json.loads(gdf2.to_json())

def gdf_to_featurecollection_with_ids(gdf: gpd.GeoDataFrame, key_col: str):
    """
    GeoJSON con feature.id = __loc__ (útil para descargas limpias).
    """
    keep = [c for c in [key_col, "__loc__", gdf.geometry.name] if c in gdf.columns]
    gdf2 = gdf[keep].copy()
    gj = json.loads(gdf2.to_json())
    for feat in gj.get("features", []):
        props = feat.get("properties", {})
        feat["id"] = str(props.get("__loc__", ""))
    return gj

@st.cache_data(show_spinner=False)
def read_gdf(path: str) -> gpd.GeoDataFrame:
    return gpd.read_file(path)

# ---------------------------
# UI
# ---------------------------
st.title("Mapa interactivo de México: Estados y Municipios (archivos por-estado)")

with st.sidebar:
    st.header("Fuentes de datos")
    st.write(f"Carpeta de datos: `./{DATA_DIR}`")
    st.caption("Acepta archivos por-estado .json y .geojson con municipios.")

    st.header("Selección")
    avail = list_state_files()
    if not avail:
        st.error("No encontré archivos .json/.geojson por-estado en ./data.")
        st.stop()

    pretty_states = sorted([os.path.splitext(os.path.basename(p))[0] for p in avail.values()],
                           key=lambda s: simplify_name(s))
    estado_sel = st.selectbox("Estado", options=pretty_states, index=0)

    st.markdown("---")
    # Visual
    base_opacity = st.slider("Opacidad de la capa base", 0.10, 1.00, 0.35, step=0.05)
    lw_estado = st.slider("Grosor de contorno del estado", 1, 12, 3)
    lw_mun = st.slider("Grosor del municipio", 1, 12, 4)
    op_mun = st.slider("Opacidad del municipio", 0.10, 1.00, 0.6, step=0.05)
    mun_color = st.color_picker("Color del municipio seleccionado", value="#4169E1")  # royalblue

    st.markdown("---")
    show_outline = st.checkbox("Mostrar contorno del estado", value=True)
    auto_zoom = st.checkbox("Ajustar zoom automáticamente al estado", value=True)
    if not auto_zoom:
        zoom_manual = st.slider("Zoom manual", 3.0, 9.5, 5.0, step=0.1)

    st.markdown("---")
    simplify_on = st.checkbox("Simplificar geometrías (mejora rendimiento)", value=False)
    tol = st.slider("Tolerancia de simplificación (grados)", 0.0, 0.005, 0.0000, step=0.0001, format="%.4f")

# ---------------------------
# Carga del estado (cache + spinner)
# ---------------------------
with st.spinner("Cargando geometrías..."):
    file_map = list_state_files()
    chosen_path = match_state_to_file(estado_sel, file_map)
    if not chosen_path or not os.path.exists(chosen_path):
        st.error(f"No pude localizar el archivo del estado seleccionado: '{estado_sel}'.")
        st.stop()

    try:
        gdf_muns = read_gdf(chosen_path)
    except Exception as e:
        st.error(f"Error leyendo el archivo '{chosen_path}': {e}")
        st.stop()

    gdf_muns = fix_gdf(gdf_muns)

# Filtro: sólo Polygon/MultiPolygon y geometría no nula
gdf_muns = gdf_muns[gdf_muns.geometry.notna()].copy()
gdf_muns = gdf_muns[gdf_muns.geometry.geom_type.isin(["Polygon", "MultiPolygon"])].copy()

# Simplificación opcional
if simplify_on and tol > 0:
    try:
        gdf_muns.geometry = gdf_muns.geometry.simplify(tol, preserve_topology=True)
    except Exception:
        st.warning("No se pudo simplificar la geometría con el valor dado. Se continúa sin simplificar.")

# Columna de municipio
mun_col = find_mun_name_col(gdf_muns)
if not mun_col:
    st.error("No pude identificar la columna de nombre de municipio. Revisa el archivo.")
    st.write("Columnas disponibles:", list(gdf_muns.columns))
    st.stop()

# Lista de municipios
mun_list = sorted(gdf_muns[mun_col].astype(str).fillna("").unique())
mun_sel = st.selectbox("Municipio", options=mun_list, index=0)

# ---------------------------
# Construcción de figura
# ---------------------------
fig = go.Figure()

# Centro y zoom (heurística)
minx, miny, maxx, maxy = gdf_muns.total_bounds
cx, cy = (minx + maxx) / 2, (miny + maxy) / 2
diag = max(maxx - minx, maxy - miny)
zoom_auto = 4.5
if diag < 1.5:
    zoom_auto = 6.2
elif diag < 3:
    zoom_auto = 5.4
elif diag < 6:
    zoom_auto = 4.8
zoom = zoom_auto if auto_zoom else zoom_manual

# Capa base: todos los municipios (gris)
gdf_muns = gdf_muns.reset_index(drop=True).copy()
gdf_muns["__loc__"] = gdf_muns.index.astype(str)
gj_muns = gdf_to_featurecollection_minimal(gdf_muns, key_col=mun_col)

fig.add_trace(
    go.Choroplethmapbox(
        geojson=gj_muns,
        featureidkey="properties.__loc__",
        locations=gdf_muns["__loc__"].astype(str).tolist(),
        z=[1.0 for _ in range(len(gdf_muns))],
        colorscale="Greys",
        showscale=False,
        marker_line_width=0.5,      # alias planos (compatibilidad)
        marker_line_color="gray",
        name="Municipios",
        opacity=base_opacity,
    )
)

# Municipio seleccionado (color elegido)
sel = gdf_muns[gdf_muns[mun_col].astype(str) == str(mun_sel)].copy()
if sel.empty:
    st.error("No encontré el municipio seleccionado en el GeoDataFrame. Verifica acentos/nombres.")
    st.stop()

sel["__loc__"] = ["0"]
gj_sel = gdf_to_featurecollection_minimal(sel, key_col=mun_col)

fig.add_trace(
    go.Choroplethmapbox(
        geojson=gj_sel,
        featureidkey="properties.__loc__",
        locations=sel["__loc__"].astype(str).tolist(),
        z=[1.0],
        colorscale=[[0, mun_color], [1, mun_color]],
        showscale=False,
        marker_line_width=lw_mun,
        marker_line_color="navy",
        name=f"{mun_sel}",
        opacity=op_mun,
    )
)

# Contorno del estado (disuelto)
if show_outline:
    outline = dissolve_state_outline(gdf_muns)
    if outline is not None and not outline.is_empty.any():
        try:
            geom = outline.iloc[0]
            outlines = []
            if geom.geom_type == "Polygon":
                outlines = [geom.exterior.coords]
            elif geom.geom_type == "MultiPolygon":
                outlines = [poly.exterior.coords for poly in geom.geoms]

            for coords in outlines:
                xs = [pt[0] for pt in coords]
                ys = [pt[1] for pt in coords]
                fig.add_trace(
                    go.Scattermapbox(
                        lon=xs, lat=ys,
                        mode="lines",
                        line=dict(width=lw_estado, color="black"),
                        name=f"Contorno {estado_sel}",
                    )
                )
        except Exception:
            pass

# Estilo y centrado
mapbox_kwargs = dict(
    center={"lat": cy, "lon": cx},
    zoom=zoom,
)
# Si hay token en secrets, úsalo (estilos Mapbox); si no, carto-positron
mapbox_token = st.secrets.get("MAPBOX_TOKEN", None) if hasattr(st, "secrets") else None
if mapbox_token:
    fig.update_layout(
        mapbox_accesstoken=mapbox_token,
        mapbox_style="mapbox://styles/mapbox/streets-v12",
        margin=dict(l=0, r=0, t=0, b=0),
        legend=dict(orientation="h", y=0.02),
        mapbox=mapbox_kwargs,
    )
else:
    fig.update_layout(
        mapbox_style="carto-positron",
        margin=dict(l=0, r=0, t=0, b=0),
        legend=dict(orientation="h", y=0.02),
        mapbox=mapbox_kwargs,
    )

# Bounds opcionales cuando el zoom es automático
if auto_zoom:
    fig.update_layout(mapbox_bounds={
        "west": float(minx), "east": float(maxx),
        "south": float(miny), "north": float(maxy)
    })

st.subheader("Mapa")
st.plotly_chart(fig, use_container_width=True)

# ---------------------------
# Descargas
# ---------------------------
# Municipio seleccionado
sel_download = gdf_to_featurecollection_with_ids(sel, key_col=mun_col)
st.download_button(
    "Descargar municipio seleccionado (.geojson)",
    data=json.dumps(sel_download),
    file_name=f"{simplify_name(estado_sel)}_{simplify_name(mun_sel)}.geojson",
    mime="application/geo+json"
)

# Estado completo
state_download = gdf_to_featurecollection_with_ids(gdf_muns, key_col=mun_col)
st.download_button(
    "Descargar estado completo (.geojson)",
    data=json.dumps(state_download),
    file_name=f"{simplify_name(estado_sel)}.geojson",
    mime="application/geo+json"
)

# ---------------------------
# Diagnóstico rápido
# ---------------------------
with st.expander("Diagnóstico del archivo cargado"):
    st.json({
        "archivo": os.path.basename(chosen_path),
        "CRS": str(getattr(gdf_muns, "crs", None)),
        "filas": int(gdf_muns.shape[0]),
        "columnas": list(gdf_muns.columns),
        "geom_types": dict(pd.Series(gdf_muns.geometry.geom_type).value_counts()),
        "bounds[minx,miny,maxx,maxy]": list(map(float, [minx, miny, maxx, maxy])),
        "columna_municipio_detectada": mun_col,
        "simplificado": simplify_on,
        "tolerancia_simplificacion": float(tol),
    })
