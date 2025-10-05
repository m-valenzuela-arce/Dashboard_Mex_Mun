import json
import plotly.graph_objects as go
import streamlit as st

st.set_page_config(page_title="Aguascalientes - Municipios (mínimo robusto)", layout="wide")

# --- Cargar GeoJSON ---
with open("data/Aguascalientes.json", "r", encoding="utf-8") as f:
    gj = json.load(f)

# --- Utilidades simples para bounds ---
def geom_bounds(geom):
    xs, ys = [], []
    def walk(obj):
        if isinstance(obj, (list, tuple)):
            if len(obj) == 2 and all(isinstance(v, (int, float)) for v in obj):
                xs.append(float(obj[0])); ys.append(float(obj[1]))
            else:
                for it in obj: 
                    walk(it)
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

# --- Asegurar id por-feature para locations ---
features = gj.get("features", [])
for i, feat in enumerate(features):
    feat["id"] = str(i)  # Plotly buscará 'id' en cada Feature

all_ids = [f["id"] for f in features]

# --- Centro y zoom automáticos ---
b_state = fc_bounds(gj)
if b_state:
    minx,miny,maxx,maxy = b_state
    cx, cy = (minx+maxx)/2.0, (miny+maxy)/2.0
    diag = max(maxx-minx, maxy-miny)
    if   diag < 1.5: zoom_state = 6.2
    elif diag < 3.0: zoom_state = 5.4
    elif diag < 6.0: zoom_state = 4.8
    else:            zoom_state = 4.5
else:
    cx, cy, zoom_state = -102.3, 22.0, 6.0

# --- Figura mínima (sin hovertemplate, sin text) ---
fig = go.Figure(
    go.Choroplethmapbox(
        geojson=gj,
        locations=all_ids,
        z=[1.0]*len(all_ids),
        colorscale=[[0,"lightgray"],[1,"lightgray"]],
        showscale=False,
        opacity=0.7,
        name="Municipios",
        featureidkey="id"   # explícito para versiones viejas de Plotly
    )
)

fig.update_layout(
    mapbox_style="carto-positron",
    mapbox_center={"lat": cy, "lon": cx},
    mapbox_zoom=zoom_state,
    margin=dict(l=0, r=0, t=0, b=0),
    height=720
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
