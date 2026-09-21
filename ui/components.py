"""
ui/components.py — Composants HSE PYXIS réutilisables (v2, corrigé)
====================================================================
CORRECTION : tout le HTML passe par theme.html(), qui applique
textwrap.dedent(). Sans cela, un HTML indenté de 4 espaces est interprété
par Markdown comme un bloc de code et s'affiche en clair à l'écran.
"""

import streamlit as st

from ui.theme import html


def card(title: str, content: str, icon: str = "📌"):
    html(f"""
        <div class="pyxis-card">
            <div style="font-size:1.5rem;margin-bottom:0.5rem;">{icon}</div>
            <div style="font-weight:700;font-size:1.05rem;margin-bottom:0.5rem;">{title}</div>
            <div style="opacity:0.85;font-size:0.9rem;line-height:1.5;">{content}</div>
        </div>
    """)


def badge(text: str, kind: str = "info"):
    html(f'<span class="pyxis-badge badge-{kind}">{text}</span>')


def hero(title: str, subtitle: str, tagline: str = ""):
    html(f"""
        <div class="pyxis-hero">
            <h1>{title}</h1>
            <p>{subtitle}</p>
            <div class="pyxis-tagline">{tagline}</div>
        </div>
    """)


def pillars(items):
    """Affiche les piliers HSE PYXIS. items = [(icon, title, desc), ...]"""
    blocks = "".join(
        f'<div class="pyxis-pillar">'
        f'<div class="pyxis-pillar-icon">{icon}</div>'
        f'<div class="pyxis-pillar-label">{title}</div>'
        f'<div style="font-size:0.75rem;opacity:0.7;margin-top:0.3rem;">{desc}</div>'
        f'</div>'
        for icon, title, desc in items
    )
    html(f'<div class="pyxis-pillars">{blocks}</div>')


def spacer(height: str = "1rem"):
    html(f'<div style="height:{height};"></div>')
