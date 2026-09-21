"""
ui/theme.py — HSE PYXIS Design System (v3, corrigé)
====================================================
Source unique de vérité pour toute l'identité visuelle HSE PYXIS.

CORRECTIONS v3
--------------
1. Le CSS n'est plus indenté. Streamlit passe d'abord le texte dans un
   parseur Markdown : toute ligne indentée de 4 espaces ou plus devient un
   « bloc de code » et s'affiche telle quelle à l'écran au lieu d'être
   interprétée. C'était la cause du « code bizarre » affiché sur la page
   d'accueil ET du thème qui ne s'appliquait pas.
   -> Tout le HTML/CSS commence maintenant en colonne 0.
   -> Utiliser html() ci-dessous pour tout HTML injecté ailleurs.
2. Couverture complète du mode clair : conteneur principal, header,
   sidebar, menus déroulants (portails BaseWeb), expanders, onglets,
   tableaux, alertes, code.
3. color-scheme CSS -> les éléments natifs (scrollbars, sélecteurs)
   suivent le thème.
4. current_theme() / apply_theme() : une seule source de vérité.
"""

import textwrap

import streamlit as st

from ui.i18n import is_rtl


# ============================================================
# 1. PALETTE HSE PYXIS (extraite du logo)
# ============================================================
PYXIS_GREEN       = "#00C853"
PYXIS_GREEN_DARK  = "#009624"
PYXIS_GREEN_LIGHT = "#5EFC82"

PYXIS_BLUE        = "#2979FF"
PYXIS_BLUE_DARK   = "#0039CB"
PYXIS_BLUE_LIGHT  = "#6B9BFF"

PYXIS_SILVER      = "#B0BEC5"
PYXIS_SILVER_DARK = "#78909C"

PYXIS_DANGER      = "#FF1744"
PYXIS_WARNING     = "#FFAB00"
PYXIS_SUCCESS     = PYXIS_GREEN
PYXIS_INFO        = PYXIS_BLUE


# ============================================================
# 2. BACKGROUNDS (dark & light)
# ============================================================
DARK_BG       = "#0A1628"
DARK_SURFACE  = "#152238"
DARK_ELEVATED = "#1E2F4A"
DARK_TEXT     = "#F5F7FA"
DARK_MUTED    = "#90A4AE"

LIGHT_BG       = "#F4F7FB"
LIGHT_SURFACE  = "#FFFFFF"
LIGHT_ELEVATED = "#E8EEF5"
LIGHT_TEXT     = "#0A1628"
LIGHT_MUTED    = "#546E7A"

DEFAULT_THEME = "dark"


# ============================================================
# 3. GRADIENTS
# ============================================================
GRADIENT_PRIMARY = f"linear-gradient(135deg, {PYXIS_GREEN} 0%, {PYXIS_BLUE} 100%)"
GRADIENT_DARK    = f"linear-gradient(135deg, {DARK_BG} 0%, {PYXIS_BLUE_DARK} 100%)"
GRADIENT_HERO    = f"linear-gradient(135deg, {PYXIS_BLUE_DARK} 0%, {PYXIS_GREEN_DARK} 100%)"


# ============================================================
# 4. HELPERS
# ============================================================
def current_theme() -> str:
    """Thème actif ('dark' ou 'light') — source de vérité unique."""
    theme = st.session_state.get("theme", DEFAULT_THEME)
    return theme if theme in ("dark", "light") else DEFAULT_THEME


def html(markup: str):
    """Injecte du HTML SANS risque d'être transformé en bloc de code.

    À utiliser partout à la place de st.markdown(\"\"\"...\"\"\", unsafe_allow_html=True)
    quand le HTML est indenté dans le code source.
    """
    st.markdown(textwrap.dedent(markup).strip(), unsafe_allow_html=True)


def palette(mode: str | None = None) -> dict:
    """Retourne les couleurs du thème demandé (ou du thème actif)."""
    mode = mode or current_theme()
    if mode == "light":
        return {
            "bg": LIGHT_BG, "surface": LIGHT_SURFACE, "elevated": LIGHT_ELEVATED,
            "text": LIGHT_TEXT, "muted": LIGHT_MUTED,
            "border": "rgba(10,22,40,0.10)",
            "shadow": "0 8px 32px rgba(10,22,40,0.08)",
            "scheme": "light",
        }
    return {
        "bg": DARK_BG, "surface": DARK_SURFACE, "elevated": DARK_ELEVATED,
        "text": DARK_TEXT, "muted": DARK_MUTED,
        "border": "rgba(255,255,255,0.10)",
        "shadow": "0 8px 32px rgba(0,0,0,0.40)",
        "scheme": "dark",
    }


# ============================================================
# 5. INJECTION CSS
# ============================================================
def inject_css(mode: str | None = None):
    """Injecte le CSS HSE PYXIS complet.

    mode : 'dark' | 'light' | None (None = thème de la session).
    """
    p = palette(mode)

    # ---- RTL (arabe) ----
    rtl_css = ""
    if is_rtl():
        rtl_css = """
.stApp, section[data-testid="stSidebar"] { direction: rtl; }

section[data-testid="stSidebar"] {
text-align: right;
border-right: none;
border-left: 1px solid var(--pyxis-border);
}

.stMarkdown, .stTextInput label, .stSelectbox label, .stNumberInput label,
.stTextArea label, .stRadio label, .stCheckbox label { text-align: right; }

[data-testid="stDataFrame"], [data-testid="stDataEditor"],
.stPlotlyChart, .js-plotly-plot { direction: ltr; text-align: left; }
"""

    # ---- CSS principal (AUCUNE indentation : sinon Markdown -> bloc de code) ----
    css = f"""
<style>
@import url('https://fonts.googleapis.com/css2?family=Cairo:wght@400;600;700;900&family=Inter:wght@400;500;600;700;800&display=swap');

:root {{
--pyxis-bg: {p['bg']};
--pyxis-surface: {p['surface']};
--pyxis-elevated: {p['elevated']};
--pyxis-text: {p['text']};
--pyxis-muted: {p['muted']};
--pyxis-border: {p['border']};
--pyxis-shadow: {p['shadow']};
--pyxis-green: {PYXIS_GREEN};
--pyxis-blue: {PYXIS_BLUE};
color-scheme: {p['scheme']};
}}

html, body, .stApp, [class*="css"] {{
font-family: 'Inter', 'Cairo', -apple-system, BlinkMacSystemFont, sans-serif;
}}

/* ---------- Conteneurs principaux ---------- */
.stApp,
[data-testid="stAppViewContainer"],
[data-testid="stMain"],
[data-testid="stBottomBlockContainer"] {{
background: var(--pyxis-bg) !important;
color: var(--pyxis-text);
}}

[data-testid="stHeader"], [data-testid="stToolbar"] {{
background: transparent !important;
color: var(--pyxis-text);
}}

[data-testid="stAppViewContainer"] .stMarkdown,
[data-testid="stAppViewContainer"] p,
[data-testid="stAppViewContainer"] li,
[data-testid="stAppViewContainer"] label,
[data-testid="stCaptionContainer"],
[data-testid="stWidgetLabel"] * {{
color: var(--pyxis-text);
}}

[data-testid="stCaptionContainer"], small {{ color: var(--pyxis-muted) !important; }}

/* ---------- Sidebar ---------- */
section[data-testid="stSidebar"],
section[data-testid="stSidebar"] > div {{
background: var(--pyxis-surface) !important;
border-right: 1px solid var(--pyxis-border);
}}

section[data-testid="stSidebar"] p,
section[data-testid="stSidebar"] label,
section[data-testid="stSidebar"] span,
section[data-testid="stSidebar"] li {{
color: var(--pyxis-text);
}}

/* ---------- Titres ---------- */
h1, h2, h3, h4, h5, h6 {{
color: var(--pyxis-text) !important;
font-weight: 700 !important;
letter-spacing: -0.02em;
}}

.stApp h1 {{
background: {GRADIENT_PRIMARY};
-webkit-background-clip: text;
-webkit-text-fill-color: transparent;
background-clip: text;
font-weight: 900 !important;
}}

/* ---------- Boutons ---------- */
.stButton > button, .stDownloadButton > button, .stFormSubmitButton > button {{
background: {GRADIENT_PRIMARY};
color: #FFFFFF !important;
border: none;
border-radius: 12px;
padding: 0.6rem 1.4rem;
font-weight: 600;
font-size: 0.95rem;
transition: all 0.25s ease;
box-shadow: 0 4px 16px rgba(0,200,83,0.25);
}}

.stButton > button:hover, .stDownloadButton > button:hover {{
transform: translateY(-2px);
box-shadow: 0 8px 24px rgba(0,200,83,0.40);
}}

.stButton > button[kind="secondary"] {{
background: transparent;
color: var(--pyxis-text) !important;
border: 1.5px solid var(--pyxis-border);
box-shadow: none;
}}

.stButton > button[kind="secondary"]:hover {{
border-color: var(--pyxis-green);
color: var(--pyxis-green) !important;
}}

/* ---------- Champs de saisie ---------- */
.stTextInput input, .stTextArea textarea, .stNumberInput input,
.stDateInput input, .stTimeInput input,
.stSelectbox div[data-baseweb="select"] > div,
.stMultiSelect div[data-baseweb="select"] > div {{
background: var(--pyxis-elevated) !important;
color: var(--pyxis-text) !important;
border: 1px solid var(--pyxis-border) !important;
border-radius: 10px !important;
}}

.stTextInput input:focus, .stTextArea textarea:focus, .stNumberInput input:focus {{
border-color: var(--pyxis-green) !important;
box-shadow: 0 0 0 3px rgba(0,200,83,0.15) !important;
}}

/* Menus déroulants (rendus hors de .stApp par BaseWeb) */
div[data-baseweb="popover"] div[role="listbox"],
div[data-baseweb="popover"] ul,
div[data-baseweb="menu"] {{
background: var(--pyxis-elevated) !important;
color: var(--pyxis-text) !important;
border: 1px solid var(--pyxis-border) !important;
}}

div[data-baseweb="popover"] li, div[data-baseweb="menu"] li {{ color: var(--pyxis-text) !important; }}
div[data-baseweb="popover"] li:hover {{ background: rgba(0,200,83,0.15) !important; }}

/* ---------- Expander / onglets / tableaux / alertes ---------- */
[data-testid="stExpander"] {{
background: var(--pyxis-surface);
border: 1px solid var(--pyxis-border);
border-radius: 14px;
}}
[data-testid="stExpander"] summary, [data-testid="stExpander"] p {{ color: var(--pyxis-text) !important; }}

.stTabs [data-baseweb="tab"] {{ color: var(--pyxis-muted); }}
.stTabs [aria-selected="true"] {{ color: var(--pyxis-green) !important; }}

[data-testid="stDataFrame"], [data-testid="stTable"] {{
background: var(--pyxis-surface);
border: 1px solid var(--pyxis-border);
border-radius: 12px;
}}

[data-testid="stAlert"] {{
background: var(--pyxis-elevated) !important;
color: var(--pyxis-text) !important;
border-radius: 12px;
border: 1px solid var(--pyxis-border);
}}

code, .stCode, pre {{
background: var(--pyxis-elevated) !important;
color: var(--pyxis-text) !important;
border-radius: 8px;
}}

/* ---------- Metrics ---------- */
div[data-testid="stMetric"] {{
background: var(--pyxis-surface);
border: 1px solid var(--pyxis-border);
border-radius: 14px;
padding: 1rem 1.2rem;
box-shadow: var(--pyxis-shadow);
}}

div[data-testid="stMetricLabel"], div[data-testid="stMetricLabel"] * {{
color: var(--pyxis-muted) !important;
font-weight: 600 !important;
text-transform: uppercase;
font-size: 0.75rem !important;
letter-spacing: 0.05em;
}}

div[data-testid="stMetricValue"] {{
color: var(--pyxis-green) !important;
font-weight: 800 !important;
font-size: 1.8rem !important;
}}

/* ---------- Composants HSE PYXIS ---------- */
.pyxis-card {{
background: var(--pyxis-surface);
border: 1px solid var(--pyxis-border);
border-radius: 16px;
padding: 1.5rem;
box-shadow: var(--pyxis-shadow);
transition: all 0.3s ease;
color: var(--pyxis-text);
}}

.pyxis-card:hover {{
transform: translateY(-4px);
border-color: var(--pyxis-green);
box-shadow: 0 12px 40px rgba(0,200,83,0.15);
}}

.pyxis-badge {{
display: inline-block;
padding: 0.3rem 0.8rem;
border-radius: 999px;
font-size: 0.75rem;
font-weight: 700;
text-transform: uppercase;
letter-spacing: 0.05em;
}}

.badge-success {{ background: rgba(0,200,83,0.15); color: {PYXIS_GREEN}; }}
.badge-danger  {{ background: rgba(255,23,68,0.15); color: {PYXIS_DANGER}; }}
.badge-warning {{ background: rgba(255,171,0,0.15); color: {PYXIS_WARNING}; }}
.badge-info    {{ background: rgba(41,121,255,0.15); color: {PYXIS_BLUE}; }}

.pyxis-hero {{
background: {GRADIENT_HERO};
border-radius: 24px;
padding: 3rem 2rem;
text-align: center;
color: #FFFFFF;
box-shadow: 0 20px 60px rgba(0,57,203,0.35);
position: relative;
overflow: hidden;
}}

.pyxis-hero::before {{
content: '';
position: absolute;
top: -50%;
right: -50%;
width: 200%;
height: 200%;
background: radial-gradient(circle, rgba(0,200,83,0.15) 0%, transparent 70%);
animation: pyxis-pulse 8s ease-in-out infinite;
}}

@keyframes pyxis-pulse {{
0%, 100% {{ transform: scale(1); opacity: 0.6; }}
50% {{ transform: scale(1.1); opacity: 0.9; }}
}}

/* le hero garde un titre blanc lisible, quel que soit le thème */
.stApp .pyxis-hero h1 {{
font-size: 3.2rem !important;
margin-bottom: 0.5rem;
background: none !important;
-webkit-text-fill-color: #FFFFFF !important;
color: #FFFFFF !important;
position: relative;
z-index: 1;
}}

.pyxis-hero p {{ font-size: 1.15rem; opacity: 0.95; position: relative; z-index: 1; color: #FFFFFF !important; }}

.pyxis-tagline {{
font-size: 0.85rem;
letter-spacing: 0.3em;
text-transform: uppercase;
opacity: 0.85;
margin-top: 0.5rem;
position: relative;
z-index: 1;
}}

.pyxis-pillars {{
display: flex;
justify-content: center;
gap: 1.5rem;
margin: 2rem 0;
flex-wrap: wrap;
}}

.pyxis-pillar {{
flex: 1;
min-width: 140px;
max-width: 200px;
text-align: center;
padding: 1.5rem 1rem;
background: var(--pyxis-surface);
border: 1px solid var(--pyxis-border);
border-radius: 16px;
color: var(--pyxis-text);
transition: all 0.3s ease;
}}

.pyxis-pillar:hover {{ transform: translateY(-6px); border-color: var(--pyxis-green); }}
.pyxis-pillar-icon {{ font-size: 2rem; margin-bottom: 0.5rem; }}
.pyxis-pillar-label {{ font-weight: 700; font-size: 0.85rem; letter-spacing: 0.1em; color: var(--pyxis-text); }}

#MainMenu {{ visibility: hidden; }}
footer {{ visibility: hidden; }}
{rtl_css}
</style>
"""
    st.markdown(css, unsafe_allow_html=True)


def apply_theme():
    """À appeler une fois par rerun, juste après st.set_page_config()."""
    inject_css(current_theme())


# ============================================================
# 6. PLOTLY
# ============================================================
def get_chart_colors() -> dict:
    """Palette pour les graphiques Plotly."""
    return {
        "green":    PYXIS_GREEN,
        "blue":     PYXIS_BLUE,
        "silver":   PYXIS_SILVER,
        "danger":   PYXIS_DANGER,
        "warning":  PYXIS_WARNING,
        "gradient": GRADIENT_PRIMARY,
    }


def get_plotly_template(mode: str | None = None) -> dict:
    """Template Plotly cohérent avec le thème HSE PYXIS actif."""
    p = palette(mode)
    grid = "rgba(255,255,255,0.06)" if (mode or current_theme()) == "dark" else "rgba(10,22,40,0.08)"
    return {
        "paper_bgcolor": p["bg"],
        "plot_bgcolor": p["surface"],
        "font": {"color": p["text"], "family": "Inter, Cairo, sans-serif"},
        "legend": {"font": {"color": p["text"]}},
        "xaxis": {"gridcolor": grid, "zerolinecolor": grid},
        "yaxis": {"gridcolor": grid, "zerolinecolor": grid},
    }


def show_plotly(fig, **kwargs):
    """Affiche une figure Plotly en respectant le thème HSE PYXIS actif.

    À utiliser à la place de st.plotly_chart(fig, ...).
    """
    fig.update_layout(**get_plotly_template(current_theme()))
    kwargs.setdefault("use_container_width", True)
    st.plotly_chart(fig, theme=None, **kwargs)
