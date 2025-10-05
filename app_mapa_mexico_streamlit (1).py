# -*- coding: utf-8 -*-
import os
import json
import streamlit as st
import plotly.graph_objects as go

st.set_page_config(page_title="Prueba mínima Aguascalientes", layout="wide")

DATA_PATH = os.path.join("data", "Aguascalientes.json")  # ajusta si el nombre difiere

# ---------- util: bounds desde el GeoJSON (sin shapely) ----------
def geom_bounds(geom):
    gtype = geom.get("type")
    coords = geom.get("coordinates", [])
    xs, ys = [], []

    def walk(obj):
        if isinstance(obj, (list, tuple)):
            if len(obj) == 2 and all(isinstance(v, (int, float)) for v in obj):
                xs.append(float(obj[0])); ys.append(float(obj[1]))
            else:
                for it in obj:
                    walk(it)

    if gtype in ("Polygon", "MultiPolygon"):
        walk(coords)
    # si fuera otro tipo, lo ignoramos
    if not xs or not ys:
        return None
    return min(xs), min(ys), max(xs), max(ys)

def fc_bounds(feature_collection):
    minx=miny=1e9
    maxx=maxy=-1e9
    found=False
    for feat in feature_collection.get("features", []):
        g = feat.get("geometry")
        if not g:
            continue
        b = geom_bounds(g)
        if not b:
            continue
        x0,y0,x1,y1 = b
        minx=min(minx,x0); miny=min(miny,y0)
        maxx=max(maxx,x1); maxy=max(maxy,y1)
        found=True
    if not found:
        return None
    return (minx, miny, maxx, maxy)

# ---------- carga ----------
if not os.path.exists(DATA_PATH):
    st.error(f"No existe el archivo: {DATA_PATH}")
    st.stop()

try:
    with open(DATA_PATH, "r", encoding="utf-8") as f:
        gj = json.load(f)
except Exception as e:
    st.error("No pude leer el GeoJSON. ¿Es un JSON válido?")
    st.code(repr(e))
    st.stop()

if gj.get("type") != "FeatureCollection":
    st.error("El archivo no es un FeatureCollection válido.")
    st.stop()

# Ponemos un id string único a cada feature para usarlo como 'locations'
for i, feat in enumerate(gj.get("features", [])):
    feat["id"] = str(i)

# lista de municipios (NOMGEO)
mun_names = []
for feat in gj.get("features", []):
    props = feat.get("properties", {})
    name = props.get("NOMGEO")
    if isinstance(name, str):
        mun_names.append(name)
mun_names = sorted(set(mun_names))

if not mun_names:
    st.error("No encontré 'NOMGEO' en las propiedades. Revisa el archivo.")
    st.stop()

st.title("Prueba mínima: Aguascalientes (solo Plotly + JSON)")

with st.sidebar:
    st.header("Controles")
    mun_sel = st.selectbox("Municipio", options=mun_names, index=0)
    op_base = st.slider("Opacidad base", 0.10, 1.00, 0.35, 0.05)
    op_sel  = st.slider("Opacidad municipio", 0.10, 1.00, 0.70, 0.05)

# Base: todas las features
all_feature_ids = [feat["id"] for feat in gj.get("features", [])]

# Seleccionadas: solo las de ese NOMGEO (por si hubiese multiparte)
sel_ids = []
sel_fc = {"type": "FeatureCollection", "features": []}
for feat in gj.get("features", []):
    if feat.get("properties", {}).get("NOMGEO") == mun_sel:
        sel_ids.append(feat["id"])
        sel_fc["features"].append(feat)

# Bounds y centro/zoom heurístico
b = fc_bounds(gj)
if b:
    minx, miny, maxx, maxy = b
    cx, cy = (minx + maxx) / 2.0, (miny + maxy) / 2.0
    diag = max(maxx - minx, maxy - miny)
    if diag < 1.5:
        zoom = 6.2
    elif diag < 3:
        zoom = 5.4
    elif diag < 6:
        zoom = 4.8
    else:
        zoom = 4.5
else:
    # fallback al centro aproximado del estado
    cx, cy, zoom = -102.3, 22.0, 5.4

# Figura
fig = go.Figure()

# Capa base gris (todas las features)
fig.add_trace(
    go.Choroplethmapbox(
        geojson=gj,
        locations=all_feature_ids,
        z=[1.0]*len(all_feature_ids),
        colorscale=[[0,"lightgray"],[1,"lightgray"]],
        showscale=False,
        opacity=op_base,
        name="Municipios"
    )
)

# Capa azul (solo el municipio elegido)
if sel_ids:
    fig.add_trace(
        go.Choroplethmapbox(
            geojson=sel_fc,
            locations=sel_ids,
            z=[1.0]*len(sel_ids),
            colorscale=[[0,"royalblue"],[1,"royalblue"]],
            showscale=False,
            opacity=op_sel,
            name=str(mun_sel)
        )
    )

fig.update_layout(
    mapbox_style="carto-positron",
    mapbox_center={"lat": cy, "lon": cx},
    mapbox_zoom=zoom,
    margin=dict(l=0, r=0, t=0, b=0),
    legend=dict(orientation="h", y=0.02),
)

st.plotly_chart(fig, use_container_width=True)

with st.expander("Diagnóstico"):
    st.json({
        "archivo": DATA_PATH,
        "num_features": len(gj.get("features", [])),
        "municipios_unicos": len(mun_names),
        "ejemplo_municipios": mun_names[:10],
        "bounds": fc_bounds(gj)
    })
