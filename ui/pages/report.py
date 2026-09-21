"""
ui/pages/report.py — Étape 4 : Rapport IA (HSE PYXIS)
=======================================================
Interface Streamlit pour la génération de rapport d'audit.

Moteur IA : ai_service.py (Gemini), comme l'Étape 1 (vérification
d'évidence) et l'Étape 5 (plan PDCA) — les trois étapes partagent le même
service d'IA, conformément au découpage de l'application.

Principe i18n
-------------
Deux langues coexistent ici et ne doivent pas être confondues :
    - la langue de l'INTERFACE (get_current_lang()) : libellés des widgets,
      traduits via ui.i18n.t() (locales/*.json) ;
    - la langue du RAPPORT (choisie via un selectbox dédié) : contenu généré
      par le LLM, transmis tel quel à ai_service.generer_rapport().
Un audit consulté en arabe peut très bien produire un rapport en anglais.
"""

from datetime import datetime

import pandas as pd
import streamlit as st

from ui.i18n import t, LANGUAGES, get_current_lang
import ai_service


def _get_report_filename(audit_id: str, extension: str = "md") -> str:
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    safe_audit_id = audit_id.replace(" ", "_").replace("/", "_")
    return f"rapport_HSE_{safe_audit_id}_{timestamp}.{extension}"


def _collect_report_data(db, audit_id: str):
    """Rassemble les données NC/PC + statistiques pour le prompt IA,
    à partir des résultats Monte Carlo (même logique que l'Étape 4
    d'origine : Top 10 des symptômes les plus à risque)."""
    conformites = db.get_conformity_by_audit(audit_id)
    n_nc = sum(1 for v in conformites.values() if v == "NC")
    n_pc = sum(1 for v in conformites.values() if v == "PC")
    n_c = sum(1 for v in conformites.values() if v == "C")
    n_total = len(conformites)

    stats_summary = {
        "total_items": n_total,
        "n_nc": n_nc,
        "n_pc": n_pc,
        "n_c": n_c,
    }

    mc_results = db.get_mc_results(audit_id)
    items_data = []
    if mc_results:
        df_mc = pd.DataFrame(mc_results, columns=[
            "id", "audit_id", "item_id", "n_iterations",
            "freq_min", "freq_mode", "freq_max",
            "freq_moyenne", "freq_p05", "freq_p50", "freq_p95",
            "severite", "score_risque",
            "niveau_sev", "niveau_prob", "niveau_risque", "couleur", "created_at",
        ])
        df_mc_sorted = df_mc.sort_values("score_risque", ascending=False)
        top_10 = df_mc_sorted.head(10)

        for _, row in top_10.iterrows():
            item_row = db.get_item(row["item_id"])
            if not item_row:
                continue
            items_data.append({
                "item_id": row["item_id"],
                "section": item_row[1],
                "equipement": item_row[2],
                "symptome": item_row[3],
                "severity": row["severite"],
                "conformite": conformites.get(row["item_id"], "NC"),
                "freq_moyenne": row["freq_moyenne"],
                "risk_class": row["niveau_risque"],
            })

    return items_data, stats_summary


def render_report_page(db, audit_id: str, site_name: str = "—"):
    st.header(t("step4.title"))
    st.caption(t("step4.caption"))

    status = ai_service.get_status()

    if not status["configured"]:
        st.warning(f"**{t('step4.not_configured_title')}**")
        st.info(t("step4.not_configured_body"))
        return

    st.caption(t("step4.model_label", model=status["model"]))

    if not st.session_state.get("batch_done"):
        st.info(t("step4.batch_required"))

    items_data, stats_summary = _collect_report_data(db, audit_id)

    if stats_summary.get("total_items", 0) == 0:
        st.warning(t("step4.no_data"))
        return

    col_a, col_b, col_c, col_d = st.columns(4)
    col_a.metric(t("step4.metric_total"), stats_summary["total_items"])
    col_b.metric("NC", stats_summary["n_nc"])
    col_c.metric("PC", stats_summary["n_pc"])
    col_d.metric("C", stats_summary["n_c"])

    st.markdown("---")

    # ---- Langue du RAPPORT (indépendante de la langue de l'interface) ----
    report_lang_options = list(LANGUAGES.keys())
    default_idx = report_lang_options.index(get_current_lang())

    col1, col2 = st.columns([1, 2])
    with col1:
        report_language = st.selectbox(
            t("step4.report_language"),
            report_lang_options,
            index=default_idx,
            format_func=lambda x: f"{LANGUAGES[x]['flag']} {LANGUAGES[x]['label']}",
            key="report_language_select",
        )

    custom_instructions = st.text_area(
        t("step4.custom_instructions"),
        key="report_custom_instructions",
        placeholder=t("step4.custom_instructions_placeholder"),
        height=80,
    )

    if st.button(t("step4.generate_button"), type="primary", key="generate_report_btn"):
        with st.spinner(t("step4.generating", model=status["model"])):
            ai_result = ai_service.generer_rapport(
                audit_id=audit_id,
                site_name=site_name,
                nc_pc_items=items_data,
                stats_summary=stats_summary,
                langue=report_language,
                custom_instructions=custom_instructions,
            )

        if ai_result.get("erreur"):
            result = {
                "success": False,
                "report": "",
                "error": t("step4.error_api", error=ai_result["erreur"], _lang=report_language),
            }
        else:
            result = {
                "success": True,
                "report": ai_result["markdown"],
                "duration_s": 0,
                "tokens_used": 0,
            }

        st.session_state["last_report_result"] = result
        st.session_state["last_report_language"] = report_language

    # ---- Affichage du dernier résultat (survit au rerun du bouton téléchargement) ----
    result = st.session_state.get("last_report_result")
    if not result:
        return

    if not result["success"]:
        # result["error"] est déjà traduit dans la langue du RAPPORT choisie
        # (pas forcément celle de l'interface) : c'est voulu, l'utilisateur
        # vient de la sélectionner explicitement.
        st.error(result["error"])
        return

    st.success(t("step4.generated_ok"))
    st.markdown("---")
    st.markdown(result["report"])
    st.markdown("---")

    st.download_button(
        t("step4.download_button"),
        result["report"].encode("utf-8"),
        _get_report_filename(audit_id),
        "text/markdown",
    )
    st.caption(t("step4.disclaimer"))
