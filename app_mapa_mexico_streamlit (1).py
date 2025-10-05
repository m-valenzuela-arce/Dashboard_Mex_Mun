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

# --- Asegurar ids para plotly.locations ---
for i, feat in enumerate(gj.get("features", [])):
    feat["id"] = str(i)

# --- Lista de municipios (NOMGEO) ---
mun_names = []
for feat in gj.get("features", []):
    name = feat.get("properties", {}).get("NOMGEO")
    if isinstance(name, str):
        mun_names.append(name)
mun_names = sorted(set(mun_names))

# --- UI mínima: selector en la barra lateral ---
st.title("Aguascalientes: municipios (interactivo mínimo)")
mun_sel = st.sidebar.selectbox("Municipio", options=mun_names, index=0)
op_base = st.sidebar.slider("Opacidad base", 0.10, 1.00, 0.35, 0.05)
op_sel  = st.sidebar.slider("Opacidad municipio", 0.10, 1.00, 0.70, 0.05)

# --- ids base y features seleccionadas ---
all_ids = [feat["id"] for feat in gj.get("features", [])]

sel_ids = []
sel_fc = {"type": "FeatureCollection", "features": []}
for feat in gj.get("features", []):
    if feat.get("properties", {}).get("NOMGEO") == mun_sel:
        sel_ids.append(feat["id"])
        sel_fc["features"].append(feat)

# --- centro y zoom (auto por bounds del estado; si quieres, zoom al municipio) ---
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

# Si quieres auto-zoom al municipio seleccionado, cambia a True
AUTO_ZOOM_MUNICIPIO = True
if AUTO_ZOOM_MUNICIPIO and sel_fc["features"]:
    b_sel = fc_bounds(sel_fc)
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
        hovertemplate="<b>%{properties.NOM_ENT}</b><br>%{properties.NOMGEO}<extra></extra>",
    )
)

if sel_ids:
    fig.add_trace(
        go.Choroplethmapbox(
            geojson=sel_fc,
            locations=sel_ids,
            z=[1.0]*len(sel_ids),
            colorscale=[[0,"royalblue"],[1,"royalblue"]],
            showscale=False,
            opacity=op_sel,
            name=str(mun_sel),
            hovertemplate="<b>%{properties.NOM_ENT}</b><br>%{properties.NOMGEO}<extra></extra>",
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
