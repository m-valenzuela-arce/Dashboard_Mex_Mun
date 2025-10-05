import streamlit as st
import json
import plotly.graph_objects as go

# --- Título ---
st.title("Mapa básico - Aguascalientes")

# --- Cargar GeoJSON ---
with open("data/Aguascalientes.json", "r", encoding="utf-8") as f:
    geojson_data = json.load(f)

# --- Crear figura simple ---
fig = go.Figure(go.Choroplethmapbox(
    geojson=geojson_data,
    locations=["Aguascalientes"],  # Fake location (required but unused)
    z=[1],  # Un solo valor
    featureidkey="properties.NOM_ENT"
))

# --- Configurar el mapa ---
fig.update_layout(
    mapbox_style="carto-positron",
    mapbox_zoom=7,
    mapbox_center={"lat": 22.0, "lon": -102.3},
    margin={"r":0,"t":0,"l":0,"b":0}
)

# --- Mostrar ---
st.plotly_chart(fig)
