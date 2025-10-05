# app_mapa_mexico.py
# Streamlit: Estados y Municipios (MX) con contorno de estado vía Scattermapbox
import json
import os
import unicodedata
import streamlit as st
import geopandas as gpd
from shapely.geometry import LineString, MultiLineString
from shapely.ops import unary_union
import plotly.graph_objects as go

# ---------------------------
# Utilidades de nombres/paths
# ---------------------------
DATA_DIR = "data"

def slug(s: str) -> str:
    if s is None:
        return ""
    s = s.strip().lower()
    s = unicodedata.normalize("NFKD", s)
    s = "".join(c for c in s if not unicodedata.combining(c))
    # normaliza espacios y puntos
    s = s.replace(".", " ")
    while "  " in s:
        s = s.replace("  ", " ")
    return s

# Mapeos “comunes” -> “oficial” y variantes de archivo
NOMBRES_CANON = {
    "aguascalientes":"Aguascalientes",
    "baja california":"Baja California",
    "baja california sur":"Baja California Sur",
    "campeche":"Campeche",
    "chiapas":"Chiapas",
    "chihuahua":"Chihuahua",
    "ciudad de mexico":"Ciudad de México",
    "cdmx":"Ciudad de México",
    "coahuila":"Coahuila de Zaragoza",
    "coahuila de zaragoza":"Coahuila de Zaragoza",
    "colima":"Colima",
    "durango":"Durango",
    "guanajuato":"Guanajuato",
    "guerrero":"Guerrero",
    "hidalgo":"Hidalgo",
    "jalisco":"Jalisco",
    "mexico":"México",                    # << Estado de México
    "estado de mexico":"México",         # alias
    "michoacan":"Michoacán de Ocampo",
    "michoacan de ocampo":"Michoacán de Ocampo",
    "morelos":"Morelos",
    "nayarit":"Nayarit",
    "nuevo leon":"Nuevo León",
    "oaxaca":"Oaxaca",
    "puebla":"Puebla",
    "queretaro":"Querétaro",
    "quintana roo":"Quintana Roo",
    "san luis potosi":"San Luis Potosí",
    "sinaloa":"Sinaloa",
    "sonora":"Sonora",
    "tabasco":"Tabasco",
    "tamaulipas":"Tamaulipas",
    "tlaxcala":"Tlaxcala",
    "veracruz":"Veracruz de Ignacio de la Llave",
    "veracruz de ignacio de la llave":"Veracruz de Ignacio de la Llave",
    "yucatan":"Yucatán",
    "zacatecas":"Zacatecas",
}

# Candidatos de nombres de archivos por estado (con acentos o sin acentos)
def candidates_for_state(canon_name: str):
    base = canon_name
    simples = slug(canon_name).title()  # p.ej. "Veracruz De Ignacio De La Llave"
    # variantes directas
    files = [
        f"{canon_name}.geojson",
        f"{canon_name}.json",
        f"{simples}.geojson",
        f"{simples}.json",
    ]
    # algunos alias más frecuentes
    alias = {
        "México": ["Mexico.geojson","Mexico.json","Estado de México.geojson","Estado de México.json",
                   "Estado de Mexico.geojson","Estado de Mexico.json","México.geojson","México.json"],
        "Michoacán de Ocampo": ["Michoacan de Ocampo.geojson","Michoacan de Ocampo.json","Michoacán.geojson","Michoacán.json","Michoacan.geojson","Michoacan.json"],
        "Veracruz de Ignacio de la Llave":["Veracruz.geojson","Veracruz.json"],
        "Coahuila de Zaragoza": ["Coahuila.geojson","Coahuila.json"],
        "Ciudad de México": ["CDMX.geojson","CDMX.json","Ciudad de Mexico.geojson","Ciudad de Mexico.json"],
        "Nuevo León": ["Nuevo Leon.geojson","Nuevo Leon.json"],
        "Querétaro": ["Queretaro.geojson","Queretaro.json"],
        "Yucatán": ["Yucatan.geojson","Yucatan.json"],
        "San Luis Potosí": ["San Luis Potosi.geojson","San Luis Potosi.json"],
        "Quintana Roo": ["QuintanaRoo.geojson","QuintanaRoo.json"],
    }
    files.extend(alias.get(canon_name, []))
    # asegura únicos
    seen, out = set(), []
    for f in files:
        if f not in seen:
            seen.add(f); out.append(f)
    return out

def find_state_file(canon_name: str):
    # busca en DATA_DIR con todas las variantes (resistente a acentos/espacios)
    cands = candidates_for_state(canon_name)
    # además inspecciona la carpeta y matchea por slug del stem
    all_files = [f for f in os.listdir(DATA_DIR) if f.lower().endswith((".geojson",".json"))]
    # primero: coincidencias exactas de los candidatos
    for f in cands:
        if f in all_files:
            return os.path.join(DATA_DIR, f)
    # segundo: por slug de nombre canónico vs slug de filename
    target = slug(canon_name)
    for f in all_files:
        stem = os.path.splitext(f)[0]
        if slug(stem) == target:
            return os.path.join(DATA_DIR, f)
    # tercero: heurística: archivo cuyo stem contenga el canónico
    for f in all_files:
        stem = slug(os.path.splitext(f)[0])
        if target in stem:
            return os.path.join(DATA_DIR, f)
    return None

def load_gdf(path: str) -> gpd.GeoDataFrame:
    # geopandas lee tanto .json como .geojson si son FeatureCollection válidas
    gdf = gpd.read_file(path)
    # homogeneiza columnas conocidas
    cols = [c.lower() for c in gdf.columns]
    rename = {}
    for c in gdf.columns:
        lc = c.lower()
        if lc in ("nomgeo","mun_name","municipio","name","nombre"):
            rename[c] = "mun_name"
        if lc in ("nom_ent","state_name","entidad","estado"):
            rename[c] = "state_name"
        if lc in ("cvegeo","mun_id","cve_mun","cve_municipio"):
            rename[c] = "mun_id"
        if lc in ("cve_ent","state_code","cve_state","cve_entidad"):
            rename[c] = "state_code"
        if lc == "id":
            rename[c] = "id"
    if rename:
        gdf = gdf.rename(columns=rename)
    return gdf

def _boundary_coords(geom):
    """Devuelve (lons, lats) con separadores None para Scattermapbox a partir del 'boundary'."""
    b = geom.boundary
    lons, lats = [], []
    def add_line(ls: LineString):
        xs, ys = ls.xy
        lons.extend(list(xs)); lats.extend(list(ys))
        lons.append(None); lats.append(None)
    if isinstance(b, LineString):
        add_line(b)
    elif isinstance(b, MultiLineString):
        for ls in b.geoms:
            add_line(ls)
    else:
        try:
            for ls in b:
                add_line(ls)
        except Exception:
            pass
    if lons and lons[-1] is None:
        lons.pop(); lats.pop()
    return lons, lats

# ---------------------------
# UI
# ---------------------------
st.set_page_config(page_title="Mapa MX • Estados y Municipios", layout="wide")
st.title("Mapa interactivo de México: Estados y Municipios")

st.caption("Coloca archivos por estado en `./data` (p.ej. `Sonora.json`, `México.geojson`, etc.). "
           "También puedes incluir un archivo general `municipalities.geojson`.")

# Descubre estados disponibles según archivos en /data
disponibles = []
for key, canon in NOMBRES_CANON.items():
    p = find_state_file(canon)
    if p:
        disponibles.append(canon)
disponibles = sorted(set(disponibles))

col1, col2, col3, col4 = st.columns([1.2,1.2,1,1])
with col1:
    estado_in = st.selectbox(
        "Selecciona estado",
        options=disponibles if disponibles else list(NOMBRES_CANON.values()),
        index=(disponibles.index("Sonora") if "Sonora" in disponibles else 0)
    )
canon = NOMBRES_CANON.get(slug(estado_in), estado_in)

with col2:
    lw_estado = st.slider("Grosor de contorno del estado", 1, 12, 4, 1)
with col3:
    lw_mun = st.slider("Grosor del municipio", 1, 12, 3, 1)
with col4:
    op_mun = st.slider("Opacidad del municipio", 0.10, 1.00, 0.60, 0.05)

# Carga GDF del estado (munis del estado)
state_path = find_state_file(canon)
if not state_path:
    st.error(f"No encontré archivo en `/data` para **{canon}**. "
             f"Renombra el archivo con el nombre del estado (ej: `{canon}.json`) o coloca un alias.")
    st.stop()

try:
    gdf_muns = load_gdf(state_path)
except Exception as e:
    st.error(f"Error leyendo `{os.path.basename(state_path)}`: {e}")
    st.stop()

if gdf_muns.empty or gdf_muns.geometry.is_empty.all():
    st.error("El GeoDataFrame del estado está vacío o sin geometría.")
    st.stop()

# Campos de nombre municipio/estado
mun_col = "mun_name" if "mun_name" in gdf_muns.columns else None
if not mun_col:
    # intenta inferir otra vez
    for c in gdf_muns.columns:
        if slug(c) in ("nomgeo","municipio","name","nombre"):
            mun_col = c; break
if not mun_col:
    st.warning("No se encontró columna de nombre de municipio; se usará índice numérico.")
    gdf_muns["mun_name"] = [f"Municipio {i}" for i in range(len(gdf_muns))]
    mun_col = "mun_name"

# Selección de municipio
mun_list = sorted(list(gdf_muns[mun_col].astype(str).unique()))
mun_sel = st.selectbox("Municipio", options=mun_list, index=0)

# Figura
bounds = gdf_muns.total_bounds  # [minx, miny, maxx, maxy]
cx = (bounds[0]+bounds[2])/2
cy = (bounds[1]+bounds[3])/2
# zoom heurístico por extensión
extent = max(bounds[2]-bounds[0], bounds[3]-bounds[1])
if extent > 8:
    zoom = 4.2
elif extent > 5:
    zoom = 5.0
elif extent > 3:
    zoom = 5.5
elif extent > 2:
    zoom = 6.0
else:
    zoom = 6.5

fig = go.Figure()

# 1) Contorno del estado con Scattermapbox (robusto)
try:
    geom_estado = unary_union(gdf_muns.geometry)
    lons, lats = _boundary_coords(geom_estado)
    if lons and lats:
        fig.add_trace(
            go.Scattermapbox(
                lon=lons, lat=lats, mode="lines",
                line=dict(width=lw_estado, color="black"),
                hoverinfo="skip",
                name=f"Contorno • {canon}",
            )
        )
except Exception:
    pass

# 2) Capa base: todos los municipios del estado (gris)
# Para Choroplethmapbox, necesitamos 'locations' y 'featureidkey' que casen.
# Usaremos el índice (creamos un id estable).
gdf_muns = gdf_muns.reset_index(drop=True).copy()
gdf_muns["__loc__"] = gdf_muns.index.astype(str)
# exporta a geojson (en memoria)
gj_muns = json.loads(gdf_muns.to_json())

fig.add_trace(
    go.Choroplethmapbox(
        geojson=gj_muns,
        featureidkey="properties.__loc__",
        locations=gdf_muns["__loc__"],
        z=[1]*len(gdf_muns),  # dummy
        colorscale=[[0, "lightgray"], [1, "lightgray"]],
        showscale=False,
        marker_line_width=0.5,
        marker_line_color="gray",
        hoverinfo="skip",
        name="Municipios",
        opacity=0.35,
    )
)

# 3) Municipio seleccionado (resaltado)
sel = gdf_muns[gdf_muns[mun_col].astype(str) == str(mun_sel)].copy()
if sel.empty:
    st.error("No encontré el municipio seleccionado en el GeoDataFrame. Revisa nombres/acentos del archivo.")
    st.stop()

sel["__loc__"] = ["0"]  # una sola feature
gj_sel = json.loads(sel.to_json())

fig.add_trace(
    go.Choroplethmapbox(
        geojson=gj_sel,
        featureidkey="properties.__loc__",
        locations=sel["__loc__"],
        z=[1],
        colorscale=[[0, "royalblue"], [1, "royalblue"]],
        showscale=False,
        marker_line_width=lw_mun,
        marker_line_color="navy",
        hovertemplate=f"<b>{canon}</b><br>{mun_sel}<extra></extra>",
        name=f"{mun_sel}",
        opacity=op_mun,
    )
)

fig.update_layout(
    mapbox_style="carto-positron",
    mapbox_zoom=zoom,
    mapbox_center={"lat": cy, "lon": cx},
    margin=dict(l=0, r=0, t=0, b=0),
    legend=dict(orientation="h", yanchor="bottom", y=0.01, xanchor="left", x=0.01),
)

st.plotly_chart(fig, use_container_width=True)

# ---------------------------
# Diagnóstico opcional
# ---------------------------
with st.expander("Diagnóstico de archivos"):
    st.write({
        "estado_seleccionado": canon,
        "archivo_estado": state_path,
        "filas": int(len(gdf_muns)),
        "cols": list(gdf_muns.columns),
        "geom_types": dict(gdf_muns.geom_type.value_counts()),
        "bounds[minx,miny,maxx,maxy]": list(map(float, gdf_muns.total_bounds)),
    })
