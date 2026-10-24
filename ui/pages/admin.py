"""
ui/pages/admin.py — Administration : utilisateurs + journal d'audit (HSE PYXIS)
===============================================================================
Page réservée au rôle « admin » (étape 7 de la navigation).
"""

import hashlib
from datetime import date, timedelta

import pandas as pd
import streamlit as st

import auth
from ui.i18n import t
from ui.pages.login import role_label

AUDIT_PAGE_SIZE = 100
AUDIT_EXPORT_MAX = 10_000


def _flash(kind: str, text: str):
    st.session_state["adm_flash"] = (kind, text)


def _show_flash():
    flash = st.session_state.pop("adm_flash", None)
    if flash:
        {"success": st.success, "error": st.error, "warning": st.warning}.get(flash[0], st.info)(flash[1])


def _err_text(err: auth.AuthError) -> str:
    return t(err.key, **err.params)


def _digest_filters(filters: dict) -> str:
    raw = "|".join(f"{k}={filters[k]}" for k in sorted(filters))
    return hashlib.md5(raw.encode("utf-8")).hexdigest()[:10]


def _audit_action_label(code: str) -> str:
    return t(f"audit.act.{code}")


# ------------------------------------------------------------
# Utilisateurs
# ------------------------------------------------------------
def _users_table(users: list[dict]):
    adb = auth.get_auth_db()
    rows = []
    for u in users:
        if not u["active"]:
            status = f"⛔ {t('admin.status_inactive')}"
        elif adb.is_locked(u):
            status = f"🔒 {t('admin.status_locked')}"
        else:
            status = f"✅ {t('admin.status_active')}"
        rows.append({
            t("auth.username"): u["username"],
            t("auth.full_name"): u["full_name"] or "—",
            t("admin.col_role"): role_label(u["role"]),
            t("admin.col_status"): status,
            t("admin.col_last_login"): u["last_login"] or "—",
            t("admin.col_created"): u["created_at"] or "—",
        })
    st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)


def _render_create_user(me: dict):
    adb = auth.get_auth_db()
    st.markdown(f"#### ➕ {t('admin.create_title')}")
    st.caption(t("admin.create_caption"))

    if "adm_suggested_pw" not in st.session_state:
        st.session_state["adm_suggested_pw"] = auth.generate_temp_password()
    st.caption(t("admin.suggested_pw"))
    st.code(st.session_state["adm_suggested_pw"], language=None)

    with st.form("adm_create_form", clear_on_submit=True):
        c1, c2 = st.columns(2)
        username = c1.text_input(t("auth.username"), help=t("auth.username_help"))
        full_name = c2.text_input(t("auth.full_name"))
        c3, c4 = st.columns(2)
        role = c3.selectbox(t("admin.col_role"), list(auth.ROLES), index=len(auth.ROLES) - 1,
                            format_func=role_label)
        temp_pw = c4.text_input(t("admin.temp_password"), type="password",
                                help=t("auth.password_help", n=auth.MIN_PASSWORD_LEN))
        submitted = st.form_submit_button(t("admin.create_button"), type="primary")

    if submitted:
        try:
            adb.create_user(username, temp_pw, role, full_name=full_name, must_change_password=True,
                            actor=me["username"], actor_role=me["role"])
        except auth.AuthError as err:
            st.error(_err_text(err))
            return
        st.session_state["adm_suggested_pw"] = auth.generate_temp_password()
        _flash("success", t("admin.created_ok", name=auth.normalize_username(username)))
        st.rerun()


def _render_manage_user(me: dict, users: list[dict]):
    adb = auth.get_auth_db()
    st.markdown(f"#### 🛠️ {t('admin.manage_title')}")

    by_id = {u["id"]: u for u in users}
    uid = st.selectbox(
        t("admin.select_user"), list(by_id.keys()),
        format_func=lambda i: f"{by_id[i]['username']} — {role_label(by_id[i]['role'])}",
        key="adm_selected_user")
    target = by_id[uid]
    is_self = target["id"] == me["id"]
    if is_self:
        st.caption(f"ℹ️ {t('admin.self_note')}")

    c1, c2 = st.columns(2)

    # ---- rôle ----
    with c1:
        new_role = st.selectbox(
            t("admin.col_role"), list(auth.ROLES), index=list(auth.ROLES).index(target["role"]),
            format_func=role_label, key=f"adm_role_{uid}", disabled=is_self)
        if st.button(t("admin.apply_role"), key=f"adm_role_btn_{uid}",
                     disabled=is_self or new_role == target["role"]):
            try:
                adb.set_role(uid, new_role, me["id"], me["username"], me["role"])
                _flash("success", t("admin.role_changed", name=target["username"]))
            except auth.AuthError as err:
                _flash("error", _err_text(err))
            st.rerun()

    # ---- activation / déverrouillage ----
    with c2:
        if target["active"]:
            if st.button(f"⛔ {t('admin.deactivate')}", key=f"adm_off_{uid}", disabled=is_self):
                try:
                    adb.set_active(uid, False, me["id"], me["username"], me["role"])
                    _flash("success", t("admin.deactivated", name=target["username"]))
                except auth.AuthError as err:
                    _flash("error", _err_text(err))
                st.rerun()
        else:
            if st.button(f"✅ {t('admin.activate')}", key=f"adm_on_{uid}"):
                adb.set_active(uid, True, me["id"], me["username"], me["role"])
                _flash("success", t("admin.activated", name=target["username"]))
                st.rerun()
        if adb.is_locked(target):
            if st.button(f"🔓 {t('admin.unlock')}", key=f"adm_unlock_{uid}"):
                adb.unlock_user(uid, me["username"], me["role"])
                _flash("success", t("admin.unlocked", name=target["username"]))
                st.rerun()

    # ---- réinitialisation du mot de passe ----
    with st.expander(f"🔑 {t('admin.reset_title')}"):
        st.caption(t("admin.reset_caption"))
        with st.form(f"adm_reset_form_{uid}", clear_on_submit=True):
            new_pw = st.text_input(t("admin.temp_password"), type="password",
                                   help=t("auth.password_help", n=auth.MIN_PASSWORD_LEN))
            do_reset = st.form_submit_button(t("admin.reset_button"))
        if do_reset:
            try:
                adb.admin_reset_password(uid, new_pw, me["username"], me["role"])
                _flash("success", t("admin.reset_ok", name=target["username"]))
                st.rerun()
            except auth.AuthError as err:
                st.error(_err_text(err))


def _render_users_tab(me: dict):
    users = auth.get_auth_db().list_users()
    st.markdown(f"#### 👥 {t('admin.users_title')} ({len(users)})")
    _users_table(users)
    st.markdown("---")
    _render_manage_user(me, users)
    st.markdown("---")
    _render_create_user(me)

    with st.expander(f"ℹ️ {t('admin.roles_legend')}"):
        for r in auth.ROLES:
            st.markdown(f"**{role_label(r)}** — {t(f'auth.role_{r}_desc')}")


# ------------------------------------------------------------
# Journal d'audit
# ------------------------------------------------------------
def _render_audit_tab():
    adb = auth.get_auth_db()
    st.caption(t("admin.audit_caption"))

    ALL = ""
    c1, c2, c3 = st.columns(3)
    user_sel = c1.selectbox(t("admin.audit_user"), [ALL] + adb.audit_users(),
                            format_func=lambda x: t("admin.audit_all") if x == ALL else x, key="adm_au_user")
    act_sel = c2.selectbox(t("admin.audit_action"), [ALL] + adb.audit_actions(),
                           format_func=lambda x: t("admin.audit_all") if x == ALL else _audit_action_label(x),
                           key="adm_au_action")
    search = c3.text_input(t("admin.audit_search"), key="adm_au_search")

    date_from = date_to = None
    if st.checkbox(t("admin.audit_filter_dates"), key="adm_au_use_dates"):
        d1, d2 = st.columns(2)
        date_from = d1.date_input(t("admin.audit_from"), value=date.today() - timedelta(days=30),
                                  format="DD/MM/YYYY", key="adm_au_from")
        date_to = d2.date_input(t("admin.audit_to"), value=date.today(),
                                format="DD/MM/YYYY", key="adm_au_to")

    filters = dict(
        username=user_sel or None,
        action=act_sel or None,
        date_from=date_from.isoformat() if date_from else None,
        date_to=date_to.isoformat() if date_to else None,
        search=search.strip() or None,
    )

    total = adb.count_audit(**filters)
    n_pages = max(1, -(-total // AUDIT_PAGE_SIZE))
    p1, p2 = st.columns([1, 3])
    # La clé dépend des filtres : si le nombre de pages diminue, le widget repart à 1
    # au lieu de garder une valeur hors limites (erreur Streamlit).
    page_key = "adm_au_page_" + _digest_filters(filters)
    page = p1.number_input(t("admin.audit_page"), min_value=1, max_value=n_pages, value=1, step=1,
                           key=page_key)
    p2.metric(t("admin.audit_total"), total)

    rows = adb.get_audit(limit=AUDIT_PAGE_SIZE, offset=(int(page) - 1) * AUDIT_PAGE_SIZE, **filters)
    if not rows:
        st.info(t("admin.audit_empty"))
        return

    def _fmt(r):
        return {
            t("admin.audit_col_time"): r["ts"],
            t("admin.audit_user"): r["username"],
            t("admin.col_role"): role_label(r["role"]) if r["role"] in auth.ROLES else (r["role"] or "—"),
            t("admin.audit_action"): _audit_action_label(r["action"]),
            t("admin.audit_col_entity"): r["entity"] or "—",
            t("admin.audit_col_ref"): r["entity_id"] or "—",
            t("admin.audit_col_details"): r["details"] or "",
        }

    st.dataframe(pd.DataFrame([_fmt(r) for r in rows]), use_container_width=True, hide_index=True)

    export_rows = adb.get_audit(limit=AUDIT_EXPORT_MAX, offset=0, **filters)
    csv = pd.DataFrame([_fmt(r) for r in export_rows]).to_csv(index=False).encode("utf-8-sig")
    st.download_button(f"⬇️ {t('admin.audit_export')}", data=csv, file_name="journal_audit_hse_pyxis.csv",
                       mime="text/csv", key="adm_au_export")


# ------------------------------------------------------------
# Point d'entrée
# ------------------------------------------------------------
def render_admin_page():
    auth.require_permission("manage_users", "admin_page")
    me = auth.current_user()

    st.header(f"🔐 {t('admin.title')}")
    _show_flash()
    tab_users, tab_audit = st.tabs([f"👥 {t('admin.tab_users')}", f"📜 {t('admin.tab_audit')}"])
    with tab_users:
        _render_users_tab(me)
    with tab_audit:
        if auth.has_permission("view_audit"):
            _render_audit_tab()
