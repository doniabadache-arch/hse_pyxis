"""
results_viewer.py
=================
Dictionnaire de fonctions d'affichage et de classification.

Extrait de app_risk.pyy.py — utilisé par audit_app.py pour :
- charger la matrice depuis matrice.db (dynamique)
- classifier les symptômes NC/PC (fréquence → niveau probabilité → classe risque)
- afficher heatmap, metric cards, graphiques Plotly

Ne contient AUCUNE logique métier (Monte Carlo, PLL, coût-bénéfice, etc.).
Ces logiques restent dans leurs modules respectifs.
"""

import sqlite3
from contextlib import closing

import pandas as pd
import numpy as np
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from ui.theme import show_plotly
from ui.i18n import t
from ui.display import tr_matrix_label


DB_PATH = "matrice.db"


# ============================================================
# 1. CHARGEMENT DE LA MATRICE (DYNAMIQUE, SANS CACHE)
# ============================================================
def load_matrix_dfs(site_name, db_path=DB_PATH):
    """
    Charge les 3 tables de matrice.db comme DataFrames pandas.

    Retourne
    --------
    (df_sev, df_prob, df_seuils)
        - df_sev     : level, label, color, action
        - df_prob    : level, label, frequency_range, color
        - df_seuils  : max_score, risk_label, color
    """
    with closing(sqlite3.connect(db_path)) as conn:
        df_sev = pd.read_sql_query(
            "SELECT level, label, color, action FROM severity_config "
            "WHERE site_name = ? ORDER BY level",
            conn, params=(site_name,)
        )
        df_prob = pd.read_sql_query(
            "SELECT level, label, frequency_range, color FROM probability_config "
            "WHERE site_name = ? ORDER BY level",
            conn, params=(site_name,)
        )
        df_seuils = pd.read_sql_query(
            "SELECT max_score, risk_label, color FROM risk_thresholds "
            "WHERE site_name = ? ORDER BY max_score",
            conn, params=(site_name,)
        )
    return df_sev, df_prob, df_seuils


# ============================================================
# 2. CONVERSION FRÉQUENCE → NIVEAU DE PROBABILITÉ
# ============================================================
def freq_to_prob_level(freq, df_prob):
    """
    Convertit une fréquence annuelle en (level, label, color)
    selon la plage définie dans la matrice.

    Formats supportés :
        "< 1e-5 /an"
        "> 1e-1 /an"
        "1e-5 à 1e-3 /an"
    """
    for _, row in df_prob.iterrows():
        s = str(row["frequency_range"]).replace("/an", "").strip()
        try:
            # "< 1e-5"
            if "<" in s and "à" not in s:
                limit = float(s.split("<")[1].strip())
                if freq < limit:
                    return int(row["level"]), row["label"], row["color"]
            # "> 1e-1"
            elif ">" in s and "à" not in s:
                limit = float(s.split(">")[1].strip())
                if freq > limit:
                    return int(row["level"]), row["label"], row["color"]
            # "1e-5 à 1e-3"
            elif "à" in s:
                parts = s.split("à")
                low = float(parts[0].strip())
                high = float(parts[1].strip())
                if low <= freq < high:
                    return int(row["level"]), row["label"], row["color"]
        except Exception:
            continue

    # Fallback : premier niveau
    first = df_prob.iloc[0]
    return int(first["level"]), first["label"], first["color"]


# ============================================================
# 3. CLASSIFICATION D'UN SCORE (SÉVÉRITÉ × PROBABILITÉ)
# ============================================================
def get_risk_class(severity, prob_level, df_seuils):
    """
    Retourne (score, risk_label, risk_color) selon les seuils configurés.
    """
    score = int(severity) * int(prob_level)
    for _, row in df_seuils.iterrows():
        if score <= row["max_score"]:
            return score, row["risk_label"], row["color"]
    last = df_seuils.iloc[-1]
    return score, last["risk_label"], last["color"]


# ============================================================
# 4. CLASSIFICATION D'UN DATAFRAME DE RÉSULTATS
# ============================================================
def classify_results_df(df, df_sev, df_prob, df_seuils):
    """
    Ajoute des colonnes de classification à un DataFrame de résultats.

    Le DataFrame doit contenir :
        - 'severite'       (int)
        - 'freq_moyenne'   (float)

    Ajoute :
        - 'prob_level', 'prob_label', 'prob_color'
        - 'risk_score', 'risk_class', 'risk_color'
    """
    if df.empty:
        return df

    def classify_row(row):
        prob_level, prob_label, prob_color = freq_to_prob_level(
            row["freq_moyenne"], df_prob
        )
        score, risk_label, risk_color = get_risk_class(
            row["severite"], prob_level, df_seuils
        )
        return pd.Series({
            "prob_level": prob_level,
            "prob_label": prob_label,
            "prob_color": prob_color,
            "risk_score": score,
            "risk_class": risk_label,
            "risk_color": risk_color,
        })

    return pd.concat([df, df.apply(classify_row, axis=1)], axis=1)


# ============================================================
# 5. AFFICHAGE : METRIC CARDS (distribution par classe)
# ============================================================
def render_metric_cards(df_classified, df_seuils):
    """
    Affiche 4 metric cards colorées :
    - total items analysés
    - nombre par classe de risque (3 premières)
    """
    col1, col2, col3, col4 = st.columns(4)

    with col1:
        st.markdown(f"""
<div style="padding:1.5rem;border-radius:12px;color:white;
background:linear-gradient(135deg,#667eea,#764ba2);
text-align:center;box-shadow:0 4px 15px rgba(0,0,0,0.1);">
<h2 style="margin:0;font-size:2.5rem;">{len(df_classified)}</h2>
<p style="margin:0;opacity:0.9;">{t("results.items_analyzed")}</p>
</div>
""", unsafe_allow_html=True)

    for col, (_, seuil_row) in zip(
        [col2, col3, col4],
        df_seuils.head(3).iterrows()
    ):
        count = len(df_classified[df_classified["risk_class"] == seuil_row["risk_label"]])
        with col:
            st.markdown(f"""
<div style="padding:1.5rem;border-radius:12px;color:white;
background:{seuil_row['color']};
text-align:center;box-shadow:0 4px 15px rgba(0,0,0,0.1);">
<h2 style="margin:0;font-size:2.5rem;">{count}</h2>
<p style="margin:0;opacity:0.9;">{tr_matrix_label(seuil_row["risk_label"])}</p>
</div>
""", unsafe_allow_html=True)


# ============================================================
# 6. AFFICHAGE : HEATMAP DE LA MATRICE
# ============================================================
def render_heatmap(df_classified, df_sev, df_prob, df_seuils):
    """
    Affiche la matrice (Sévérité × Probabilité) avec :
    - couleurs selon la classe de risque
    - identifiants des symptômes positionnés dans chaque cellule
    """
    html = "<table style='width:100%;border-collapse:collapse;font-size:13px;'>"

    # Ligne d'en-tête
    html += "<tr style='background:#2c5282;color:white;'>"
    html += f"<th style='padding:10px;'>{t('results.sev_x_prob')}</th>"
    for _, prob_row in df_prob.iterrows():
        html += (
            f"<th style='padding:10px;'>{tr_matrix_label(prob_row['label'])}"
            f"<br><small>({prob_row['level']})</small></th>"
        )
    html += "</tr>"

    # Lignes de sévérité (décroissantes)
    for _, sev_row in df_sev.sort_values("level", ascending=False).iterrows():
        sev_level = int(sev_row["level"])
        html += (
            f"<tr><td style='padding:10px;background:{sev_row['color']};"
            f"color:white;font-weight:700;text-align:center;'>"
            f"{tr_matrix_label(sev_row['label'])}<br><small>(S{sev_level})</small></td>"
        )

        for _, prob_row in df_prob.iterrows():
            prob_level = int(prob_row["level"])
            score, risk_label, risk_color = get_risk_class(
                sev_level, prob_level, df_seuils
            )

            matching = df_classified[
                (df_classified["severite"] == sev_level) &
                (df_classified["prob_level"] == prob_level)
            ]

            if len(matching) > 0:
                content = "<br>".join(matching["item_id"].tolist())
            else:
                content = f"{score}"

            html += (
                f"<td style='padding:12px;background:{risk_color};color:white;"
                f"text-align:center;border:1px solid white;font-weight:600;'>"
                f"{content}</td>"
            )

        html += "</tr>"

    html += "</table>"
    st.markdown(html, unsafe_allow_html=True)

    # Légende
    st.markdown(f"### {t('results.legend')}")
    legend_html = ""
    for _, seuil_row in df_seuils.iterrows():
        legend_html += (
            f"<span style='background:{seuil_row['color']};padding:0.5rem 1rem;"
            f"border-radius:6px;color:white;font-weight:700;margin-right:1rem;'>"
            f"{tr_matrix_label(seuil_row['risk_label'])} "
            f"({t('results.score_le', score=seuil_row['max_score'])})</span>"
        )
    st.markdown(legend_html, unsafe_allow_html=True)


# ============================================================
# 7. AFFICHAGE : GRAPHIQUES PLOTLY
# ============================================================
def render_plots(df_classified, df_seuils, top_n=10):
    """
    Affiche 3 graphiques :
    - Pie : distribution par classe
    - Bar : items par section
    - Grouped bar : risque P50 / P95 pour TOP N
    """
    col1, col2 = st.columns(2)

    # --- Pie ---
    with col1:
        class_counts = df_classified["risk_class"].value_counts()
        # Les clés restent les valeurs stockées ; seuls les noms affichés
        # sont traduits (la correspondance couleur <-> classe est préservée).
        colors_map = {
            tr_matrix_label(row["risk_label"]): row["color"]
            for _, row in df_seuils.iterrows()
        }
        class_names = [tr_matrix_label(c) for c in class_counts.index]
        fig1 = px.pie(
            values=class_counts.values,
            names=class_names,
            title=t("results.chart_distribution"),
            color=class_names,
            color_discrete_map=colors_map,
            hole=0.4,
        )
        show_plotly(fig1)

    # --- Bar ---
    with col2:
        if "section" in df_classified.columns:
            section_counts = df_classified.groupby("section").size().sort_values()
            fig2 = px.bar(
                x=section_counts.values,
                y=section_counts.index,
                orientation="h",
                title=t("results.chart_by_section"),
            )
            show_plotly(fig2)

    # --- Grouped bar TOP N ---
    st.subheader(t("results.top_n_risk", n=top_n))
    df_top = df_classified.nlargest(top_n, "risk_score")
    if not df_top.empty and "freq_p95" in df_top.columns:
        fig3 = go.Figure()
        fig3.add_trace(go.Bar(
            x=df_top["item_id"], y=df_top["freq_moyenne"],
            name=t("results.freq_mean"), marker_color="#2c5282"
        ))
        fig3.add_trace(go.Bar(
            x=df_top["item_id"], y=df_top["freq_p95"],
            name=t("results.freq_p95"), marker_color="#E74C3C"
        ))
        fig3.update_layout(barmode="group", height=400)
        show_plotly(fig3)