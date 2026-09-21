"""
ai/data_collector.py — HSE PYXIS
==================================
Collecte toutes les données d'audit depuis la base SQLite
pour les transmettre au générateur de rapport IA.

Principe i18n (identique au reste de l'application)
---------------------------------------------------
Les valeurs stockées en base restent des CODES ("NC", "CB_RECOMMENDED",
"manuelle", "Estimated"...). Elles sont traduites UNIQUEMENT au moment de
construire le texte envoyé au LLM, dans la langue du rapport demandé.

Sans cela, le modèle recevrait « CB_RECOMMENDED » et le recopierait tel quel
dans le rapport final.

Usage:
    from ai.data_collector import collect_audit_data, format_for_prompt
    data = collect_audit_data(db, audit_id, site_name)
    texte = format_for_prompt(data, language="ar")
"""

from typing import Any

from audit_db import pick_translation


# ============================================================
# TRADUCTION TOLÉRANTE (utilisable hors Streamlit)
# ============================================================
# Ce module doit pouvoir tourner en ligne de commande, sans Streamlit.
# Si l'import échoue, on retombe sur les valeurs brutes plutôt que de planter.
try:
    from ui.i18n import t_in as _t_in
    from ui.display import (
        tr_conformite as _tr_conformite,
        tr_industry as _tr_industry,
        tr_lira as _tr_lira,
        tr_matrix_label as _tr_matrix_label,
        tr_meteo as _tr_meteo,
        tr_method as _tr_method,
        tr_reco as _tr_reco,
    )
    from human_risk_indicators import niveau_lira as _niveau_lira
    I18N_AVAILABLE = True
except Exception:  # pragma: no cover — mode dégradé (CLI, tests isolés)
    I18N_AVAILABLE = False

    def _t_in(lang, key, **kwargs):
        return key.split(".")[-1].replace("_", " ").capitalize()

    def _identity(value, lang=None):
        return "" if value is None else str(value)

    _tr_conformite = _tr_industry = _tr_lira = _identity
    _tr_matrix_label = _tr_meteo = _tr_method = _tr_reco = _identity

    def _niveau_lira(_lira):
        return ""


def _L(lang: str, key: str, **kwargs) -> str:
    """Libellé de section du prompt, dans la langue du rapport."""
    return _t_in(lang, f"ai.data.{key}", **kwargs)


def _section(item: dict, lang: str) -> str:
    """Section dans la langue du rapport (repli : anglais -> français -> arabe)."""
    return pick_translation(
        lang,
        item.get("section_name"),
        item.get("section_name_fr"),
        item.get("section_name_ar"),
    )


def _equipment(item: dict, lang: str) -> str:
    """Type d'équipement dans la langue du rapport."""
    return pick_translation(
        lang,
        item.get("equipement"),
        item.get("equipement_fr"),
        item.get("equipement_ar"),
    )


def _method(item: dict, lang: str) -> str:
    """Méthode de fréquence dans la langue du rapport.

    FR / AR : traduction de l'Excel si présente ; sinon libellés des locales.
    """
    translated = item.get(f"method_{lang}") if lang in ("fr", "ar") else ""
    if translated and str(translated).strip():
        return str(translated).strip()
    return _tr_method(item.get("method"), lang=lang)


def _symptom(item: dict, lang: str) -> str:
    """Symptôme dans la langue du rapport (repli : anglais -> français -> arabe)."""
    return pick_translation(
        lang,
        item.get("symptome"),
        item.get("symptome_fr"),
        item.get("symptome_ar"),
    )


# ============================================================
# COLLECTE PRINCIPALE
# ============================================================
def collect_audit_data(db, audit_id: str, site_name: str) -> dict:
    """
    Collecte toutes les données d'un audit depuis la DB.

    Args:
        db         : instance AuditDB
        audit_id   : ID de l'audit (ex: "AUDIT-2025-001")
        site_name  : nom du site / matrice

    Returns:
        dict avec toutes les données structurées pour le LLM.
        Les valeurs restent des CODES : la traduction a lieu dans
        format_for_prompt().
    """
    data: dict[str, Any] = {
        "audit_id": audit_id,
        "site_name": site_name,
        "conformites": {},
        "mc_results": [],
        "human_risk": [],
        "cost_benefit": [],
        "dispersion": [],
        "checklist_items": {},
        "summary": {},
        # Erreurs non bloquantes (section + message), pour affichage éventuel.
        "errors": [],
    }

    def _fail(section: str, exc: Exception):
        data["errors"].append({"section": section, "error": str(exc)})
        print(f"⚠️ [{section}] {exc}")

    # ---- 1. CONFORMITÉS (C / NC / PC) ----
    try:
        conformites = db.get_conformity_by_audit(audit_id)
        data["conformites"] = conformites or {}
    except Exception as e:
        _fail("conformites", e)

    # ---- 2. CHECKLIST (référentiel des symptômes) ----
    try:
        items = db.get_checklist_items()
        for it in items:
            # it = (id, section, equipement, symptome, severity, frequency,
            #       method, source, evidence, target_human, target_env, target_asset,
            #       symptome_fr, symptome_ar, section_name_fr, section_name_ar,
            #       equipement_fr, equipement_ar, method_fr, method_ar,
            #       hazard_class, hazard_class_fr, hazard_class_ar,
            #       evidence_fr, evidence_ar,
            #       technical_reference, technical_reference_fr, technical_reference_ar)
            data["checklist_items"][it[0]] = {
                "id": it[0],
                "section_name": it[1],
                "equipement": it[2],
                "symptome": it[3],
                "symptome_fr": it[12] if len(it) > 12 else "",
                "symptome_ar": it[13] if len(it) > 13 else "",
                "section_name_fr": it[14] if len(it) > 14 else "",
                "section_name_ar": it[15] if len(it) > 15 else "",
                "equipement_fr": it[16] if len(it) > 16 else "",
                "equipement_ar": it[17] if len(it) > 17 else "",
                "method_fr": it[18] if len(it) > 18 else "",
                "method_ar": it[19] if len(it) > 19 else "",
                "hazard_class": it[20] if len(it) > 20 else "",
                "hazard_class_fr": it[21] if len(it) > 21 else "",
                "hazard_class_ar": it[22] if len(it) > 22 else "",
                "evidence_fr": it[23] if len(it) > 23 else "",
                "evidence_ar": it[24] if len(it) > 24 else "",
                "technical_reference": it[25] if len(it) > 25 else "",
                "technical_reference_fr": it[26] if len(it) > 26 else "",
                "technical_reference_ar": it[27] if len(it) > 27 else "",
                "severity": it[4],
                "frequency": it[5],
                "method": it[6],
                "source": it[7],
                "evidence_required": it[8],
                "target_human": bool(it[9]),
                "target_env": bool(it[10]),
                "target_asset": bool(it[11]),
            }
    except Exception as e:
        _fail("checklist", e)

    # ---- 3. RÉSULTATS MONTE CARLO ----
    try:
        mc_rows = db.get_mc_results(audit_id)
        for r in mc_rows:
            # r = (id, audit_id, item_id, n_iter, freq_min, freq_mode, freq_max,
            #      freq_moyenne, freq_p05, freq_p50, freq_p95, severite,
            #      score_risque, niveau_sev, niveau_prob, niveau_risque,
            #      couleur, created_at)
            data["mc_results"].append({
                "item_id": r[2],
                "n_iterations": r[3],
                "freq_min": r[4],
                "freq_mode": r[5],
                "freq_max": r[6],
                "freq_moyenne": r[7],
                "freq_p05": r[8],
                "freq_p50": r[9],
                "freq_p95": r[10],
                "severite": r[11],
                "score_risque": r[12],
                "niveau_severite": r[13],
                "niveau_probabilite": r[14],
                "niveau_risque": r[15],
                "couleur": r[16],
            })
    except Exception as e:
        _fail("monte_carlo", e)

    # ---- 4. RISQUE HUMAIN (PLL / FAR / LIRA) ----
    try:
        hr_rows = db.get_human_risk(audit_id)
        for r in hr_rows:
            # r = (id, audit_id, item_id, freq_par_an, nb_pers, duree_expo,
            #      proba_deces, proba_defaut, pll, far, lira, created_at)
            data["human_risk"].append({
                "item_id": r[2],
                "frequence_par_an": r[3],
                "nb_personnes_exposees": r[4],
                "duree_exposition_h_an": r[5],
                "proba_deces": r[6],
                "proba_deces_est_defaut": bool(r[7]),
                "pll": r[8],
                "far": r[9],
                "lira": r[10],
                # Code stable, traduit dans le prompt / à l'affichage
                "niveau_lira": _niveau_lira(r[10]) if r[10] is not None else "",
            })
    except Exception as e:
        _fail("human_risk", e)

    # ---- 5. COÛT-BÉNÉFICE ----
    try:
        cb_rows = db.get_cost_benefit(audit_id)
        for r in cb_rows:
            # r = (id, audit_id, item_id, currency, industry, freq_par_an,
            #      cout_action, cout_perte, duree_indispo, cout_indispo_jour,
            #      perte_annuelle, ratio, recommandation, created_at)
            data["cost_benefit"].append({
                "item_id": r[2],
                "currency": r[3],
                "industry": r[4],
                "frequence_par_an": r[5],
                "cout_action_corrective": r[6],
                "cout_perte_potentielle": r[7],
                "duree_indisponibilite_j": r[8],
                "cout_indisponibilite_par_jour": r[9],
                "perte_annuelle_attendue": r[10],
                "ratio_benefice_cout": r[11],
                # ⚠️ CODE ("CB_RECOMMENDED"...) produit par cost_benefit.py
                "recommandation": r[12],
            })
    except Exception as e:
        _fail("cost_benefit", e)

    # ---- 6. DISPERSION ----
    try:
        disp_rows = db.get_dispersion(audit_id)
        for r in disp_rows:
            # r = (id, audit_id, item_id, substance, taille_fuite, duree_fuite,
            #      vitesse_vent, direction_vent, temperature, pression, humidite,
            #      latitude, longitude, classe_stab, distance_impact,
            #      source_meteo, created_at)
            data["dispersion"].append({
                "item_id": r[2],
                "substance": r[3],
                "taille_fuite_kg": r[4],
                "duree_fuite_s": r[5],
                "vitesse_vent_ms": r[6],
                "direction_vent_deg": r[7],
                "temperature_c": r[8],
                "classe_stabilite": r[13],
                "distance_impact_m": r[14],
                "source_meteo": r[15],
            })
    except Exception as e:
        _fail("dispersion", e)

    # ---- 7. CALCUL DU RÉSUMÉ ----
    data["summary"] = _build_summary(data)

    return data


# ============================================================
# RÉSUMÉ
# ============================================================
def _build_summary(data: dict) -> dict:
    """Calcule un résumé statistique pour le prompt."""

    conformites = data.get("conformites", {})
    total_audited = len(conformites)
    n_nc = sum(1 for v in conformites.values() if v == "NC")
    n_pc = sum(1 for v in conformites.values() if v == "PC")
    n_c = sum(1 for v in conformites.values() if v == "C")

    mc = data.get("mc_results", [])
    top3 = sorted(mc, key=lambda x: x.get("score_risque", 0) or 0, reverse=True)[:3]

    hr = data.get("human_risk", [])
    top_hr = sorted(hr, key=lambda x: x.get("pll", 0) or 0, reverse=True)[:3]

    return {
        "total_audited": total_audited,
        "n_nc": n_nc,
        "n_pc": n_pc,
        "n_c": n_c,
        "n_analyzed": len(mc),
        "n_human": len(hr),
        "n_cost_benefit": len(data.get("cost_benefit", [])),
        "n_dispersion": len(data.get("dispersion", [])),
        "top3_risks": top3,
        "top3_human": top_hr,
    }


# ============================================================
# FORMATAGE POUR LE PROMPT
# ============================================================
def format_for_prompt(data: dict, language: str = "fr") -> str:
    """
    Transforme les données collectées en texte structuré à insérer dans le
    prompt du LLM, dans la langue du RAPPORT.

    Args:
        data     : dict issu de collect_audit_data()
        language : "fr" | "ar" | "en" — langue du rapport demandé
    """
    lang = language if language in ("fr", "ar", "en") else "fr"

    s = data["summary"]
    checklist = data["checklist_items"]
    conformites = data["conformites"]
    mc = data["mc_results"]
    hr = data["human_risk"]
    cb = data["cost_benefit"]
    disp = data["dispersion"]

    sep = "=" * 60
    lines = []

    # ---- En-tête ----
    lines.append(f"{_L(lang, 'audit_id')} : {data['audit_id']}")
    lines.append(f"{_L(lang, 'site')} : {data['site_name']}")
    lines.append("")
    lines.append(sep)
    lines.append(_L(lang, "summary_title"))
    lines.append(sep)
    lines.append(f"- {_L(lang, 'audited_symptoms')} : {s['total_audited']}")
    lines.append(f"  - {_L(lang, 'compliant')} (C) : {s['n_c']}")
    lines.append(f"  - {_L(lang, 'partial')} (PC) : {s['n_pc']}")
    lines.append(f"  - {_L(lang, 'non_compliant')} (NC) : {s['n_nc']}")
    lines.append(f"- {_L(lang, 'mc_analyses')} : {s['n_analyzed']}")
    lines.append(f"- {_L(lang, 'human_analyses')} : {s['n_human']}")
    lines.append(f"- {_L(lang, 'cb_analyses')} : {s['n_cost_benefit']}")
    lines.append(f"- {_L(lang, 'disp_analyses')} : {s['n_dispersion']}")
    lines.append("")

    # ---- Écarts de conformité ----
    if s["n_nc"] > 0 or s["n_pc"] > 0:
        lines.append(sep)
        lines.append(_L(lang, "gaps_title"))
        lines.append(sep)
        for item_id, conf in conformites.items():
            if conf in ("NC", "PC"):
                it = checklist.get(item_id, {})
                lines.append(f"[{conf}] {item_id} — {_section(it, lang)}")
                lines.append(f"     {_L(lang, 'status')} : {_tr_conformite(conf, lang=lang)}")
                lines.append(f"     {_L(lang, 'equipment')} : {_equipment(it, lang)}")
                lines.append(f"     {_L(lang, 'symptom')} : {_symptom(it, lang)[:200]}")
                lines.append(f"     {_L(lang, 'severity')} : {it.get('severity', '')}")
                lines.append("")

    # ---- Monte Carlo ----
    if mc:
        lines.append(sep)
        lines.append(_L(lang, "mc_title"))
        lines.append(sep)
        for r in sorted(mc, key=lambda x: x.get("score_risque", 0) or 0, reverse=True):
            it = checklist.get(r["item_id"], {})
            method = _method(it, lang)
            niveau = _tr_matrix_label(r.get("niveau_risque"), lang=lang)
            year = _L(lang, "year")
            lines.append(f"• {r['item_id']} — {_symptom(it, lang)[:100]}")
            lines.append(f"   {_L(lang, 'freq_mean')} : {r['freq_moyenne']:.3e} /{year}")
            lines.append(f"   P05 : {r['freq_p05']:.3e} | P50 : {r['freq_p50']:.3e} | P95 : {r['freq_p95']:.3e}")
            lines.append(f"   {_L(lang, 'severity')} : {r['severite']} | {_L(lang, 'score')} : {r['score_risque']:.2f}")
            lines.append(f"   {_L(lang, 'matrix_level')} : {niveau}")
            if method:
                lines.append(f"   {_L(lang, 'method')} : {method}")
            lines.append("")

    # ---- Risque humain ----
    if hr:
        lines.append(sep)
        lines.append(_L(lang, "human_title"))
        lines.append(sep)
        for r in sorted(hr, key=lambda x: x.get("pll", 0) or 0, reverse=True):
            year = _L(lang, "year")
            lines.append(f"• {r['item_id']}")
            lines.append(f"   PLL  : {r['pll']:.3e} {_L(lang, 'losses_per_year')}")
            lines.append(f"   FAR  : {r['far']:.3f} {_L(lang, 'deaths_per_1e8h')}")
            lines.append(f"   LIRA : {r['lira']:.3e} /{year}")
            if r.get("niveau_lira"):
                lines.append(f"   {_L(lang, 'lira_level')} : {_tr_lira(r['niveau_lira'], lang=lang)}")
            lines.append(f"   {_L(lang, 'exposed_people')} : {r['nb_personnes_exposees']}")
            lines.append(f"   {_L(lang, 'exposure_duration')} : {r['duree_exposition_h_an']:.0f} h/{year}")
            lines.append(
                f"   {_L(lang, 'p_death')} : {r['proba_deces']:.2f}"
                + (f" ({_L(lang, 'default_value')})" if r["proba_deces_est_defaut"] else "")
            )
            lines.append("")

    # ---- Coût-bénéfice ----
    if cb:
        lines.append(sep)
        lines.append(_L(lang, "cb_title"))
        lines.append(sep)
        for r in sorted(cb, key=lambda x: x.get("ratio_benefice_cout", 0) or 0, reverse=True):
            # ⚠️ Traduction du CODE de recommandation : sans cela le LLM
            # recopierait « CB_RECOMMENDED » tel quel dans le rapport.
            reco = _tr_reco(r["recommandation"], lang=lang)
            secteur = _tr_industry(r.get("industry"), lang=lang)
            lines.append(f"• {r['item_id']} — {_L(lang, 'currency')} : {r['currency']}")
            if secteur:
                lines.append(f"   {_L(lang, 'industry')} : {secteur}")
            lines.append(f"   {_L(lang, 'action_cost')} : {r['cout_action_corrective']:,.0f} {r['currency']}")
            lines.append(f"   {_L(lang, 'loss_avoided')} : {r['perte_annuelle_attendue']:,.0f} {r['currency']}")
            lines.append(f"   {_L(lang, 'ratio')} : {r['ratio_benefice_cout']:.2f}")
            lines.append(f"   {_L(lang, 'recommendation')} : {reco}")
            lines.append("")

    # ---- Dispersion ----
    if disp:
        lines.append(sep)
        lines.append(_L(lang, "disp_title"))
        lines.append(sep)
        for r in disp:
            source = _tr_meteo(r.get("source_meteo"), lang=lang)
            lines.append(f"• {r['item_id']} — {_L(lang, 'substance')} : {r['substance']}")
            lines.append(f"   {_L(lang, 'leak_size')} : {r['taille_fuite_kg']} kg")
            lines.append(f"   {_L(lang, 'leak_duration')} : {r['duree_fuite_s']} s")
            lines.append(f"   {_L(lang, 'wind')} : {r['vitesse_vent_ms']} m/s, {r['direction_vent_deg']}°")
            lines.append(f"   {_L(lang, 'stability_class')} : {r['classe_stabilite']}")
            lines.append(f"   {_L(lang, 'impact_distance')} : {r['distance_impact_m']:.0f} m")
            if source:
                lines.append(f"   {_L(lang, 'weather_source')} : {source}")
            lines.append("")

    return "\n".join(lines)


# ============================================================
# TEST RAPIDE
# ============================================================
if __name__ == "__main__":
    from audit_db import AuditDB

    db = AuditDB()
    print("i18n disponible :", I18N_AVAILABLE)
    data = collect_audit_data(db, "AUDIT-2025-001", "Site Test")
    print("Résumé :", data["summary"])
    print()
    print(format_for_prompt(data, language="fr")[:800])
