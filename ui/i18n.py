"""
ui/i18n.py — Gestion multilingue HSE PYXIS (AR / FR / EN) (v2, corrigé)
=========================================================================
CORRECTION : si une clé est absente (ou si locales/<lang>.json manque),
t() renvoyait la clé brute — on voyait « welcome.subtitle » à l'écran.
Désormais : langue demandée -> français -> anglais -> libellé lisible.
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


@st.cache_data(show_spinner=False)
def load_translations(lang: str) -> dict:
    path = LOCALES_DIR / f"{lang}.json"
    if not path.exists():
        return {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return {}


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


def t(key: str, _lang: str | None = None, **kwargs) -> str:
    """Traduit une clé, avec repli fr -> en -> libellé lisible.

    _lang : force une langue précise (utile quand la langue du RAPPORT
            diffère de celle de l'interface). Par défaut : langue active.
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
            return value
    return value


def t_in(lang: str, key: str, **kwargs) -> str:
    """Raccourci : traduit `key` dans la langue `lang`, quelle que soit l'UI."""
    return t(key, _lang=lang, **kwargs)


def get_current_lang() -> str:
    lang = st.session_state.get("language", DEFAULT_LANG)
    return lang if lang in LANGUAGES else DEFAULT_LANG


def is_rtl() -> bool:
    return LANGUAGES.get(get_current_lang(), {}).get("dir") == "rtl"


def set_language(lang: str):
    if lang in LANGUAGES:
        st.session_state.language = lang
