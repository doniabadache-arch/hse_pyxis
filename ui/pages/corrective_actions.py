"""
ui/pages/corrective_actions.py — Suivi global des actions correctives (HSE PYXIS)
==================================================================================
Page autonome qui utilise l'API de InspectionDB (table corrective_actions)
et le service email/scheduler existants.

Fonctionnalités :
  • Créer une action corrective (symptôme NC/PC + responsable + échéance + priorité)
  • Lister, filtrer, mettre à jour le statut, supprimer
  • Envoyer les rappels par email (via scheduler.check_overdue_actions)
  • Exporter en CSV
  • Respect automatique des permissions (auth.guard_db)

⚠️ Aucune table n'est créée ici : `inspection_db.py` gère déjà
   `corrective_actions`. Toutes les écritures passent par `auth.guard_db()`
   via l'instance `db` passée en argument.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta

import pandas as pd
import streamlit as st

import auth
import scheduler
from ui.i18n import t


# ============================================================
# Helpers
# ============================================================
def _status_label(code: str) -> str:
    """Libellé traduit d'un statut de corrective_actions."""
    return t(f"actions.status_{code}") if code else "—"


def _priority_label(code: str) -> str:
    return t(f"actions.priority_{code or 'medium'}")


def _is_late(action: dict, today_iso: str) -> bool:
    return bool(
        action.get("deadline")
        and action["deadline"] < today_iso
        and action.get("status") not in ("done", "closed", "cancelled")
    )


def _items_for_inspection(db, inspection_id: str) -> list[str]:
    """Liste les item_id de l'inspection qui sont NC ou PC (pour le selectbox)."""
    if not inspection_id:
        return []
    try:
        conformites = db.get_conformity_by_inspection(inspection_id) or {}
    except Exception:
        return []
    return [iid for iid, c in conformites.items() if c in ("NC", "PC")]


# ============================================================
# Filtres + liste
# ============================================================
def _render_filters(db, site_name: str | None):
    """Filtres : inspection, statut, priorité, retard uniquement."""
    with st.expander("🎛️ " + t("actions.filter_title", default="Filtres"), expanded=False):
        c1, c2, c3 = st.columns(3)
        insp = c1.text_input(
            t("actions.filter_inspection", default="ID Inspection (vide = toutes)"),
            value=st.session_state.get("ca_filter_insp", ""),
            key="ca_filter_insp",
        )
        statut_options = ["", "open", "in_progress", "done", "cancelled"]
        statut = c2.selectbox(
            t("actions.filter_status"),
            statut_options,
            format_func=lambda s: t("actions.filter_all") if s == "" else _status_label(s),
            key="ca_filter_status",
        )
        prio_options = ["", "low", "medium", "high", "critical"]
        prio = c3.selectbox(
            t("actions.filter_priority", default="Priorité"),
            prio_options,
            format_func=lambda p: t("actions.filter_all") if p == "" else _priority_label(p),
            key="ca_filter_prio",
        )
        only_late = st.checkbox(
            t("actions.filter_late"),
            value=st.session_state.get("ca_filter_late", False),
            key="ca_filter_late",
        )
    return insp.strip() or None, statut or None, prio or None, only_late


def _render_actions_list(db, inspection_id: str | None, statut: str | None,
                         prio: str | None, only_late: bool, me: dict | None):
    """Affiche la liste filtrée + actions par ligne."""
    today_iso = date.today().isoformat()
    actions = db.get_corrective_actions(inspection_id=inspection_id, status=statut) or []

    if prio:
        actions = [a for a in actions if (a.get("priority") or "medium") == prio]
    if only_late:
        actions = [a for a in actions if _is_late(a, today_iso)]

    if not actions:
        st.info(t("actions.empty"))
        return

    # KPIs
    n_total = len(actions)
    n_late = sum(1 for a in actions if _is_late(a, today_iso))
    n_done = sum(1 for a in actions if a.get("status") in ("done", "closed"))
    n_open = n_total - n_done

    k1, k2, k3, k4 = st.columns(4)
    k1.metric(t("actions.kpi_total"), n_total)
    k2.metric(t("actions.kpi_open", default="🟠 Ouvertes"), n_open)
    k3.metric(t("actions.kpi_late"), n_late)
    k4.metric(t("actions.kpi_closed"), n_done)

    st.markdown("---")

    can_edit = auth.has_permission("edit_actions")
    can_delete = auth.has_permission("delete_actions")

    for a in actions:
        late = _is_late(a, today_iso)
        statut_code = a.get("status") or "open"
        icon = "🔴" if late else ("✅" if statut_code in ("done", "closed") else "🟠")
        title = f"{icon} #{a['id']} — {(a.get('action') or '')[:80]}"

        with st.expander(title, expanded=late):
            c1, c2, c3 = st.columns(3)
            c1.markdown(f"**{t('actions.col_responsible')} :** {a.get('responsible') or '—'}")
            c2.markdown(f"**{t('actions.col_deadline')} :** {a.get('deadline') or '—'}")
            c3.markdown(f"**{t('actions.priority')} :** {_priority_label(a.get('priority'))}")

            c1, c2 = st.columns(2)
            c1.markdown(f"**{t('actions.linked_inspection')} :** {a.get('inspection_id') or '—'}")
            c2.markdown(f"**{t('actions.nc_label')} :** {a.get('item_id') or '—'}")

            if a.get("responsible_email"):
                st.caption(f"📧 {a['responsible_email']}")
            if a.get("completed_at"):
                st.caption(t("actions.completed_on", date=a["completed_at"]))

            st.markdown("---")

            bc1, bc2, bc3 = st.columns([2, 2, 3])

            with bc1:
                new_status = st.selectbox(
                    t("actions.change_status"),
                    ["open", "in_progress", "done", "cancelled"],
                    index=["open", "in_progress", "done", "cancelled"].index(
                        statut_code if statut_code in ("open", "in_progress", "done", "cancelled") else "open"
                    ),
                    format_func=_status_label,
                    key=f"ca_status_{a['id']}",
                    disabled=not can_edit,
                )
                if can_edit and new_status != statut_code:
                    if st.button(t("actions.update_button"), key=f"ca_upd_{a['id']}"):
                        try:
                            if new_status == "done":
                                db.complete_corrective_action(a["id"])
                            else:
                                with _closing_conn_ctx(db) as conn:
                                    conn.execute(
                                        "UPDATE corrective_actions SET status = ? WHERE id = ?",
                                        (new_status, a["id"]),
                                    )
                                    conn.commit()
                            st.success(t("actions.status_updated"))
                            st.rerun()
                        except Exception as e:
                            st.error(f"❌ {e}")

            with bc2:
                if can_delete:
                    if st.button(t("actions.delete_button"), key=f"ca_del_{a['id']}"):
                        try:
                            db.delete_corrective_action(a["id"])
                            st.warning(t("actions.action_deleted"))
                            st.rerun()
                        except Exception as e:
                            st.error(f"❌ {e}")

            with bc3:
                if a.get("responsible_email") and auth.has_permission("send_email"):
                    if st.button(
                        f"📧 {t('actions.send_reminder', default='Envoyer un rappel')}",
                        key=f"ca_mail_{a['id']}",
                    ):
                        try:
                            from email_service import send_email
                            html = (
                                f"<h2>Rappel : action corrective #{a['id']}</h2>"
                                f"<p><b>Action :</b> {a.get('action') or '—'}</p>"
                                f"<p><b>Échéance :</b> {a.get('deadline') or '—'}</p>"
                                f"<p><b>Priorité :</b> {_priority_label(a.get('priority'))}</p>"
                                f"<p><b>Inspection :</b> {a.get('inspection_id') or '—'}</p>"
                            )
                            res = send_email(
                                to=a["responsible_email"],
                                subject=f"⚠️ Rappel action corrective #{a['id']}",
                                html_body=html,
                            )
                            if res.get("ok"):
                                st.success(f"✅ {t('actions.reminder_sent', default='Rappel envoyé via')} {res.get('provider', '—')}")
                            else:
                                st.error(f"❌ {res.get('error') or 'Envoi échoué'}")
                        except Exception as e:
                            st.error(f"❌ {e}")


# ============================================================
# Formulaire de création
# ============================================================
def _render_create_form(db, inspection_id: str | None, site_name: str | None):
    if not auth.has_permission("edit_actions"):
        st.caption(t("auth.read_only_notice"))
        return

    with st.expander(f"➕ {t('actions.new_action')}", expanded=False):
        item_options = [""] + _items_for_inspection(db, inspection_id or "")
        with st.form("ca_create_form", clear_on_submit=True):
            c1, c2 = st.columns(2)
            insp_input = c1.text_input(
                t("actions.field_inspection"),
                value=inspection_id or "",
            )
            nc_sel = c2.selectbox(
                t("actions.field_nc"),
                item_options,
                format_func=lambda x: x or t("actions.item_none"),
            )

            action_txt = st.text_area(
                t("actions.field_description"), height=90,
            )

            c1, c2 = st.columns(2)
            resp = c1.text_input(t("actions.field_responsible"))
            resp_email = c2.text_input(t("actions.field_email"))

            c1, c2, c3 = st.columns(3)
            deadline = c1.date_input(
                t("actions.field_deadline"),
                value=date.today() + timedelta(days=14),
                format="DD/MM/YYYY",
            )
            priority = c2.selectbox(
                t("actions.priority"),
                ["low", "medium", "high", "critical"],
                index=1,
                format_func=_priority_label,
            )
            statut = c3.selectbox(
                t("actions.field_status"),
                ["open", "in_progress", "done", "cancelled"],
                format_func=_status_label,
            )

            submitted = st.form_submit_button(
                t("actions.create_button"), type="primary", use_container_width=True,
            )

        if submitted:
            if not action_txt.strip():
                st.error(t("actions.description_required"))
                return
            try:
                new_id = db.add_corrective_action(
                    inspection_id=(insp_input.strip() or inspection_id or "GENERAL"),
                    item_id=(nc_sel or None),
                    action=action_txt.strip(),
                    responsible=(resp.strip() or None),
                    responsible_email=(resp_email.strip() or None),
                    deadline=deadline.isoformat(),
                    priority=priority,
                )
                # Si le statut initial n'est pas "open", le mettre à jour
                if statut != "open" and new_id:
                    if statut == "done":
                        db.complete_corrective_action(new_id)
                    else:
                        with _closing_conn_ctx(db) as conn:
                            conn.execute(
                                "UPDATE corrective_actions SET status = ? WHERE id = ?",
                                (statut, new_id),
                            )
                            conn.commit()
                st.success(t("actions.created_ok"))
                st.rerun()
            except Exception as e:
                st.error(f"❌ {e}")


# ============================================================
# Bouton global : envoyer les rappels via scheduler
# ============================================================
def _render_reminders_block(db, site_name: str | None):
    if not auth.has_permission("send_email"):
        return

    with st.expander(f"🔔 {t('calendar.reminders_title')}", expanded=False):
        st.caption(t("calendar.reminders_caption"))

        user_email = db.get_setting("user_email") or ""
        new_email = st.text_input(
            t("calendar.user_email"),
            value=user_email,
            key="ca_user_email",
        )
        if st.button(t("calendar.user_email_save"), key="ca_save_email"):
            db.save_setting("user_email", new_email.strip())
            st.success(t("calendar.user_email_saved"))
            st.rerun()

        if st.button(
            f"▶️ {t('calendar.run_reminders')}",
            key="ca_run_reminders",
            type="primary",
        ):
            try:
                results = scheduler.run_scheduler(
                    db=db, now=datetime.now(), dry_run=False, include_weekly=False,
                )
                sent = sum(1 for r in results if r.get("status") == "sent")
                errors = sum(1 for r in results if r.get("status") == "error")
                st.success(t("calendar.reminders_done", n=sent))
                if errors:
                    st.warning(t("calendar.reminders_errors", n=errors))
                with st.expander("📋 Détail", expanded=False):
                    st.dataframe(pd.DataFrame(results), use_container_width=True)
            except Exception as e:
                st.error(t("calendar.reminders_failed", error=e))


# ============================================================
# Export CSV
# ============================================================
def _render_export(db, inspection_id: str | None):
    actions = db.get_corrective_actions(inspection_id=inspection_id) or []
    if not actions:
        return
    df = pd.DataFrame(actions)
    csv = df.to_csv(index=False).encode("utf-8-sig")
    st.download_button(
        t("actions.export_csv"),
        data=csv,
        file_name=f"actions_correctives_{inspection_id or 'all'}.csv",
        mime="text/csv",
        use_container_width=True,
        key="ca_export_csv",
    )


# ============================================================
# Contexte helper : connexion SQLite directe pour UPDATE status custom
# (car InspectionDB n'a pas de méthode dédiée pour "in_progress")
# ============================================================
from contextlib import contextmanager


@contextmanager
def _closing_conn_ctx(db):
    """Accès direct à la connexion SQLite de InspectionDB."""
    import sqlite3
    conn = sqlite3.connect(db.db_path)
    try:
        yield conn
    finally:
        conn.close()


# ============================================================
# Point d'entrée
# ============================================================
def render_corrective_actions_page(
    db=None,
    site_name: str | None = None,
    user: dict | None = None,
):
    """
    Affiche la page complète. `db` doit être un InspectionDB (ou un guard_db).
    `site_name` est informatif (filtres optionnels).
    `user` : utilisateur courant (par défaut auth.current_user()).
    """
    st.header(f"✅ {t('actions.global_title')}")
    st.caption(t("actions.global_subtitle"))

    if db is None:
        st.error("❌ Aucune base de données fournie. Passez `db=...` à render_corrective_actions_page().")
        return

    me = user or auth.current_user() or {}

    # Formulaire de création
    _render_create_form(db, inspection_id=None, site_name=site_name)

    st.markdown("---")

    # Filtres
    insp_f, statut_f, prio_f, only_late = _render_filters(db, site_name)

    # Liste
    _render_actions_list(db, insp_f, statut_f, prio_f, only_late, me)

    st.markdown("---")

    # Rappels + export
    c1, c2 = st.columns([2, 1])
    with c1:
        _render_reminders_block(db, site_name)
    with c2:
        _render_export(db, insp_f)