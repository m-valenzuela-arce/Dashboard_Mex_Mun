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
# Dibujo con Scat
