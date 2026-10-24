"""
ui/i18n.py — Gestion multilingue HSE PYXIS (AR / FR / EN)
==========================================================
v3 — Corrections et améliorations :
  • Chargement sécurisé des JSON locales (fr/ar/en)
  • Fallback fr → en → libellé lisible
  • Support des paramètres formatés {var}
  • Détection RTL automatique
  • Cache invalidable (utile si on recharge les locales à chaud)
  • Nouvelles clés pour : Dashboard, Comparison, Actions correctives,
    Wizard dispersion, GHS, Exports Excel/PDF (voir locales/*.json)
"""

import json
from pathlib import Path

import streamlit as st

LOCALES_DIR = Path(__file__).parent.parent / "locales"

LANGUAGES = {
    "fr": {"label": "Français", "flag": "🇫🇷", "dir": "ltr"},
    "ar": {"label": "العربية",  "flag": "🇩🇿", "dir": "rtl"},
    "en": {"label": "English",  "flag": "🇬🇧", "dir": "ltr"},
}

DEFAULT_LANG = "fr"
FALLBACK_CHAIN = ("fr", "en")


# ============================================================
# Chargement des traductions
# ============================================================
@st.cache_data(show_spinner=False)
def load_translations(lang: str) -> dict:
    """Charge un fichier locales/<lang>.json. Retourne {} si absent/corrompu."""
    path = LOCALES_DIR / f"{lang}.json"
    if not path.exists():
        return {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return {}


def clear_translations_cache():
    """À appeler si les fichiers JSON sont modifiés à chaud (dev)."""
    load_translations.clear()


# ============================================================
# Lookup dans un dict imbriqué
# ============================================================
def _lookup(translations: dict, key: str):
    """Résout 'a.b.c' dans un dict imbriqué. Retourne None si absent."""
    value = translations
    for part in key.split("."):
        if isinstance(value, dict) and part in value:
            value = value[part]
        else:
            return None
    return value if isinstance(value, str) else None


def _humanize(key: str) -> str:
    """Dernier recours : 'welcome.start_button' -> 'Start button'."""
    last = key.split(".")[-1].replace("_", " ").strip()
    return last.capitalize() if last else key


# ============================================================
# Traduction principale
# ============================================================
def t(key: str, _lang: str | None = None, **kwargs) -> str:
    """
    Traduit une clé, avec repli fr → en → libellé lisible.

    Args:
        key: Clé de traduction ('step2.env_title', 'nav.dashboard', …)
        _lang: Force une langue précise (utile pour rapports multilingues).
               Par défaut : langue active de l'UI.
        **kwargs: Variables à injecter dans le format {var}

    Returns:
        La traduction, ou la clé humanisée si introuvable partout.
    """
    lang = _lang if _lang in LANGUAGES else get_current_lang()

    value = None
    for candidate in (lang, *FALLBACK_CHAIN):
        value = _lookup(load_translations(candidate), key)
        if value is not None:
            break

    if value is None:
        return _humanize(key)

    if kwargs:
        try:
            return value.format(**kwargs)
        except (KeyError, IndexError, ValueError):
            # Si format échoue, on renvoie la valeur brute
            return value
    return value


def t_in(lang: str, key: str, **kwargs) -> str:
    """Raccourci : traduit `key` dans la langue `lang`, quelle que soit l'UI."""
    return t(key, _lang=lang, **kwargs)


# ============================================================
# Langue courante
# ============================================================
def get_current_lang() -> str:
    lang = st.session_state.get("language", DEFAULT_LANG)
    return lang if lang in LANGUAGES else DEFAULT_LANG


def is_rtl() -> bool:
    return LANGUAGES.get(get_current_lang(), {}).get("dir") == "rtl"


def set_language(lang: str):
    if lang in LANGUAGES:
        st.session_state.language = lang


# ============================================================
# 🆕 Helpers v3 — utiles pour les nouvelles pages
# ============================================================
def get_languages_list():
    """Retourne la liste [(code, label, flag), …] pour un selectbox."""
    return [
        (code, meta["label"], meta["flag"])
        for code, meta in LANGUAGES.items()
    ]


def t_choice(key: str, options: list, _lang: str | None = None) -> dict:
    """
    Traduit plusieurs clés d'un coup.
    Utile pour les listes comme ['actions.priority_low', 'actions.priority_high'].
    Retourne {clé_originale: traduction}.
    """
    return {k: t(k, _lang=_lang) for k in options}


# ============================================================
# Export public
# ============================================================
__all__ = [
    "t",
    "t_in",
    "t_choice",
    "get_current_lang",
    "set_language",
    "is_rtl",
    "get_languages_list",
    "load_translations",
    "clear_translations_cache",
    "LANGUAGES",
    "DEFAULT_LANG",
]