"""
ui/pages/welcome.py — Écran d'accueil HSE PYXIS (v2, corrigé)
==============================================================
CORRECTIONS
-----------
1. HTML injecté via theme.html() (dedent) -> plus de « code » affiché.
2. Le radio Thème avait un index par défaut figé sur "dark" : il ne
   reflétait pas le thème réel de la session. index= est maintenant calculé.
3. st.rerun() n'est déclenché qu'en cas de vrai changement (pas de boucle).
"""

import streamlit as st
from pathlib import Path

from ui.i18n import t, LANGUAGES, get_current_lang
from ui.components import hero, pillars, spacer
from ui.theme import html, current_theme

THEMES = ["dark", "light"]


def render_welcome():
    """Affiche l'écran d'accueil HSE PYXIS."""

    # ---- LOGO CENTRÉ ----
    logo_path = Path("assets/logo.png")
    if logo_path.exists():
        _, c2, _ = st.columns([1, 1, 1])
        with c2:
            st.image(str(logo_path), use_container_width=True)
    else:
        html("""
            <div style="text-align:center;padding:2rem 0;">
                <div style="font-size:4rem;font-weight:900;
                            background:linear-gradient(135deg,#00C853,#2979FF);
                            -webkit-background-clip:text;
                            -webkit-text-fill-color:transparent;
                            letter-spacing:0.1em;">HSE PYXIS</div>
            </div>
        """)

    # ---- HERO ----
    hero(
        title=t("app.name"),
        subtitle=t("welcome.subtitle"),
        tagline=t("app.tagline"),
    )

    spacer("1.5rem")

    # ---- DESCRIPTION ----
    html(f"""
        <div style="text-align:center;max-width:700px;margin:0 auto 2rem auto;
                    opacity:0.85;font-size:1rem;line-height:1.7;">
            {t("welcome.description")}
        </div>
    """)

    # ---- PILIERS ----
    pillars([
        ("🛡️", t("welcome.feature_1_title"), t("welcome.feature_1_desc")),
        ("🌿", t("welcome.feature_2_title"), t("welcome.feature_2_desc")),
        ("⚠️", t("welcome.feature_3_title"), t("welcome.feature_3_desc")),
        ("📋", t("welcome.feature_4_title"), t("welcome.feature_4_desc")),
    ])

    spacer()
    st.markdown("---")

    # ---- SÉLECTION LANGUE + THÈME ----
    col1, col2 = st.columns(2)

    with col1:
        st.markdown(f"### 🌍 {t('welcome.choose_language')}")
        lang_options = list(LANGUAGES.keys())
        current_lang = get_current_lang()
        lang_idx = lang_options.index(current_lang) if current_lang in lang_options else 0

        chosen_lang = st.radio(
            "Langue",
            lang_options,
            index=lang_idx,
            format_func=lambda x: f"{LANGUAGES[x]['flag']}  {LANGUAGES[x]['label']}",
            key="welcome_lang_radio",
            label_visibility="collapsed",
        )

    with col2:
        st.markdown(f"### 🎨 {t('welcome.choose_theme')}")
        theme_idx = THEMES.index(current_theme())
        chosen_theme = st.radio(
            "Thème",
            THEMES,
            index=theme_idx,
            format_func=lambda x: t("welcome.theme_dark") if x == "dark" else t("welcome.theme_light"),
            key="welcome_theme_radio",
            label_visibility="collapsed",
            horizontal=True,
        )

    # Application immédiate des choix (un seul rerun si changement réel)
    changed = (chosen_lang != get_current_lang()) or (chosen_theme != current_theme())
    st.session_state.language = chosen_lang
    st.session_state.theme = chosen_theme
    if changed:
        st.rerun()

    spacer()

    # ---- BOUTON DÉMARRER ----
    _, col_b, _ = st.columns([2, 1, 2])
    with col_b:
        if st.button(t("welcome.start_button"), type="primary", use_container_width=True):
            st.session_state.welcome_done = True
            st.rerun()
