import os
import json
import streamlit as st
import plotly.graph_objects as go

st.set_page_config(page_title="Mapa MX: Estados y Municipios (robusto)", layout="wide")

DATA_DIR = "data"

# ---------------------------
# Utilidades de archivos
# ---------------------------
def list_state_files(data_dir=DATA_DIR):
    if not os.path.isdir(data_dir):
        return {}
    mapping = {}
    for f in os.listdir(data_dir):
        if f.lower().endswith(".json") or f.lower().endswith(".geojson"):
            path = os.path.join(data_dir, f)
            name = os.path.splitext(f)[0]
            mapping[name] = path
    return dict(sorted(mapping.items(), key=lambda kv: kv[0].lower()))

def load_geojson(path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)

# ---------------------------
# Bounds y zoom
# ---------------------------
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

def feature_bounds(feat):
    return geom_bounds((feat or {}).get("geometry") or {})

def fc_bounds(fc):
    found = False
    minx=miny= 1e12
    maxx=maxy=-1e12
    for feat in fc.get("features", []):
        b = feature_bounds(feat)
        if not b: 
            continue
        x0,y0,x1,y1 = b
        minx=min(minx,x0); miny=min(miny,y0)
        maxx=max(maxx,x1); maxy=max(maxy,y1)
        found=True
    return (minx,miny,maxx,maxy) if found else None

def pick_zoom(minx, miny, maxx, maxy):
    diag = max(maxx-minx, maxy-miny)
    if   diag < 1.5: return 6.2
    elif diag < 3.0: return 5.4
    elif diag < 6.0: return 4.8
    else:            return 4.5

# ---------------------------
# Dibujo con Scattermapbox
# ---------------------------
def add_polygon_trace(fig, coords, name, fill_opacity, line_width, line_color, fillcolor=None, hovertext=None):
    # anillo exterior con relleno
    if not coords:
        return
    ext = coords[0]
    lons = [pt[0] for pt in ext]
    lats = [pt[1] for pt in ext]
    fig.add_trace(go.Scattermapbox(
        lon=lons, lat=lats,
        mode="lines",
        fill="toself",
        name=name,
        line=dict(width=line_width, color=line_color),
        fillcolor=fillcolor,
        opacity=fill_opacity,
        hoverinfo="text" if hovertext else "skip",
        text=hovertext
    ))
    # hoyos interiores como líneas
    for hole in coords[1:]:
        lons_h = [pt[0] for pt in hole]
        lats_h = [pt[1] for pt in hole]
        fig.add_trace(go.Scattermapbox(
            lon=lons_h, lat=lats_h,
            mode="lines",
            name=f"{name} (hueco)",
            line=dict(width=line_width, color=line_color),
            opacity=1.0,
            hoverinfo="skip"
        ))

def add_feature(fig, feat, name, fill_opacity, line_w, line_c, fill_c=None, hovertext=None):
    geom = (feat or {}).get("geometry") or {}
    gtype = geom.get("type")
    if gtype == "Polygon":
        add_polygon_trace(fig, geom.get("coordinates", []), name, fill_opacity, line_w, line_c, fill_c, hovertext)
    elif gtype == "MultiPolygon":
        for poly in geom.get("coordinates", []):
            add_polygon_trace(fig, poly, name, fill_opacity, line_w, line_c, fill_c, hovertext)

def feat_label(feat):
    p = (feat or {}).get("properties") or {}
    ent = p.get("NOM_ENT", "") or p.get("nom_ent", "") or ""
    mun = p.get("NOMGEO", "")  or p.get("nom_mun", "") or p.get("MUNICIPIO", "") or ""
    if ent or mun:
        return f"{ent} · {mun}"
    return "Municipio"

def feat_mun_name(feat):
    p = (feat or {}).get("properties") or {}
    for k in ("NOMGEO", "nom_mun", "MUNICIPIO", "NOM_MUN", "NOM_MPIO", "NOM_LOC"):
        if k in p and p[k]:
            return str(p[k])
    return "Municipio"

# ---------------------------
# Sidebar: selección de estado/municipio
# ---------------------------
st.sidebar.title("Controles")
files = list_state_files()
if not files:
    st.sidebar.error("No encontré archivos .json/.geojson en ./data")
    st.stop()

estado_sel = st.sidebar.selectbox("Estado (archivo):", list(files.keys()))
gj = load_geojson(files[estado_sel])

# Build lista de municipios
mun_names = []
for f in gj.get("features", []):
    mun_names.append(feat_mun_name(f))
mun_names = sorted(set(mun_names))
if not mun_names:
    mun_names = ["(Sin municipios detectados)"]
mun_sel = st.sidebar.selectbox("Municipio:", mun_names, index=0)

# Botón reset
reset_clicked = st.sidebar.button("Reset vista")

# ---------------------------
# Calcular vista (state o municipio)
# ---------------------------
b_state = fc_bounds(gj)
if b_state:
    minx, miny, maxx, maxy = b_state
    cx_state, cy_state = (minx+maxx)/2.0, (miny+maxy)/2.0
    zoom_state = pick_zoom(minx, miny, maxx, maxy)
else:
    cx_state, cy_state, zoom_state = -102.3, 22.0, 6.0

# bounds del municipio seleccionado (si existe)
sel_feat = None
for f in gj.get("features", []):
    if feat_mun_name(f) == mun_sel:
        sel_feat = f
        break

if sel_feat:
    b_sel = feature_bounds(sel_feat)
else:
    b_sel = None

if reset_clicked or not b_sel:
    cx, cy, zoom = cx_state, cy_state, zoom_state
else:
    x0,y0,x1,y1 = b_sel
    cx, cy = (x0+x1)/2.0, (y0+y1)/2.0
    zoom = pick_zoom(x0, y0, x1, y1)

# ---------------------------
# Construir figura
# ---------------------------
fig = go.Figure()

# 1) Todos los municipios en gris (debajo)
for f in gj.get("features", []):
    add_feature(
        fig, f,
        name="Municipio",
        fill_opacity=0.45,
        line_w=1,
        line_c="gray",
        fill_c="lightgray",
        hovertext=feat_label(f)
    )

# 2) Municipio seleccionado en azul (encima)
if sel_feat:
    add_feature(
        fig, sel_feat,
        name=f"Seleccionado: {feat_mun_name(sel_feat)}",
        fill_opacity=0.65,
        line_w=3,
        line_c="navy",
        fill_c="royalblue",
        hovertext=feat_label(sel_feat)
    )

fig.update_layout(
    mapbox_style="carto-positron",   # no requiere token
    mapbox_center={"lat": cy, "lon": cx},
    mapbox_zoom=zoom,
    margin=dict(l=0, r=0, t=0, b=0),
    height=740,
    showlegend=False
)

st.title("Mapa interactivo de México: Estados y Municipios (robusto)")
st.caption("Coloca archivos por-estado en la carpeta ./data (JSON/GeoJSON con polígonos municipales).")
st.plotly_chart(
    fig,
    use_container_width=True,
    config={"scrollZoom": True, "displayModeBar": True, "modeBarButtonsToRemove": []}
)
