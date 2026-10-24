"""
report_render.py — Rendu HTML professionnel (HSE PYXIS)
=======================================================
Transforme les données STRUCTURÉES (JSON produit par ai_service) en :
  * un rapport d'inspection au format "corporate" (couverture, contrôle du
    document, sommaire, sections numérotées, signatures, pied de page) ;
  * un plan PDCA visuel (cycle circulaire, cartes colorées, frise,
    tableaux, étiquettes de priorité) pensé pour donner envie de lire.

Principe garde-fou : TOUS les chiffres (taux de conformité, NC/PC/C,
sévérité, fréquence, classe de risque) viennent de la base de données,
jamais du LLM. Le LLM ne fournit que le texte qualitatif.

Sortie : une page HTML autonome (CSS inline, logo en base64) :
  - affichable dans Streamlit via components.html ;
  - téléchargeable ; Ctrl+P -> « Enregistrer en PDF » donne un A4 propre.
Langues : fr / en / ar (RTL automatique).

v3 — Compléments :
  • render_report_html() — complétée (s4, s5, s6)
  • render_pdca_html()  — implémentée (cycle SVG + tableaux)
  • build_pdf_bytes()   — pont vers pdf_renderer.render_pdf_report
  • render_pdf()        — alias court (compat. historique)
"""

from __future__ import annotations

import base64
import html as _html
import io
import math
import re
from datetime import datetime
from pathlib import Path

_ASSETS = Path(__file__).parent / "assets"

# ------------------------------------------------------------------
# Libellés (indépendants de l'interface : suivent la langue du document)
# ------------------------------------------------------------------
_L = {
    "fr": {
        "dir": "ltr", "rapport": "RAPPORT D'INSPECTION HSE", "sous_titre": "Santé · Sécurité · Environnement",
        "confidentiel": "DOCUMENT CONFIDENTIEL", "site": "Site inspecté", "inspection_id": "Référence d'inspection",
        "date": "Date d'émission", "inspecteur": "Inspecteur", "verificateur": "Vérificateur / Approbateur",
        "version": "Version", "referentiel": "Référentiel", "distribution": "Diffusion",
        "distribution_val": "Direction · Responsable HSE", "a_completer": "[À compléter]",
        "controle": "Contrôle du document", "sommaire": "Sommaire",
        "s1": "Synthèse exécutive", "s2": "Analyse quantitative", "s3": "Risques prioritaires",
        "s4": "Analyse par domaine", "s5": "Recommandations stratégiques", "s6": "Conclusion et prochaines étapes",
        "niveau_global": "Niveau de risque global", "points_cles": "Points clés",
        "total": "Points inspectés", "conf_rate": "Taux de conformité", "nc": "Non conformes",
        "pc": "Partiellement conformes", "c": "Conformes", "repartition": "Répartition de la conformité",
        "rang": "Rang", "ref": "Réf.", "domaine": "Domaine / Équipement", "ecart": "Écart constaté",
        "sev": "Sév.", "freq": "Fréq. /an", "classe": "Classe", "pourquoi": "Pourquoi critique",
        "impact": "Impact potentiel", "priorite": "Priorité", "horizon": "Échéance", "cout": "Coût",
        "action": "Action recommandée", "resp": "Pilote suggéré", "prochaines": "Prochaines étapes",
        "signatures": "Validation", "signature": "Signature", "nom_date": "Nom / Date",
        "high": "Élevée", "medium": "Moyenne", "low": "Faible", "critical": "Critique",
        "immediate": "Immédiat", "short": "Court terme", "mid": "Moyen terme",
        "gen_note": "Rapport généré avec assistance IA — les valeurs chiffrées proviennent du calcul Monte Carlo ; à valider par l'inspecteur.",
        "page": "Page", "print": "Imprimer / PDF", "domaine_nc": "NC", "domaine_pc": "PC",
        "cout0": "Coût zéro", "cout1": "Coût faible", "cout2": "Coût moyen", "cout3": "Coût élevé",
        # PDCA
        "pdca": "PLAN D'ACTION PDCA", "pdca_sub": "Amélioration continue — Roue de Deming", "reference": "Référence",
        "P": "Planifier", "D": "Déployer", "C": "Vérifier", "A": "Ajuster",
        "objectif": "Objectif", "actions": "Plan d'actions", "suivi": "Suivi", "quand": "Échéance", "qui": "Responsable",
        "cout_col": "Niveau de coût", "total_cout": "Total estimé", "verif": "Vérification", "cible": "Cible",
        "severite": "Sévérité", "conformite": "Conformité", "frequence_mc": "Fréquence", "classe_risque": "Classe de risque",
        "cycle": "Cycle d'amélioration",
    },
    "en": {
        "dir": "ltr", "rapport": "HSE INSPECTION REPORT", "sous_titre": "Health · Safety · Environment",
        "confidentiel": "CONFIDENTIAL DOCUMENT", "site": "Inspected site", "inspection_id": "Inspection reference",
        "date": "Issue date", "inspecteur": "Inspector", "verificateur": "Reviewer / Approver",
        "version": "Version", "referentiel": "Reference standard", "distribution": "Distribution",
        "distribution_val": "Management · HSE Manager", "a_completer": "[To be completed]",
        "controle": "Document control", "sommaire": "Table of contents",
        "s1": "Executive summary", "s2": "Quantitative analysis", "s3": "Priority risks",
        "s4": "Analysis by area", "s5": "Strategic recommendations", "s6": "Conclusion and next steps",
        "niveau_global": "Overall risk level", "points_cles": "Key points",
        "total": "Items inspected", "conf_rate": "Compliance rate", "nc": "Non-compliant",
        "pc": "Partially compliant", "c": "Compliant", "repartition": "Compliance breakdown",
        "rang": "Rank", "ref": "Ref.", "domaine": "Area / Equipment", "ecart": "Finding",
        "sev": "Sev.", "freq": "Freq. /yr", "classe": "Class", "pourquoi": "Why critical",
        "impact": "Potential impact", "priorite": "Priority", "horizon": "Timeframe", "cout": "Cost",
        "action": "Recommended action", "resp": "Suggested owner", "prochaines": "Next steps",
        "signatures": "Approval", "signature": "Signature", "nom_date": "Name / Date",
        "high": "High", "medium": "Medium", "low": "Low", "critical": "Critical",
        "immediate": "Immediate", "short": "Short term", "mid": "Medium term",
        "gen_note": "Report generated with AI assistance — figures come from the Monte Carlo computation; to be validated by the inspector.",
        "page": "Page", "print": "Print / PDF", "domaine_nc": "NC", "domaine_pc": "PC",
        "cout0": "No cost", "cout1": "Low cost", "cout2": "Medium cost", "cout3": "High cost",
        "pdca": "PDCA ACTION PLAN", "pdca_sub": "Continuous improvement — Deming Wheel", "reference": "Reference",
        "P": "Plan", "D": "Do", "C": "Check", "A": "Act",
        "objectif": "Objective", "actions": "Action plan", "suivi": "Follow-up", "quand": "Deadline", "qui": "Owner",
        "cout_col": "Cost level", "total_cout": "Estimated total", "verif": "Verification", "cible": "Target",
        "severite": "Severity", "conformite": "Compliance", "frequence_mc": "Frequency", "classe_risque": "Risk class",
        "cycle": "Improvement cycle",
    },
    "ar": {
        "dir": "rtl", "rapport": "تقرير التفتيش في الصحة والسلامة والبيئة", "sous_titre": "الصحة · السلامة · البيئة",
        "confidentiel": "وثيقة سرية", "site": "الموقع المفتَّش", "inspection_id": "مرجع التفتيش",
        "date": "تاريخ الإصدار", "inspecteur": "المفتِّش", "verificateur": "المراجع / المعتمِد",
        "version": "الإصدار", "referentiel": "المرجع المعياري", "distribution": "التوزيع",
        "distribution_val": "الإدارة · مسؤول HSE", "a_completer": "[يُستكمل]",
        "controle": "مراقبة الوثيقة", "sommaire": "الفهرس",
        "s1": "الملخص التنفيذي", "s2": "التحليل الكمي", "s3": "المخاطر ذات الأولوية",
        "s4": "التحليل حسب المجال", "s5": "التوصيات الاستراتيجية", "s6": "الخلاصة والخطوات التالية",
        "niveau_global": "مستوى الخطر العام", "points_cles": "النقاط الرئيسية",
        "total": "النقاط المفتَّشة", "conf_rate": "نسبة المطابقة", "nc": "غير مطابق",
        "pc": "مطابق جزئياً", "c": "مطابق", "repartition": "توزيع المطابقة",
        "rang": "الترتيب", "ref": "المرجع", "domaine": "المجال / المعدات", "ecart": "الملاحظة",
        "sev": "الخطورة", "freq": "التكرار/سنة", "classe": "الفئة", "pourquoi": "سبب الأهمية",
        "impact": "الأثر المحتمل", "priorite": "الأولوية", "horizon": "المدة", "cout": "التكلفة",
        "action": "الإجراء الموصى به", "resp": "المسؤول المقترح", "prochaines": "الخطوات التالية",
        "signatures": "الاعتماد", "signature": "التوقيع", "nom_date": "الاسم / التاريخ",
        "high": "عالية", "medium": "متوسطة", "low": "منخفضة", "critical": "حرجة",
        "immediate": "فوري", "short": "قصير المدى", "mid": "متوسط المدى",
        "gen_note": "أُنشئ هذا التقرير بمساعدة الذكاء الاصطناعي — الأرقام مصدرها حساب مونت كارلو، ويجب أن يعتمدها المفتِّش.",
        "page": "صفحة", "print": "طباعة / PDF", "domaine_nc": "غ م", "domaine_pc": "م ج",
        "cout0": "بدون تكلفة", "cout1": "تكلفة منخفضة", "cout2": "تكلفة متوسطة", "cout3": "تكلفة مرتفعة",
        "pdca": "خطة عمل PDCA", "pdca_sub": "التحسين المستمر — عجلة ديمنغ", "reference": "المرجع",
        "P": "التخطيط", "D": "التنفيذ", "C": "التحقق", "A": "التصحيح",
        "objectif": "الهدف", "actions": "خطة الإجراءات", "suivi": "المتابعة", "quand": "الأجل", "qui": "المسؤول",
        "cout_col": "مستوى التكلفة", "total_cout": "المجموع التقديري", "verif": "التحقق", "cible": "المستهدف",
        "severite": "الخطورة", "conformite": "المطابقة", "frequence_mc": "التكرار", "classe_risque": "فئة الخطر",
        "cycle": "دورة التحسين",
    },
}

# Couleurs de la charte PYXIS
GREEN, BLUE, AMBER, RED, PURPLE = "#00A843", "#2979FF", "#F5A000", "#E53935", "#7C4DFF"
NAVY, INK, MUTED = "#0A1628", "#1B2A41", "#5B6B7F"
_PRIO_COL = {"critical": "#B71C1C", "high": RED, "medium": AMBER, "low": GREEN}


# ------------------------------------------------------------------
# Utilitaires
# ------------------------------------------------------------------
def _labels(lang: str) -> dict:
    return _L.get(lang, _L["fr"])


def _x(value) -> str:
    """Échappe le HTML ; convertit **gras** et retours à la ligne."""
    if value is None:
        return ""
    s = _html.escape(str(value).strip())
    s = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", s)
    return s.replace("\n", "<br>")


def _as_list(value) -> list:
    if not value:
        return []
    return value if isinstance(value, list) else [value]


def _logo_b64(max_px: int = 220) -> str:
    """Logo réduit en base64 (le PNG d'origine fait 1,2 Mo)."""
    path = _ASSETS / "logo.png"
    if not path.exists():
        return ""
    try:
        from PIL import Image
        im = Image.open(path).convert("RGBA")
        im.thumbnail((max_px, max_px))
        buf = io.BytesIO()
        im.save(buf, "PNG", optimize=True)
        return "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode()
    except Exception:
        return ""


def _pill(text: str, color: str) -> str:
    return (f'<span class="pill" style="background:{color}1A;color:{color};'
            f'border:1px solid {color}55">{_x(text)}</span>')


def _prio_pill(prio: str, L: dict) -> str:
    key = (prio or "medium").lower()
    key = key if key in _PRIO_COL else "medium"
    return _pill(L.get(key, key), _PRIO_COL[key])


def _cost_pill(level, L: dict, estimate: str = "") -> str:
    try:
        lvl = max(0, min(3, int(level)))
    except (TypeError, ValueError):
        lvl = 1
    colors = [GREEN, "#7CB342", AMBER, RED]
    txt = estimate.strip() if estimate and estimate.strip() else L[f"cout{lvl}"]
    return _pill(("● " * 0) + txt, colors[lvl])


def _horizon(h: str, L: dict) -> str:
    h = (h or "").lower()
    return L.get({"immediate": "immediate", "short": "short", "mid": "mid", "medium": "mid"}.get(h, ""), h or "—")


def _conf_color(code: str) -> str:
    return {"NC": RED, "PC": AMBER, "C": GREEN}.get(code, MUTED)


def _donut(n_c: int, n_pc: int, n_nc: int, rate: float, L: dict) -> str:
    total = max(n_c + n_pc + n_nc, 1)
    r, cx, cy, sw = 70, 90, 90, 26
    circ = 2 * math.pi * r
    parts, offset = [], 0.0
    for val, col in ((n_c, GREEN), (n_pc, AMBER), (n_nc, RED)):
        length = circ * val / total
        if length > 0:
            parts.append(
                f'<circle cx="{cx}" cy="{cy}" r="{r}" fill="none" stroke="{col}" stroke-width="{sw}" '
                f'stroke-dasharray="{length:.2f} {circ - length:.2f}" stroke-dashoffset="{-offset:.2f}" '
                f'transform="rotate(-90 {cx} {cy})"/>')
        offset += length
    return (f'<svg viewBox="0 0 180 180" class="donut"><circle cx="{cx}" cy="{cy}" r="{r}" fill="none" '
            f'stroke="#E8EEF5" stroke-width="{sw}"/>{"".join(parts)}'
            f'<text x="{cx}" y="{cy + 2}" text-anchor="middle" class="d-big">{rate:.0f}%</text>'
            f'<text x="{cx}" y="{cy + 22}" text-anchor="middle" class="d-small">{_x(L["conf_rate"])}</text></svg>')


def _page(body: str, title: str, lang: str, footer: str, extra_css: str = "") -> str:
    L = _labels(lang)
    rtl = L["dir"] == "rtl"
    return f"""<!DOCTYPE html>
<html lang="{lang}" dir="{L['dir']}"><head><meta charset="utf-8">
<title>{_x(title)}</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&family=Cairo:wght@400;600;700;800&display=swap" rel="stylesheet">
<style>
:root{{--navy:{NAVY};--ink:{INK};--muted:{MUTED};--green:{GREEN};--blue:{BLUE};--amber:{AMBER};--red:{RED};--purple:{PURPLE};--line:#E3E9F0;--bg:#F4F7FB}}
*{{box-sizing:border-box}}
body{{margin:0;background:#E9EEF4;color:var(--ink);font-family:{"'Cairo'," if rtl else "'Inter',"}'Segoe UI',Tahoma,Arial,sans-serif;font-size:14px;line-height:1.6}}
.sheet{{max-width:900px;margin:18px auto;background:#fff;box-shadow:0 4px 24px rgba(10,22,40,.12);border-radius:6px;overflow:hidden}}
.page{{padding:34px 44px}}
h2.sec{{margin:0 0 14px;font-size:19px;color:var(--navy);display:flex;align-items:center;gap:12px;padding-bottom:8px;border-bottom:2px solid var(--navy)}}
h2.sec .num{{background:var(--navy);color:#fff;border-radius:6px;min-width:30px;height:30px;display:inline-flex;align-items:center;justify-content:center;font-size:15px}}
h3{{font-size:14px;color:var(--navy);margin:18px 0 8px;text-transform:uppercase;letter-spacing:.04em}}
table{{width:100%;border-collapse:collapse;font-size:13px}}
th{{background:var(--navy);color:#fff;text-align:{"right" if rtl else "left"};padding:8px 10px;font-weight:600;font-size:12px}}
td{{padding:8px 10px;border-bottom:1px solid var(--line);vertical-align:top}}
tr:nth-child(even) td{{background:#F8FAFC}}
.pill{{display:inline-block;padding:2px 10px;border-radius:999px;font-size:11.5px;font-weight:700;white-space:nowrap}}
.badge{{display:inline-block;padding:3px 10px;border-radius:5px;color:#fff;font-weight:700;font-size:12px}}
.kpis{{display:grid;grid-template-columns:repeat(4,1fr);gap:12px;margin:6px 0 16px}}
.kpi{{border:1px solid var(--line);border-top:4px solid var(--c,var(--blue));border-radius:8px;padding:12px;text-align:center;background:#fff}}
.kpi b{{display:block;font-size:26px;color:var(--c,var(--navy));line-height:1.1}}
.kpi span{{font-size:11.5px;color:var(--muted)}}
.callout{{border-{"right" if rtl else "left"}:5px solid var(--c,var(--blue));background:var(--bg);padding:12px 16px;border-radius:6px;margin:10px 0}}
.muted{{color:var(--muted)}}
.toc a{{color:var(--ink);text-decoration:none}}
.toc li{{padding:7px 0;border-bottom:1px dotted #B8C4D0;font-size:15px}}
.toc ol{{list-style:none;padding:0;margin:0}}
.printbtn{{position:sticky;top:0;z-index:9;text-align:{"left" if rtl else "right"};padding:8px 14px;background:#E9EEF4}}
.printbtn button{{background:var(--navy);color:#fff;border:0;border-radius:6px;padding:7px 16px;font-weight:600;cursor:pointer}}
.foot{{padding:10px 44px;border-top:1px solid var(--line);font-size:11px;color:var(--muted);display:flex;justify-content:space-between;gap:10px}}
@page{{size:A4;margin:14mm 12mm 16mm;@bottom-center{{content:"{_x(L['page'])} " counter(page);font-size:9pt;color:#78909C}}}}}}
@media print{{body{{background:#fff}}.sheet{{box-shadow:none;margin:0;max-width:none;border-radius:0}}.printbtn{{display:none}}
 .brk{{break-before:page}}.nobreak{{break-inside:avoid}}*{{-webkit-print-color-adjust:exact;print-color-adjust:exact}}}}}}
{extra_css}
</style></head><body>
<div class="printbtn"><button onclick="window.print()">{_x(L['print'])}</button></div>
<div class="sheet">{body}<div class="foot"><span>{_x(footer)}</span><span>HSE PYXIS</span></div></div>
</body></html>"""


# ==================================================================
# 1. RAPPORT D'INSPECTION OFFICIEL
# ==================================================================
_REPORT_CSS = f"""
.cover{{background:linear-gradient(135deg,{NAVY} 0%,#12315C 60%,#0D5C63 100%);color:#fff;padding:46px 44px 38px;position:relative;min-height:330px}}
.cover .logo{{height:62px;background:#fff;border-radius:10px;padding:6px}}
.cover .tag{{display:block;width:max-content;margin-top:34px;border:1px solid #ffffff66;border-radius:999px;padding:3px 14px;font-size:11px;letter-spacing:.12em}}
.cover h1{{margin:12px 0 4px;font-size:34px;line-height:1.15;letter-spacing:.01em}}
.cover .sub{{color:#B8D4F0;font-size:15px}}
.cover .site{{margin-top:26px;font-size:22px;font-weight:700;border-top:3px solid {GREEN};padding-top:14px;display:inline-block}}
.cover .ref{{margin-top:6px;color:#B8D4F0;font-size:13px}}
.ctl td:first-child{{width:32%;font-weight:700;background:#EEF3F8;color:var(--navy)}}
.sum-grid{{display:grid;grid-template-columns:190px 1fr;gap:18px;align-items:center}}
.gauge{{border-radius:12px;color:#fff;padding:18px 12px;text-align:center}}
.gauge small{{display:block;opacity:.9;font-size:11.5px;text-transform:uppercase;letter-spacing:.06em}}
.gauge b{{font-size:26px}}
.msgs{{display:grid;grid-template-columns:repeat(3,1fr);gap:10px;margin-top:14px}}
.msg{{background:var(--bg);border-radius:8px;padding:11px 12px;font-size:13px;border-top:3px solid var(--blue)}}
.quant{{display:grid;grid-template-columns:200px 1fr;gap:16px;align-items:center}}
.donut{{width:190px;height:190px}} .d-big{{font-size:30px;font-weight:800;fill:{NAVY}}} .d-small{{font-size:9px;fill:{MUTED}}}
.legend{{display:flex;gap:16px;flex-wrap:wrap;margin-top:8px;font-size:12px}}
.legend i{{display:inline-block;width:11px;height:11px;border-radius:3px;margin-inline-end:5px;vertical-align:-1px}}
.stack{{display:flex;height:13px;border-radius:7px;overflow:hidden;background:#E8EEF5;min-width:120px}}
.dom{{display:grid;grid-template-columns:1fr 1fr;gap:12px}}
.dcard{{border:1px solid var(--line);border-radius:8px;padding:12px 14px;break-inside:avoid}}
.dcard h4{{margin:0 0 6px;font-size:13.5px;color:var(--navy)}}
.rank{{display:inline-flex;width:24px;height:24px;border-radius:50%;background:var(--navy);color:#fff;align-items:center;justify-content:center;font-weight:700;font-size:12px}}
.sign{{display:grid;grid-template-columns:repeat(3,1fr);gap:14px;margin-top:14px}}
.sign div{{border:1px solid var(--line);border-radius:8px;padding:10px 12px;height:110px;font-size:12px}}
.sign b{{display:block;color:var(--navy);margin-bottom:4px}}
@media(max-width:700px){{.sum-grid,.quant,.dom{{grid-template-columns:1fr}}.kpis{{grid-template-columns:repeat(2,1fr)}}.msgs,.sign{{grid-template-columns:1fr}}}}}}
"""


def render_report_html(data: dict, items: list, stats: dict, sections: list,
                       meta: dict, lang: str = "fr") -> str:
    """
    data     : JSON structuré du LLM (textes uniquement)
    items    : top risques issus de la BD (item_id, section, equipement, symptome,
               severity, conformite, freq_moyenne, risk_class, couleur)
    stats    : {total_items, n_nc, n_pc, n_c}
    sections : [{"section": str, "nc": int, "pc": int, "c": int}] (depuis la BD)
    meta     : {site, inspection_id, inspector, reviewer, date, version}
    """
    L = _labels(lang)
    data = data or {}
    site = meta.get("site", "—")
    inspection_id = meta.get("inspection_id", "—")
    date = meta.get("date") or datetime.now().strftime("%d/%m/%Y")
    tbc = L["a_completer"]
    total = stats.get("total_items", 0)
    n_nc, n_pc, n_c = stats.get("n_nc", 0), stats.get("n_pc", 0), stats.get("n_c", 0)
    rate = (100.0 * n_c / total) if total else 0.0
    logo = _logo_b64()
    ref_code = f"HSE-RAP-{re.sub(r'[^A-Za-z0-9]+', '-', str(inspection_id)).strip('-')[:24]}"

    # ---------- Couverture ----------
    cover = f"""<div class="cover">
      {f'<img class="logo" src="{logo}" alt="logo">' if logo else ''}
      <div class="tag">{_x(L['confidentiel'])}</div>
      <h1>{_x(L['rapport'])}</h1><div class="sub">{_x(L['sous_titre'])}</div>
      <div class="site">{_x(site)}</div>
      <div class="ref">{_x(ref_code)} · {_x(date)}</div></div>"""

    # ---------- Contrôle du document + sommaire ----------
    ctl_rows = [
        (L["site"], site), (L["inspection_id"], inspection_id), (L["date"], date),
        (L["inspecteur"], meta.get("inspector") or tbc), (L["verificateur"], meta.get("reviewer") or tbc),
        (L["version"], meta.get("version") or "1.0"), (L["referentiel"], "ISO 45001 · ISO 14001"),
        (L["distribution"], L["distribution_val"]),
    ]
    ctl = "".join(f"<tr><td>{_x(k)}</td><td>{_x(v)}</td></tr>" for k, v in ctl_rows)
    toc_items = "".join(f'<li><a href="#s{i}">{i}. {_x(L[f"s{i}"])}</a></li>' for i in range(1, 7))
    front = f"""<div class="page"><h2 class="sec"><span class="num">i</span>{_x(L['controle'])}</h2>
      <table class="ctl">{ctl}</table>
      <h3 style="margin-top:26px">{_x(L['sommaire'])}</h3><div class="toc"><ol>{toc_items}</ol></div></div>"""

    # ---------- 1. Synthèse exécutive ----------
    lvl = (data.get("overall_risk_level") or "medium").lower()
    lvl = lvl if lvl in _PRIO_COL else "medium"
    msgs = "".join(
        f'<div class="msg" style="border-top-color:{[RED, AMBER, BLUE][i % 3]}">{_x(m)}</div>'
        for i, m in enumerate(_as_list(data.get("key_messages"))[:3]))
    s1 = f"""<div class="page brk" id="s1"><h2 class="sec"><span class="num">1</span>{_x(L['s1'])}</h2>
      <div class="sum-grid"><div class="gauge" style="background:{_PRIO_COL[lvl]}"><small>{_x(L['niveau_global'])}</small><b>{_x(L[lvl])}</b></div>
      <div>{_x(data.get('executive_summary'))}</div></div>
      {f'<h3>{_x(L["points_cles"])}</h3><div class="msgs">{msgs}</div>' if msgs else ''}</div>"""

    # ---------- 2. Analyse quantitative ----------
    legend = "".join(
        f'<span><i style="background:{c}"></i>{_x(L[k])} : <b>{v}</b></span>'
        for k, v, c in (("c", n_c, GREEN), ("pc", n_pc, AMBER), ("nc", n_nc, RED)))
    kpis = "".join(
        f'<div class="kpi" style="--c:{c}"><b>{v}</b><span>{_x(L[k])}</span></div>'
        for k, v, c in (("total", total, BLUE), ("c", n_c, GREEN), ("pc", n_pc, AMBER), ("nc", n_nc, RED)))
    sec_rows = ""
    for s in sections:
        tot = max(s["nc"] + s["pc"] + s["c"], 1)
        bar = "".join(
            f'<div style="width:{100.0 * s[k] / tot:.1f}%;background:{col}"></div>'
            for k, col in (("c", GREEN), ("pc", AMBER), ("nc", RED)))
        sec_rows += (f'<tr><td>{_x(s["section"])}</td><td style="width:40%"><div class="stack">{bar}</div></td>'
                     f'<td>{s["nc"]}</td><td>{s["pc"]}</td><td>{s["c"]}</td></tr>')
    sec_table = (f'<h3>{_x(L["repartition"])} — {_x(L["domaine"].split("/")[0].strip())}</h3>'
                 f'<table><tr><th>{_x(L["domaine"].split("/")[0].strip())}</th><th></th>'
                 f'<th>{_x(L["domaine_nc"])}</th><th>{_x(L["domaine_pc"])}</th><th>C</th></tr>{sec_rows}</table>'
                 if sec_rows else "")
    s2 = f"""<div class="page brk" id="s2"><h2 class="sec"><span class="num">2</span>{_x(L['s2'])}</h2>
      <div class="kpis">{kpis}</div>
      <div class="quant"><div>{_donut(n_c, n_pc, n_nc, rate, L)}</div><div><h3 style="margin-top:0">{_x(L['repartition'])}</h3>
      <div class="legend">{legend}</div></div></div>{sec_table}</div>"""

    # ---------- 3. Risques prioritaires ----------
    ai_risks = {str(r.get("item_id")): r for r in _as_list(data.get("top_risks")) if isinstance(r, dict)}
    rows = ""
    for i, it in enumerate(items, 1):
        ai = ai_risks.get(str(it["item_id"]), {})
        col = it.get("couleur") or RED
        why = _x(ai.get("why_critical"))
        imp = _x(ai.get("potential_impact"))
        rows += f"""<tr class="nobreak"><td><span class="rank">{i}</span></td>
          <td><b>{_x(it['item_id'])}</b><br>{_pill(it.get('conformite', ''), _conf_color(it.get('conformite', '')))}</td>
          <td><b>{_x(it.get('section', ''))}</b><br><span class="muted">{_x(it.get('equipement', ''))}</span></td>
          <td>{_x(it.get('symptome', ''))}{f'<br><br><b>{_x(L["pourquoi"])} :</b> {why}' if why else ''}{f'<br><b>{_x(L["impact"])} :</b> {imp}' if imp else ''}</td>
          <td style="text-align:center">{_x(it.get('severity', ''))}</td>
          <td>{float(it.get('freq_moyenne') or 0):.1e}</td>
          <td><span class="badge" style="background:{_html.escape(str(col))}">{_x(it.get('risk_class', '—'))}</span></td></tr>"""
    s3 = f"""<div class="page brk" id="s3"><h2 class="sec"><span class="num">3</span>{_x(L['s3'])}</h2>
      <table><tr><th>{_x(L['rang'])}</th><th>{_x(L['ref'])}</th><th>{_x(L['domaine'])}</th><th>{_x(L['ecart'])}</th>
      <th>{_x(L['sev'])}</th><th>{_x(L['freq'])}</th><th>{_x(L['classe'])}</th></tr>{rows}</table></div>"""

    # ---------- 4. Analyse par domaine ----------
    cards = ""
    for d in _as_list(data.get("domain_analysis")):
        if not isinstance(d, dict):
            continue
        trend = f'<div class="muted" style="margin-top:6px">↗ {_x(d.get("trend"))}</div>' if d.get("trend") else ""
        cards += f'<div class="dcard"><h4>{_x(d.get("section"))}</h4>{_x(d.get("observation"))}{trend}</div>'
    s4 = (f'<div class="page brk" id="s4"><h2 class="sec"><span class="num">4</span>{_x(L["s4"])}</h2>'
          f'<div class="dom">{cards}</div></div>') if cards else ""

    # ---------- 5. Recommandations ----------
    order = {"high": 0, "critical": 0, "medium": 1, "low": 2}
    recs = sorted([r for r in _as_list(data.get("recommendations")) if isinstance(r, dict)],
                  key=lambda r: order.get(str(r.get("priority", "medium")).lower(), 1))
    rec_rows = "".join(
        f"""<tr class="nobreak"><td><span class="rank">{i}</span></td>
        <td><b>{_x(r.get('title'))}</b><br>{_x(r.get('description'))}
        {f'<br><span class="muted">{_x(L["resp"])} : {_x(r.get("owner_suggested"))}</span>' if r.get('owner_suggested') else ''}</td>
        <td>{_prio_pill(r.get('priority'), L)}</td><td>{_x(_horizon(r.get('horizon'), L))}</td>
        <td>{_cost_pill(r.get('cost_level'), L)}</td></tr>"""
        for i, r in enumerate(recs, 1))
    s5 = f"""<div class="page brk" id="s5"><h2 class="sec"><span class="num">5</span>{_x(L['s5'])}</h2>
      <table><tr><th>#</th><th>{_x(L['action'])}</th><th>{_x(L['priorite'])}</th><th>{_x(L['horizon'])}</th>
      <th>{_x(L['cout'])}</th></tr>{rec_rows}</table></div>"""

    # ---------- 6. Conclusion + signatures ----------
    steps = "".join(f"<li>{_x(s)}</li>" for s in _as_list(data.get("next_steps")))
    s6 = f"""<div class="page brk" id="s6"><h2 class="sec"><span class="num">6</span>{_x(L['s6'])}</h2>
      <div>{_x(data.get('conclusion'))}</div>
      {f'<h3>{_x(L["prochaines"])}</h3><ol>{steps}</ol>' if steps else ''}
      <h3>{_x(L['signatures'])}</h3>
      <div class="sign nobreak"><div><b>{_x(L['inspecteur'])}</b>{_x(meta.get('inspector') or tbc)}<br><span class="muted">{_x(L['signature'])}</span></div>
      <div><b>{_x(L['verificateur'])}</b>{_x(meta.get('reviewer') or tbc)}<br><span class="muted">{_x(L['signature'])}</span></div>
      <div><b>{_x(L['distribution'])}</b>{_x(L['distribution_val'])}<br><span class="muted">{_x(L['nom_date'])}</span></div></div>
      <p class="muted" style="font-size:11.5px;margin-top:18px">{_x(L['gen_note'])}</p></div>"""

    footer = f"{ref_code} · {L['confidentiel']} · {site}"
    return _page(cover + front + s1 + s2 + s3 + s4 + s5 + s6, f"{L['rapport']} — {site}", lang, footer, _REPORT_CSS)


# ==================================================================
# 2. PLAN D'ACTION PDCA
# ==================================================================
_PDCA_COL = {"P": "#1F4E79", "D": "#2F6B5E", "C": "#B7791F", "A": "#5B4B8A"}

_PDCA_CSS = f"""
.pd-head{{background:{NAVY};color:#fff;padding:22px 40px;display:flex;justify-content:space-between;gap:20px;align-items:center;border-bottom:4px solid {GREEN}}}
.pd-head h1{{margin:0;font-size:21px;letter-spacing:.04em}} .pd-head .sub{{color:#B8C7D9;font-size:12.5px}}
.pd-head .logo{{height:44px;background:#fff;border-radius:6px;padding:4px}}
.pd-body{{padding:24px 40px 10px}}
.idgrid{{display:grid;grid-template-columns:repeat(4,1fr);border:1px solid var(--line);border-radius:6px;margin:14px 0 6px}}
.idgrid div{{padding:10px 14px;border-inline-end:1px solid var(--line);text-align:center}}
.idgrid div:last-child{{border:0}} .idgrid small{{display:block;color:var(--muted);font-size:10.5px;text-transform:uppercase;letter-spacing:.06em}}
.idgrid b{{font-size:17px;color:var(--navy)}}
.desc{{margin:14px 0 0;color:var(--ink)}} .desc .ref{{color:var(--muted);font-size:12px}}
.cyc{{display:grid;grid-template-columns:230px 1fr;gap:26px;align-items:center;margin:8px 0}}
.cycle{{width:225px;height:225px}} .cycle text{{font-family:inherit}}
.ph{{display:flex;gap:12px;align-items:flex-start;padding:9px 0;border-bottom:1px solid var(--line)}}
.ph:last-child{{border:0}}
.ph .L{{width:30px;height:30px;border-radius:4px;background:var(--c);color:#fff;font-weight:700;display:flex;align-items:center;justify-content:center;flex:none}}
.ph b{{color:var(--c);font-size:12px;text-transform:uppercase;letter-spacing:.05em;display:block}}
.obj{{border-inline-start:5px solid {NAVY};background:var(--bg);padding:11px 16px;margin:6px 0;font-weight:600}}
.num{{text-align:center;font-weight:700;color:{NAVY};width:34px}}
tfoot td{{background:#EEF3F8!important;font-weight:700;border-top:2px solid {NAVY}}}
.when{{font-weight:700;color:{NAVY};white-space:nowrap}}
@media(max-width:700px){{.cyc{{grid-template-columns:1fr}}.idgrid{{grid-template-columns:repeat(2,1fr)}}}}}}
"""


def _cycle_svg() -> str:
    """Roue PDCA sobre : 4 secteurs fléchés (sens horaire), lettre centrée."""
    cx = cy = 112
    r_out, r_in, gap = 102, 58, 5
    out = []

    def pt(r, a):
        return cx + r * math.cos(a), cy + r * math.sin(a)

    for letter, start in (("P", -90), ("D", 0), ("C", 90), ("A", 180)):
        a0, a1 = math.radians(start + gap), math.radians(start + 90 - gap - 7)
        x0, y0 = pt(r_out, a0); x1, y1 = pt(r_out, a1)
        x2, y2 = pt(r_in, a1); x3, y3 = pt(r_in, a0)
        col = _PDCA_COL[letter]
        out.append(f'<path d="M{x0:.1f},{y0:.1f} A{r_out},{r_out} 0 0 1 {x1:.1f},{y1:.1f} '
                   f'L{x2:.1f},{y2:.1f} A{r_in},{r_in} 0 0 0 {x3:.1f},{y3:.1f} Z" fill="{col}"/>')
        mid = (r_out + r_in) / 2
        tip = pt(mid, a1 + math.radians(13))
        b1, b2 = pt(r_out + 5, a1), pt(r_in - 5, a1)
        out.append(f'<polygon points="{b1[0]:.1f},{b1[1]:.1f} {tip[0]:.1f},{tip[1]:.1f} {b2[0]:.1f},{b2[1]:.1f}" fill="{col}"/>')
        lx, ly = pt(mid, (a0 + a1) / 2)
        out.append(f'<text x="{lx:.1f}" y="{ly + 9:.1f}" text-anchor="middle" font-size="26" font-weight="700" fill="#fff">{letter}</text>')
    out.append(f'<circle cx="{cx}" cy="{cy}" r="44" fill="#fff" stroke="#E3E9F0"/>'
               f'<text x="{cx}" y="{cy + 6}" text-anchor="middle" font-size="17" font-weight="700" fill="{NAVY}">PDCA</text>')
    return f'<svg class="cycle" viewBox="0 0 224 224" role="img" aria-label="PDCA">{"".join(out)}</svg>'


def _money(v) -> str:
    try:
        return f"{int(float(v)):,}".replace(",", " ")
    except (TypeError, ValueError):
        return ""


def render_pdca_html(data: dict, item: dict, mc: dict, meta: dict, lang: str = "fr") -> str:
    """
    data : JSON du LLM  {objective, phases{P,D,C,A}, actions[{title,owner,deadline,cost_level}], followup[{when,check,target}]}
    item : {item_id, section, equipement, symptome, severity, conformite}   (BD)
    mc   : {freq_moyenne, risk_class, couleur}                               (BD)
    """
    L = _labels(lang)
    data = data or {}
    phases = data.get("phases") or {}
    logo = _logo_b64(160)
    sev = item.get("severity", "—")
    rcol = _html.escape(str(mc.get("couleur") or NAVY))
    ref_code = f"HSE-PDCA-{re.sub(r'[^A-Za-z0-9]+', '-', str(item.get('item_id', ''))).strip('-')}"

    head = f"""<div class="pd-head"><div><h1>{_x(L['pdca'])}</h1><div class="sub">{_x(L['pdca_sub'])}</div></div>
      {f'<img class="logo" src="{logo}" alt="logo">' if logo else ''}</div>"""

    idgrid = f"""<div class="idgrid">
      <div><small>{_x(L['severite'])}</small><b>{_x(sev)}/5</b></div>
      <div><small>{_x(L['conformite'])}</small><b style="color:{_conf_color(item.get('conformite', ''))}">{_x(item.get('conformite'))}</b></div>
      <div><small>{_x(L['frequence_mc'])}</small><b>{float(mc.get('freq_moyenne') or 0):.1e} /an</b></div>
      <div><small>{_x(L['classe_risque'])}</small><b style="color:{rcol}">{_x(mc.get('risk_class', '—'))}</b></div></div>
      <p class="desc"><span class="ref">{_x(ref_code)} · {_x(meta.get('site', ''))} · {_x(item.get('section', ''))} — {_x(item.get('equipement', ''))}</span><br>{_x(item.get('symptome'))}</p>"""

    ph_rows = "".join(
        f'<div class="ph" style="--c:{_PDCA_COL[k]}"><span class="L">{k}</span><div><b>{_x(L[k])}</b>{_x(phases.get(k))}</div></div>'
        for k in "PDCA")
    cycle = f'<h3>{_x(L["cycle"])}</h3><div class="cyc">{_cycle_svg()}<div>{ph_rows}</div></div>'

    obj = (f'<h3>{_x(L["objectif"])}</h3><div class="obj">{_x(data.get("objective"))}</div>'
           if data.get("objective") else "")

    rows = ""
    for i, a in enumerate([a for a in _as_list(data.get("actions")) if isinstance(a, dict)], 1):
        rows += (f'<tr class="nobreak"><td class="num">{i}</td><td>{_x(a.get("title"))}</td><td>{_x(a.get("owner"))}</td>'
                 f'<td class="when">{_x(a.get("deadline"))}</td><td style="text-align:center">{_cost_pill(a.get("cost_level", 0), L)}</td></tr>')
    actions = (f'<h3>{_x(L["actions"])}</h3><table><thead><tr><th>#</th><th>{_x(L["actions"])}</th><th>{_x(L["qui"])}</th>'
               f'<th>{_x(L["quand"])}</th><th style="text-align:center">{_x(L["cout_col"])}</th></tr></thead><tbody>{rows}</tbody></table>')

    fu_rows = "".join(
        f'<tr class="nobreak"><td class="when">{_x(f.get("when"))}</td><td>{_x(f.get("check"))}</td><td>{_x(f.get("target"))}</td></tr>'
        for f in _as_list(data.get("followup")) if isinstance(f, dict))
    followup = (f'<h3>{_x(L["suivi"])}</h3><table><thead><tr><th style="width:90px"></th><th>{_x(L["verif"])}</th>'
                f'<th>{_x(L["cible"])}</th></tr></thead><tbody>{fu_rows}</tbody></table>') if fu_rows else ""

    body = head + f'<div class="pd-body">{idgrid}{cycle}{obj}{actions}{followup}</div>'
    footer = f"{ref_code} · {meta.get('inspection_id', '')} · {L['confidentiel']}"
    return _page(body, f"{L['pdca']} — {item.get('item_id')}", lang, footer, _PDCA_CSS)


# ==================================================================
# 3. PONT VERS pdf_renderer (PDF signé + QR)
# ==================================================================
def build_pdf_bytes(inspection_id: str,
                    site_name: str = "",
                    inspector_name: str = "",
                    results_df=None,
                    summary: dict | None = None,
                    notes: str = "",
                    language: str = "fr") -> bytes | None:
    """
    Génère un PDF signé (QR code) via pdf_renderer.render_pdf_report.

    Args:
        inspection_id : identifiant de l'inspection
        site_name     : nom du site
        inspector_name: nom de l'inspecteur
        results_df    : DataFrame des résultats (optionnel)
        summary       : dict {indicateur: valeur} (ex: {"NC": 5, "C": 20})
        notes         : texte libre
        language      : 'fr' | 'ar' | 'en'

    Returns:
        bytes du PDF, ou None si reportlab/qrcode manquent.
    """
    try:
        from pdf_renderer import render_pdf_report
    except ImportError:
        return None

    return render_pdf_report(
        inspection_id=str(inspection_id),
        site_name=site_name,
        inspector_name=inspector_name,
        results_df=results_df,
        summary=summary or {},
        extra_notes=notes,
        language=language,
    )


# Alias court pour compatibilité historique (Dounia mission #7 : « render_pdf »)
def render_pdf(inspection_id: str,
               site_name: str = "",
               inspector_name: str = "",
               results_df=None,
               summary: dict | None = None,
               notes: str = "",
               language: str = "fr") -> bytes | None:
    """Alias de build_pdf_bytes() — conservé pour compatibilité."""
    return build_pdf_bytes(
        inspection_id=inspection_id,
        site_name=site_name,
        inspector_name=inspector_name,
        results_df=results_df,
        summary=summary,
        notes=notes,
        language=language,
    )


# ============================================================
# Export public
# ============================================================
__all__ = [
    "render_report_html",
    "render_pdca_html",
    "build_pdf_bytes",
    "render_pdf",
    # utilitaires utilisés par report_template.py
    "_labels", "_x", "_as_list", "_page", "_REPORT_CSS", "_logo_b64",
]