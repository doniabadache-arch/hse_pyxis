"""
ui/pages/login.py — Connexion, premier administrateur, changement de mot de passe,
                    bloc « compte » de la barre latérale (HSE PYXIS)
===============================================================================
Toute la logique (hachage, verrouillage, audit) est dans auth.py : ce fichier ne fait
que l'affichage. Les messages d'erreur arrivent sous forme de clés de traduction
(AuthError.key) et sont traduits ici.
"""

import os

import streamlit as st

import auth
from ui.i18n import t
from ui.theme import html


def role_label(role: str) -> str:
    return t(f"auth.role_{role}")


def _show_error(err: auth.AuthError):
    st.error(t(err.key, **err.params))


def _pop_notice():
    notice = st.session_state.pop(auth.SESSION_NOTICE_KEY, None)
    if notice:
        st.warning(t(notice))


def _title(icon: str, text: str, caption: str = ""):
    html(f"""
<div style="text-align:center;margin:0.5rem 0 1rem 0;">
<div style="font-size:2.2rem;">{icon}</div>
<div style="font-size:1.4rem;font-weight:800;">{text}</div>
</div>
""")
    if caption:
        st.caption(caption)


# ------------------------------------------------------------
# Connexion
# ------------------------------------------------------------
def render_login():
    """Page affichée tant qu'aucun utilisateur n'est connecté."""
    adb = auth.get_auth_db()
    _, col, _ = st.columns([1, 2, 1])
    with col:
        _pop_notice()
        if not adb.has_users():
            _render_first_admin_setup(adb)
        else:
            _render_login_form(adb)


def _render_login_form(adb: auth.AuthDB):
    _title("🔐", t("auth.login_title"), t("auth.login_subtitle"))
    with st.form("auth_login_form"):
        username = st.text_input(t("auth.username"), key="auth_login_username",
                                 autocomplete="username")
        password = st.text_input(t("auth.password"), type="password", key="auth_login_password",
                                 autocomplete="current-password")
        submitted = st.form_submit_button(t("auth.login_button"), type="primary",
                                          use_container_width=True)
    if submitted:
        try:
            user = adb.authenticate(username, password)
        except auth.AuthError as err:
            _show_error(err)
            return
        auth.login_user(user)
        st.rerun()


def _render_first_admin_setup(adb: auth.AuthDB):
    _title("🛡️", t("auth.setup_title"), t("auth.setup_caption"))
    setup_key = os.getenv("PYXIS_SETUP_KEY", "").strip()
    with st.form("auth_setup_form"):
        full_name = st.text_input(t("auth.full_name"), key="auth_setup_name")
        username = st.text_input(t("auth.username"), key="auth_setup_username",
                                 help=t("auth.username_help"))
        pw1 = st.text_input(t("auth.password"), type="password", key="auth_setup_pw1",
                            help=t("auth.password_help", n=auth.MIN_PASSWORD_LEN))
        pw2 = st.text_input(t("auth.confirm_password"), type="password", key="auth_setup_pw2")
        key_in = st.text_input(t("auth.setup_key"), type="password", key="auth_setup_key") if setup_key else ""
        submitted = st.form_submit_button(t("auth.create_admin_button"), type="primary",
                                          use_container_width=True)
    if not submitted:
        return
    if setup_key and key_in.strip() != setup_key:
        st.error(t("auth.err_setup_key"))
        return
    if pw1 != pw2:
        st.error(t("auth.err_password_mismatch"))
        return
    try:
        adb.create_user(username, pw1, auth.ROLE_ADMIN, full_name=full_name,
                        actor=auth.normalize_username(username), actor_role=auth.ROLE_ADMIN,
                        only_if_empty=True)
        user = adb.authenticate(username, pw1)
    except auth.AuthError as err:
        _show_error(err)
        return
    auth.login_user(user)
    st.rerun()


# ------------------------------------------------------------
# Changement de mot de passe obligatoire (compte créé / réinitialisé par un admin)
# ------------------------------------------------------------
def _password_change_form(form_key: str, title: str | None = None) -> bool:
    """Formulaire commun. Retourne True si le mot de passe a été changé."""
    user = auth.current_user()
    with st.form(form_key, clear_on_submit=True):
        old = st.text_input(t("auth.old_password"), type="password", key=f"{form_key}_old")
        new1 = st.text_input(t("auth.new_password"), type="password", key=f"{form_key}_new1",
                             help=t("auth.password_help", n=auth.MIN_PASSWORD_LEN))
        new2 = st.text_input(t("auth.confirm_password"), type="password", key=f"{form_key}_new2")
        submitted = st.form_submit_button(title or t("auth.change_password"), type="primary",
                                          use_container_width=True)
    if not submitted:
        return False
    if new1 != new2:
        st.error(t("auth.err_password_mismatch"))
        return False
    try:
        auth.get_auth_db().change_password(user["id"], old, new1)
    except auth.AuthError as err:
        _show_error(err)
        return False
    return True


def render_force_password_change():
    user = auth.current_user()
    _, col, _ = st.columns([1, 2, 1])
    with col:
        _title("🔑", t("auth.force_change_title"), t("auth.force_change_caption", name=user["username"]))
        if _password_change_form("auth_force_pw"):
            st.session_state[auth.SESSION_USER_KEY]["must_change_password"] = False
            st.success(t("auth.password_changed"))
            st.rerun()
        st.button(t("auth.logout"), key="auth_force_logout", on_click=_cb_logout)


# ------------------------------------------------------------
# Bloc compte dans la barre latérale
# ------------------------------------------------------------
def _cb_logout():
    auth.logout("logout")


def render_account_box():
    """Nom, rôle, changement de mot de passe et déconnexion (en haut de la sidebar)."""
    user = auth.current_user()
    if not user:
        return
    display = user.get("full_name") or user["username"]
    with st.sidebar:
        st.markdown(f"👤 **{display}**")
        st.caption(f"@{user['username']} · {role_label(user['role'])}")
        with st.expander(f"🔑 {t('auth.change_password')}"):
            if _password_change_form("auth_sidebar_pw"):
                st.success(t("auth.password_changed"))
        st.button(f"🚪 {t('auth.logout')}", key="auth_logout_btn",
                  on_click=_cb_logout, use_container_width=True)
        st.markdown("---")


def render_read_only_notice():
    """Petit bandeau pour les pages consultables mais non modifiables par ce rôle."""
    st.info(f"👁️ {t('auth.read_only_notice')}")
