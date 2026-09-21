"""
ui/layout.py — Header, Sidebar, Footer HSE PYXIS (v2, corrigé)
===============================================================
CORRECTIONS
-----------
1. HTML injecté via theme.html() (dedent) -> plus de « code » affiché.
2. render_sidebar() : le radio Thème n'avait ni index ni rerun — le
   changement ne s'appliquait qu'à l'interaction suivante. Corrigé.
3. La clé du radio Thème de la sidebar est renommée
   ("layout_sidebar_theme_radio") pour ne plus entrer en conflit avec
   celle déjà utilisée dans audit_app.py (DuplicateWidgetID).
"""

import streamlit as st
from pathlib import Path

from ui.i18n import t, LANGUAGES, get_current_lang, set_language
from ui.theme import html, current_theme

THEMES = ["dark", "light"]


def render_header():
    """Header commun en haut de page."""
    logo_path = Path("assets/logo_icon.png")
    if not logo_path.exists():
        logo_path = Path("assets/logo.png")

    cols = st.columns([1, 8, 3])

    with cols[0]:
        if logo_path.exists():
            st.image(str(logo_path), width=70)

    with cols[1]:
        html(f"""
            <div style="padding-top:0.4rem;">
                <span style="font-size:1.9rem;font-weight:900;
                             background:linear-gradient(135deg,#00C853,#2979FF);
                             -webkit-background-clip:text;
                             -webkit-text-fill-color:transparent;
                             letter-spacing:0.05em;">{t('app.name')}</span>
                <div style="font-size:0.7rem;letter-spacing:0.3em;
                            color:#90A4AE;margin-top:0.1rem;">{t('app.tagline')}</div>
            </div>
        """)

    with cols[2]:
        lang_options = list(LANGUAGES.keys())
        current_lang = get_current_lang()
        idx = lang_options.index(current_lang) if current_lang in lang_options else 0

        new_lang = st.selectbox(
            "🌍",
            lang_options,
            index=idx,
            format_func=lambda x: f"{LANGUAGES[x]['flag']} {LANGUAGES[x]['label']}",
            key="header_lang_selector",
            label_visibility="collapsed",
        )
        if new_lang != current_lang:
            set_language(new_lang)
            st.rerun()

    st.markdown("---")


def render_sidebar(audit_id: str = ""):
    """Sidebar HSE PYXIS (langue + thème)."""
    with st.sidebar:
        logo_path = Path("assets/logo.png")
        if logo_path.exists():
            _, c2, _ = st.columns([1, 2, 1])
            with c2:
                st.image(str(logo_path), use_container_width=True)

        html(f"""
            <div style="text-align:center;margin:1rem 0;">
                <div style="font-size:1.4rem;font-weight:900;
                            background:linear-gradient(135deg,#00C853,#2979FF);
                            -webkit-background-clip:text;
                            -webkit-text-fill-color:transparent;
                            letter-spacing:0.1em;">{t('app.name')}</div>
                <div style="font-size:0.6rem;letter-spacing:0.25em;
                            color:#90A4AE;margin-top:0.3rem;">{t('app.tagline')}</div>
            </div>
        """)

        st.markdown("---")
        st.markdown(f"### ⚙️ {t('nav.settings')}")

        # ---- Langue ----
        st.caption(f"🌍 {t('nav.language')}")
        lang_options = list(LANGUAGES.keys())
        current_lang = get_current_lang()
        idx = lang_options.index(current_lang) if current_lang in lang_options else 0

        new_lang = st.radio(
            "Langue",
            lang_options,
            index=idx,
            format_func=lambda x: f"{LANGUAGES[x]['flag']} {LANGUAGES[x]['label']}",
            key="layout_sidebar_lang_radio",
            label_visibility="collapsed",
        )
        if new_lang != current_lang:
            set_language(new_lang)
            st.rerun()

        # ---- Thème ----
        st.caption(f"🎨 {t('nav.theme')}")
        theme_now = current_theme()
        new_theme = st.radio(
            "Thème",
            THEMES,
            index=THEMES.index(theme_now),
            format_func=lambda x: t("welcome.theme_dark") if x == "dark" else t("welcome.theme_light"),
            key="layout_sidebar_theme_radio",
            label_visibility="collapsed",
            horizontal=True,
        )
        if new_theme != theme_now:
            st.session_state.theme = new_theme
            st.rerun()


def render_footer():
    """Footer HSE PYXIS."""
    st.markdown("---")
    html(f"""
        <div style="text-align:center;padding:1rem 0;opacity:0.7;
                    font-size:0.75rem;color:#90A4AE;">
            <div style="font-weight:700;letter-spacing:0.2em;
                        background:linear-gradient(135deg,#00C853,#2979FF);
                        -webkit-background-clip:text;
                        -webkit-text-fill-color:transparent;">HSE PYXIS</div>
            <div style="margin-top:0.3rem;">{t('footer.copyright')}</div>
        </div>
    """)
