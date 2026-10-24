"""
dispersion_wizard.py — Assistant pas-à-pas pour la dispersion atmosphérique.
Ordre logique : 1) Localisation → 2) Météo → 3) Fuite → 4) Carte & résultats.
"""
import streamlit as st


def _t(key, default=None):
    """Wrapper i18n optionnel : utilise ui.i18n.t si dispo, sinon default."""
    try:
        from ui.i18n import t as _t_real
        return _t_real(key)
    except Exception:
        return default or key


def render_dispersion_wizard(iid, substance_options):
    """
    Affiche l'assistant complet. Retourne un dict avec les paramètres saisis.
    """
    st.markdown(f"##### {_t('step2.env_title', 'Dispersion atmosphérique')}")

    # ═══════════════════════════════════════════════════════
    # ÉTAPE 1 : LOCALISATION
    # ═══════════════════════════════════════════════════════
    st.markdown(f"#### 📍 {_t('step2.env_step1_location', 'Étape 1 : Localisation du site')}")
    st.caption(_t("step2.env_step1_caption",
                  "Commencez par définir l'emplacement du site."))

    st.session_state.setdefault(f"lat_{iid}", 36.7538)
    st.session_state.setdefault(f"lon_{iid}", 3.0588)

    loc_method = st.radio(
        _t("step2.env_location_method", "Méthode de localisation"),
        ["env_loc_search", "env_loc_gps", "env_loc_manual"],
        format_func=lambda k: _t(f"step2.{k}", k),
        horizontal=True,
        key=f"locmethod_{iid}",
    )

    if loc_method == "env_loc_search":
        from ui.map_dispersion import search_location
        q_loc = st.text_input(
            _t("step2.env_loc_search_label", "Rechercher un lieu"),
            placeholder=_t("step2.env_loc_search_placeholder",
                           "Ex : Alger, Raffinerie, Port…"),
            key=f"locq_{iid}",
        )
        if q_loc and len(q_loc.strip()) >= 3:
            with st.spinner(_t("common.loading", "Recherche…")):
                results = search_location(q_loc.strip())
            if results:
                choice = st.selectbox(
                    _t("step2.env_loc_search_results", "Résultats"),
                    results,
                    format_func=lambda r: r["name"],
                    key=f"locsel_{iid}",
                )
                st.session_state[f"lat_{iid}"] = float(choice["lat"])
                st.session_state[f"lon_{iid}"] = float(choice["lon"])
            else:
                st.warning(_t("step2.env_loc_search_no_results", "Aucun résultat."))

    elif loc_method == "env_loc_gps":
        st.caption(_t("step2.env_loc_gps_help",
                      "Autorisez la géolocalisation dans votre navigateur."))
        if st.button(_t("step2.env_loc_gps_button", "📍 Obtenir ma position"),
                     key=f"gpsbtn_{iid}"):
            st.session_state[f"gps_req_{iid}"] = True
        if st.session_state.get(f"gps_req_{iid}"):
            try:
                from streamlit_js_eval import get_geolocation
                gps = get_geolocation(component_key=f"gps_{iid}")
                coords = (gps or {}).get("coords") if isinstance(gps, dict) else None
                if coords and "latitude" in coords:
                    st.session_state[f"lat_{iid}"] = float(coords["latitude"])
                    st.session_state[f"lon_{iid}"] = float(coords["longitude"])
                    st.success(_t("step2.env_loc_gps_success", "Position GPS récupérée !"))
                else:
                    st.caption(_t("step2.env_loc_gps_hint", "En attente…"))
            except ImportError:
                st.warning("pip install streamlit-js-eval")
            except Exception:
                st.caption(_t("step2.env_loc_gps_hint", "En attente…"))

    coords_locked = loc_method != "env_loc_manual"
    c1, c2 = st.columns(2)
    latitude = c1.number_input(
        _t("step2.env_latitude", "Latitude"),
        min_value=-90.0, max_value=90.0, format="%.6f",
        disabled=coords_locked, key=f"lat_{iid}",
    )
    longitude = c2.number_input(
        _t("step2.env_longitude", "Longitude"),
        min_value=-180.0, max_value=180.0, format="%.6f",
        disabled=coords_locked, key=f"lon_{iid}",
    )
    st.info(f"📍 {_t('step2.env_current_coords', 'Coordonnées actuelles')} : "
            f"{latitude:.5f}, {longitude:.5f}")
    st.markdown("---")

    # ═══════════════════════════════════════════════════════
    # ÉTAPE 2 : MÉTÉO
    # ═══════════════════════════════════════════════════════
    st.markdown(f"#### 🌦 {_t('step2.env_step2_weather', 'Étape 2 : Météo')}")
    st.caption(_t("step2.env_step2_caption",
                  "Récupérez la météo actuelle selon la localisation."))

    weather_data = None
    use_weather = False
    try:
        from weather_service import (is_configured as weather_configured,
                                     get_weather_or_none)
        if weather_configured():
            st.session_state.setdefault(f"weather_data_{iid}", None)
            wm = st.radio(
                "Méthode météo", ["par_coords", "par_ville"],
                format_func=lambda k: {
                    "par_coords": "📍 Par coordonnées (recommandé)",
                    "par_ville": "🏙 Par ville",
                }[k],
                horizontal=True, key=f"weather_method_{iid}",
            )
            if wm == "par_coords":
                c1, c2 = st.columns([3, 1])
                c1.info(f"📍 {latitude:.5f}, {longitude:.5f}")
                with c2:
                    st.markdown("&nbsp;")
                    if st.button("🌦 Récupérer", key=f"weather_fetch_coords_{iid}",
                                 use_container_width=True, type="primary"):
                        with st.spinner(_t("common.loading", "…")):
                            d = get_weather_or_none(lat=latitude, lon=longitude)
                        if d:
                            st.session_state[f"weather_data_{iid}"] = d
                            st.success(f"✅ {d['ville_detectee']}")
                            st.rerun()
                        else:
                            st.error("❌ Météo indisponible.")
            else:
                c1, c2 = st.columns([3, 1])
                city = c1.text_input(_t("step2.env_weather_city_label", "Ville"),
                                     key=f"weather_city_input_{iid}")
                with c2:
                    st.markdown("&nbsp;")
                    if st.button(_t("step2.env_weather_fetch_button", "🌦 Récupérer"),
                                 key=f"weather_fetch_city_{iid}",
                                 use_container_width=True):
                        with st.spinner(_t("common.loading", "…")):
                            d = get_weather_or_none(city=city)
                        if d:
                            st.session_state[f"weather_data_{iid}"] = d
                            st.session_state[f"lat_{iid}"] = d["latitude"]
                            st.session_state[f"lon_{iid}"] = d["longitude"]
                            st.success(f"✅ {d['ville_detectee']}")
                            st.rerun()
                        else:
                            st.error("❌ Ville introuvable.")

            weather_data = st.session_state.get(f"weather_data_{iid}")
            if weather_data:
                c1, c2, c3, c4 = st.columns(4)
                c1.metric("💨 Vent", f"{weather_data['vitesse_vent_m_s']:.1f} m/s")
                c2.metric("🧭 Direction", f"{weather_data['direction_vent_deg']:.0f}°")
                c3.metric("🌡 Temp.", f"{weather_data['temperature_c']:.1f}°C")
                c4.metric("💧 Humidité", f"{weather_data['humidite_pct']:.0f}%")
                use_weather = st.checkbox(
                    _t("step2.env_weather_applied", "Appliquer la météo"),
                    value=True, key=f"use_weather_{iid}",
                )
        else:
            st.info(_t("step2.env_weather_not_configured",
                       "Service météo non configuré (clé API)."))
    except ImportError:
        st.info("weather_service non disponible.")

    st.markdown("---")

    # ═══════════════════════════════════════════════════════
    # ÉTAPE 3 : FUITE
    # ═══════════════════════════════════════════════════════
    st.markdown(f"#### 🧪 {_t('step2.env_step3_leak', 'Étape 3 : Données de fuite')}")
    st.caption(_t("step2.env_step3_caption",
                  "Sélectionnez la substance et les paramètres."))

    sub_mode = st.radio(
        _t("step2.chem_mode", "Source"),
        ["local", "pubchem"],
        format_func=lambda k: _t(f"step2.chem_mode_{k}", k),
        horizontal=True, key=f"submode_{iid}",
    )

    c1, c2 = st.columns(2)
    if sub_mode == "local":
        substance_env = c1.selectbox(
            _t("step2.env_substance", "Substance"),
            substance_options,
            format_func=lambda x: (_t("common.select_placeholder", "-- Sélectionner --")
                                   if x == "-- Sélectionner --" else x),
            key=f"subenv_{iid}",
        )
    else:
        typed = c1.text_input(
            _t("step2.chem_custom_label", "Nom de la substance"),
            key=f"subenv_custom_{iid}",
        )
        substance_env = typed.strip() if len(typed.strip()) >= 3 else None

    c1, c2 = st.columns(2)
    taille_fuite = c1.number_input(
        _t("step2.env_leak_size", "Taille de fuite (kg)"),
        min_value=0.0, value=50.0, key=f"tfuite_{iid}",
    )
    duree_fuite = c2.number_input(
        _t("step2.env_leak_duration", "Durée (s)"),
        min_value=1.0, value=300.0, key=f"dfuite_{iid}",
    )

    if substance_env and substance_env != "-- Sélectionner --":
        try:
            from chemical_db_interface import get_chemical_properties
            with st.spinner(_t("step2.chem_loading", "…")):
                chem = get_chemical_properties(substance_env)
            with st.expander(_t("step2.chem_expander",
                                f"Propriétés : {substance_env}"),
                             expanded=False):
                src = chem.get("source", "default")
                if src == "pubchem":
                    st.info(_t("step2.chem_source_pubchem",
                               "Source : PubChem"))
                elif src == "json":
                    st.success(_t("step2.chem_source_local", "Source : locale"))
                else:
                    st.warning(_t("step2.chem_source_default", "Valeurs par défaut."))
                c1, c2, c3 = st.columns(3)
                if chem.get("cas"):
                    c1.metric("CAS", chem["cas"])
                if chem.get("cid"):
                    c2.metric("CID", chem["cid"])
                if chem.get("molecular_formula"):
                    c3.metric("Formule", chem["molecular_formula"])
                if chem.get("masse_moleculaire"):
                    st.caption(f"Masse molaire : {chem['masse_moleculaire']:.2f} g/mol")
                seuil = chem.get("seuil_toxique_mg_m3", 100.0)
                st.caption(f"Seuil toxique : {seuil:.2f} mg/m³")
            # Bloc GHS
            try:
                from ghs_service import render_ghs_block
                with st.expander("⚠️ Classification GHS", expanded=False):
                    render_ghs_block(substance_env)
            except Exception:
                pass
        except Exception as e:
            st.info(f"Propriétés indisponibles : {e}")

    st.markdown("💨 Paramètres de vent")
    c1, c2 = st.columns(2)
    if use_weather and weather_data:
        vitesse_vent = c1.number_input(
            _t("step2.env_wind_speed", "Vitesse du vent (m/s)"),
            min_value=0.1,
            value=max(0.1, float(weather_data["vitesse_vent_m_s"])),
            key=f"vvent_{iid}",
            help="🌦 Valeur OpenWeather appliquée",
        )
        direction_vent = c2.number_input(
            _t("step2.env_wind_dir", "Direction (°)"),
            min_value=0.0, max_value=360.0,
            value=float(weather_data["direction_vent_deg"]),
            key=f"dvent_{iid}",
            help="🌦 Valeur OpenWeather appliquée",
        )
    else:
        vitesse_vent = c1.number_input(
            _t("step2.env_wind_speed", "Vitesse du vent (m/s)"),
            min_value=0.1, value=3.0, key=f"vvent_{iid}",
        )
        direction_vent = c2.number_input(
            _t("step2.env_wind_dir", "Direction (°)"),
            min_value=0.0, max_value=360.0, value=270.0, key=f"dvent_{iid}",
        )
    temperature = st.number_input(
        _t("step2.env_temperature", "Température (°C)"),
        value=float(weather_data["temperature_c"]) if (use_weather and weather_data) else 25.0,
        key=f"temp_{iid}",
    )

    st.markdown("---")

    # ═══════════════════════════════════════════════════════
    # ÉTAPE 4 : CARTE & RÉSULTATS
    # ═══════════════════════════════════════════════════════
    st.markdown(f"#### 🗺 {_t('step2.env_step4_map', 'Étape 4 : Carte & résultats')}")
    st.caption(_t("step2.env_step4_caption",
                  "Visualisez la zone d'impact."))

    result = {
        "latitude": latitude, "longitude": longitude,
        "substance": substance_env,
        "taille_fuite": taille_fuite, "duree_fuite": duree_fuite,
        "vitesse_vent": vitesse_vent, "direction_vent": direction_vent,
        "temperature": temperature,
        "use_weather": use_weather,
    }

    if (substance_env and substance_env != "-- Sélectionner --"
            and taille_fuite and duree_fuite and vitesse_vent):
        try:
            from chemical_db_interface import get_chemical_properties
            from dispersion_aloha import (determiner_classe_stabilite,
                                          calculer_distance_impact)
            from ui.map_dispersion import render_dispersion_map

            props = get_chemical_properties(substance_env)
            seuil = props.get("seuil_toxique_mg_m3", 100.0)
            debit = (taille_fuite * 1000.0) / duree_fuite
            classe = determiner_classe_stabilite(vitesse_vent)
            d_impact = calculer_distance_impact(
                debit, vitesse_vent, classe, seuil / 1000.0
            )
            render_dispersion_map(
                latitude=latitude, longitude=longitude,
                distance_impact_m=d_impact,
                substance=substance_env,
                label=f"Fuite {substance_env}",
                wind_dir=direction_vent,
            )
            c1, c2, c3 = st.columns(3)
            c1.metric(_t("step2.env_toxic_threshold", "Seuil"), f"{seuil:.2f} mg/m³")
            c2.metric(_t("step2.env_impact_distance", "Distance"), f"{d_impact:.0f} m")
            c3.metric(_t("step2.env_stability_class", "Classe"), classe)
            result["distance_impact_m"] = d_impact
            result["seuil_mg_m3"] = seuil
            result["classe_stabilite"] = classe
        except Exception as e:
            st.info(_t("step2.env_map_error", f"Carte indisponible : {e}"))
    else:
        st.info(_t("step2.env_map_no_data", "Complétez les étapes 1–3."))

    return result