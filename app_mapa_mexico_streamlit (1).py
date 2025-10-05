import json
import plotly.graph_objects as go
import streamlit as st

st.set_page_config(page_title="Aguascalientes - Municipios", layout="wide")

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

# --- Asignar id y texto por-feature ---
features = gj.get("features", [])
for i, feat in enumerate(features):
    feat["id"] = str(i)
    props = feat.get("properties", {}) or {}
    ent = str(props.get("NOM_ENT", "") or "")
    mun = str(props.get("NOMGEO", "") or "")
    # Guardar un tooltip listo
    props["_text"] = f"{ent} — {mun}" if mun else ent

all_ids  = [f["id"] for f in features]
all_text = [f.get("properties", {}).get("_text", "") for f in features]

# --- Lista de municipios para el selector ---
mun_names = sorted({(f.get("properties", {}) or {}).get("NOMGEO", "") for f in features if isinstance((f.get("properties", {}) or {}).get("NOMGEO", ""), str)})
if not mun_names:
    mun_names = ["(sin municipios)"]

# --- UI mínima ---
st.title("Aguascalientes: municipios (interactivo mínimo)")
mun_sel = st.sidebar.selectbox("Municipio", options=mun_names, index=0)
op_base = st.sidebar.slider("Opacidad base", 0.10, 1.00, 0.35, 0.05)
op_sel  = st.sidebar.slider("Opacidad municipio", 0.10, 1.00, 0.70, 0.05)

# --- Filtrar features del municipio seleccionado ---
sel_features = []
for f in features:
    if (f.get("properties", {}) or {}).get("NOMGEO") == mun_sel:
        sel_features.append(f)

sel_ids  = [f["id"] for f in sel_features]
sel_text = [f.get("properties", {}).get("_text", "") for f in sel_features]

# --- Centro y zoom ---
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

AUTO_ZOOM_MUNICIPIO = True
if AUTO_ZOOM_MUNICIPIO and sel_features:
    b_sel = fc_bounds({"type": "FeatureCollection", "features": sel_features})
    if b_sel:
        sx0, sy0, sx1, sy1 = b_sel
        cx, cy = (sx0+sx1)/2.0, (sy0+sy1)/2.0
        sdiag = max(sx1-sx0, sy1-sy0)
        if   sdiag < 0.3: zoom_state = 9.0
        elif sdiag < 0.6: zoom_state = 7.5
        else:             zoom_state = 6.2

# --- Figura: base gris + municipio azul ---
fig = go.Figure()

fig.add_trace(
    go.Choroplethmapbox(
        geojson=gj,
        locations=all_ids,
        z=[1.0]*len(all_ids),
        colorscale=[[0,"lightgray"],[1,"lightgray"]],
        showscale=False,
        opacity=op_base,
        name="Municipios",
        text=all_text,                           # usamos 'text'…
        hovertemplate="%{text}<extra></extra>",  # …y lo mostramos aquí
    )
)

if sel_ids:
    fig.add_trace(
        go.Choroplethmapbox(
            geojson={"type": "FeatureCollection", "features": sel_features},
            locations=sel_ids,
            z=[1.0]*len(sel_ids),
            colorscale=[[0,"royalblue"],[1,"royalblue"]],
            showscale=False,
            opacity=op_sel,
            name=str(mun_sel),
            text=sel_text,
            hovertemplate="%{text}<extra></extra>",
        )
    )

fig.update_layout(
    mapbox_style="carto-positron",
    mapbox_center={"lat": cy, "lon": cx},
    mapbox_zoom=zoom_state,
    margin=dict(l=0, r=0, t=0, b=0),
    legend=dict(orientation="h", y=0.02),
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
