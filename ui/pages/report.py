"""
ui/pages/report.py — Étape 4 : Rapport IA (HSE PYXIS)
=======================================================
Interface Streamlit pour la génération de rapport d'inspection.

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
Une inspection consultée en arabe peut très bien produire un rapport en anglais.
"""

from datetime import datetime
from pathlib import Path

import pandas as pd
import streamlit as st
import streamlit.components.v1 as components

from ui.i18n import t, LANGUAGES, get_current_lang
import auth
import ai_service
import email_service
from company_profile import build_company_profile_text
from report_render import render_report_html
import report_template

# Nombre de symptômes (écarts) les plus à risque repris dans le rapport.
# TOUS sont transmis à l'IA ET affichés dans le rapport (plus de limite à 5).
TOP_N_RISKS = 10


def _get_report_filename(inspection_id: str, extension: str = "html") -> str:
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    safe_inspection_id = inspection_id.replace(" ", "_").replace("/", "_")
    return f"rapport_HSE_{safe_inspection_id}_{timestamp}.{extension}"


def _collect_report_data(db, inspection_id: str):
    """Rassemble les données NC/PC + statistiques pour le prompt IA,
    à partir des résultats Monte Carlo (même logique que l'Étape 4
    d'origine : Top 10 des symptômes les plus à risque)."""
    conformites = db.get_conformity_by_inspection(inspection_id)
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

    mc_results = db.get_mc_results(inspection_id)
    items_data = []
    if mc_results:
        df_mc = pd.DataFrame(mc_results, columns=[
            "id", "inspection_id", "item_id", "n_iterations",
            "freq_min", "freq_mode", "freq_max",
            "freq_moyenne", "freq_p05", "freq_p50", "freq_p95",
            "severite", "score_risque",
            "niveau_sev", "niveau_prob", "niveau_risque", "couleur", "created_at",
        ])
        df_mc_sorted = df_mc.sort_values("score_risque", ascending=False)
        top_n = df_mc_sorted.head(TOP_N_RISKS)

        for _, row in top_n.iterrows():
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
                "couleur": row["couleur"],
            })

    return items_data, stats_summary


def _collect_sections(db, inspection_id: str) -> list:
    """Répartition NC/PC/C par section, calculée depuis la BD (jamais par l'IA)."""
    agg = {}
    for iid, conf in db.get_conformity_by_inspection(inspection_id).items():
        row = db.get_item(iid)
        if not row:
            continue
        d = agg.setdefault(row[1], {"section": row[1], "nc": 0, "pc": 0, "c": 0})
        key = {"NC": "nc", "PC": "pc", "C": "c"}.get(conf)
        if key:
            d[key] += 1
    return sorted(agg.values(), key=lambda x: (-x["nc"], -x["pc"]))


def _render_template_picker():
    """Choix / import du modèle de rapport de l'entreprise.
    Retourne {"name", "data", "ext", "outline", "headings", "has_marker"} ou None."""
    st.caption(t("step4.tpl_help"))
    uploaded = st.file_uploader(
        t("step4.tpl_upload"), type=[e.lstrip(".") for e in report_template.ALLOWED_EXT],
        key="report_tpl_upload")

    saved = report_template.list_saved_templates()
    choice = ""
    if saved:
        choice = st.selectbox(
            t("step4.tpl_saved"), [""] + saved,
            format_func=lambda x: x or t("step4.tpl_none"), key="report_tpl_saved")

    data, name = None, None
    if uploaded is not None:
        data, name = uploaded.getvalue(), uploaded.name
        if auth.has_permission("manage_templates") and st.button(t("step4.tpl_save_btn"), key="report_tpl_save_btn"):
            try:
                report_template.save_template(name, data)
                st.success(t("step4.tpl_saved_ok", name=name))
            except ValueError as e:
                st.error(str(e))
    elif choice:
        data, name = report_template.load_saved_template(choice), choice
        if auth.has_permission("manage_templates") and st.button(t("step4.tpl_delete"), key="report_tpl_delete_btn"):
            report_template.delete_saved_template(choice)
            st.rerun()

    if not data:
        st.info(t("step4.tpl_required"))
        return None

    try:
        info = report_template.extract_outline(data, name)
    except ValueError as e:
        st.error(str(e))
        return None
    if not info["outline"].strip():
        st.warning(t("step4.tpl_empty"))
        return None

    with st.expander(t("step4.tpl_detected", n=len(info["headings"]))):
        if info["headings"]:
            for lvl, title in info["headings"]:
                st.markdown(f"{'&nbsp;' * 4 * (lvl - 1)}• {title}", unsafe_allow_html=True)
        else:
            st.caption(t("step4.tpl_no_headings"))
    if info["ext"] == ".docx":
        st.caption(t("step4.tpl_marker_found") if info["has_marker"] else t("step4.tpl_marker_missing"))
    else:
        st.caption(t("step4.tpl_non_docx_note"))
    info.update({"name": name, "data": data})
    return info


def _render_email_section(inspection_id: str, site_name: str, html_doc: str = None,
                          docx_bytes: bytes = None):
    """Bloc « Email » de la page Rapport : statut, destinataire, test, envoi.
    html_doc=None → le rapport n'est pas encore généré (envoi désactivé)."""
    if not auth.has_permission("send_email"):
        return          # lecteur : pas d'envoi d'email
    st.markdown("---")
    st.markdown("### 📧 Envoyer le rapport par email")

    status = email_service.get_status()
    if not status["configured"]:
        st.warning("⚠️ SMTP non configuré — ajoutez SMTP_* dans le fichier `.env`.")
        return

    if status.get("api_configured"):
        st.caption("✅ Brevo API configurée")
    for i, p in enumerate(status.get("smtp_providers", []), 1):
        role = "Fallback" if p["is_fallback"] else "Principal"
        st.caption(f"{i}. {role} : {p['label']} ({p['mode']})")

    # Pré-remplissage depuis le destinataire de la barre latérale (et mise à jour s'il change)
    side_to = st.session_state.get("email_recipient", "")
    if ("report_email_to" not in st.session_state
            or st.session_state.get("_report_email_side_prev") != side_to):
        st.session_state["report_email_to"] = side_to
        st.session_state["_report_email_side_prev"] = side_to

    to = st.text_input("📬 Adresse email du destinataire", key="report_email_to",
                       placeholder="manager@company.com").strip()

    attach_docx = False
    if docx_bytes:
        attach_docx = st.checkbox("Joindre aussi le fichier Word (.docx)",
                                  value=True, key="report_email_attach_docx")

    b1, b2 = st.columns(2)

    # ---- Test d'envoi ----
    if b1.button("🧪 Tester l'envoi", key="report_test_email_btn", use_container_width=True):
        if not to or "@" not in to:
            st.error("❌ Adresse email invalide.")
        else:
            with st.spinner("Test..."):
                r = email_service.send_email(
                    to=to,
                    subject="🎉 HSE PYXIS — Test Email",
                    html_body=("<html><body style=\"font-family:Arial;\">"
                               "<h1 style=\"color:#00C853;\">🎉 Test réussi !</h1>"
                               "<p>Votre configuration email fonctionne.</p></body></html>"),
                )
            if r["ok"]:
                st.success(f"✅ Test envoyé via **{r['provider']}**")
            else:
                st.error(f"❌ {r['error']}")

    # ---- Envoi du rapport ----
    if html_doc is None:
        b2.button("📧 Envoyer le rapport", key="send_report_email_btn",
                  disabled=True, use_container_width=True)
        st.caption("Générez d'abord le rapport pour pouvoir l'envoyer.")
        return

    if b2.button("📧 Envoyer le rapport", key="send_report_email_btn", type="primary",
                 use_container_width=True):
        if not to or "@" not in to:
            st.error("❌ Adresse email invalide.")
            return

        tmp_path = None
        attachments = None
        try:
            if attach_docx and docx_bytes:
                import tempfile
                tmp_path = Path(tempfile.mkdtemp()) / _get_report_filename(inspection_id, "docx")
                tmp_path.write_bytes(docx_bytes)
                attachments = [str(tmp_path)]

            with st.spinner("Envoi en cours..."):
                r = email_service.send_email(
                    to=to,
                    subject=f"📊 Rapport d'inspection {inspection_id} — {site_name}",
                    html_body=html_doc,
                    attachments=attachments,
                )
        finally:
            if tmp_path is not None:
                try:
                    tmp_path.unlink()
                    tmp_path.parent.rmdir()
                except OSError:
                    pass

        if r["ok"]:
            st.success(f"✅ Rapport envoyé à **{to}** via **{r['provider']}**")
        else:
            st.error(f"❌ Échec : {r['error']}")


def render_report_page(db, inspection_id: str, site_name: str = "—"):
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

    items_data, stats_summary = _collect_report_data(db, inspection_id)

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

    m1, m2, m3 = st.columns(3)
    inspector = m1.text_input("Inspecteur / المفتِّش / Inspector", key="report_inspector")
    reviewer = m2.text_input("Vérificateur / المراجع / Reviewer", key="report_reviewer")
    version = m3.text_input("Version", value="1.0", key="report_version")

    st.markdown("---")
    tpl_mode = st.radio(
        t("step4.tpl_mode"), ["default", "company"],
        format_func=lambda m: t(f"step4.tpl_mode_{m}"),
        horizontal=True, key="report_tpl_mode")
    template_info = _render_template_picker() if tpl_mode == "company" else None

    if items_data:
        st.caption(t("step4.top_n_note", n=len(items_data)))

    custom_instructions = st.text_area(
        t("step4.custom_instructions"),
        key="report_custom_instructions",
        placeholder=t("step4.custom_instructions_placeholder"),
        height=80,
    )

    use_company = tpl_mode == "company"
    if st.button(t("step4.generate_button"), type="primary", key="generate_report_btn",
                 disabled=(use_company and template_info is None)):
        with st.spinner(t("step4.generating", model=status["model"])):
            company_profile_text = build_company_profile_text(
                st.session_state.get("company_profile_data", {})
            )
            if use_company:
                ai_result = ai_service.generer_rapport_modele(
                    inspection_id=inspection_id,
                    site_name=site_name,
                    items=items_data,
                    stats_summary=stats_summary,
                    template_outline=template_info["outline"],
                    langue=report_language,
                    custom_instructions=custom_instructions,
                    company_profile=company_profile_text,
                    sections_summary=_collect_sections(db, inspection_id),
                )
            else:
                ai_result = ai_service.generer_rapport(
                    inspection_id=inspection_id,
                    site_name=site_name,
                    nc_pc_items=items_data,
                    stats_summary=stats_summary,
                    langue=report_language,
                    custom_instructions=custom_instructions,
                    company_profile=company_profile_text,
                    sections_summary=_collect_sections(db, inspection_id),
                )

        if ai_result.get("erreur"):
            result = {
                "success": False,
                "report": "",
                "error": t("step4.error_api", error=ai_result["erreur"], _lang=report_language),
            }
        else:
            meta = {
                "site": site_name, "inspection_id": inspection_id,
                "inspector": inspector, "reviewer": reviewer, "version": version,
                "date": datetime.now().strftime("%d/%m/%Y"),
            }
            if use_company:
                result = {
                    "success": True, "mode": "company", "meta": meta,
                    "report": report_template.normalize_report(
                        ai_result["data"], items_data, report_language),
                    # le .docx du modèle sert de base de mise en page à l'export Word
                    "template_bytes": template_info["data"] if template_info["ext"] == ".docx" else None,
                }
            else:
                result = {"success": True, "mode": "default", "data": ai_result["data"], "meta": meta}

        st.session_state["last_report_result"] = result
        st.session_state["last_report_language"] = report_language

    # ---- Affichage du dernier résultat (survit au rerun du bouton téléchargement) ----
    result = st.session_state.get("last_report_result")
    if not result:
        _render_email_section(inspection_id, site_name)
        return

    if not result["success"]:
        # result["error"] est déjà traduit dans la langue du RAPPORT choisie
        # (pas forcément celle de l'interface) : c'est voulu, l'utilisateur
        # vient de la sélectionner explicitement.
        st.error(result["error"])
        return

    st.success(t("step4.generated_ok"))
    st.markdown("---")

    # Les chiffres sont relus en BD à chaque affichage (jamais ceux du LLM).
    lang = st.session_state.get("last_report_language", "fr")

    if result.get("mode") == "company":
        sections = _collect_sections(db, inspection_id)
        html_doc = report_template.render_custom_report_html(
            result["report"], items_data, stats_summary, sections, result["meta"], lang=lang)
        components.html(html_doc, height=900, scrolling=True)
        d1, d2 = st.columns(2)
        docx_bytes = None
        try:
            docx_bytes = report_template.build_docx(
                result["report"], items_data, stats_summary, sections, result["meta"],
                lang=lang, template_bytes=result.get("template_bytes"))
            d1.download_button(
                t("step4.download_docx"), docx_bytes,
                _get_report_filename(inspection_id, "docx"), report_template.DOCX_MIME,
                key="dl_report_docx")
        except Exception as e:  # ne jamais perdre l'aperçu HTML à cause de l'export Word
            d1.error(t("step4.docx_error", error=str(e)))
        d2.download_button(
            t("step4.download_html"), html_doc.encode("utf-8"),
            _get_report_filename(inspection_id), "text/html", key="dl_report_html")
        _render_email_section(inspection_id, site_name, html_doc, docx_bytes)
        st.caption(t("step4.disclaimer"))
        return

    html_doc = render_report_html(
        result["data"], items_data, stats_summary, _collect_sections(db, inspection_id),
        result["meta"], lang=lang)
    components.html(html_doc, height=900, scrolling=True)

    st.download_button(
        t("step4.download_button"),
        html_doc.encode("utf-8"),
        _get_report_filename(inspection_id),
        "text/html",
        help="Ouvrir le fichier puis Ctrl+P → « Enregistrer au format PDF » (A4, mise en page officielle).",
    )
    _render_email_section(inspection_id, site_name, html_doc)
    st.caption(t("step4.disclaimer"))
