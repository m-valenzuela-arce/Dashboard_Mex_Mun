# app_mapa_mexico_estados_municipios.py
# Streamlit + Plotly para mapa interactivo de México por estado (archivos por estado)
# Coloca en ./data los archivos GeoJSON por estado con extensión .json (uno por estado):
#   Aguascalientes.json, Baja California.json, ... , Yucatán.json, Zacatecas.json
# El contenido puede llamarse .json aunque sea GeoJSON válido (FeatureCollection).
#
# Requisitos:
#   pip install streamlit plotly geopandas shapely pyproj
#
# Ejecuta:
#   streamlit run app_mapa_mexico_estados_municipios.py

import json
import os
import unicodedata
from pathlib import Path

import geopandas as gpd
import plotly.graph_objects as go
import streamlit as st
from shapely.ops import unary_union

# ---------- Configuración básica ----------
st.set_page_config(page_title="Mapa Estados y Municipios (MX)", layout="wide")

st.title("Mapa interactivo de México: Estados y Municipios (archivos por estado)")
st.caption("Coloca tus archivos por estado (GeoJSON en formato .json) dentro de la carpeta `./data`.")

DATA_DIR = Path("data")

# ---------- Utilidades ----------

@st.cache_data(show_spinner=False)
def listar_archivos_estado(data_dir: Path):
    """Devuelve dict {nombre_base_sin_ext: ruta} para todos los .json en data_dir."""
    archivos = {}
    if data_dir.exists():
        for p in data_dir.glob("*.json"):
            archivos[p.stem] = p
    return archivos

def normalizar(s: str) -> str:
    """Normaliza texto para comparaciones robustas (quita acentos/espacios extras, minúsculas)."""
    s = unicodedata.normalize("NFKD", s)
    s = "".join(c for c in s if not unicodedata.combining(c))
    return " ".join(s.lower().split())

# Mapeo de nombres “comunes” -> nombre real del archivo (sin .json)
# Lo que pediste: usar estos nombres cortos en el selector.
NOMBRE_COMUN_A_ARCHIVO = {
    "estado de mexico": "México",
    "veracruz": "Veracruz de Ignacio de la Llave",
    "michoacan": "Michoacán de Ocampo",
    "ciudad de mexico": "Ciudad de México",
    "coahuila": "Coahuila de Zaragoza",
}

# ---------- Carga de datos por estado ----------

@st.cache_data(show_spinner=True)
def cargar_municipios_estado(path_json: Path) -> gpd.GeoDataFrame:
    """
    Carga un GeoJSON (aunque su extensión sea .json) de municipios de un estado.
    Asegura que existan columnas estandarizadas:
      - 'mun_name' para el nombre del municipio
      - 'mun_code' si existe código
    Añade 'mun_id' (índice entero) para enlazar con Plotly.
    """
    # Algunos archivos pueden fallar con fiona si tienen CRSs raros; gpd.read_file suele manejarlo bien.
    gdf = gpd.read_file(path_json)

    # Detectar nombre de columna de municipio
    posibles_nombres = ["NOMGEO", "mun_name", "NOM_MUN", "NOM_MPIO", "NOMBRE", "name"]
    mun_col = None
    for c in posibles_nombres:
        if c in gdf.columns:
            mun_col = c
            break
    if mun_col is None:
        # Si no encontramos, crea una genérica
        gdf["mun_name"] = gdf.index.astype(str)
        mun_col = "mun_name"
    else:
        if mun_col != "mun_name":
            gdf = gdf.rename(columns={mun_col: "mun_name"})

    # Código de municipio (si existe)
    posibles_cod = ["CVEGEO", "CVE_MUN", "clave", "code", "MUN", "MUN_CODE", "CVE_MPIO"]
    for c in posibles_cod:
        if c in gdf.columns:
            gdf = gdf.rename(columns={c: "mun_code"})
            break
    if "mun_code" not in gdf.columns:
        gdf["mun_code"] = None

    # Asegurar CRS WGS84
    try:
        if gdf.crs is None:
            # Asumimos WGS84 si viene vacío (muchos archivos de INEGI vienen así pero coords son lon/lat)
            gdf.set_crs("EPSG:4326", inplace=True)
        else:
            gdf = gdf.to_crs("EPSG:4326")
    except Exception:
        # Si algo falla, seguimos sin reproyectar
        pass

    # ID único para plotly featureidkey
    gdf = gdf.reset_index(drop=True)
    gdf["mun_id"] = gdf.index.astype(int)

    return gdf

def construir_geojson_from_gdf(gdf: gpd.GeoDataFrame) -> dict:
    """Convierte el GeoDataFrame a dict GeoJSON con propiedades incluidas."""
    gj = json.loads(gdf.to_json())
    return gj

# ---------- UI: selección de estado/municipio y estilos ----------

col_left, col_right = st.columns([1, 3])

with col_left:
    st.subheader("Selecciona")

    archivos = listar_archivos_estado(DATA_DIR)
    if not archivos:
        st.error("No se encontraron archivos `.json` en `./data`. Coloca los 32 archivos por estado ahí.")
        st.stop()

    # Construir lista de etiquetas de estados para selector:
    #   - Si el archivo tiene un nombre mapeado -> mostrar el nombre común.
    #   - Si no, mostrar el nombre del archivo tal cual (sin ext).
    etiqueta_a_archivo = {}
    usados = set()
    # Primero agrega los mapeados (si existen en el directorio):
    for comun_norm, archivo_base in NOMBRE_COMUN_A_ARCHIVO.items():
        # Buscar la clave exacta que haya en archivos (case/acentos correctos):
        # archivos keys are stems (with proper accents).
        if archivo_base in archivos:
            etiqueta = archivo_base  # etiqueta visible por defecto
            # Cambiamos etiqueta visible al nombre "común" como pediste
            if comun_norm == "estado de mexico":
                etiqueta = "Estado de México"
            elif comun_norm == "veracruz":
                etiqueta = "Veracruz"
            elif comun_norm == "michoacan":
                etiqueta = "Michoacán"
            elif comun_norm == "ciudad de mexico":
                etiqueta = "Ciudad de México"
            elif comun_norm == "coahuila":
                etiqueta = "Coahuila"
            etiqueta_a_archivo[etiqueta] = archivos[archivo_base]
            usados.add(archivo_base)

    # Luego agrega el resto de estados tal cual aparezcan
    for stem, ruta in sorted(archivos.items()):
        if stem not in usados:
            etiqueta_a_archivo[stem] = ruta

    opciones_estado = list(etiqueta_a_archivo.keys())

    estado_sel = st.selectbox("Estado", opciones_estado, index=opciones_estado.index("Sonora") if "Sonora" in opciones_estado else 0)

    # Cargar municipios del estado seleccionado
    gdf_muns = cargar_municipios_estado(etiqueta_a_archivo[estado_sel])

    # Selector de municipio por nombre (mun_name)
    muns_ordenados = sorted(gdf_muns["mun_name"].astype(str).unique())
    mun_sel = st.selectbox("Municipio", muns_ordenados, index=0)

    st.subheader("Estilo de resaltado")
    lw_estado = st.slider("Grosor de contorno del estado", 1, 12, 3)
    lw_mun = st.slider("Grosor del municipio", 1, 12, 3)
    op_mun = st.slider("Opacidad del municipio", 0.10, 1.00, 0.6, step=0.05)

with col_right:
    st.subheader("Mapa")

    # GeoJSON de municipios
    gj_muns = construir_geojson_from_gdf(gdf_muns)

    # Índice del municipio seleccionado
    mun_row = gdf_muns[gdf_muns["mun_name"].astype(str) == str(mun_sel)]
    if mun_row.empty:
        st.warning("No se encontró el municipio seleccionado en el archivo del estado.")
        st.stop()
    sel_id = int(mun_row.iloc[0]["mun_id"])

    # Geometría del estado (unión de municipios) para contorno
    try:
        geom_estado = unary_union(gdf_muns.geometry)
        gdf_estado = gpd.GeoDataFrame({"name": [estado_sel]}, geometry=[geom_estado], crs=gdf_muns.crs)
        gdf_estado["eid"] = 0
        gj_estado = json.loads(gdf_estado.to_json())
    except Exception as e:
        gj_estado = None

    # Construir figura
    fig = go.Figure()

    # Capa 1: Contorno del estado (sin relleno, solo línea)
    if gj_estado is not None:
        fig.add_trace(
            go.Choroplethmapbox(
                geojson=gj_estado,
                featureidkey="properties.eid",
                locations=[0],
                z=[1],  # dummy
                colorscale=[[0, "rgba(0,0,0,0)"], [1, "rgba(0,0,0,0)"]],
                showscale=False,
                marker_line_width=lw_estado,
                marker_line_color="black",
                hovertemplate="<b>%{customdata}</b><extra></extra>",
                customdata=[estado_sel],
                opacity=0.01,  # casi transparente (sólo borde)
            )
        )

    # Capa 2: Municipios (todos) con baja opacidad (gris claro)
    fig.add_trace(
        go.Choroplethmapbox(
            geojson=gj_muns,
            featureidkey="properties.mun_id",
            locations=gdf_muns["mun_id"],
            z=[1] * len(gdf_muns),
            colorscale=[[0, "#D3D3D3"], [1, "#D3D3D3"]],
            showscale=False,
            marker_line_width=0.5,
            marker_line_color="#666",
            hovertemplate="<b>%{customdata[0]}</b><br>CVE: %{customdata[1]}<extra></extra>",
            customdata=list(zip(gdf_muns["mun_name"].astype(str), gdf_muns.get("mun_code", [""] * len(gdf_muns)).astype(str))),
            opacity=0.35,
        )
    )

    # Capa 3: Municipio seleccionado (color destacado)
    fig.add_trace(
        go.Choroplethmapbox(
            geojson=gj_muns,
            featureidkey="properties.mun_id",
            locations=[sel_id],
            z=[10],
            colorscale=[[0, "#1f77b4"], [1, "#1f77b4"]],  # azul por defecto de Plotly
            showscale=False,
            marker_line_width=lw_mun,
            marker_line_color="#1f77b4",
            hovertemplate="<b>%{customdata[0]}</b><br>CVE: %{customdata[1]}<extra></extra>",
            customdata=[(str(mun_row.iloc[0]['mun_name']), str(mun_row.iloc[0].get('mun_code', '')))],
            opacity=op_mun,
        )
    )

    # Centrar el mapa al estado (bounds)
    try:
        bounds = gdf_muns.total_bounds  # [minx, miny, maxx, maxy]
        center_lon = float((bounds[0] + bounds[2]) / 2)
        center_lat = float((bounds[1] + bounds[3]) / 2)
        zoom_guess = 5  # ajustaremos un poco según tamaño del estado
        # Heurística de zoom
        dx = bounds[2] - bounds[0]
        dy = bounds[3] - bounds[1]
        span = max(dx, dy)
        if span < 1.5:
            zoom_guess = 7
        if span < 1.0:
            zoom_guess = 8
        if span < 0.5:
            zoom_guess = 9
    except Exception:
        center_lon, center_lat, zoom_guess = -102.0, 23.5, 4.2

    fig.update_layout(
        mapbox_style="carto-positron",
        mapbox_zoom=zoom_guess,
        mapbox_center={"lon": center_lon, "lat": center_lat},
        margin=dict(l=0, r=0, t=0, b=0),
        height=720,
    )

    st.plotly_chart(fig, use_container_width=True)

# ---------- Panel de diagnóstico (opcional) ----------
with st.expander("Ver diagnóstico de archivos / capas"):
    st.write({
        "data_dir": str(DATA_DIR.resolve()),
        "num_archivos_json": len(listar_archivos_estado(DATA_DIR)),
        "estado_seleccionado": estado_sel,
        "ruta_estado": str(etiqueta_a_archivo[estado_sel]),
        "gdf_muns_shape": gdf_muns.shape,
        "gdf_muns_columns": list(gdf_muns.columns),
        "gdf_muns_crs": str(gdf_muns.crs),
        "bounds[minx,miny,maxx,maxy]": list(map(float, gdf_muns.total_bounds)),
    })
