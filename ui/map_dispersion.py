"""
ui/map_dispersion.py — HSE PYXIS
==================================
Carte interactive de dispersion (Leaflet + OpenStreetMap).

v2 — Ajouts (Méthode #11) :
  • Cercles AEGL-1/2/3 (jaune / orange / rouge)
  • Cercles ERPG-1/2/3 (pointillés vert / violet / bordeaux)
  • Flèche de direction du vent
  • Correction automatique du label "Unknown"
  • Légende HTML + auto-zoom sur la plus grande zone
  • Compatibilité totale avec l'API existante

Usage :
    from ui.map_dispersion import render_dispersion_map, search_location

    # Version simple (compatible ancienne API)
    render_dispersion_map(
        latitude=36.7538,
        longitude=3.0588,
        distance_impact_m=250,
        substance="H2S",
        label="Fuite H2S — zone A",
    )

    # Version enrichie (avec AEGL/ERPG + vent)
    render_dispersion_map(
        latitude=36.7538,
        longitude=3.0588,
        distance_impact_m=250,
        substance="H2S",
        label="Fuite H2S — zone A",
        wind_dir=270,          # degrés, direction D'OÙ vient le vent
        aegl_1=100, aegl_2=300, aegl_3=800,
        erpg_1=80,  erpg_2=200, erpg_3=600,
    )
"""

import folium
import streamlit as st
from streamlit_folium import st_folium


# ============================================================
# COULEURS SELON GRAVITÉ
# ============================================================
def _color_from_distance(distance_m: float) -> str:
    """Rouge si impact > 500m, orange si > 200m, vert sinon."""
    if distance_m >= 500:
        return "#E74C3C"   # rouge
    if distance_m >= 200:
        return "#E67E22"   # orange
    return "#27AE60"       # vert


# ============================================================
# 🆕 NORMALISATION DU LABEL "Unknown"
# ============================================================
def _normalize_label(substance: str, label: str) -> tuple[str, str]:
    """
    Remplace 'Unknown' / 'inconnu' / vide par des libellés lisibles.
    Retourne (substance_clean, label_clean).
    """
    _UNKNOWN_KEYS = {"unknown", "inconnu", "inconnue", "n/a", "na", "—", "-", ""}

    s_clean = (substance or "").strip()
    if s_clean.lower() in _UNKNOWN_KEYS:
        s_clean = "Substance inconnue"

    l_clean = (label or "").strip()
    if l_clean.lower() in _UNKNOWN_KEYS:
        l_clean = f"Fuite {s_clean}" if s_clean != "Substance inconnue" else "Point de fuite"

    return s_clean, l_clean


# ============================================================
# CARTE PRINCIPALE
# ============================================================
def render_dispersion_map(
    latitude: float,
    longitude: float,
    distance_impact_m: float = 100.0,
    substance: str = "—",
    label: str = "",
    zoom_start: int = 13,
    # 🆕 Paramètres optionnels (compatibles avec appels existants)
    wind_dir: float | None = None,
    aegl_1: float | None = None,
    aegl_2: float | None = None,
    aegl_3: float | None = None,
    erpg_1: float | None = None,
    erpg_2: float | None = None,
    erpg_3: float | None = None,
    height: int = 450,
):
    """
    Affiche une carte interactive centrée sur le point de fuite.

    Args:
        latitude, longitude : coordonnées du point de fuite
        distance_impact_m   : rayon de la zone d'impact (m)
        substance           : nom de la substance (tooltip)
        label               : libellé court (ex: "Fuite H2S — zone A")
        zoom_start          : niveau de zoom initial
        wind_dir            : 🆕 direction du vent en degrés (0=Nord, 90=Est)
                              — dessine une flèche indiquant où va le vent
        aegl_1/2/3          : 🆕 rayons AEGL (m) — cercles jaune/orange/rouge
        erpg_1/2/3          : 🆕 rayons ERPG (m) — cercles pointillés
        height              : 🆕 hauteur de la carte en pixels (défaut 450)
    """
    # ── Normalisation "Unknown" ──
    substance, label = _normalize_label(substance, label)

    color = _color_from_distance(distance_impact_m)

    # ── Créer la carte ──
    m = folium.Map(
        location=[latitude, longitude],
        zoom_start=zoom_start,
        tiles="OpenStreetMap",
    )

    # ── Cercle principal (zone d'impact) ──
    folium.Circle(
        location=[latitude, longitude],
        radius=distance_impact_m,
        color=color,
        weight=2,
        fill=True,
        fill_color=color,
        fill_opacity=0.25,
        popup=folium.Popup(
            f"<b>{substance}</b><br>"
            f"Distance d'impact : <b>{distance_impact_m:.0f} m</b>",
            max_width=250,
        ),
        tooltip=f"Zone d'impact — {distance_impact_m:.0f} m",
    ).add_to(m)

    # ── 🆕 Cercles AEGL (jaune / orange / rouge) ──
    for radius, clr, name in (
        (aegl_1, "#FFD700", "AEGL-1"),
        (aegl_2, "#FFA500", "AEGL-2"),
        (aegl_3, "#FF0000", "AEGL-3"),
    ):
        if radius and radius > 0:
            folium.Circle(
                location=[latitude, longitude],
                radius=float(radius),
                color=clr,
                weight=2,
                fill=True,
                fill_color=clr,
                fill_opacity=0.08,
                popup=f"{name} : {radius:.0f} m",
                tooltip=f"{name} — {radius:.0f} m",
            ).add_to(m)

    # ── 🆕 Cercles ERPG (pointillés) ──
    for radius, clr, name in (
        (erpg_1, "#008000", "ERPG-1"),
        (erpg_2, "#800080", "ERPG-2"),
        (erpg_3, "#8B0000", "ERPG-3"),
    ):
        if radius and radius > 0:
            folium.Circle(
                location=[latitude, longitude],
                radius=float(radius),
                color=clr,
                weight=2,
                dash_array="6,4",
                fill=False,
                popup=f"{name} : {radius:.0f} m",
                tooltip=f"{name} — {radius:.0f} m",
            ).add_to(m)

    # ── 🆕 Flèche de direction du vent ──
    if wind_dir is not None:
        # wind_dir = direction D'OÙ vient le vent (0=Nord)
        # La flèche doit pointer VERS où va le vent (opposé)
        arrow_dir = (wind_dir + 180) % 360
        folium.Marker(
            location=[latitude, longitude],
            icon=folium.DivIcon(
                html=(
                    f'<div style="font-size:34px; line-height:1; '
                    f'text-align:center; transform: rotate({arrow_dir}deg); '
                    f'transform-origin: center; color:#1E3A8A;">⬆️</div>'
                ),
                icon_size=(40, 40),
                icon_anchor=(20, 20),
            ),
            popup=f"Vent : {wind_dir:.0f}° (d'où il vient)",
            tooltip=f"💨 Vent {wind_dir:.0f}°",
        ).add_to(m)

    # ── Marqueur du point de fuite (ajouté APRÈS les cercles pour rester au-dessus) ──
    folium.Marker(
        location=[latitude, longitude],
        popup=folium.Popup(
            f"<b>{label}</b><br>"
            f"Substance : {substance}<br>"
            f"Rayon : {distance_impact_m:.0f} m"
            + (f"<br>Vent : {wind_dir:.0f}°" if wind_dir is not None else ""),
            max_width=250,
        ),
        tooltip=label,
        icon=folium.Icon(color="red", icon="warning-sign", prefix="glyphicon"),
    ).add_to(m)

    # ── 🆕 Légende HTML ──
    legend_html = """
    <div style="position: fixed; bottom: 30px; left: 30px; z-index: 9999;
                background: white; padding: 10px 14px; border-radius: 6px;
                border: 1px solid #ccc; font-size: 12px; line-height: 1.6;
                box-shadow: 0 2px 8px rgba(0,0,0,0.15);">
        <b>Légende</b><br>
        <span style="color:#2c5282;">━</span> Zone d'impact<br>
        <span style="color:#FFD700;">━</span> AEGL-1 / ERPG-1<br>
        <span style="color:#FFA500;">━</span> AEGL-2 / ERPG-2<br>
        <span style="color:#FF0000;">━</span> AEGL-3 / ERPG-3<br>
        <span style="color:#008000;">┅</span> ERPG (pointillés)<br>
        <span style="color:#1E3A8A;">⬆️</span> Direction du vent
    </div>
    """
    m.get_root().html.add_child(folium.Element(legend_html))

    # ── 🆕 Ajustement automatique du zoom sur la plus grande zone ──
    _radii = [
        distance_impact_m,
        aegl_1, aegl_2, aegl_3,
        erpg_1, erpg_2, erpg_3,
    ]
    _max_radius = max([r for r in _radii if r and r > 0], default=0)

    if _max_radius > distance_impact_m * 1.2 and _max_radius > 0:
        # Si une zone AEGL/ERPG est plus grande que le rayon principal,
        # on recadre la carte pour tout voir
        margin = _max_radius * 1.4 / 111000  # degrés ≈ mètres / 111000
        m.fit_bounds([
            [latitude - margin, longitude - margin],
            [latitude + margin, longitude + margin],
        ])

    # ── Affichage dans Streamlit ──
    # Clé unique qui inclut les paramètres AEGL/ERPG/wind pour éviter
    # les collisions de cache entre rendus
    _key = (
        f"map_{latitude:.5f}_{longitude:.5f}_{distance_impact_m:.0f}"
        f"_{wind_dir if wind_dir is not None else 'nw'}"
        f"_{aegl_1 or 0}_{aegl_2 or 0}_{aegl_3 or 0}"
        f"_{erpg_1 or 0}_{erpg_2 or 0}_{erpg_3 or 0}"
    )

    st_folium(
        m,
        height=height,
        width=None,
        returned_objects=[],
        key=_key,
    )

    # ── Légende textuelle (sous la carte) ──
    _legend_parts = [f"🗺️ Zone d'impact : **{distance_impact_m:.0f} m**"]
    if wind_dir is not None:
        _legend_parts.append(f"💨 Vent : **{wind_dir:.0f}°**")
    if aegl_3 or aegl_2 or aegl_1:
        _aegl_vals = [v for v in (aegl_1, aegl_2, aegl_3) if v]
        _legend_parts.append(
            "🟡 AEGL : " + " / ".join(f"{v:.0f} m" for v in _aegl_vals)
        )
    if erpg_3 or erpg_2 or erpg_1:
        _erpg_vals = [v for v in (erpg_1, erpg_2, erpg_3) if v]
        _legend_parts.append(
            "🟣 ERPG : " + " / ".join(f"{v:.0f} m" for v in _erpg_vals)
        )

    st.caption(" — ".join(_legend_parts))


# ============================================================
# RECHERCHE D'UN LIEU PAR NOM (Nominatim / OpenStreetMap)
# ============================================================
@st.cache_data(show_spinner=False)
def search_location(query: str) -> list[dict]:
    """
    Recherche un lieu par nom via Nominatim (OpenStreetMap).

    Args:
        query : nom du lieu (ex: "Alger", "Hassi Messaoud")

    Returns:
        list de dicts : [{"name": "...", "lat": 36.75, "lon": 3.05}, ...]
        (max 5 résultats)
    """
    if not query or len(query.strip()) < 3:
        return []

    try:
        from geopy.geocoders import Nominatim
        geolocator = Nominatim(user_agent="hse_pyxis_app", timeout=10)
        locations = geolocator.geocode(query, exactly_one=False, limit=5)

        if not locations:
            return []

        return [
            {
                "name": loc.address,
                "lat": loc.latitude,
                "lon": loc.longitude,
            }
            for loc in locations
        ]
    except Exception:
        return []


# ============================================================
# 🆕 Helper : extraction AEGL/ERPG depuis les propriétés chimiques
# ============================================================
def extract_aegl_erpg_from_props(props: dict) -> dict:
    """
    Extrait les rayons AEGL/ERPG (en mètres) depuis un dict de propriétés
    chimiques renvoyé par chemical_db_interface.

    Si les valeurs ne sont pas présentes, retourne des clés avec None.

    Usage :
        props = get_chemical_properties("H2S")
        zones = extract_aegl_erpg_from_props(props)
        render_dispersion_map(..., **zones)
    """
    return {
        "aegl_1": props.get("aegl_1_m"),
        "aegl_2": props.get("aegl_2_m"),
        "aegl_3": props.get("aegl_3_m"),
        "erpg_1": props.get("erpg_1_m"),
        "erpg_2": props.get("erpg_2_m"),
        "erpg_3": props.get("erpg_3_m"),
    }


# ============================================================
# Export public
# ============================================================
__all__ = [
    "render_dispersion_map",
    "search_location",
    "extract_aegl_erpg_from_props",
    "_color_from_distance",
    "_normalize_label",
]