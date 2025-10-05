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

# Nombres "cortos" → nombres oficiales que suelen venir en archivos
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

    try:
        invalid = ~gdf.geometry.is_valid
        if invalid.any():
            gdf.loc[invalid, gdf.geometry.name] = gdf.loc[invalid, gdf.geometry.name].buffer(0)
    except Exception:
        pass

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
    try:
        geom = unary_union(gdf.geometry)
        return gpd.GeoSeries([geom], crs=gdf.crs)
    except Exception:
        return None

def gdf_to_featurecollection_with_ids(gdf: gpd.GeoDataFrame, key_col: str):
    """
    Exporta GeoJSON mínimo con feature.id = __loc__ (para que Plotly mapee sin featureidkey).
    Incluye sólo geometry + key_col + __loc__.
    """
    keep = [c for c in [key_col, "__loc__", gdf.geometry.name] if c in gdf.columns]
    gdf2 = gdf[keep].copy()
    gj = json.loads(gdf2.to_json())
    # poner id a cada feature
    for feat in gj.get("features", []):
        loc = None
        props = feat.get("properties", {})
        if "__loc__" in props:
            loc = str(props["__loc__"])
        feat["id"] = loc
    return gj

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

    lw_estado = st.slider("Grosor de contorno del estado", 1, 12, 3)
    lw_mun = st.slider("Grosor del municipio", 1, 12, 4)
    op_mun = st.slider("Opacidad del municipio", 0.10, 1.00, 0.6, step=0.05)

# ---------------------------
# Carga del estado
# ---------------------------
file_map = list_state_files()
chosen_path = match_state_to_file(estado_sel, file_map)
if not chosen_path or not os.path.exists(chosen_path):
    st.error(f"No pude localizar el archivo del estado seleccionado: '{estado_sel}'.")
    st.stop()

try:
    gdf_muns = gpd.read_file(chosen_path)
except Exception as e:
    st.error(f"Error leyendo el archivo '{chosen_path}': {e}")
    st.stop()

gdf_muns = fix_gdf(gdf_muns)

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

# Centro y zoom
minx, miny, maxx, maxy = gdf_muns.total_bounds
cx, cy = (minx + maxx) / 2, (miny + maxy) / 2
diag = max(maxx - minx, maxy - miny)
zoom = 4.5
if diag < 1.5:
    zoom = 6.2
elif diag < 3:
    zoom = 5.4
elif diag < 6:
    zoom = 4.8

# Base: todos los municipios (gris)
gdf_muns = gdf_muns.reset_index(drop=True).copy()
gdf_muns["__loc__"] = gdf_muns.index.astype(str)
gj_muns = gdf_to_featurecollection_with_ids(gdf_muns, key_col=mun_col)

fig.add_trace(
    go.Choroplethmapbox(
        geojson=gj_muns,
        # SIN featureidkey (usamos feature.id)
        locations=gdf_muns["__loc__"],
        z=[1]*len(gdf_muns),
        colorscale=[[0, "lightgray"], [1, "lightgray"]],
        showscale=False,
        marker_line_width=0.5,
        marker_line_color="gray",
        name="Municipios",
        opacity=0.35,
    )
)

# Municipio seleccionado (azul)
sel = gdf_muns[gdf_muns[mun_col].astype(str) == str(mun_sel)].copy()
if sel.empty:
    st.error("No encontré el municipio seleccionado en el GeoDataFrame. Verifica acentos/nombres.")
    st.stop()

sel["__loc__"] = ["0"]
gj_sel = gdf_to_featurecollection_with_ids(sel, key_col=mun_col)

fig.add_trace(
    go.Choroplethmapbox(
        geojson=gj_sel,
        locations=sel["__loc__"],
        z=[1],
        colorscale=[[0, "royalblue"], [1, "royalblue"]],
        showscale=False,
        marker_line_width=lw_mun,
        marker_line_color="navy",
        hovertemplate=f"<b>{estado_sel}</b><br>{mun_sel}<extra></extra>",
        name=f"{mun_sel}",
        opacity=op_mun,
    )
)

# Contorno del estado (disuelto) usando Scattermapbox
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

fig.update_layout(
    mapbox_style="carto-positron",
    mapbox_center={"lat": cy, "lon": cx},
    mapbox_zoom=zoom,
    margin=dict(l=0, r=0, t=0, b=0),
    legend=dict(orientation="h", y=0.02)
)

st.subheader("Mapa")
st.plotly_chart(fig, use_container_width=True)

# Diagnóstico
with st.expander("Diagnóstico del archivo cargado"):
    st.json({
        "archivo": os.path.basename(chosen_path),
        "CRS": str(getattr(gdf_muns, "crs", None)),
        "filas": int(gdf_muns.shape[0]),
        "columnas": list(gdf_muns.columns),
        "geom_types": dict(pd.Series(gdf_muns.geometry.geom_type).value_counts()),
        "bounds[minx,miny,maxx,maxy]": list(map(float, gdf_muns.total_bounds)),
        "columna_municipio_detectada": mun_col,
    })
