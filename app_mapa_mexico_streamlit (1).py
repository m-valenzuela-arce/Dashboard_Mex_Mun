import json
import streamlit as st
import plotly.graph_objects as go

st.set_page_config(page_title="Aguascalientes - Mapa (capas Mapbox)", layout="wide")

# --- Cargar GeoJSON ---
with open("data/Aguascalientes.json", "r", encoding="utf-8") as f:
    gj = json.load(f)

# --- Bounds/centro/zoom simples ---
def geom_bounds(geom):
    xs, ys = [], []
    def walk(obj):
        if isinstance(obj, (list, tuple)):
            if len(obj) == 2 and all(isinstance(v, (int, float)) for v in obj):
                xs.append(float(obj[0])); ys.append(float(obj[1]))
            else:
                for it in obj: walk(it)
    if geom and geom.get("type") in ("Polygon", "MultiPolygon"):
        walk(geom.get("coordinates", []))
    return (min(xs), min(ys), max(xs), max(ys)) if xs and ys else None

def fc_bounds(fc):
    found = False
    minx=miny= 1e9
    maxx=maxy=-1e9
    for feat in fc.get("features", []):
        b = geom_bounds(feat.get("geometry"))
        if not b: 
            continue
        x0,y0,x1,y1 = b
        minx=min(minx,x0); miny=min(miny,y0)
        maxx=max(maxx,x1); maxy=max(maxy,y1)
        found=True
    return (minx,miny,maxx,maxy) if found else None

b = fc_bounds(gj)
if b:
    minx, miny, maxx, maxy = b
    cx, cy = (minx+maxx)/2.0, (miny+maxy)/2.0
    diag = max(maxx-minx, maxy-miny)
    if   diag < 1.5: zoom = 6.2
    elif diag < 3.0: zoom = 5.4
    elif diag < 6.0: zoom = 4.8
    else:            zoom = 4.5
else:
    cx, cy, zoom = -102.3, 22.0, 6.0

# --- Figura vacía (usaremos capas de Mapbox)
fig = go.Figure()

# Capa de RELLENO (gris claro)
fig.update_layout(
    mapbox=dict(
        style="carto-positron",
        center=dict(lat=cy, lon=cx),
        zoom=zoom,
        layers=[
            dict(
                sourcetype="geojson",
                source=gj,
                type="fill",
                color="lightgray",
                opacity=0.6,
            ),
            dict(
                sourcetype="geojson",
                source=gj,
                type="line",
                color="black",
                line=dict(width=1),
            ),
        ],
    ),
    margin=dict(l=0, r=0, t=0, b=0),
    height=720,
)

st.plotly_chart(
    fig,
    use_container_width=True,
    config={
        "scrollZoom": True,
        "displayModeBar": True,
        "modeBarButtonsToRemove": []
    }
)
