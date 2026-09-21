"""
ui/display.py — Couche de traduction pour l'AFFICHAGE uniquement
================================================================
Principe fondamental :
    * Les VALEURS STOCKÉES en base de données ne changent jamais.
      ("C", "PC", "NC", "À auditer", "Direct", "Estimated", "manuelle", ...)
    * Seul l'AFFICHAGE passe par les fonctions de ce module.

Cela garantit que :
    - les comparaisons dans le code (`if conformite == "À auditer"`) continuent
      de fonctionner quelle que soit la langue ;
    - un audit saisi en français reste lisible en arabe ou en anglais ;
    - aucune migration de base n'est nécessaire.

Fonctions principales
---------------------
tr_conformite / conformite_display_options / conformite_from_display
    Conformité (valeur métier <-> libellé affiché).
tr_matrix_label
    Libellés de matrice (sévérité / probabilité / seuils / actions).
    Traduit UNIQUEMENT les libellés par défaut connus (dans les 3 langues) ;
    un libellé saisi à la main par l'utilisateur est renvoyé tel quel.
tr_reco / tr_lira / tr_method / tr_meteo / tr_industry / tr_stability
    Valeurs générées par les modules métier.
"""

import re

from audit_db import (
    symptom_of, symptom_all_text,
    section_of, equipment_of, hazard_of, method_translation_of,
    evidence_of, technical_reference_of,
    COL_METHOD_RAW,
)
from ui.i18n import t, LANGUAGES, load_translations, get_current_lang

# ============================================================
# 1. CONFORMITÉ
# ============================================================
# ⚠️ Ces valeurs sont stockées en base : NE JAMAIS les traduire à la source.
CONFORMITE_A_AUDITER = "À auditer"
CONFORMITE_VALUES = [CONFORMITE_A_AUDITER, "C", "PC", "NC"]

_CONFORMITE_KEYS = {
    CONFORMITE_A_AUDITER: "values.conformite.to_audit",
    "C": "values.conformite.c",
    "PC": "values.conformite.pc",
    "NC": "values.conformite.nc",
}

CONFORMITE_EMOJI = {
    CONFORMITE_A_AUDITER: "⚪",
    "C": "✅",
    "PC": "⚠️",
    "NC": "❌",
}


def tr_conformite(value: str, lang: str | None = None) -> str:
    """Libellé affiché d'une conformité stockée."""
    key = _CONFORMITE_KEYS.get(value)
    return t(key, _lang=lang) if key else str(value)


def conformite_display_options() -> list:
    """Options traduites, dans l'ordre métier (pour data_editor)."""
    return [tr_conformite(v) for v in CONFORMITE_VALUES]


def conformite_to_display(value: str) -> str:
    """Valeur stockée -> libellé affiché (alias explicite)."""
    return tr_conformite(value)


def conformite_from_display(label: str) -> str:
    """Libellé affiché -> valeur stockée.

    Tolérant : accepte aussi une valeur déjà stockée, ou un libellé
    d'une autre langue (utile si la langue change en cours de saisie).
    """
    if label in CONFORMITE_VALUES:
        return label

    for value, key in _CONFORMITE_KEYS.items():
        for lang in LANGUAGES:
            translations = load_translations(lang)
            candidate = _lookup(translations, key)
            if candidate is not None and candidate == label:
                return value

    return CONFORMITE_A_AUDITER


# ============================================================
# 2. OUTILS INTERNES
# ============================================================
def _lookup(translations: dict, key: str):
    """Résout 'a.b.c' dans un dict imbriqué (copie locale de i18n._lookup)."""
    value = translations
    for part in key.split("."):
        if isinstance(value, dict) and part in value:
            value = value[part]
        else:
            return None
    return value if isinstance(value, str) else None


_REVERSE_CACHE: dict = {}
_PATTERN_CACHE: list = []


def _reverse_index(prefix: str) -> dict:
    """Construit {libellé_dans_n_importe_quelle_langue: clé} pour un préfixe.

    Permet de reconnaître un libellé enregistré en français et de l'afficher
    en arabe (et réciproquement).
    """
    if prefix in _REVERSE_CACHE:
        return _REVERSE_CACHE[prefix]

    index = {}
    for lang in LANGUAGES:
        translations = load_translations(lang)
        node = translations
        for part in prefix.split("."):
            node = node.get(part, {}) if isinstance(node, dict) else {}
        if isinstance(node, dict):
            for sub_key, value in node.items():
                if isinstance(value, str):
                    index.setdefault(value.strip(), f"{prefix}.{sub_key}")

    _REVERSE_CACHE[prefix] = index
    return index


def _translate_known(value, prefix: str, default_key: str | None = None,
                     lang: str | None = None) -> str:
    """Traduit `value` si c'est un libellé connu sous `prefix`, sinon tel quel."""
    if value is None:
        return ""
    raw = str(value).strip()
    if not raw:
        return raw

    # a) La valeur stockée EST le nom de la clé ("oil_gas", "manuelle", "Direct")
    direct = _lookup(load_translations("fr"), f"{prefix}.{raw}")
    if direct is not None:
        return t(f"{prefix}.{raw}", _lang=lang)

    # b) La valeur stockée est un libellé déjà traduit dans une des langues
    key = _reverse_index(prefix).get(raw)
    if key:
        return t(key, _lang=lang)

    if default_key:
        return t(default_key, value=raw, _lang=lang)
    return raw


# ============================================================
# 3. LIBELLÉS DE MATRICE (sévérité / probabilité / seuils / actions)
# ============================================================
def _level_default_patterns():
    """Motifs regex de 'Niveau {n}' dans les 3 langues."""
    if _PATTERN_CACHE:
        return _PATTERN_CACHE

    patterns = []
    for lang in LANGUAGES:
        template = _lookup(load_translations(lang), "step0.level_default")
        if not template or "{n}" not in template:
            continue
        escaped = re.escape(template).replace(r"\{n\}", r"(\d+)")
        patterns.append(re.compile(f"^{escaped}$"))

    _PATTERN_CACHE.extend(patterns)
    return patterns


def tr_matrix_label(label, lang: str | None = None) -> str:
    """Traduit un libellé de matrice s'il fait partie des valeurs par défaut.

    Un libellé personnalisé (saisi par l'auditeur) est renvoyé inchangé :
    il n'existe qu'en une seule langue en base, et le traduire
    automatiquement serait faux.
    """
    if label is None:
        return ""
    raw = str(label).strip()
    if not raw:
        return raw

    # a) Libellés par défaut (Acceptable, Tolérable, Aucune, Surveillance...)
    key = _reverse_index("matrix_defaults").get(raw)
    if key:
        return t(key, _lang=lang)

    # b) « Niveau 3 » / « المستوى 3 » / « Level 3 »
    for pattern in _level_default_patterns():
        match = pattern.match(raw)
        if match:
            return t("step0.level_default", n=match.group(1), _lang=lang)

    # c) Libellé personnalisé -> inchangé
    return raw


def tr_matrix_series(series):
    """Applique tr_matrix_label à une colonne pandas (pratique pour l'affichage)."""
    return series.apply(tr_matrix_label)


# ============================================================
# 4. VALEURS PRODUITES PAR LES MODULES MÉTIER
# ============================================================
def tr_reco(value, lang: str | None = None) -> str:
    """Recommandation coût-bénéfice.

    Accepte le CODE renvoyé par cost_benefit.recommandation_code() ainsi que
    les anciennes phrases françaises déjà stockées en base (rétro-compatibilité).
    """
    if value is None:
        return ""
    raw = str(value).strip()
    if not raw:
        return raw

    codes = {
        "CB_STRONGLY_RECOMMENDED": "values.reco.strongly_recommended",
        "CB_RECOMMENDED": "values.reco.recommended",
        "CB_TO_REVIEW": "values.reco.to_review",
        "CB_NOT_PRIORITY": "values.reco.not_priority",
    }
    if raw in codes:
        return t(codes[raw], _lang=lang)

    # --- Rétro-compatibilité : lignes enregistrées avant l'i18n ---
    upper = raw.upper()
    if "FORTEMENT" in upper:
        return t("values.reco.strongly_recommended", _lang=lang)
    if "EXAMINER" in upper:
        return t("values.reco.to_review", _lang=lang)
    if "NON PRIORITAIRE" in upper:
        return t("values.reco.not_priority", _lang=lang)
    if "RECOMMAND" in upper:
        return t("values.reco.recommended", _lang=lang)

    return raw


def tr_lira(code, lang: str | None = None) -> str:
    """Niveau LIRA (code renvoyé par human_risk_indicators.niveau_lira)."""
    mapping = {
        "LIRA_UNACCEPTABLE": ("values.lira.unacceptable", "🔴"),
        "LIRA_ALARP": ("values.lira.alarp", "🟠"),
        "LIRA_NEGLIGIBLE": ("values.lira.negligible", "🟢"),
    }
    entry = mapping.get(str(code).strip())
    if not entry:
        return str(code)
    key, emoji = entry
    return f"{emoji} {t(key, _lang=lang)}"


def tr_method(value, lang: str | None = None) -> str:
    """Méthode d'estimation de fréquence (Direct / Calcule / Estimated)."""
    return _translate_known(value, "values.method", lang=lang)


def tr_meteo(value, lang: str | None = None) -> str:
    """Source météo (manuelle / openweather / ...)."""
    return _translate_known(value, "values.meteo", lang=lang)


def tr_industry(value, lang: str | None = None) -> str:
    """Secteur industriel (oil_gas, pharma, ...)."""
    return _translate_known(value, "values.industry", lang=lang)


def tr_stability(value) -> str:
    """Classe de stabilité de Pasquill (A..F) : code universel, non traduit."""
    return str(value) if value is not None else ""


def tr_risk_level(value, lang: str | None = None) -> str:
    """Niveau de risque renvoyé par matrice_manager (libellé ou 'non défini')."""
    from matrice_manager import RISK_LEVEL_UNDEFINED

    if str(value).strip() == RISK_LEVEL_UNDEFINED:
        return t("values.risk.undefined", _lang=lang)
    return tr_matrix_label(value, lang=lang)


# ============================================================
# 5. CHECKLIST — symptômes multilingues (FR / AR / EN)
# ============================================================
def tr_symptom(item, lang: str | None = None) -> str:
    """Symptôme d'une ligne de la checklist, dans la langue de l'interface.

    `item` = tuple renvoyé par db.get_item() / db.get_checklist_items().
    Langue par défaut : langue active. Repli automatique (traduction vide) :
    langue demandée -> anglais -> français -> arabe.
    La valeur stockée en base n'est jamais modifiée.
    """
    return symptom_of(item, lang or get_current_lang())


def tr_section(item, lang: str | None = None) -> str:
    """Nom de section d'une ligne de la checklist, dans la langue de l'interface."""
    return section_of(item, lang or get_current_lang())


def tr_equipment(item, lang: str | None = None) -> str:
    """Type d'équipement d'une ligne de la checklist, dans la langue de l'interface."""
    return equipment_of(item, lang or get_current_lang())


def tr_hazard(item, lang: str | None = None) -> str:
    """Classe de danger d'une ligne de la checklist, dans la langue de l'interface."""
    lang = lang or get_current_lang()
    value = hazard_of(item, lang)
    # Repli anglais : la valeur source est un code en minuscules (« pressure »).
    return value.capitalize() if lang == "en" and value.islower() else value


def tr_evidence(item, lang: str | None = None) -> str:
    """Preuve requise d'une ligne de la checklist, dans la langue de l'interface."""
    return evidence_of(item, lang or get_current_lang())


def tr_technical_reference(item, lang: str | None = None) -> str:
    """Référence technique d'une ligne de la checklist, dans la langue de l'interface."""
    return technical_reference_of(item, lang or get_current_lang())


def tr_method_of(item, lang: str | None = None) -> str:
    """Méthode d'estimation de fréquence d'une ligne de la checklist.

    FR / AR : traduction lue dans l'Excel (method_fr / method_ar) ;
    EN ou traduction absente : libellés des fichiers locales (tr_method).
    Le code stocké (Direct / Calcule / Estimated) n'est jamais modifié.
    """
    lang = lang or get_current_lang()
    translated = method_translation_of(item, lang)
    if translated:
        return translated
    try:
        raw = item[COL_METHOD_RAW]
    except (IndexError, KeyError, TypeError):
        raw = ""
    return tr_method(raw, lang=lang)


def symptom_search_text(item) -> str:
    """Symptôme dans les 3 langues (pour que la recherche marche quelle que
    soit la langue affichée ou tapée)."""
    return symptom_all_text(item)
