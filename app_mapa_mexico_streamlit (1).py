import json
import streamlit as st
import plotly.graph_objects as go

st.set_page_config(page_title="Aguascalientes - Mapa robusto", layout="wide")

# --- Cargar GeoJSON ---
with open("data/Aguascalientes.json", "r", encoding="utf-8") as f:
    gj = json.load(f)

# --- Bounds/centro/zoom ---
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

# --- Helpers: convertir GeoJSON -> Scattermapbox con relleno ---
def add_polygon_trace(fig, coords, name="polígono", fill_opacity=0.5, line_width=1):
    """
    coords: lista de anillos (cada anillo es lista de [lon,lat])
    Usamos el anillo exterior (coords[0]) para el relleno; 
    anillos interiores (si existen) se dibujan como líneas (sin 'fill').
    """
    if not coords:
        return

    # Anillo exterior
    ext = coords[0]
    lons = [pt[0] for pt in ext]
    lats = [pt[1] for pt in ext]
    fig.add_trace(go.Scattermapbox(
        lon=lons, lat=lats,
        mode="lines",
        fill="toself",
        name=name,
        line=dict(width=line_width),
        opacity=fill_opacity,
        hoverinfo="skip"  # evitamos problemas de hover
    ))

    # Anillos interiores (si hay), solo borde
    for hole in coords[1:]:
        lons_h = [pt[0] for pt in hole]
        lats_h = [pt[1] for pt in hole]
        fig.add_trace(go.Scattermapbox(
            lon=lons_h, lat=lats_h,
            mode="lines",
            name=f"{name} (hueco)",
            line=dict(width=line_width),
            opacity=1.0,
            hoverinfo="skip"
        ))

def add_feature_to_fig(fig, feature, fill_opacity=0.5, line_width=1):
    geom = feature.get("geometry") or {}
    gtype = geom.get("type")
    if gtype == "Polygon":
        coords = geom.get("coordinates", [])
        add_polygon_trace(fig, coords, name="Municipio", fill_opacity=fill_opacity, line_width=line_width)
    elif gtype == "MultiPolygon":
        for poly in geom.get("coordinates", []):
            add_polygon_trace(fig, poly, name="Municipio", fill_opacity=fill_opacity, line_width=line_width)

# --- Construir figura: un trazo por polígono ---
fig = go.Figure()
for feat in gj.get("features", []):
    add_feature_to_fig(fig, feat, fill_opacity=0.55, line_width=1)

fig.update_layout(
    mapbox_style="carto-positron",   # no requiere token
    mapbox_center={"lat": cy, "lon": cx},
    mapbox_zoom=zoom,
    margin=dict(l=0, r=0, t=0, b=0),
    height=720,
    showlegend=False
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
