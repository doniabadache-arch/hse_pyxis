"""
audit_app.py (UNIFIED v2)
=========================
Application Streamlit unique — 4 étapes :
- Étape 0 : Configuration Matrice         (copié de matrix_app.py)
- Étape 1 : Audit (choix matrice + symptôme)
- Étape 2 : Formulaires NC/PC + Batch      (basé sur audit_app.py v1)
- Étape 3 : Résultats + Classification     (basé sur app_risk.pyy via results_viewer)

Usage:
    streamlit run audit_app.py
"""

import streamlit as st
import hmac
import json
import os
import sqlite3
import time
from pathlib import Path
from contextlib import closing

import pandas as pd
import numpy as np
import plotly.graph_objects as go

# ---- Modules internes ----
import ai_service
from audit_db import AuditDB, strip_multilingual_suffix
from matrice_manager import MatriceManager
from risk_matrix import RiskMatrixConfig

from monte_carlo_engine import (
    simuler_frequence_triangulaire,
    resumer_distribution,
    calculer_score_risque,
    N_ITER_APERCU,
    N_ITER_FINAL,
)
from human_risk_indicators import (
    evaluer_risque_humain,
    niveau_lira,
    SEUILS_LIRA_INDICATIFS,
)
from cost_benefit import (
    evaluer_cout_benefice,
    CURRENCIES,
    DEFAULT_CURRENCY,
    get_default_indisponibilite,
    convert_from_eur,
    format_amount,
    get_currency_symbol,
)
from dispersion_aloha import evaluer_dispersion

# ---- Module d'affichage (Étape 3) ----
from results_viewer import (
    load_matrix_dfs,
    classify_results_df,
    render_metric_cards,
    render_heatmap,
    render_plots,
    freq_to_prob_level,
)

# ---- Interface (thème, langue, layout, accueil) ----
from ui.theme import apply_theme, current_theme, show_plotly
from ui.i18n import t, set_language, get_current_lang
from ui.display import (
    CONFORMITE_A_AUDITER,
    CONFORMITE_EMOJI,
    conformite_display_options,
    conformite_from_display,
    tr_conformite,
    tr_industry,
    tr_lira,
    tr_matrix_label,
    tr_meteo,
    tr_method,
    tr_reco,
    tr_symptom,
    tr_section,
    tr_equipment,
    tr_evidence,
    tr_method_of,
    symptom_search_text,
)
from ui.layout import render_header, render_footer
from ui.pages.welcome import render_welcome


# ============================================================
# CONFIGURATION STREAMLIT
# ============================================================
st.set_page_config(
    page_title=t("app.full_title"),
    page_icon="🛡️",
    layout="wide",
)

# ---- Injection du CSS HSE PYXIS ----
apply_theme()


# ============================================================
# ACCÈS PROTÉGÉ PAR MOT DE PASSE
# ============================================================
# Mot de passe : d'abord st.secrets["APP_PASSWORD"] (Streamlit Cloud > Settings >
# Secrets), sinon la variable d'environnement APP_PASSWORD, sinon la valeur par défaut.
# Si le dépôt GitHub est PUBLIC, la valeur par défaut est lisible par tous :
# définissez alors APP_PASSWORD dans les secrets.
_DEFAULT_APP_PASSWORD = "pyxis2026"


def _get_app_password() -> str:
    try:
        secret = st.secrets.get("APP_PASSWORD")
        if secret:
            return str(secret)
    except Exception:
        pass  # pas de secrets.toml (exécution locale)
    return os.environ.get("APP_PASSWORD") or _DEFAULT_APP_PASSWORD


def _require_password() -> None:
    """Bloque l'application tant que le bon mot de passe n'a pas été saisi."""
    if st.session_state.get("auth_ok", False):
        return

    st.markdown("## 🔒 HSE PYXIS")
    with st.form("auth_form"):
        saisi = st.text_input(
            "Mot de passe · Password · كلمة المرور",
            type="password",
            key="auth_pwd_input",
        )
        envoye = st.form_submit_button("Entrer · Enter · دخول", type="primary")

    if envoye:
        if hmac.compare_digest(saisi.encode("utf-8"), _get_app_password().encode("utf-8")):
            st.session_state["auth_ok"] = True
            st.rerun()
        else:
            time.sleep(1)  # ralentit les essais répétés
            st.error("Mot de passe incorrect · Incorrect password · كلمة المرور غير صحيحة")
    st.stop()


_require_password()

# ---- Écran d'accueil (avant démarrage) ----
if not st.session_state.get("welcome_done", False):
    render_welcome()
    st.stop()

# ---- Header HSE PYXIS ----
render_header()


# ============================================================
# INITIALISATION
# ============================================================
db = AuditDB()
matrice_manager = MatriceManager()


# ============================================================
# SESSION STATE
# ============================================================
if "current_step" not in st.session_state:
    st.session_state.current_step = 0

if "audit_buffer" not in st.session_state:
    st.session_state.audit_buffer = {}

if "batch_done" not in st.session_state:
    st.session_state.batch_done = False

if "active_site" not in st.session_state:
    sites = matrice_manager.list_sites()
    st.session_state.active_site = sites[0] if sites else None


# ============================================================
# SIDEBAR — NAVIGATION PAR ÉTAPES
# ============================================================
st.sidebar.header(f"🧭 {t('nav.navigation')}")

STEPS = {
    0: t("nav.step_0"),
    1: t("nav.step_1"),
    2: t("nav.step_2"),
    3: t("nav.step_3"),
}

# Ajout de l'étape 4 : Rapport IA
STEPS[4] = t("nav.step_4")

# Ajout de l'étape 5 : Plan PDCA (IA)
STEPS[5] = t("nav.step_5")

step = st.sidebar.radio(
    t("nav.active_step"),
    options=list(STEPS.keys()),
    format_func=lambda x: STEPS[x],
    index=st.session_state.current_step,
    key="navigation_radio",
)
st.session_state.current_step = step


# ============================================================
# SIDEBAR — INFOS D'AUDIT
# ============================================================
st.sidebar.markdown("---")
st.sidebar.header(f"📋 {t('sidebar.audit_info')}")

audit_id = st.sidebar.text_input(
    t("sidebar.audit_id"),
    value="AUDIT-2025-001",
    key="audit_id_input",
)


# ============================================================
# SIDEBAR — STATUT DU BUFFER
# ============================================================
st.sidebar.markdown("---")
st.sidebar.header(f"📊 {t('sidebar.audit_status')}")

buffer = st.session_state.audit_buffer
n_total = len(buffer)
n_nc = sum(1 for v in buffer.values() if v["conformite"] == "NC")
n_pc = sum(1 for v in buffer.values() if v["conformite"] == "PC")
n_c = sum(1 for v in buffer.values() if v["conformite"] == "C")

st.sidebar.metric(t("sidebar.total_entered"), n_total)

col1, col2 = st.sidebar.columns(2)
col1.metric(tr_conformite("NC"), n_nc)
col2.metric(tr_conformite("PC"), n_pc)
st.sidebar.metric(tr_conformite("C"), n_c)

if st.sidebar.button(t("sidebar.reset_buffer")):
    st.session_state.audit_buffer = {}
    st.session_state.batch_done = False
    st.sidebar.success(t("sidebar.buffer_reset"))
    st.rerun()


# ============================================================
# SIDEBAR — PARAMÈTRES (Langue + Thème)
# ============================================================
st.sidebar.markdown("---")
st.sidebar.header(f"⚙️ {t('nav.settings')}")

# ---- Langue ----
from ui.i18n import LANGUAGES
lang_options = list(LANGUAGES.keys())
current_lang = get_current_lang()
lang_idx = lang_options.index(current_lang) if current_lang in lang_options else 0

new_lang = st.sidebar.selectbox(
    f"🌍 {t('nav.language')}",
    lang_options,
    index=lang_idx,
    format_func=lambda x: f"{LANGUAGES[x]['flag']} {LANGUAGES[x]['label']}",
    key="sidebar_lang_select",
)
if new_lang != current_lang:
    set_language(new_lang)
    st.rerun()

# ---- Thème ----
theme_actuel = current_theme()
new_theme = st.sidebar.radio(
    f"🎨 {t('nav.theme')}",
    ["dark", "light"],
    index=0 if theme_actuel == "dark" else 1,
    format_func=lambda x: t("welcome.theme_dark") if x == "dark" else t("welcome.theme_light"),
    key="sidebar_theme_radio",
)
if new_theme != theme_actuel:
    st.session_state.theme = new_theme
    st.rerun()


# ============================================================
# LOAD SUBSTANCES (cache)
# ============================================================
@st.cache_data
def load_substances():
    """Charge substances_clean.json si présent."""
    f = Path("data/substances_clean.json")
    if not f.exists():
        return []
    with open(f, "r", encoding="utf-8") as fp:
        return json.load(fp)


substances_db = load_substances()
substance_options = ["-- Sélectionner --"] + [
    s.get("name") or f"Unknown ({s.get('source_filename')})"
    for s in substances_db
]


# ============================================================
# LOAD CHECKLIST DEPUIS EXCEL (cache)
# ============================================================
def load_checklist_from_excel():
    """Charge la checklist depuis anomaly checklist/HSE_Checklist_Final_118.xlsx."""
    import openpyxl

    xlsx_path = Path("anomaly checklist/HSE_Checklist_Final_118.xlsx")

    if not xlsx_path.exists():
        st.error(t("checklist.file_not_found", path=xlsx_path.resolve()))
        st.info(t("checklist.check_folder"))
        return []

    try:
        wb = openpyxl.load_workbook(xlsx_path, data_only=True)
        ws = wb.active

        headers = [cell.value for cell in ws[1]]
        col_index = {}
        for i, h in enumerate(headers):
            if h is not None:
                col_index[str(h).strip().lower()] = i

        with st.expander(t("checklist.debug_title")):
            st.write(t("checklist.debug_raw_headers"), headers)
            st.write(t("checklist.debug_indexed_columns"), list(col_index.keys()))

        def get_val(row_values, *names, default=None):
            for n in names:
                n_lower = n.lower().strip()
                if n_lower in col_index:
                    val = row_values[col_index[n_lower]]
                    if val is not None:
                        return val
            return default

        items = []
        for row_idx, row in enumerate(ws.iter_rows(min_row=2, values_only=True), start=2):
            item_id = get_val(row, "id")
            if not item_id:
                continue

            try:
                freq_val = get_val(row, "frequency/year", "frequency", default=0.001)
                try:
                    freq_val = float(freq_val)
                except (ValueError, TypeError):
                    freq_val = 0.001

                sev_val = get_val(row, "severity", default=3)
                try:
                    sev_val = int(float(sev_val))
                except (ValueError, TypeError):
                    sev_val = 3

                def to_bool(val):
                    if isinstance(val, bool):
                        return val
                    return str(val).strip().upper() == "TRUE"

                # --- Traductions lues dans l'Excel (colonnes *_fr / *_ar) ---
                # Les colonnes *_full (nom complet de l'équipement) sont prioritaires.
                _sec_fr = str(get_val(row, "section_name_fr", default="")).strip()
                _sec_ar = str(get_val(row, "section_name_ar", default="")).strip()
                _sym_fr = str(get_val(row, "symptome_fr", default="")).strip()
                _sym_ar = str(get_val(row, "symptome_ar", default="")).strip()
                _eq_fr_std = str(get_val(row, "equipement_type_fr", "equipement_fr", default="")).strip()
                _eq_ar_std = str(get_val(row, "equipement_type_ar", "equipement_ar", default="")).strip()
                _eq_fr_full = str(get_val(row, "equipement_type_fr_full", default="")).strip()
                _eq_ar_full = str(get_val(row, "equipement_type_ar_full", default="")).strip()
                _eq_fr = _eq_fr_full or _eq_fr_std
                _eq_ar = _eq_ar_full or _eq_ar_std
                _ev_fr = str(get_val(row, "evidence_fr", default="")).strip()
                _ev_ar = str(get_val(row, "evidence_ar", default="")).strip()
                _tr_fr = str(get_val(row, "technical_referance_fr", "technical_reference_fr", default="")).strip()
                _tr_ar = str(get_val(row, "technical_referance_ar", "technical_reference_ar", default="")).strip()

                items.append({
                    "id": str(item_id),
                    # Colonnes de base : on garde le SEUL texte anglais, même si la
                    # cellule Excel est écrite « EN / FR / AR ».
                    "section_name": strip_multilingual_suffix(
                        get_val(row, "section_name", "section", default=""), [_sec_fr], [_sec_ar]),
                    "equipement": strip_multilingual_suffix(
                        get_val(row, "equipement_type", "equipement", default=""),
                        [_eq_fr_full, _eq_fr_std], [_eq_ar_full, _eq_ar_std]),
                    # Traductions section / équipement / méthode / classe de danger
                    # (colonnes Excel *_fr et *_ar)
                    "section_name_fr": _sec_fr,
                    "section_name_ar": _sec_ar,
                    "equipement_fr": _eq_fr,
                    "equipement_ar": _eq_ar,
                    "method_fr": str(get_val(row, "frequency_method_fr", "method_fr", default="")).strip(),
                    "method_ar": str(get_val(row, "frequency_method_ar", "method_ar", default="")).strip(),
                    "hazard_class": str(get_val(row, "hazzard class", "hazzard_class", "hazard class", "hazard_class", default="")).strip(),
                    "hazard_class_fr": str(get_val(row, "hazzard_class_fr", "hazard_class_fr", default="")).strip(),
                    "hazard_class_ar": str(get_val(row, "hazzard_class_ar", "hazard_class_ar", default="")).strip(),
                    "symptome": strip_multilingual_suffix(
                        get_val(row, "symptom", "symptome", default=""), [_sym_fr], [_sym_ar]),
                    # Traductions du symptôme (colonnes Excel symptome_fr / symptome_ar)
                    "symptome_fr": _sym_fr,
                    "symptome_ar": _sym_ar,
                    "severity": sev_val,
                    "frequency": freq_val,
                    "method": str(get_val(row, "frequency_method", "method", default="Estimated")),
                    "source": str(get_val(row, "frequency_source", "source", default="")),
                    "evidence": strip_multilingual_suffix(
                        get_val(row, "evidence", default=""), [_ev_fr], [_ev_ar]),
                    # Traductions de la preuve requise et de la référence technique
                    "evidence_fr": _ev_fr,
                    "evidence_ar": _ev_ar,
                    "technical_reference": strip_multilingual_suffix(
                        get_val(row, "technical referance", "technical_referance", "technical reference", "technical_reference", default=""),
                        [_tr_fr], [_tr_ar]),
                    "technical_reference_fr": _tr_fr,
                    "technical_reference_ar": _tr_ar,
                    "target_human": to_bool(get_val(row, "target human", "target_human", default=False)),
                    "target_env": to_bool(get_val(row, "target environment", "target_env", default=False)),
                    "target_asset": to_bool(get_val(row, "target asset", "target_asset", default=False)),
                })
            except Exception as e:
                st.warning(t("checklist.row_skipped", row=row_idx, error=e))
                continue

        return items

    except Exception as e:
        st.error(t("checklist.excel_error", error=e))
        import traceback
        st.code(traceback.format_exc())
        return []


# ---- Chargement initial de la checklist ----
items = db.get_checklist_items()

# Base créée avant l'ajout des traductions (symptôme, section, équipement,
# méthode, classe de danger) : on resynchronise UNE fois par session depuis l'Excel. Les résultats d'audit
# (audit_data, mc_results...) ne sont pas touchés : ils référencent l'item par son id.
_refresh_translations = (
    bool(items)
    and not st.session_state.get("_checklist_i18n_checked", False)
    and db.checklist_needs_translation_refresh()
)
st.session_state["_checklist_i18n_checked"] = True

if not items or _refresh_translations:
    with st.spinner(t("checklist.loading")):
        excel_items = load_checklist_from_excel()
        if excel_items:
            db.save_checklist_items(excel_items)
            items = db.get_checklist_items()
            if _refresh_translations:
                st.success(t("checklist.i18n_refreshed", n=len(items)))
            else:
                st.success(t("checklist.items_loaded", n=len(items)))
        elif not items:
            st.error(t("checklist.load_failed"))
            st.stop()
        # sinon : échec du rafraîchissement -> on garde la checklist déjà en base


# ============================================================
# ÉTAPE 0 — CONFIGURATION MATRICE
# (copié et adapté de matrix_app.py)
# ============================================================
COULEURS = ["#2ECC71", "#F1C40F", "#E67E22", "#E74C3C", "#8B0000", "#5B2C6F"]
# Libellés par défaut : générés dans la langue active. Une fois enregistrés,
# ils sont retraduits à l'affichage par ui.display.tr_matrix_label().
_ACTION_KEYS = ["none", "monitoring", "planned", "priority", "immediate", "urgent"]
_SEUIL_KEYS = ["acceptable", "tolerable", "high", "critical", "unacceptable"]


def actions_par_defaut():
    return [t(f"matrix_defaults.action_{k}") for k in _ACTION_KEYS]


def labels_seuils_par_defaut():
    return [t(f"matrix_defaults.threshold_{k}") for k in _SEUIL_KEYS]


# Préfixes des clés de widgets de l'Étape 0 qui contiennent un libellé
# (sévérité, action, probabilité, seuil). Les couleurs, scores et fréquences
# ne sont volontairement PAS concernés.
_STEP0_LABEL_KEY_PREFIXES = ("sev_label_", "sev_action_", "prob_label_", "seuil_label_")


def _is_default_matrix_label(value) -> bool:
    """True si `value` est un libellé PAR DÉFAUT connu (dans n'importe quelle langue).

    Ex. « Niveau 1 », « Level 1 », « المستوى 1 », « Aucune », « Critical »...
    Un nom saisi à la main (« Négligeable », « Catastrophique »...) renvoie False :
    il ne doit jamais être écrasé lors d'un changement de langue.
    """
    raw = str(value or "").strip()
    if not raw:
        return False
    # Un libellé par défaut a au moins une traduction différente de lui-même
    # (« Acceptable » est identique en FR/EN mais devient « مقبول » en AR).
    return any(tr_matrix_label(raw, lang=code) != raw for code in LANGUAGES)


def _retranslate_default_matrix_labels():
    """Retraduit les champs de l'Étape 0 quand la langue de l'interface change.

    Streamlit conserve la valeur d'un widget qui a une `key` et ignore alors le
    nouveau `value` par défaut. On supprime donc, au changement de langue, les
    seuls champs dont le contenu est encore un libellé par défaut : ils sont
    reconstruits juste après avec la traduction de la nouvelle langue.
    """
    lang = get_current_lang()
    previous = st.session_state.get("_step0_labels_lang")
    st.session_state["_step0_labels_lang"] = lang
    if previous is None or previous == lang:
        return

    for key in list(st.session_state.keys()):
        if (
            isinstance(key, str)
            and key.startswith(_STEP0_LABEL_KEY_PREFIXES)
            and _is_default_matrix_label(st.session_state[key])
        ):
            del st.session_state[key]


def render_step_0_matrix_config():
    """Étape 0 : Configuration de la matrice de risque (UI copiée de matrix_app.py)."""

    # Doit être appelé AVANT la création des widgets ci-dessous.
    _retranslate_default_matrix_labels()

    st.header(t("step0.title"))
    st.caption(t("step0.caption"))

    # ---- CHOIX DU SITE ----
    # ⚠️ "-- Nouveau site --" reste la valeur logique (comparaisons ci-dessous) : ne pas
    # la traduire directement, seul l'affichage passe par format_func.
    sites = matrice_manager.list_sites()
    col1, col2 = st.columns([2, 2])
    choix = col1.selectbox(
        t("step0.site_label"),
        ["-- Nouveau site --"] + sites,
        format_func=lambda x: t("step0.new_site_option") if x == "-- Nouveau site --" else x,
        key="matrix_site_choice",
    )

    site_name = (
        col2.text_input(t("step0.new_site_name_label"), key="matrix_site_input")
        if choix == "-- Nouveau site --"
        else choix
    )
    site_name = site_name.strip() if site_name else ""

    if not site_name:
        st.info(t("step0.choose_or_new_site"))
        return

    if choix == "-- Nouveau site --" and site_name in sites:
        st.warning(t("step0.site_exists_warning"))

    st.markdown("---")

    # ---- NOMBRE DE NIVEAUX ----
    col1, col2 = st.columns(2)
    nb_severite = col1.number_input(
        t("step0.nb_severite_label"),
        min_value=2, max_value=6, value=5,
        key="nb_severite",
    )
    nb_probabilite = col2.number_input(
        t("step0.nb_probabilite_label"),
        min_value=2, max_value=6, value=5,
        key="nb_probabilite",
    )
    SCORE_MAX = nb_severite * nb_probabilite

    # ---- SÉVÉRITÉ ----
    st.header(t("step0.severity_header"))
    severite_existante = matrice_manager.get_matrix(site_name)

    severite_data = []
    for i in range(1, nb_severite + 1):
        ancien = next((row for row in severite_existante if row[0] == i), None)
        label_defaut = tr_matrix_label(ancien[1]) if ancien else t("step0.level_default", n=i)
        couleur_defaut = ancien[2] if ancien else COULEURS[(i - 1) % len(COULEURS)]
        _actions = actions_par_defaut()
        action_defaut = tr_matrix_label(ancien[3]) if ancien else _actions[(i - 1) % len(_actions)]

        col1, col2, col3 = st.columns([3, 2, 1])
        label = col1.text_input(t("step0.level_label", n=i), label_defaut, key=f"sev_label_{i}")
        action = col2.text_input(t("step0.action_label", n=i), action_defaut, key=f"sev_action_{i}")
        couleur = col3.color_picker(
            t("step0.color_label", n=i), couleur_defaut, key=f"sev_c_{i}",
            label_visibility="collapsed",
        )
        severite_data.append({"Level": i, "Label": label, "Action": action, "Color": couleur})

    # ---- PROBABILITÉ ----
    st.header(t("step0.probability_header"))
    st.caption(t("step0.probability_caption"))
    probabilite_existante = matrice_manager.get_probability(site_name)

    probabilite_data = []
    for i in range(1, nb_probabilite + 1):
        ancien = next((row for row in probabilite_existante if row[0] == i), None)
        label_defaut = tr_matrix_label(ancien[1]) if ancien else t("step0.level_default", n=i)
        freq_defaut = ancien[2] if ancien else ""
        couleur_defaut = ancien[3] if ancien else COULEURS[(i - 1) % len(COULEURS)]

        col1, col2, col3 = st.columns([2, 2, 1])
        label = col1.text_input(t("step0.level_label", n=i), label_defaut, key=f"prob_label_{i}")
        freq = col2.text_input(
            t("step0.frequency_label", n=i),
            freq_defaut, key=f"prob_freq_{i}",
        )
        couleur = col3.color_picker(
            t("step0.color_label", n=i), couleur_defaut, key=f"prob_c_{i}",
            label_visibility="collapsed",
        )
        probabilite_data.append({
            "Level": i, "Label": label,
            "FrequencyRange": freq, "Color": couleur,
        })

    # ---- SEUILS DE RISQUE ----
    st.header(t("step0.thresholds_header"))
    st.caption(t("step0.thresholds_caption", max=SCORE_MAX))
    seuils_existants = matrice_manager.get_thresholds(site_name)

    max_seuils = min(5, SCORE_MAX)
    nb_seuils = st.number_input(
        t("step0.nb_bands_label"),
        min_value=2, max_value=max_seuils,
        value=len(seuils_existants) if seuils_existants else 4,
        key="nb_seuils",
    )

    seuils_data = []
    for i in range(1, nb_seuils + 1):
        ancien = seuils_existants[i - 1] if len(seuils_existants) >= i else None
        score_defaut = ancien[0] if ancien else (SCORE_MAX * i) // nb_seuils
        _seuils_lbl = labels_seuils_par_defaut()
        label_defaut = tr_matrix_label(ancien[1]) if ancien else _seuils_lbl[(i - 1) % len(_seuils_lbl)]
        couleur_defaut = ancien[2] if ancien else COULEURS[(i - 1) % len(COULEURS)]

        col1, col2, col3 = st.columns([2, 2, 1])
        label = col1.text_input(t("step0.threshold_name_label", n=i), label_defaut, key=f"seuil_label_{i}")
        score = col2.number_input(
            t("step0.threshold_score_label", n=i),
            min_value=1, max_value=SCORE_MAX,
            value=min(score_defaut, SCORE_MAX),
            key=f"seuil_max_{i}",
        )
        couleur = col3.color_picker(
            t("step0.color_label", n=i), couleur_defaut, key=f"seuil_c_{i}",
            label_visibility="collapsed",
        )
        seuils_data.append({"MaxScore": score, "Label": label, "Color": couleur})

    # Le dernier seuil couvre toujours le score maximum
    seuils_data[-1]["MaxScore"] = SCORE_MAX
    seuils_data.sort(key=lambda row: row["MaxScore"])

    # ---- SAUVEGARDE ----
    st.markdown("---")
    if st.button(t("step0.save_button"), type="primary", key="save_matrix_btn"):
        labels_sev = [row["Label"] for row in severite_data]
        labels_prob = [row["Label"] for row in probabilite_data]
        scores = [row["MaxScore"] for row in seuils_data]

        if len(labels_sev) != len(set(labels_sev)) or len(labels_prob) != len(set(labels_prob)):
            st.error(t("step0.labels_unique_error"))
        elif scores != sorted(set(scores)):
            st.error(t("step0.thresholds_increasing_error"))
        else:
            try:
                matrice_manager.save_full_matrix(
                    site_name, severite_data, probabilite_data, seuils_data,
                )
                st.session_state.active_site = site_name
                st.success(t("step0.save_success", site=site_name))
                st.balloons()
            except Exception as e:
                st.error(t("step0.save_error", error=e))

    # ---- APERÇU ----
    st.header(t("step0.preview_header"))

    def niveau_de_risque(score, seuils):
        for seuil in seuils:
            if score <= seuil["MaxScore"]:
                return seuil["Label"]
        return seuils[-1]["Label"]

    tableau = []
    for prob in sorted(probabilite_data, key=lambda r: r["Level"], reverse=True):
        ligne = {t("step0.probability_column"): tr_matrix_label(prob["Label"])}
        for sev in severite_data:
            score = prob["Level"] * sev["Level"]
            niveau = tr_matrix_label(niveau_de_risque(score, seuils_data))
            ligne[tr_matrix_label(sev["Label"])] = f"{score} ({niveau})"
        tableau.append(ligne)

    st.dataframe(pd.DataFrame(tableau), use_container_width=True, hide_index=True)

    # ---- SUPPRESSION DE MATRICES ----
    st.markdown("---")
    st.header(t("step0.delete_header"))

    sites_existants = matrice_manager.list_sites()

    if not sites_existants:
        st.info(t("step0.no_matrix_to_delete"))
        return

    col1, col2 = st.columns([3, 1])

    with col1:
        site_a_supprimer = st.selectbox(
            t("step0.delete_selector_label"),
            sites_existants,
            key="delete_matrix_selector",
        )

    with col2:
        st.write("")
        st.write("")
        if st.button(t("step0.delete_button"), type="secondary", key="delete_matrix_btn"):
            st.session_state["confirm_delete"] = site_a_supprimer

    # ---- Confirmation ----
    if st.session_state.get("confirm_delete"):
        site_conf = st.session_state["confirm_delete"]

        st.warning(t("step0.delete_confirm_warning", site=site_conf))

        col1, col2 = st.columns(2)

        with col1:
            if st.button(t("step0.delete_confirm_yes"), type="primary", key="confirm_delete_yes"):
                try:
                    matrice_manager.delete_matrix(site_conf)
                    st.success(t("step0.delete_success", site=site_conf))
                    st.session_state["confirm_delete"] = None
                    st.session_state["active_site"] = None
                    st.rerun()
                except Exception as e:
                    st.error(t("step0.delete_error", error=e))

        with col2:
            if st.button(t("step0.delete_confirm_no"), key="confirm_delete_no"):
                st.session_state["confirm_delete"] = None
                st.rerun()

# ============================================================
# ÉTAPE 1 — AUDIT (Sélection matrice + symptôme + buffer)
# ============================================================
# ============================================================
# ÉTAPE 1 — AUDIT (Tableau complet avec conformité)
# ============================================================
def render_step_1_audit():
    """Étape 1 : Tableau d'audit — tous les symptômes + conformité + evidence."""

    st.header(t("step1.title"))
    st.caption(t("step1.caption"))

    # ============================================================
    # 1. VÉRIFIER QU'UNE MATRICE EXISTE
    # ============================================================
    available_sites = matrice_manager.list_sites()

    if not available_sites:
        st.error(t("step1.no_matrix"))
        st.info(t("step1.goto_step0"))
        return

    # ============================================================
    # 2. CHOIX DE LA MATRICE ACTIVE
    # ============================================================
    st.subheader(t("step1.active_matrix"))

    default_site = st.session_state.get("active_site", available_sites[0])
    if default_site not in available_sites:
        default_site = available_sites[0]

    site_name = st.selectbox(
        t("step1.choose_matrix"),
        available_sites,
        index=available_sites.index(default_site),
        key="audit_site_selector",
    )
    st.session_state.active_site = site_name

    try:
        matrix_config = RiskMatrixConfig(site_name=site_name)
        st.success(t(
            "step1.matrix_loaded",
            site=site_name,
            n_sev=len(matrix_config.severity_levels),
            n_prob=len(matrix_config.probability_levels),
        ))
    except Exception as e:
        st.error(t("common.matrix_error", error=e))
        return

    st.markdown("---")

    # ============================================================
    # 3. PRÉPARER LES DONNÉES POUR LE TABLEAU
    # ============================================================
    st.subheader(t("step1.audit_table"))

    # Charger les items depuis la DB
    all_items = db.get_checklist_items()

    # Récupérer les conformités déjà saisies (si l'utilisateur revient)
    conformites_existantes = db.get_conformity_by_audit(audit_id)

    # 🤖 Vérifications IA déjà enregistrées (ai_service.verifier_evidence)
    ai_verifications = db.get_all_ai_verifications(audit_id)
    AI_EMOJI = {
        "conforme": "✅",
        "partiel": "⚠️",
        "non_conforme": "❌",
        "absent": "❓",
    }

    # Construire le DataFrame
    rows = []
    for item in all_items:
        # Structure de item (tuple) :
        # (id, section_name, equipement, symptome, severity, frequency,
        #  method, source, evidence, target_human, target_env, target_asset)
        item_id = item[0]
        section_name = tr_section(item)
        equipement = tr_equipment(item)
        symptome = item[3]
        severity = item[4]
        evidence = tr_evidence(item)

        conformite_actuelle = conformites_existantes.get(
            item_id, CONFORMITE_A_AUDITER
        )

        # 🤖 Statut IA (résumé pour la colonne du tableau)
        ai_data = ai_verifications.get(item_id)
        if ai_data:
            ai_emoji = AI_EMOJI.get(ai_data.get("verdict", ""), "❓")
            ai_status = f"{ai_emoji} {ai_data.get('score', 0)}"
        else:
            ai_status = "—"

        rows.append({
            "ID": item_id,
            "Section": section_name,
            "Équipement": equipement,
            "Symptôme": tr_symptom(item),
            "Sévérité": severity,
            "Evidence requis": evidence,
            # Valeur AFFICHÉE ; reconvertie en code avant enregistrement.
            "Conformité": tr_conformite(conformite_actuelle),
            "IA": ai_status,
            "Note": "",
        })

    df_audit = pd.DataFrame(rows)

    # ============================================================
    # 4. AFFICHER LA PROGRESSION
    # ============================================================
    n_total = len(df_audit)
    n_traites = sum(
        1 for v in df_audit["Conformité"]
        if conformite_from_display(v) != CONFORMITE_A_AUDITER
    )

    col1, col2 = st.columns([1, 3])
    with col1:
        st.metric(t("step1.progress"), f"{n_traites} / {n_total}")

    with col2:
        if n_total > 0:
            progress_pct = n_traites / n_total
            st.progress(progress_pct)

    st.markdown("---")

   # ============================================================
    # 5. TABLEAU ÉDITABLE
    # ============================================================
    edited_df = st.data_editor(
        df_audit,
        use_container_width=True,
        hide_index=True,
        height=600,
        column_config={
            "ID": st.column_config.TextColumn(
                t("step1.col_id"),
                disabled=True,
                width="small",
            ),
            "Section": st.column_config.TextColumn(
                t("step1.col_section"),
                disabled=True,
                width="medium",
            ),
            "Équipement": st.column_config.TextColumn(
                t("step1.col_equipment"),
                disabled=True,
                width="small",
            ),
            "Symptôme": st.column_config.TextColumn(
                t("step1.col_symptom"),
                disabled=True,
                width="large",
            ),
            "Sévérité": st.column_config.NumberColumn(
                t("step1.col_severity"),
                disabled=True,
                width="small",
            ),
            "Evidence requis": st.column_config.TextColumn(
                t("step1.col_evidence_required"),
                disabled=True,
                width="medium",
            ),
            "Conformité": st.column_config.SelectboxColumn(
                t("step1.col_conformity"),
                options=conformite_display_options(),
                required=True,
                width="small",
            ),
            "IA": st.column_config.TextColumn(
                t("step1.col_ai"),
                disabled=True,
                width="small",
                help=t("step1.col_ai_help"),
            ),
            "Note": st.column_config.TextColumn(
                t("step1.col_note"),
                width="medium",
            ),
        },
        key="audit_table_editor",
    )

    # ============================================================
    # 6. BOUTON ENREGISTRER
    # ============================================================
    st.markdown("---")

    col1, col2 = st.columns([1, 3])

    with col1:
        if st.button(
            t("step1.save_conformities"),
            type="primary",
            key="save_conformites_btn",
        ):
            n_saved = 0
            n_c = n_pc = n_nc = 0

            for _, row in edited_df.iterrows():
                item_id = row["ID"]
                # Libellé affiché -> valeur métier stockée en base
                conformite = conformite_from_display(row["Conformité"])

                if conformite == CONFORMITE_A_AUDITER:
                    continue

                # Sauvegarder en DB
                if conformite == "C":
                    db.save_conformity_only(audit_id, site_name, item_id, "C")
                    n_c += 1
                else:
                    # NC ou PC → sauvegarder dans audit_data
                    db.save_conformity_only(audit_id, site_name, item_id, conformite)
                    if conformite == "NC":
                        n_nc += 1
                    else:
                        n_pc += 1

                # Mettre à jour le buffer en session_state
                item_row = db.get_item(item_id)
                if item_row:
                    st.session_state.audit_buffer[item_id] = {
                        "conformite": conformite,
                        "severity": item_row[4],
                        "freq": item_row[5],
                        "method": item_row[6],
                        "t_human": bool(item_row[9]),
                        "t_env": bool(item_row[10]),
                        "t_asset": bool(item_row[11]),
                    }

                n_saved += 1

            st.success(t(
                "step1.save_success",
                n=n_saved, n_c=n_c, n_pc=n_pc, n_nc=n_nc,
            ))
            st.rerun()

    with col2:
        st.caption(t("step1.save_hint"))

    # ============================================================
    # 7. RÉCAPITULATIF
    # ============================================================
    if n_traites > 0:
        st.markdown("---")
        st.subheader(t("step1.recap"))

        def _count_conf(code):
            return sum(
                1 for v in df_audit["Conformité"]
                if conformite_from_display(v) == code
            )

        col1, col2, col3, col4 = st.columns(4)
        col1.metric(t("step1.total_processed"), n_traites)
        col2.metric(tr_conformite("C"), _count_conf("C"))
        col3.metric(tr_conformite("PC"), _count_conf("PC"))
        col4.metric(tr_conformite("NC"), _count_conf("NC"))

        # ============================================================
    # ============================================================
    # 8. EVIDENCE — UPLOAD DE FICHIERS POUR TOUS LES SYMPTÔMES (118)
    # ============================================================
    st.markdown("---")
    st.subheader(t("step1.evidence_title"))
    st.caption(t("step1.evidence_caption"))

    # ---- Préparer la liste complète des symptômes (118) ----
    all_items = db.get_checklist_items()
    conformites_actuelles = db.get_conformity_by_audit(audit_id)

    # Charger les évidences existantes
    existing_audit_data = db.get_audit_data(audit_id)
    evidence_existing = {}
    for e in existing_audit_data:
        # e[3] = item_id, e[25] = evidence_text, e[26] = evidence_file
        item_id_e = e[3]
        has_text = bool(e[25]) if len(e) > 25 else False
        has_file = bool(e[26]) if len(e) > 26 else False
        evidence_existing[item_id_e] = {
            "text": e[25] if len(e) > 25 else "",
            "file": e[26] if len(e) > 26 else None,
            "has_text": has_text,
            "has_file": has_file,
        }

    # ---- Filtres ----
    col1, col2 = st.columns([2, 1])

    with col1:
        search_ev = st.text_input(
            t("step1.evidence_search"),
            key="evidence_search",
            placeholder=t("step1.evidence_search_placeholder"),
        )

    with col2:
        # Les valeurs restent des CODES stables ; seul l'affichage est traduit.
        FILTRES_EV = ["ALL", "ONLY_C", "ONLY_PC", "ONLY_NC", "NO_EV", "WITH_EV"]
        _FILTRE_EV_KEYS = {
            "ALL": "step1.filter_all",
            "ONLY_C": "step1.filter_only_c",
            "ONLY_PC": "step1.filter_only_pc",
            "ONLY_NC": "step1.filter_only_nc",
            "NO_EV": "step1.filter_no_evidence",
            "WITH_EV": "step1.filter_with_evidence",
        }
        filtre_ev = st.selectbox(
            t("step1.evidence_filter"),
            FILTRES_EV,
            format_func=lambda x: t(_FILTRE_EV_KEYS[x]),
            key="evidence_filter",
        )

    # ---- Construire la liste filtrée ----
    items_filtres = []
    for item in all_items:
        iid = item[0]
        section_name_i = item[1]
        symptome_i = symptom_search_text(item)  # FR + AR + EN : recherche possible dans toutes les langues
        # Preuve requise : texte anglais + FR + AR -> recherche dans toutes les langues
        evidence_requis = " ".join(
            str(item[k]) for k in (8, 23, 24) if len(item) > k and item[k]
        )
        conf_i = conformites_actuelles.get(iid, CONFORMITE_A_AUDITER)

        # Appliquer le filtre de recherche
        if search_ev:
            search_lower = search_ev.lower()
            if (search_lower not in iid.lower() and
                search_lower not in symptome_i.lower() and
                search_lower not in evidence_requis.lower()):
                continue

        # Appliquer le filtre Conformité/Evidence
        ev = evidence_existing.get(iid, {})
        has_ev = ev.get("has_text", False) or ev.get("has_file", False)

        if filtre_ev == "ONLY_C" and conf_i != "C":
            continue
        elif filtre_ev == "ONLY_PC" and conf_i != "PC":
            continue
        elif filtre_ev == "ONLY_NC" and conf_i != "NC":
            continue
        elif filtre_ev == "NO_EV" and has_ev:
            continue
        elif filtre_ev == "WITH_EV" and not has_ev:
            continue

        items_filtres.append(item)

    st.markdown(f"**{t('step1.n_symptoms_shown', n=len(items_filtres))}**")

    # ---- Dossier de stockage ----
    evidence_dir = Path("audit_evidence") / audit_id
    evidence_dir.mkdir(parents=True, exist_ok=True)

    # ---- Afficher les expanders ----
    for item in items_filtres:
        iid = item[0]
        symptome_i = tr_symptom(item)
        # Texte source (anglais) transmis à la vérification IA ; version traduite pour l'affichage
        evidence_requis = item[8] if len(item) > 8 else ""
        evidence_affiche = tr_evidence(item)
        conf_i = conformites_actuelles.get(iid, CONFORMITE_A_AUDITER)

        # Emoji selon conformité
        emoji = CONFORMITE_EMOJI.get(conf_i, "⚪")

        # Vérifier si evidence existe déjà
        ev = evidence_existing.get(iid, {})
        has_text = ev.get("has_text", False)
        has_file = ev.get("has_file", False)

        # Badge
        badge = ""
        if has_file:
            badge += " 📎"
        if has_text:
            badge += " 📝"

        # Titre du expander
        titre = f"{emoji} {iid} — {symptome_i[:70]}{badge}"

        with st.expander(titre, expanded=False):
            # ---- Evidence requis (lecture seule) ----
            st.markdown(f"**{t('step1.evidence_required')} :** {evidence_affiche}")
            st.markdown("---")

            # ---- 🤖 Résultat IA (si déjà enregistré) ----
            ai_saved = db.get_ai_verification(audit_id, iid)
            if ai_saved:
                verdict_saved = ai_saved["verdict"]
                score_saved = ai_saved["score"]
                emoji_saved = AI_EMOJI.get(verdict_saved, "❓")

                st.markdown(
                    t(
                        "step1.ai_verdict_line",
                        emoji=emoji_saved,
                        verdict=t(f"step1.ai_verdict_{verdict_saved}"),
                        score=score_saved,
                    )
                )
                if ai_saved.get("commentaire"):
                    st.caption(f"💬 {ai_saved['commentaire']}")

                if ai_saved.get("suggestions"):
                    with st.expander(t("step1.ai_suggestions_saved")):
                        for s in ai_saved["suggestions"]:
                            st.markdown(f"- {s}")

                st.markdown("---")

            # ---- Note textuelle ----
            note_val = ev.get("text", "")
            note = st.text_area(
                t("step1.evidence_note"),
                value=note_val,
                key=f"ev_text_{iid}",
                height=80,
                placeholder=t("step1.evidence_note_placeholder"),
            )

            # ---- Upload fichier ----
            uploaded_file = st.file_uploader(
                t("step1.evidence_file"),
                type=["png", "jpg", "jpeg", "pdf", "docx", "xlsx", "txt"],
                key=f"ev_file_{iid}",
            )

            # Afficher le fichier existant
            if has_file:
                st.caption(t("step1.evidence_current_file", file=ev.get("file")))

            # ---- Bouton Enregistrer ----
            if st.button(
                t("step1.evidence_save", id=iid),
                key=f"save_ev_{iid}",
            ):
                file_path = ev.get("file")  # Garder l'ancien par défaut

                if uploaded_file is not None:
                    safe_name = uploaded_file.name.replace(" ", "_")
                    file_path = evidence_dir / f"{iid}_{safe_name}"
                    with open(file_path, "wb") as f:
                        f.write(uploaded_file.getbuffer())

                # Sauvegarder dans DB
                audit_data = {
                    "conformite": conf_i if conf_i != CONFORMITE_A_AUDITER else None,
                    "evidence_text": note,
                    "evidence_file": str(file_path) if file_path else None,
                }

                # Fusionner avec les données existantes
                for e in existing_audit_data:
                    if e[3] == iid:
                        audit_data.update({
                            "n_personnes": e[5],
                            "heures_expo": e[6],
                            "p_fat": e[7],
                            "substance": e[8],
                            "taille_fuite_kg": e[9],
                            "duree_fuite_s": e[10],
                            "vitesse_vent_ms": e[11],
                            "direction_vent_deg": e[12],
                            "temperature_c": e[13],
                            "pression_hpa": e[14],
                            "humidite_pct": e[15],
                            "latitude": e[16],
                            "longitude": e[17],
                            "source_meteo": e[18],
                            "cout_action": e[19],
                            "cout_perte": e[20],
                            "duree_arret_j": e[21],
                            "cout_indispo_jour": e[22],
                            "currency": e[23],
                            "industry": e[24],
                        })
                        break

                db.save_audit_data(audit_id, site_name, iid, audit_data)
                st.success(t("step1.evidence_saved", id=iid))
                if uploaded_file is not None:
                    st.caption(t("step1.evidence_file_saved", file=file_path))

                # ============================================================
                # 🤖 VÉRIFICATION IA AUTOMATIQUE (ai_service.verifier_evidence)
                # ============================================================
                if not ai_service.is_configured():
                    st.info(t("step1.ai_not_configured"))
                else:
                    with st.spinner(t("step1.ai_verifying")):
                        ai_result = ai_service.verifier_evidence(
                            symptome_id=iid,
                            symptome_description=symptome_i,
                            evidence_requis=evidence_affiche,
                            evidence_text=note,
                            image_path=str(file_path) if file_path and uploaded_file else None,
                            conformite=conf_i if conf_i != CONFORMITE_A_AUDITER else "NC",
                        )

                    if ai_result.get("erreur"):
                        st.warning(t("step1.ai_error", error=ai_result["erreur"]))
                    else:
                        db.save_ai_verification(audit_id, iid, ai_result)

                        verdict = ai_result["verdict"]
                        score = ai_result["score"]
                        emoji = AI_EMOJI.get(verdict, "❓")
                        line = t(
                            "step1.ai_verdict_line",
                            emoji=emoji,
                            verdict=t(f"step1.ai_verdict_{verdict}"),
                            score=score,
                        )

                        if verdict == "conforme":
                            st.success(line)
                        elif verdict == "partiel":
                            st.warning(line)
                        else:
                            st.error(line)

                        if ai_result.get("commentaire"):
                            st.markdown(f"**{t('step1.ai_comment_label')} :** {ai_result['commentaire']}")

                        if ai_result.get("suggestions"):
                            with st.expander(t("step1.ai_suggestions")):
                                for s in ai_result["suggestions"]:
                                    st.markdown(f"- {s}")


# ============================================================
# (SUITE — PARTIE B À AJOUTER ICI)
# ============================================================

# ============================================================
# ÉTAPE 2 — MONTE CARLO + FORMULAIRES NC/PC + BATCH
# ============================================================
# ============================================================
# ÉTAPE 2 — MONTE CARLO + TOP 10 + FORMULAIRES
# ============================================================
def calculer_score_matrice(sev_n, freq_moyenne, df_prob):
    """
    Score de risque cohérent avec la matrice (et avec l'Étape 3) :
        score = niveau_sévérité × niveau_probabilité     (ex. 4 × 3 = 12)
    Retourne (score, niveau_probabilité).
    """
    prob_level, _, _ = freq_to_prob_level(freq_moyenne, df_prob)
    return float(sev_n) * int(prob_level), int(prob_level)


def render_step_2_monte_carlo():
    """Étape 2 : Monte Carlo batch → Top 10 → Formulaires détaillés."""

    st.header(t("step2.title"))

    # ============================================================
    # 0. VÉRIFICATIONS PRÉALABLES
    # ============================================================
    site_name = st.session_state.get("active_site")
    if not site_name:
        st.error(t("step2.no_active_matrix"))
        return

    try:
        matrix_config = RiskMatrixConfig(site_name=site_name)
        _, df_prob, _ = load_matrix_dfs(site_name)
    except Exception as e:
        st.error(t("common.matrix_error", error=e))
        return

    buffer = st.session_state.audit_buffer
    nc_pc_items = {
        iid: data for iid, data in buffer.items()
        if data["conformite"] in ("NC", "PC")
    }

    if not nc_pc_items:
        st.info(t("step2.no_nc_pc"))
        return

    st.caption(t("step2.nc_pc_count", n=len(nc_pc_items), site=site_name))

    st.markdown("---")

    # ============================================================
    # PHASE A : MONTE CARLO RAPIDE SUR TOUS LES NC/PC
    # ============================================================
    st.subheader(t("step2.phase_a_title"))
    st.caption(t("step2.phase_a_caption"))

    # Vérifier si déjà fait
    phase_a_done = st.session_state.get("phase_a_done", False)

    col1, col2 = st.columns([1, 3])

    with col1:
        if st.button(
            t("step2.run_quick"),
            type="primary",
            key="run_phase_a_btn",
        ):
            progress = st.progress(0)
            status = st.empty()
            results_a = []

            for idx, (iid, data) in enumerate(nc_pc_items.items()):
                status.text(t(
                    "step2.analyzing",
                    i=idx + 1, total=len(nc_pc_items), id=iid,
                ))

                item_row = db.get_item(iid)
                if not item_row:
                    continue

                sev_n = item_row[4]

                # Monte Carlo 10k
                try:
                   # Calculer les bornes triangulaires à partir du catalogue
                    freq_ref = data.get("freq", 0.001)
                    method_n = data.get("method", "Estimated")
                    factor = {"Direct": 2.0, "Calcule": 3.0, "Estimated": 5.0}.get(method_n, 3.0)

                    freq_min_val = freq_ref / factor
                    freq_mode_val = freq_ref
                    freq_max_val = freq_ref * factor

                    echant = simuler_frequence_triangulaire(
                        freq_min_val,
                        freq_mode_val,
                        freq_max_val,
                        n_iterations=N_ITER_APERCU,
                    )
                    stats = resumer_distribution(echant)
                    score, prob_level = calculer_score_matrice(
                        sev_n, stats["freq_moyenne"], df_prob
                    )

                    results_a.append({
                        "item_id": iid,
                        "conformite": data["conformite"],
                        "severite": sev_n,
                        "freq_moyenne": stats["freq_moyenne"],
                        "freq_p50": stats["freq_p50"],
                        "freq_p95": stats["freq_p95"],
                        "score": score,
                        "prob_level": prob_level,
                        # Conserver les données du buffer pour la Phase C
                        "buffer_data": data,
                    })
                except Exception as e:
                    st.warning(t("step2.item_error", id=iid, error=e))

                progress.progress((idx + 1) / len(nc_pc_items))

            progress.empty()
            status.empty()

            # Trier et garder Top 10
            # Tri : score matrice (sév × prob), puis fréquence moyenne × sév
            # pour départager les ex-aequo.
            results_a.sort(
                key=lambda r: (r["score"], r["freq_moyenne"] * float(r["severite"])),
                reverse=True,
            )
            top_10 = results_a[:10]

            st.session_state["phase_a_results"] = results_a
            st.session_state["top_10"] = top_10
            st.session_state["phase_a_done"] = True

            st.success(t("step2.quick_done", n=len(results_a)))
            st.rerun()

    with col2:
        if phase_a_done:
            st.info(t(
                "step2.already_done",
                n=len(st.session_state.get("top_10", [])),
            ))
        else:
            st.caption(t("step2.quick_hint"))

    # ============================================================
    # PHASE B : AFFICHAGE DU TOP 10
    # ============================================================
    if not phase_a_done:
        st.markdown("---")
        st.info(t("step2.run_phase_a_first"))
        return

    st.markdown("---")
    st.subheader(t("step2.phase_b_title"))

    top_10 = st.session_state.get("top_10", [])
    if not top_10:
        st.warning(t("step2.no_top10"))
        return

    # DataFrame pour affichage
    df_top10 = pd.DataFrame([
        {
            t("step2.col_rank"): i + 1,
            t("step2.col_id"): r["item_id"],
            t("step2.col_conformity"): tr_conformite(r["conformite"]),
            t("step2.col_severity"): r["severite"],
            t("step2.col_freq_mean"): f"{r['freq_moyenne']:.6e}",
            t("step2.col_freq_p95"): f"{r['freq_p95']:.6e}",
            t("step2.col_prob_level"): r.get("prob_level"),
            t("step2.col_score"): f"{r['score']:.0f}",
        }
        for i, r in enumerate(top_10)
    ])

    st.dataframe(df_top10, use_container_width=True, hide_index=True)

    st.info(t("step2.forms_below"))

    # ============================================================
    # PHASE C : FORMULAIRES DÉTAILLÉS POUR CHAQUE TOP 10
    # ============================================================
    st.markdown("---")
    st.subheader(t("step2.phase_c_title"))

    st.caption(t("step2.phase_c_caption"))

    for rank, top_item in enumerate(top_10, start=1):
        iid = top_item["item_id"]
        data = top_item["buffer_data"]
        conformite = top_item["conformite"]
        severity = top_item["severite"]

        # Charger les infos complètes du symptôme
        item_row = db.get_item(iid)
        if not item_row:
            continue

        section_n = tr_section(item_row)
        equip_n = tr_equipment(item_row)
        sympt_n = tr_symptom(item_row)
        sev_n = item_row[4]
        freq_n = item_row[5]
        method_n = item_row[6]
        src_n = item_row[7]
        _evidence_n = item_row[8]
        t_h = item_row[9]
        t_e = item_row[10]
        t_a = item_row[11]

        t_human = bool(t_h)
        t_env = bool(t_e)
        t_asset = bool(t_a)

        emoji = CONFORMITE_EMOJI.get(conformite, "⚠️")

        with st.expander(
            t(
                "step2.form_expander",
                rank=rank, id=iid, emoji=emoji,
                conformite=tr_conformite(conformite),
                score=f"{top_item['score']:.4e}",
            ),
            expanded=(rank == 1),
        ):

            # ---- Afficher le contexte ----
            st.markdown(f"""
**{t('step2.ctx_section')}** : {section_n}  
**{t('step2.ctx_equipment')}** : {equip_n}  
**{t('step2.ctx_symptom')}** : {sympt_n[:200]}  
**{t('step2.ctx_severity')}** : {sev_n} | **{t('step2.ctx_freq_cat')}** : {freq_n} | **{t('step2.ctx_method')}** : {tr_method_of(item_row)}
""")

            st.markdown("---")

            # ============================================================
            # MONTE CARLO (100k)
            # ============================================================
            st.markdown(f"##### {t('step2.mc_final_title')}")
            # Calculer les bornes triangulaires à partir du catalogue
            _freq_ref = data.get("freq", 0.001)
            _factor = {"Direct": 2.0, "Calcule": 3.0, "Estimated": 5.0}.get(method_n, 3.0)
            _freq_min = _freq_ref / _factor
            _freq_mode = _freq_ref
            _freq_max = _freq_ref * _factor

            st.caption(t(
                "step2.mc_bounds",
                a=f"{_freq_min:.6e}",
                m=f"{_freq_mode:.6e}",
                b=f"{_freq_max:.6e}",
            ))

            override_freq = st.checkbox(
                t("step2.mc_override"),
                value=False,
                key=f"override_{iid}",
            )

            if override_freq:
                col1, col2, col3 = st.columns(3)
                fmin = col1.number_input(
                    t("step2.mc_a_min"), value=_freq_min, format="%.8f",
                    key=f"fmin_{iid}",
                )
                fmode = col2.number_input(
                    t("step2.mc_m_mode"), value=_freq_mode, format="%.8f",
                    key=f"fmode_{iid}",
                )
                fmax = col3.number_input(
                    t("step2.mc_b_max"), value=_freq_max, format="%.8f",
                    key=f"fmax_{iid}",
                )
            else:
                fmin = _freq_min
                fmode = _freq_mode
                fmax = _freq_max

            st.markdown("")

            # ============================================================
            # CIBLE HUMAINE
            # ============================================================
            n_personnes = heures_expo = p_fat = None

            if t_human:
                st.markdown(f"##### {t('step2.human_title')}")

                col1, col2, col3 = st.columns(3)
                n_personnes = col1.number_input(
                    t("step2.human_n_people"), min_value=0, value=5,
                    key=f"npers_{iid}",
                )
                heures_expo = col2.number_input(
                    t("step2.human_expo_hours"), min_value=0.0, value=2000.0,
                    key=f"hexpo_{iid}",
                )
                p_fat = col3.number_input(
                    t("step2.human_p_fat"),
                    min_value=0.0, max_value=1.0, value=0.1, step=0.01,
                    key=f"pfat_{iid}",
                )
                st.markdown("")

            # ============================================================
            # CIBLE ENVIRONNEMENTALE
            # ============================================================
            substance_env = None
            taille_fuite = duree_fuite = None
            vitesse_vent = direction_vent = temperature = None
            latitude = longitude = None
            source_meteo = "manuelle"

            if t_env:
                st.markdown(f"##### {t('step2.env_title')}")

                # ---- Substance et fuite ----
                col1, col2 = st.columns(2)
                substance_env = col1.selectbox(
                    t("step2.env_substance"), substance_options,
                    format_func=lambda x: (
                        t("common.select_placeholder")
                        if x == "-- Sélectionner --" else x
                    ),
                    key=f"subenv_{iid}",
                )
                taille_fuite = col2.number_input(
                    t("step2.env_leak_size"), min_value=0.0, value=50.0,
                    key=f"tfuite_{iid}",
                )

                col1, col2 = st.columns(2)
                duree_fuite = col1.number_input(
                    t("step2.env_leak_duration"), min_value=1.0, value=300.0,
                    key=f"dfuite_{iid}",
                )
                vitesse_vent = col2.number_input(
                    t("step2.env_wind_speed"), min_value=0.1, value=3.0,
                    key=f"vvent_{iid}",
                )

                col1, col2 = st.columns(2)
                direction_vent = col1.number_input(
                    t("step2.env_wind_dir"), min_value=0.0, max_value=360.0, value=270.0,
                    key=f"dvent_{iid}",
                )
                temperature = col2.number_input(
                    t("step2.env_temperature"), value=25.0,
                    key=f"temp_{iid}",
                )

                st.markdown("")
# ---- Plot Concentration vs Distance ----
                st.markdown(f"**{t('step2.env_curve_title')}**")
                st.caption(t("step2.env_curve_caption"))

                if st.button(
                    t("step2.env_curve_button"),
                    key=f"plot_disp_{iid}",
                ):
                    if substance_env and substance_env != "-- Sélectionner --":
                        try:
                            from chemical_db_interface import get_chemical_properties
                            import numpy as np

                            # Propriétés chimiques
                            props = get_chemical_properties(substance_env)
                            seuil_mg_m3 = props["seuil_toxique_mg_m3"]
                            seuil_g_m3 = seuil_mg_m3 / 1000.0

                            # Débit d'émission
                            debit_g_s = (taille_fuite * 1000.0) / duree_fuite

                            # Classe de stabilité
                            from dispersion_aloha import (
                                determiner_classe_stabilite,
                                concentration_axe,
                                calculer_distance_impact,
                            )
                            classe = determiner_classe_stabilite(vitesse_vent)

                            # Distances (1 m à 5000 m)
                            distances = np.linspace(1, 5000, 500)
                            concentrations = np.array([
                                concentration_axe(d, debit_g_s, vitesse_vent, classe)
                                for d in distances
                            ])
                            concentrations_mg = concentrations * 1000.0  # g/m³ → mg/m³

                            # Distance d'impact
                            d_impact = calculer_distance_impact(
                                debit_g_s, vitesse_vent, classe, seuil_g_m3
                            )

                            # Créer le plot avec Plotly
                            import plotly.graph_objects as go

                            fig = go.Figure()

                            # Courbe de concentration
                            fig.add_trace(go.Scatter(
                                x=distances,
                                y=concentrations_mg,
                                mode="lines",
                                name=t("step2.env_concentration"),
                                line=dict(color="#2c5282", width=2),
                            ))

                            # Ligne horizontale : seuil toxique
                            fig.add_hline(
                                y=seuil_mg_m3,
                                line_dash="dash",
                                line_color="orange",
                                annotation_text=t("step2.env_toxic_threshold_line", value=seuil_mg_m3),
                                annotation_position="top right",
                            )

                            # Point rouge : distance d'impact
                            if d_impact > 0 and d_impact <= 5000:
                                fig.add_trace(go.Scatter(
                                    x=[d_impact],
                                    y=[seuil_mg_m3],
                                    mode="markers",
                                    name=t("step2.env_impact_distance_pt", value=f"{d_impact:.0f}"),
                                    marker=dict(color="red", size=14, symbol="circle"),
                                ))

                            fig.update_layout(
                                title=t("step2.env_plot_title", substance=substance_env),
                                xaxis_title=t("step2.env_axis_distance"),
                                yaxis_title=t("step2.env_axis_concentration"),
                                height=450,
                                hovermode="x unified",
                                legend=dict(
                                    yanchor="top", y=0.99,
                                    xanchor="right", x=0.99,
                                ),
                            )

                            show_plotly(fig)

                            # Résumé numérique
                            col1, col2, col3 = st.columns(3)
                            col1.metric(
                                t("step2.env_toxic_threshold"),
                                f"{seuil_mg_m3:.2f} mg/m³",
                            )
                            col2.metric(
                                t("step2.env_impact_distance"),
                                f"{d_impact:.0f} m",
                            )
                            col3.metric(
                                t("step2.env_stability_class"),
                                classe,
                            )

                        except Exception as e:
                            st.error(t("common.generic_error", error=e))
                            import traceback
                            st.code(traceback.format_exc())
                    else:
                        st.warning(t("step2.env_select_substance_first"))

                st.markdown("")
            # ============================================================
            # CIBLE MATÉRIELLE
            # ============================================================
            cout_action = cout_perte = duree_arret = cout_indispo_jour = None
            currency = DEFAULT_CURRENCY
            industry = "generic"

            if t_asset:
                st.markdown(f"##### {t('step2.asset_title')}")

                col1, col2 = st.columns(2)
                currency = col1.selectbox(
                    t("step2.asset_currency"),
                    list(CURRENCIES.keys()),
                    index=list(CURRENCIES.keys()).index(DEFAULT_CURRENCY),
                    format_func=lambda c: f"{c} — {CURRENCIES[c]['label']}",
                    key=f"curr_{iid}",
                )
                industry = col2.selectbox(
                    t("step2.asset_industry"),
                    ["oil_gas", "petrochemical", "pharma", "manufacturing", "mining", "generic"],
                    index=5,
                    format_func=tr_industry,
                    key=f"ind_{iid}",
                )

                symbol = CURRENCIES[currency]["symbol"]

                col1, col2 = st.columns(2)
                cout_action = col1.number_input(
                    t("step2.asset_action_cost", symbol=symbol),
                    min_value=0.0, value=15000.0,
                    key=f"cact_{iid}",
                )
                cout_perte = col2.number_input(
                    t("step2.asset_loss_cost", symbol=symbol),
                    min_value=0.0, value=200000.0,
                    key=f"cperte_{iid}",
                )

                col1, col2 = st.columns(2)
                duree_arret = col1.number_input(
                    t("step2.asset_downtime_days"), min_value=0.0, value=10.0,
                    key=f"darret_{iid}",
                )

                default_indispo = get_default_indisponibilite(industry)
                if currency != "EUR":
                    default_indispo = convert_from_eur(default_indispo, currency)

                cout_indispo_jour = col2.number_input(
                    t("step2.asset_downtime_cost", symbol=symbol),
                    min_value=0.0, value=float(default_indispo),
                    key=f"cindispo_{iid}",
                )

                st.markdown("")

            # ============================================================
            # BOUTON ENREGISTRER (POUR CE SYMPTÔME)
            # ============================================================
            st.markdown("---")

            if st.button(
                t("step2.save_form", id=iid),
                type="primary",
                key=f"save_form_{iid}",
            ):
                # Mettre à jour le buffer
                st.session_state.audit_buffer[iid].update({
                    "freq_min": fmin,
                    "freq_mode": fmode,
                    "freq_max": fmax,
                    "n_personnes": n_personnes,
                    "heures_expo": heures_expo,
                    "p_fat": p_fat,
                    "substance_env": substance_env,
                    "taille_fuite": taille_fuite,
                    "duree_fuite": duree_fuite,
                    "vitesse_vent": vitesse_vent,
                    "direction_vent": direction_vent,
                    "temperature": temperature,
                    "latitude": latitude,
                    "longitude": longitude,
                    "source_meteo": source_meteo,
                    "cout_action": cout_action,
                    "cout_perte": cout_perte,
                    "duree_arret": duree_arret,
                    "cout_indispo_jour": cout_indispo_jour,
                    "currency": currency,
                    "industry": industry,
                })
                st.success(t("step2.form_saved", id=iid))

    # ============================================================
    # BOUTON FINAL : LANCER L'ANALYSE COMPLÈTE
    # ============================================================
    st.markdown("---")
    st.subheader(t("step2.final_title"))

    st.caption(t("step2.final_caption"))

    if st.button(
        t("step2.final_button"),
        type="primary",
        key="run_final_analysis_btn",
    ):
        progress = st.progress(0)
        status = st.empty()

        for idx, top_item in enumerate(top_10):
            iid = top_item["item_id"]
            data = st.session_state.audit_buffer.get(iid)
            if not data:
                continue

            status.text(t(
                "step2.final_analyzing",
                i=idx + 1, total=len(top_10), id=iid,
            ))

            item_row = db.get_item(iid)
            # بدل (_, section_n, equip_n, ...) = item_row
            section_n = item_row[1]
            equip_n = item_row[2]
            sympt_n = item_row[3]
            sev_n = item_row[4]
            freq_n = item_row[5]
            method_n = item_row[6]
            src_n = item_row[7]
            evidence_n = item_row[8]
            t_h = item_row[9]
            t_e = item_row[10]
            t_a = item_row[11]

            # Monte Carlo 100k
            # Bornes triangulaires : si le formulaire du symptôme n'a pas été
            # enregistré, on retombe sur les valeurs du catalogue (même repli
            # pour la simulation ET pour l'enregistrement du résultat).
            freq_min_final = data.get("freq_min", data["freq"])
            freq_mode_final = data.get("freq_mode", data["freq"])
            freq_max_final = data.get("freq_max", data["freq"] * 3)
            echant = simuler_frequence_triangulaire(
                freq_min_final,
                freq_mode_final,
                freq_max_final,
                n_iterations=N_ITER_FINAL,
            )
            stats = resumer_distribution(echant)
            position = matrix_config.positionner(sev_n, stats["freq_moyenne"])
            score, _ = calculer_score_matrice(sev_n, stats["freq_moyenne"], df_prob)

            # Sauvegarder audit_data complet
            audit_data = {
                "conformite": data["conformite"],
                "n_personnes": data.get("n_personnes"),
                "heures_expo": data.get("heures_expo"),
                "p_fat": data.get("p_fat"),
                "substance": data.get("substance_env"),
                "taille_fuite_kg": data.get("taille_fuite"),
                "duree_fuite_s": data.get("duree_fuite"),
                "vitesse_vent_ms": data.get("vitesse_vent"),
                "direction_vent_deg": data.get("direction_vent"),
                "temperature_c": data.get("temperature"),
                "latitude": data.get("latitude"),
                "longitude": data.get("longitude"),
                "source_meteo": data.get("source_meteo"),
                "cout_action": data.get("cout_action"),
                "cout_perte": data.get("cout_perte"),
                "duree_arret_j": data.get("duree_arret"),
                "cout_indispo_jour": data.get("cout_indispo_jour"),
                "currency": data.get("currency"),
                "industry": data.get("industry"),
            }
            db.save_audit_data(audit_id, site_name, iid, audit_data)

            # MC result
            db.save_mc_result(audit_id, iid, {
                "n_iterations": N_ITER_FINAL,
                "freq_min": freq_min_final,
                "freq_mode": freq_mode_final,
                "freq_max": freq_max_final,
                **stats,
                "severite": sev_n,
                "score_risque": score,
                "niveau_severite_matrice": position["label_severite"],
                "niveau_probabilite_matrice": position["label_probabilite"],
                "niveau_risque_matrice": position["niveau_risque"],
                "couleur_matrice": position["couleur"],
            })

            # Human
            if t_h and data.get("n_personnes"):
                try:
                    hr = evaluer_risque_humain(
                        symptom_id=iid,
                        frequence_par_an=stats["freq_moyenne"],
                        nb_personnes_exposees=data["n_personnes"],
                        duree_exposition_h_an=data["heures_expo"],
                        proba_deces=data["p_fat"],
                    )
                    db.save_human_risk(audit_id, iid, hr)
                except Exception:
                    pass

            # Cost-benefit
            if t_a and data.get("cout_action") is not None:
                try:
                    cb = evaluer_cout_benefice(
                        symptom_id=iid,
                        frequence_par_an=stats["freq_moyenne"],
                        cout_action_corrective=data["cout_action"],
                        cout_perte_potentielle=data.get("cout_perte", 0.0),
                        duree_indisponibilite_j=data.get("duree_arret", 0.0),
                        cout_indisponibilite_par_jour=data.get("cout_indispo_jour", 0.0),
                        currency=data.get("currency", DEFAULT_CURRENCY),
                        industry=data.get("industry", "generic"),
                    )
                    db.save_cost_benefit(audit_id, iid, cb)
                except Exception as e:
                    st.error(t("step2.cost_benefit_failed", id=iid, error=e))
                    import traceback
                    st.code(traceback.format_exc())

            # Dispersion
            if t_e and data.get("substance_env") and data["substance_env"] != "-- Sélectionner --":
                try:
                    disp = evaluer_dispersion(
                        symptom_id=iid,
                        substance=data["substance_env"],
                        taille_fuite_kg=data["taille_fuite"],
                        duree_fuite_s=data["duree_fuite"],
                        vitesse_vent_m_s=data["vitesse_vent"],
                        direction_vent_deg=data["direction_vent"],
                        temperature_c=data["temperature"],
                        source_meteo=data.get("source_meteo", "manuelle"),
                    )
                    db.save_dispersion(audit_id, iid, disp)
                except Exception:
                    pass

            progress.progress((idx + 1) / len(top_10))

        progress.empty()
        status.empty()
        st.success(t("step2.final_done", n=len(top_10)))
        st.session_state.batch_done = True
        st.info(t("step2.goto_step3"))
# ============================================================
# ÉTAPE 3 — RÉSULTATS + CLASSIFICATION
# ============================================================
def render_step_3_results():
    """Étape 3 : Résultats + classification dans la matrice active."""

    st.header(t("step3.title"))

    if not st.session_state.batch_done:
        st.info(t("step3.batch_not_run"))
        return

    # ---- RÉCUPÉRER LES RÉSULTATS ----
    mc_results = db.get_mc_results(audit_id)

    if not mc_results:
        st.warning(t("step3.no_results"))
        return

    # ---- CHARGER LA MATRICE ACTIVE ----
    site_name = st.session_state.get("active_site")
    if not site_name:
        st.error(t("step3.no_active_matrix"))
        return

    try:
        df_sev, df_prob, df_seuils = load_matrix_dfs(site_name)
    except Exception as e:
        st.error(t("step3.matrix_load_error", error=e))
        return

    st.caption(t("step3.active_matrix", site=site_name))

    # ---- CONSTRUIRE LE DATAFRAME ----
    df = pd.DataFrame(mc_results, columns=[
        "id", "audit_id", "item_id", "n_iterations",
        "freq_min", "freq_mode", "freq_max",
        "freq_moyenne", "freq_p05", "freq_p50", "freq_p95",
        "severite", "score_risque",
        "niveau_sev", "niveau_prob", "niveau_risque", "couleur", "created_at",
    ])

    # Renommer pour cohérence avec results_viewer
    df = df.rename(columns={"severite": "severite"})

    # ---- CLASSIFIER SELON LA MATRICE ACTIVE ----
    df_classified = classify_results_df(df, df_sev, df_prob, df_seuils)

    # Trier par risque décroissant
    df_classified = df_classified.sort_values("risk_score", ascending=False)
    df_classified["rank"] = range(1, len(df_classified) + 1)

    # ---- METRIC CARDS ----
    st.markdown("---")
    st.subheader(t("step3.overview"))
    render_metric_cards(df_classified, df_seuils)

    st.markdown("---")

    # ---- RÉCUPÉRER RISQUE HUMAIN (PLL / FAR / LIRA) ----
    hr_rows = db.get_human_risk(audit_id)
    df_hr = pd.DataFrame(hr_rows, columns=[
        "id", "audit_id", "item_id", "frequence_par_an",
        "nb_personnes_exposees", "duree_exposition_h_an",
        "proba_deces", "proba_deces_est_defaut",
        "pll", "far", "lira", "created_at",
    ])
    if not df_hr.empty:
        df_hr = df_hr.merge(
            df_classified[["item_id", "severite", "risk_class", "risk_color"]],
            on="item_id", how="left",
        )

    # ---- RÉCUPÉRER COÛT-BÉNÉFICE ----
    cb_rows = db.get_cost_benefit(audit_id)
    df_cb = pd.DataFrame(cb_rows, columns=[
        "id", "audit_id", "item_id", "currency", "industry",
        "frequence_par_an", "cout_action_corrective",
        "cout_perte_potentielle", "duree_indisponibilite_j",
        "cout_indisponibilite_par_jour", "perte_annuelle_attendue",
        "ratio_benefice_cout", "recommandation", "created_at",
    ])
    if df_cb.empty:
        st.warning(t("step3.no_cost_benefit"))

    # ---- RÉCUPÉRER DISPERSION ----
    disp_rows = db.get_dispersion(audit_id)
    df_disp = pd.DataFrame(disp_rows, columns=[
        "id", "audit_id", "item_id", "substance", "taille_fuite_kg",
        "duree_fuite_s", "vitesse_vent_ms", "direction_vent_deg",
        "temperature_c", "pression_hpa", "humidite_pct",
        "latitude", "longitude", "classe_stabilite",
        "distance_impact_m", "source_meteo", "created_at",
    ])

    # ---- TABS INTERNES (dynamiques selon les données disponibles) ----
    tab_labels = [
        t("step3.tab_top10"),
        t("step3.tab_matrix"),
        t("step3.tab_all"),
        t("step3.tab_plots"),
        t("step3.tab_human"),
    ]
    if not df_cb.empty:
        tab_labels.append(t("step3.tab_cost_benefit"))
    if not df_disp.empty:
        tab_labels.append(t("step3.tab_dispersion"))

    _tabs = st.tabs(tab_labels)
    tab_top, tab_matrix, tab_all, tab_plots, tab_human = _tabs[:5]
    _next = 5
    tab_cb = None
    tab_disp = None
    if not df_cb.empty:
        tab_cb = _tabs[_next]
        _next += 1
    if not df_disp.empty:
        tab_disp = _tabs[_next]
        _next += 1

    # ---- TAB 1 : TOP 10 ----
    with tab_top:
        st.subheader(t("step3.top10_title"))

        # On garde risk_color dans top10 (utilisé pour les badges plus bas),
        # mais on ne l'affiche pas dans le tableau.
        top10 = df_classified.head(10)[
            ["rank", "item_id", "freq_moyenne", "freq_p95",
             "severite", "prob_label", "risk_score", "risk_class", "risk_color"]
        ]

        top10_display = top10.drop(columns=["risk_color"]).copy()
        top10_display["prob_label"] = top10_display["prob_label"].apply(tr_matrix_label)
        top10_display["risk_class"] = top10_display["risk_class"].apply(tr_matrix_label)
        top10_display = top10_display.rename(columns={
            "rank": t("step3.col_rank"),
            "item_id": t("step3.col_symptom"),
            "freq_moyenne": t("step3.col_freq_mean"),
            "freq_p95": t("step3.col_freq_p95"),
            "severite": t("step3.col_severity"),
            "prob_label": t("step3.col_probability"),
            "risk_score": t("step3.col_risk_score"),
            "risk_class": t("step3.col_risk_class"),
        })

        st.dataframe(
            top10_display,
            use_container_width=True,
            hide_index=True,
        )

        # Affichage carte par carte
        st.markdown(f"### {t('step3.details')}")
        for _, row in top10.iterrows():
            col1, col2, col3 = st.columns([1, 4, 2])

            with col1:
                st.markdown(f"""
<div style="text-align:center;padding:1rem;background:#1e3a5f;
color:white;border-radius:12px;">
<div style="font-size:0.8rem;opacity:0.8;">{t('step3.rank_badge')}</div>
<div style="font-size:2rem;font-weight:700;">#{row['rank']}</div>
</div>
""", unsafe_allow_html=True)

            with col2:
                st.markdown(f"### {row['item_id']}")
                st.markdown(
                    f"<span style='background:{row['risk_color']};padding:0.3rem 0.8rem;"
                    f"border-radius:6px;color:white;font-weight:700;'>"
                    f"{tr_matrix_label(row['risk_class'])}</span>",
                    unsafe_allow_html=True,
                )

            with col3:
                st.metric(t("step3.col_severity"), f"{row['severite']}")
                st.metric(t("step3.col_probability"), tr_matrix_label(row["prob_label"]))
                st.metric(t("step3.col_freq_mean"), f"{row['freq_moyenne']:.6f}")

            st.markdown("---")

    # ---- TAB 2 : MATRICE HEATMAP ----
    with tab_matrix:
        st.subheader(t("step3.matrix_title"))
        st.caption(t("step3.matrix_caption", site=site_name))

        render_heatmap(df_classified, df_sev, df_prob, df_seuils)

    # ---- TAB 3 : TOUS ----
    with tab_all:
        st.subheader(t("step3.all_title"))

        # Filtre par classe — les VALEURS restent celles stockées en base,
        # seul l'affichage passe par tr_matrix_label().
        available_classes = df_seuils["risk_label"].tolist()
        filter_class = st.multiselect(
            t("step3.filter_by_class"),
            available_classes,
            default=available_classes,
            format_func=tr_matrix_label,
            key="filter_class_results",
        )

        df_display = df_classified[df_classified["risk_class"].isin(filter_class)]

        df_display_tr = df_display[[
            "rank", "item_id", "severite", "freq_moyenne",
            "prob_label", "risk_score", "risk_class",
        ]].copy()
        df_display_tr["prob_label"] = df_display_tr["prob_label"].apply(tr_matrix_label)
        df_display_tr["risk_class"] = df_display_tr["risk_class"].apply(tr_matrix_label)

        st.dataframe(
            df_display_tr.rename(columns={
                "rank": t("step3.col_rank"),
                "item_id": t("step3.col_symptom"),
                "severite": t("step3.col_severity"),
                "freq_moyenne": t("step3.col_freq_mean"),
                "prob_label": t("step3.col_probability"),
                "risk_score": t("step3.col_risk_score"),
                "risk_class": t("step3.col_risk_class"),
            }),
            use_container_width=True,
            hide_index=True,
        )

        # Export CSV
        csv = df_classified.to_csv(index=False).encode("utf-8")
        st.download_button(
            t("step3.download_csv"),
            csv,
            f"audit_{audit_id}_results.csv",
            "text/csv",
        )

    # ---- TAB 4 : GRAPHIQUES ----
    with tab_plots:
        st.subheader(t("step3.plots_title"))
        render_plots(df_classified, df_seuils, top_n=10)

    # ---- TAB 5 : RISQUE HUMAIN (PLL / FAR / LIRA) ----
    with tab_human:
        st.subheader(t("step3.human_title"))

        if df_hr.empty:
            st.info(t("step3.human_empty"))
        else:
            df_hr_disp = df_hr.copy()
            # Code stable -> libellé traduit (la classification reste identique
            # quelle que soit la langue).
            df_hr_disp["niveau_lira_code"] = df_hr_disp["lira"].apply(niveau_lira)
            df_hr_disp["niveau_lira"] = df_hr_disp["niveau_lira_code"].apply(tr_lira)

            st.caption(t(
                "step3.lira_thresholds",
                high=f"{SEUILS_LIRA_INDICATIFS['inacceptable']:.0e}",
                low=f"{SEUILS_LIRA_INDICATIFS['negligeable']:.0e}",
            ))

            st.dataframe(
                df_hr_disp[[
                    "item_id", "nb_personnes_exposees", "duree_exposition_h_an",
                    "proba_deces", "pll", "far", "lira", "niveau_lira",
                ]].rename(columns={
                    "item_id": t("step3.col_symptom"),
                    "nb_personnes_exposees": t("step3.col_n_people"),
                    "duree_exposition_h_an": t("step3.col_expo_hours"),
                    "proba_deces": t("step3.col_p_death"),
                    "pll": t("step3.col_pll"),
                    "far": t("step3.col_far"),
                    "lira": t("step3.col_lira"),
                    "niveau_lira": t("step3.col_lira_level"),
                }),
                use_container_width=True,
                hide_index=True,
            )

            st.markdown(f"### {t('step3.details_by_symptom')}")
            for _, row in df_hr_disp.iterrows():
                with st.expander(f"{row['item_id']} — {row['niveau_lira']}"):
                    c1, c2, c3 = st.columns(3)
                    c1.metric(t("step3.metric_pll"), f"{row['pll']:.3e}")
                    c2.metric(t("step3.metric_far"), f"{row['far']:.3f}")
                    c3.metric(t("step3.metric_lira"), f"{row['lira']:.3e}")
                    st.caption(
                        t(
                            "step3.human_detail_caption",
                            freq=f"{row['frequence_par_an']:.3e}",
                            n=int(row["nb_personnes_exposees"]),
                            hours=f"{row['duree_exposition_h_an']:.0f}",
                            p=f"{row['proba_deces']:.2f}",
                        )
                        + (
                            " " + t("step3.default_value")
                            if row["proba_deces_est_defaut"] else ""
                        )
                    )

            # Graphique LIRA par symptôme
            fig_lira = go.Figure()
            fig_lira.add_trace(go.Bar(
                x=df_hr_disp["item_id"], y=df_hr_disp["lira"],
                marker_color="#c0392b", name=t("step3.col_lira"),
            ))
            fig_lira.add_hline(
                y=SEUILS_LIRA_INDICATIFS["inacceptable"],
                line_dash="dash", line_color="red",
                annotation_text=t("step3.lira_line_unacceptable"),
            )
            fig_lira.add_hline(
                y=SEUILS_LIRA_INDICATIFS["negligeable"],
                line_dash="dash", line_color="green",
                annotation_text=t("step3.lira_line_negligible"),
            )
            fig_lira.update_layout(
                yaxis_type="log", title=t("step3.lira_chart_title"), height=400,
            )
            show_plotly(fig_lira)

    # ---- TAB 6 : COÛT-BÉNÉFICE ----
    if tab_cb is not None:
        with tab_cb:
            st.subheader(t("step3.cb_title"))
            st.caption(t("step3.cb_caption"))

            df_cb_disp = df_cb.copy()
            df_cb_disp["perte_fmt"] = df_cb_disp.apply(
                lambda r: format_amount(r["perte_annuelle_attendue"], r["currency"]),
                axis=1,
            )
            df_cb_disp["cout_fmt"] = df_cb_disp.apply(
                lambda r: format_amount(r["cout_action_corrective"], r["currency"]),
                axis=1,
            )
            # Code stable -> texte traduit (compatible avec les anciennes lignes)
            df_cb_disp["reco_fmt"] = df_cb_disp["recommandation"].apply(tr_reco)

            st.dataframe(
                df_cb_disp[[
                    "item_id", "cout_fmt", "perte_fmt",
                    "ratio_benefice_cout", "reco_fmt",
                ]].rename(columns={
                    "item_id": t("step3.col_symptom"),
                    "cout_fmt": t("step3.col_action_cost"),
                    "perte_fmt": t("step3.col_annual_loss"),
                    "ratio_benefice_cout": t("step3.col_ratio"),
                    "reco_fmt": t("step3.col_recommendation"),
                }),
                use_container_width=True,
                hide_index=True,
            )

            st.markdown(f"### {t('step3.details_by_symptom')}")
            for _, row in df_cb_disp.iterrows():
                with st.expander(t(
                    "step3.cb_expander",
                    id=row["item_id"],
                    ratio=f"{row['ratio_benefice_cout']:.2f}",
                )):
                    c1, c2, c3 = st.columns(3)
                    c1.metric(t("step3.col_action_cost"), row["cout_fmt"])
                    c2.metric(t("step3.metric_loss_avoided"), row["perte_fmt"])
                    c3.metric(t("step3.col_ratio"), f"{row['ratio_benefice_cout']:.2f}")
                    st.info(row["reco_fmt"])

            fig_cb = go.Figure()
            fig_cb.add_trace(go.Bar(
                x=df_cb_disp["item_id"], y=df_cb_disp["ratio_benefice_cout"],
                marker_color=[
                    "#27ae60" if v >= 1 else "#e67e22" if v >= 0.5 else "#c0392b"
                    for v in df_cb_disp["ratio_benefice_cout"]
                ],
            ))
            fig_cb.add_hline(y=1, line_dash="dash", line_color="gray",
                              annotation_text=t("step3.cb_breakeven"))
            fig_cb.update_layout(title=t("step3.cb_chart_title"), height=400)
            show_plotly(fig_cb)

    # ---- TAB 7 : DISPERSION ----
    if tab_disp is not None:
        with tab_disp:
            st.subheader(t("step3.disp_title"))
            df_disp_tr = df_disp[[
                "item_id", "substance", "taille_fuite_kg", "duree_fuite_s",
                "vitesse_vent_ms", "direction_vent_deg", "temperature_c",
                "classe_stabilite", "distance_impact_m", "source_meteo",
            ]].copy()
            df_disp_tr["source_meteo"] = df_disp_tr["source_meteo"].apply(tr_meteo)

            st.dataframe(
                df_disp_tr.rename(columns={
                    "item_id": t("step3.col_symptom"),
                    "substance": t("step3.col_substance"),
                    "taille_fuite_kg": t("step3.col_leak_size"),
                    "duree_fuite_s": t("step3.col_leak_duration"),
                    "vitesse_vent_ms": t("step3.col_wind"),
                    "direction_vent_deg": t("step3.col_wind_dir"),
                    "temperature_c": t("step3.col_temperature"),
                    "classe_stabilite": t("step3.col_stability"),
                    "distance_impact_m": t("step3.col_impact_distance"),
                    "source_meteo": t("step3.col_weather_source"),
                }),
                use_container_width=True,
                hide_index=True,
            )


# ============================================================
# ÉTAPE 5 — PLAN PDCA (IA) — ai_service.generer_plan_pdca
# ============================================================
def render_step_5_pdca():
    """Étape 5 : Génération d'un plan PDCA pour un symptôme NC/PC."""

    st.header(t("step5.title"))
    st.caption(t("step5.caption"))

    # ---- Vérifications ----
    if not st.session_state.batch_done:
        st.info(t("step5.batch_required"))
        return

    mc_results = db.get_mc_results(audit_id)
    if not mc_results:
        st.warning(t("step5.no_results"))
        return

    # ---- Préparer la liste des symptômes NC/PC ----
    conformites = db.get_conformity_by_audit(audit_id)
    nc_pc_ids = [
        iid for iid, conf in conformites.items()
        if conf in ("NC", "PC")
    ]

    if not nc_pc_ids:
        st.info(t("step5.no_nc_pc"))
        return

    # ---- DataFrame MC pour tri ----
    df_mc = pd.DataFrame(mc_results, columns=[
        "id", "audit_id", "item_id", "n_iterations",
        "freq_min", "freq_mode", "freq_max",
        "freq_moyenne", "freq_p05", "freq_p50", "freq_p95",
        "severite", "score_risque",
        "niveau_sev", "niveau_prob", "niveau_risque", "couleur", "created_at",
    ])
    df_mc = df_mc.sort_values("score_risque", ascending=False)

    # Filtrer : seulement NC/PC
    df_nc_pc = df_mc[df_mc["item_id"].isin(nc_pc_ids)]

    if df_nc_pc.empty:
        st.info(t("step5.no_nc_pc_mc"))
        return

    # ---- Sélection du symptôme ----
    st.subheader(t("step5.choose_symptom_header"))
    st.caption(t("step5.choose_symptom_caption"))

    # Construire les options avec description
    options = []
    for _, row in df_nc_pc.iterrows():
        iid = row["item_id"]
        item_row = db.get_item(iid)
        if not item_row:
            continue
        label = t(
            "step5.symptom_option_label",
            id=iid,
            severity=row["severite"],
            score=row["score_risque"],
            symptom=tr_symptom(item_row)[:60],
        )
        options.append((iid, label))

    if not options:
        st.warning(t("step5.no_valid_symptom"))
        return

    labels = [opt[1] for opt in options]
    selected_label = st.selectbox(
        t("step5.symptom_selector"),
        labels,
        key="pdca_symptom_selector",
    )

    # Retrouver l'ID
    selected_idx = labels.index(selected_label)
    selected_id = options[selected_idx][0]

    # ---- Infos du symptôme ----
    item_row = db.get_item(selected_id)
    mc_row = df_nc_pc[df_nc_pc["item_id"] == selected_id].iloc[0]

    st.markdown("---")

    col1, col2 = st.columns([2, 1])
    with col1:
        st.markdown(f"**{t('step5.field_id')}** : `{selected_id}`")
        st.markdown(f"**{t('step5.field_section')}** : {tr_section(item_row)}")
        st.markdown(f"**{t('step5.field_equipment')}** : {tr_equipment(item_row)}")
        st.markdown(f"**{t('step5.field_symptom')}** : {tr_symptom(item_row)}")
    with col2:
        st.metric(t("step5.metric_severity"), item_row[4])
        st.metric(t("step5.metric_conformity"), tr_conformite(conformites.get(selected_id, "—")))
        st.metric(t("step5.metric_risk_class"), mc_row["niveau_risque"] or "—")

    st.markdown("---")

    if not ai_service.is_configured():
        st.warning(f"**{t('step4.not_configured_title')}**")
        st.info(t("step4.not_configured_body"))
        return

    # ---- Bouton Générer ----
    if st.button(
        t("step5.generate_button", id=selected_id),
        type="primary",
        key=f"gen_pdca_{selected_id}",
    ):
        item_data = {
            "item_id": selected_id,
            "section": tr_section(item_row),
            "equipement": tr_equipment(item_row),
            "symptome": tr_symptom(item_row),
            "severity": item_row[4],
            "conformite": conformites.get(selected_id, "NC"),
        }

        with st.spinner(t("step5.generating")):
            result = ai_service.generer_plan_pdca(
                item=item_data,
                freq_moyenne=mc_row["freq_moyenne"],
                risk_class=mc_row["niveau_risque"] or "N/A",
                langue=get_current_lang(),
            )

        if result.get("erreur"):
            st.error(t("step5.error_api", error=result["erreur"]))
        else:
            st.session_state[f"pdca_markdown_{selected_id}"] = result["markdown"]
            st.success(t("step5.generated_ok"))

    # ---- Affichage du plan ----
    pdca_key = f"pdca_markdown_{selected_id}"
    if pdca_key in st.session_state:
        st.markdown("---")
        st.subheader(t("step5.plan_generated_header"))

        st.markdown(st.session_state[pdca_key])

        st.markdown("---")

        col1, col2 = st.columns(2)

        with col1:
            st.download_button(
                t("step5.download_button"),
                st.session_state[pdca_key].encode("utf-8"),
                f"pdca_{selected_id}.md",
                "text/markdown",
                key=f"download_pdca_{selected_id}",
            )

        with col2:
            if st.button(t("step5.regenerate_button"), key=f"regen_pdca_{selected_id}"):
                del st.session_state[pdca_key]
                st.rerun()


# ============================================================
# DISPATCH — ROUTAGE VERS LA BONNE ÉTAPE
# ============================================================
# Import de la page rapport (optionnelle : le module peut ne pas être présent)
try:
    from ui.pages.report import render_report_page
except ImportError:
    def render_report_page(*_args, **_kwargs):
        st.header(t("nav.step_4"))
        st.info(t("step4.unavailable"))

if step == 0:
    render_step_0_matrix_config()
elif step == 1:
    render_step_1_audit()
elif step == 2:
    render_step_2_monte_carlo()
elif step == 3:
    render_step_3_results()
elif step == 4:
    render_report_page(db, audit_id, site_name=st.session_state.get("active_site", "—"))
elif step == 5:
    render_step_5_pdca()


# ============================================================
# FOOTER HSE PYXIS
# ============================================================
render_footer()

st.sidebar.markdown("---")
st.sidebar.caption(
    t("sidebar.footer_audit_id", id=audit_id)
    + "  \n"
    + t("sidebar.footer_active_matrix",
        site=st.session_state.get("active_site", "—"))
)