"""
ui/auth_guard.py — Garde-fou réutilisable pour pages protégées
==============================================================
Usage dans une page :
    from ui.auth_guard import guard
    guard("create_inspection")
"""

import streamlit as st
from auth import is_authenticated, has_permission, current_role


def guard(permission: str | None = None) -> bool:
    """Retourne True si l'accès est autorisé, sinon affiche un message et bloque."""
    if not is_authenticated():
        st.error("🔒 Vous devez être connecté pour accéder à cette page.")
        st.stop()
    if permission and not has_permission(permission):
        st.error(
            f"⛔ Accès refusé. Rôle requis pour `{permission}` "
            f"(votre rôle : {current_role()})."
        )
        st.stop()
    return True