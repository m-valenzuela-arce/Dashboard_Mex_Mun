import json
import plotly.graph_objects as go
import streamlit as st

st.set_page_config(page_title="Aguascalientes - Interactivo mínimo", layout="wide")

# --- Cargar GeoJSON ---
with open("data/Aguascalientes.json", "r", encoding="utf-8") as f:
    gj = json.load(f)

# --- Asignar id a cada feature para usarlo como 'locations' ---
for i, feat in enumerate(gj.get("features", [])):
    feat["id"] = str(i)

feature_ids = [feat["id"] for feat in gj.get("features", [])]

# --- Calcular bounds para centrar/zoom automático ---
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
        if not b: continue
        x0,y0,x1,y1 = b
        minx=min(minx,x0); miny=min(miny,y0)
        maxx=max(maxx,x1); maxy=max(maxy,y1)
        found=True
    return (minx,miny,maxx,maxy) if found else None

b = fc_bounds(gj)
if b:
    minx,miny,maxx,maxy = b
    cx, cy = (minx+maxx)/2.0, (miny+maxy)/2.0
    diag = max(maxx-minx, maxy-miny)
    if   diag < 1.5: zoom = 6.2
    elif diag < 3.0: zoom = 5.4
    elif diag < 6.0: zoom = 4.8
    else:            zoom = 4.5
else:
    cx, cy, zoom = -102.3, 22.0, 6.0

# --- Figura ---
fig = go.Figure(go.Choroplethmapbox(
    geojson=gj,
    locations=feature_ids,             # usa los ids que acabamos de poner
    z=[1.0]*len(feature_ids),          # valor plano (un color)
    colorscale=[[0,"lightgray"],[1,"lightgray"]],
    showscale=False,
    name="Aguascalientes"
))

fig.update_layout(
    mapbox_style="carto-positron",
    mapbox_center={"lat": cy, "lon": cx},
    mapbox_zoom=zoom,
    margin=dict(l=0, r=0, t=0, b=0),
    legend=dict(orientation="h", y=0.02),
    height=720
)

# Habilitar zoom con scroll y mostrar modebar
st.plotly_chart(
    fig,
    use_container_width=True,
    config={
        "scrollZoom": True,           # zoom con rueda/gesto
        "displayModeBar": True,       # barra de herramientas visible
        "modeBarButtonsToRemove": []  # deja todo habilitado
    }
)

