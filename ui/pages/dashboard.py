# ui/pages/dashboard.py
"""
Tableau de bord — HSE PYXIS
===========================
Affiche les indicateurs clés de performance (KPI) :
- Non-conformités ouvertes / fermées
- Taux de conformité
- Actions correctives en retard
- Indicateurs de sécurité (TRIR / LTIFR simplifiés)
"""

import streamlit as st
import pandas as pd
import plotly.express as px
from datetime import date, timedelta

from ui.i18n import t


def _get_user_role():
    """Récupère le rôle de l'utilisateur connecté (depuis auth.py)"""
    user = st.session_state.get("user", {})
    return user.get("role", "Lecteur")


def render_dashboard_page(db=None, site_name=None):
    """
    Point d'entrée de la page Tableau de Bord.
    
    Args:
        db: Instance de InspectionDB (obligatoire)
        site_name: Nom du site actif (optionnel — utilisé comme filtre par défaut)
    """
    
    if db is None:
        st.error("❌ Aucune base de données fournie. Le tableau de bord ne peut pas s'afficher.")
        return

    # =========================================================
    # 1. RÉCUPÉRATION DES SITES (fallback si matrice_manager absent)
    # =========================================================
    sites_list = []
    try:
        # Essayer de récupérer les sites depuis les inspections existantes
        # (ou depuis une méthode de db si elle existe)
        if hasattr(db, "list_sites"):
            sites_list = db.list_sites() or []
        elif hasattr(db, "get_all_sites"):
            sites_list = db.get_all_sites() or []
        else:
            # Fallback : on utilise les sites des inspections déjà enregistrées
            try:
                all_insp = db.list_inspections() or []
                # On ne peut pas déduire le site ici, donc on laisse vide
                sites_list = []
            except Exception:
                sites_list = []
    except Exception:
        sites_list = []

    # =========================================================
    # 2. FILTRES (Site + Période)
    # =========================================================
    st.header("📊 " + t("dashboard.title"))
    st.caption(t("dashboard.subtitle"))

    col1, col2, col3 = st.columns([2, 2, 2])
    
    with col1:
        site_options = ["-- Tous les sites --"] + sites_list
        # Si site_name est fourni, on le met par défaut
        default_idx = 0
        if site_name and site_name in site_options:
            default_idx = site_options.index(site_name)
        selected_site = st.selectbox(
            "Site", 
            site_options, 
            index=default_idx,
            key="dash_site"
        )
    
    with col2:
        date_from = st.date_input(
            "Du",
            value=date.today() - timedelta(days=90),
            key="dash_date_from"
        )
    
    with col3:
        date_to = st.date_input(
            "Au",
            value=date.today(),
            key="dash_date_to"
        )

    site_filter = None if selected_site == "-- Tous les sites --" else selected_site

    st.markdown("---")

    # =========================================================
    # 3. RÉCUPÉRATION DES DONNÉES (avec fallbacks)
    # =========================================================
    with st.spinner("Chargement..."):
        # Inspections
        try:
            all_inspections = db.list_inspections() or []
        except Exception:
            all_inspections = []
        
        # Actions correctives (on récupère tout, on filtrera après)
        try:
            corrective_actions = db.get_corrective_actions() or []
        except Exception:
            corrective_actions = []

    # Filtrer par site si nécessaire
    # (les inspections n'ont pas toujours site_name direct — on essaie)
    if site_filter:
        filtered_actions = []
        for a in corrective_actions:
            # On garde si le site correspond ou si pas d'info de site
            if a.get("site_name") == site_filter:
                filtered_actions.append(a)
        corrective_actions = filtered_actions

    # =========================================================
    # 4. CALCULS DES KPI
    # =========================================================
    total_inspections = len(all_inspections)
    
    # NC ouvertes = actions correctives non terminées
    open_nc = sum(
        1 for a in corrective_actions 
        if a.get("status") in ("open", "in_progress")
    )
    
    # Actions en retard
    today_iso = date.today().isoformat()
    late_actions = sum(
        1 for a in corrective_actions 
        if a.get("status") not in ("done", "closed", "cancelled")
        and a.get("deadline")
        and a.get("deadline") < today_iso
    )
    
    # Taux de conformité (moyenne sur toutes les inspections)
    total_points = 0
    total_conformes = 0
    for insp_id in all_inspections:
        try:
            conf = db.get_conformity_by_inspection(insp_id)
            if conf:
                total_points += len(conf)
                total_conformes += sum(1 for c in conf.values() if c == "C")
        except Exception:
            continue
    
    taux_conformite = (total_conformes / total_points * 100) if total_points > 0 else 0.0

    # =========================================================
    # 5. CARTES KPI
    # =========================================================
    st.subheader("🎯 Indicateurs clés")
    
    kpi1, kpi2, kpi3, kpi4 = st.columns(4)
    kpi1.metric(
        label="🔍 Inspections",
        value=total_inspections
    )
    kpi2.metric(
        label="⚠️ NC ouvertes",
        value=open_nc,
    )
    kpi3.metric(
        label="✅ Taux de conformité",
        value=f"{taux_conformite:.1f} %"
    )
    kpi4.metric(
        label="⏰ Actions en retard",
        value=late_actions,
        delta=f"-{late_actions}" if late_actions > 0 else None,
        delta_color="inverse"
    )

    st.markdown("---")

    # =========================================================
    # 6. GRAPHIQUES
    # =========================================================
    st.subheader("📈 Visualisations")
    
    col_graph1, col_graph2 = st.columns(2)

    # --- Graphique 1 : Répartition des Conformités ---
    with col_graph1:
        st.markdown("**Répartition des conformités**")
        if total_points > 0:
            fig_pie = px.pie(
                values=[total_conformes, total_points - total_conformes],
                names=["Conformes", "Non conformes"],
                color_discrete_sequence=["#2ECC71", "#E74C3C"],
                hole=0.4
            )
            fig_pie.update_layout(
                margin=dict(t=0, b=0, l=0, r=0), 
                height=350,
                paper_bgcolor="rgba(0,0,0,0)",
                plot_bgcolor="rgba(0,0,0,0)",
            )
            st.plotly_chart(fig_pie, use_container_width=True)
        else:
            st.info("ℹ️ Aucune donnée de conformité disponible.")

    # --- Graphique 2 : Répartition des actions par statut ---
    with col_graph2:
        st.markdown("**Actions correctives par statut**")
        if corrective_actions:
            df_actions = pd.DataFrame(corrective_actions)
            if "status" in df_actions.columns:
                status_counts = df_actions["status"].value_counts().reset_index()
                status_counts.columns = ["Statut", "Nombre"]
                
                fig_bar = px.bar(
                    status_counts, 
                    x="Statut", 
                    y="Nombre",
                    color="Statut",
                    color_discrete_sequence=["#3498DB", "#F39C12", "#2ECC71", "#E74C3C"]
                )
                fig_bar.update_layout(
                    margin=dict(t=0, b=0, l=0, r=0), 
                    height=350,
                    showlegend=False,
                    paper_bgcolor="rgba(0,0,0,0)",
                    plot_bgcolor="rgba(0,0,0,0)",
                )
                st.plotly_chart(fig_bar, use_container_width=True)
            else:
                st.info("ℹ️ Aucune donnée d'actions disponible.")
        else:
            st.info("ℹ️ Aucune action corrective enregistrée.")

    # =========================================================
    # 7. TABLEAU DES ACTIONS EN RETARD
    # =========================================================
    st.markdown("---")
    st.subheader("🚨 Actions en retard")
    
    late_list = [
        a for a in corrective_actions 
        if a.get("status") not in ("done", "closed", "cancelled")
        and a.get("deadline")
        and a.get("deadline") < today_iso
    ]
    
    if late_list:
        df_late = pd.DataFrame(late_list)
        
        # Renommer les colonnes visibles
        rename_map = {
            "item_id": "Item",
            "action": "Action",
            "responsible": "Responsable",
            "deadline": "Échéance",
        }
        cols_to_show = [c for c in rename_map.keys() if c in df_late.columns]
        
        st.dataframe(
            df_late[cols_to_show].rename(columns=rename_map),
            use_container_width=True,
            hide_index=True
        )
    else:
        st.success("✅ Aucune action en retard — tout est à jour !")

    # =========================================================
    # 8. INDICATEURS DE SÉCURITÉ (TRIR / LTIFR)
    # =========================================================
    st.markdown("---")
    with st.expander("📚 Indicateurs TRIR / LTIFR", expanded=False):
        st.caption(
            "TRIR = Total Recordable Incident Rate (taux d'incidents enregistrables) · "
            "LTIFR = Lost Time Injury Frequency Rate (taux de fréquence des accidents avec arrêt)."
        )
        
        col_a, col_b = st.columns(2)
        with col_a:
            heures_travail = st.number_input(
                "Heures travaillées (année)", 
                min_value=1.0, value=100000.0, step=1000.0,
                key="dash_trir_hours"
            )
            nb_accidents = st.number_input(
                "Nombre d'incidents enregistrables", 
                min_value=0, value=0, step=1,
                key="dash_trir_accidents"
            )
        with col_b:
            nb_jours_arret = st.number_input(
                "Jours d'arrêt cumulés", 
                min_value=0, value=0, step=1,
                key="dash_ltifr_days"
            )
        
        # Calculs standards (OSHA / ILO)
        trir = (nb_accidents * 200000) / heures_travail if heures_travail > 0 else 0
        ltifr = (nb_jours_arret * 1000000) / heures_travail if heures_travail > 0 else 0
        
        col_m1, col_m2 = st.columns(2)
        col_m1.metric("TRIR", f"{trir:.2f}")
        col_m2.metric("LTIFR", f"{ltifr:.2f}")