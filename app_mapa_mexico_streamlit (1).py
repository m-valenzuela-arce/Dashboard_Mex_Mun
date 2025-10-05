# -*- coding: utf-8 -*-
import json
import os
import streamlit as st
import geopandas as gpd
import plotly.graph_objects as go

st.set_page_config(page_title="Prueba Aguascalientes", layout="wide")

# ---------- CONFIG ----------
DATA_PATH = os.path.join("data", "Aguascalientes.json")  # tu archivo
MUN_NAME_COL_CANDIDATES = ["NOMGEO", "NOM_MUN", "MUNICIPIO", "mun_name"]

# ---------- CARGA ----------
if not os.path.exists(DATA_PATH):
    st.error(f"No existe el archivo: {DATA_PATH}")
    st.stop()

try:
    gdf = gpd.read_file(DATA_PATH)
except Exception as e:
    st.error(f"Error leyendo el GeoJSON: {e}")
    st.stop()

# Asegura CRS (CRS84 ~ lon/lat); forzamos a 4326 para Plotly
try:
    if gdf.crs is None:
        gdf = gdf.set_crs(4326, allow_override=True)
    elif gdf.crs.to_epsg() != 4326:
        gdf = gdf.to_crs(4326)
except Exception:
    gdf = gdf.set_crs(4326, allow_override=True)

# Solo polígonos válidos
gdf = gdf[gdf.geometry.notna()].copy()
gdf = gdf[gdf.geometry.geom_type.isin(["Polygon", "MultiPolygon"])].copy()

# Detecta nombre de municipio
mun_col = None
for c in MUN_NAME_COL_CANDIDATES:
    if c in gdf.columns:
        mun_col = c
        break
if mun_col is None:
    # fallback: primera columna de texto
    text_cols = [c for c in gdf.columns if gdf[c].dtype == object]
    mun_col = text_cols[0] if text_cols else None

if mun_col is None:
    st.error("No encontré una columna de nombre de municipio.")
    st.write("Columnas disponibles:", list(gdf.columns))
    st.stop()

# Lista municipios
gdf = gdf.reset_index(drop=True).copy()
gdf["__loc__"] = gdf.index.astype(str)
mun_list = sorted(gdf[mun_col].astype(str).fillna("").unique())

st.sidebar.header("Prueba con un estado")
mun_sel = st.sidebar.selectbox("Municipio", options=mun_list, index=0)
op_base = st.sidebar.slider("Opacidad base", 0.1, 1.0, 0.35, 0.05)
op_sel = st.sidebar.slider("Opacidad municipio", 0.1, 1.0, 0.7, 0.05)

# ---------- GEOJSONS mínimos ----------
def to_geojson_with_ids(gdf_keep, key_col):
    keep = [c for c in [key_col, "__loc__", gdf_keep.geometry.name] if c in gdf_keep.columns]
    gj = json.loads(gdf_keep[keep].to_json())
    # Poner feature.id = __loc__ para evitar featureidkey
    for feat in gj.get("features", []):
        props = feat.get("properties", {})
        feat["id"] = str(props.get("__loc__", ""))
    return gj

gj_all = to_geojson_with_ids(gdf, mun_col)

sel = gdf[gdf[mun_col].astype(str) == str(mun_sel)].copy()
sel["__loc__"] = ["sel"]  # un id fijo
gj_sel = to_geojson_with_ids(sel, mun_col)

# ---------- Bounds, centro y zoom sencillo ----------
minx, miny, maxx, maxy = gdf.total_bounds
cx, cy = (minx + maxx) / 2, (miny + maxy) / 2
diag = max(maxx - minx, maxy - miny)
zoom = 5.4
if diag < 1.5:
    zoom = 6.2
elif diag < 3:
    zoom = 5.4
elif diag < 6:
    zoom = 4.8
else:
    zoom = 4.5

# ---------- FIGURA ----------
fig = go.Figure()

# Capa base (gris)
fig.add_trace(
    go.Choroplethmapbox(
        geojson=gj_all,
        locations=gdf["__loc__"].astype(str).tolist(),
        z=[1.0] * len(gdf),
        colorscale=[[0, "lightgray"], [1, "lightgray"]],
        showscale=False,
        opacity=op_base,
        name="Municipios",
    )
)

# Municipio seleccionado (azul)
fig.add_trace(
    go.Choroplethmapbox(
        geojson=gj_sel,
        locations=["sel"],
        z=[1.0],
        colorscale=[[0, "royalblue"], [1, "royalblue"]],
        showscale=False,
        opacity=op_sel,
        name=str(mun_sel),
    )
)

fig.update_layout(
    mapbox_style="carto-positron",  # no requiere token
    mapbox_center={"lat": cy, "lon": cx},
    mapbox_zoom=zoom,
    margin=dict(l=0, r=0, t=0, b=0),
    legend=dict(orientation="h", y=0.02),
)

st.title("Prueba rápida: Aguascalientes (1 archivo)")
st.plotly_chart(fig, use_container_width=True)

with st.expander("Diagnóstico"):
    st.json({
        "archivo": DATA_PATH,
        "CRS": str(getattr(gdf, "crs", None)),
        "filas": int(gdf.shape[0]),
        "columnas": list(gdf.columns),
        "geom_types": gdf.geometry.geom_type.value_counts().to_dict(),
        "bounds[minx,miny,maxx,maxy]": list(map(float, gdf.total_bounds)),
        "columna_municipio": mun_col,
    })
