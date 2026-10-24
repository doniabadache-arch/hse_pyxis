"""
ui/pages/calendar.py — HSE PYXIS
==================================
Page « Programme d'inspection » : calendrier mensuel, planification,
fenêtre du jour (Commencer / Modifier / Supprimer) et liste filtrable.

Calendrier :
  • streamlit-calendar (FullCalendar.js) s'il est installé
  • sinon, grille mensuelle intégrée (aucune dépendance)

Couleurs :  🔴 aujourd'hui · 🟡 en cours · 🟢 terminé · 🟠 à venir · 🔵 en retard · ⚪ rien

Usage (inspection_app.py) :
    from ui.pages.calendar import render_calendar_page
    render_calendar_page(db, sites=[...], sections=[...], default_site="...")
"""

import calendar as _cal
from datetime import date, datetime, time as dtime

import pandas as pd
import streamlit as st

import auth
from ui.i18n import t

# ------------------------------------------------------------
# Statuts
# ------------------------------------------------------------
STATUS_ORDER = ["today", "in_progress", "done", "upcoming", "overdue"]
STATUS_EMOJI = {
    "today": "🔴", "in_progress": "🟡", "done": "🟢",
    "upcoming": "🟠", "overdue": "🔵", "none": "⚪",
}
STATUS_COLOR = {
    "today": "#E53935", "in_progress": "#FBC02D", "done": "#43A047",
    "upcoming": "#FB8C00", "overdue": "#1E88E5",
}


def effective_status(sched: dict, today: date | None = None) -> str:
    """Statut affiché : calculé à partir du statut stocké et de la date."""
    today = today or date.today()
    if sched["status"] == "done":
        return "done"
    if sched["status"] == "in_progress":
        return "in_progress"
    try:
        d = date.fromisoformat(sched["scheduled_date"])
    except (TypeError, ValueError):
        return "upcoming"
    if d == today:
        return "today"
    return "overdue" if d < today else "upcoming"


def status_label(key: str) -> str:
    return f"{STATUS_EMOJI[key]} {t(f'calendar.status_{key}')}"


# ------------------------------------------------------------
# Callbacks (exécutés avant le rerun → modification d'état autorisée)
# ------------------------------------------------------------
def _set_msg(kind: str, text: str):
    st.session_state["cal_msg"] = (kind, text)


def _default_ref(d: date) -> str:
    return f"INSPECTION-{d:%Y%m%d}-{datetime.now():%H%M}"


def _init_form_defaults(sites, sections, default_site):
    ss = st.session_state
    ss.setdefault("cal_new_date", date.today())
    ss.setdefault("cal_new_time", dtime(9, 0))
    ss.setdefault("cal_new_site", default_site if default_site in sites else (sites[0] if sites else ""))
    ss.setdefault("cal_new_ref", "")
    ss.setdefault("cal_new_inspector", "")
    ss.setdefault("cal_new_email", "")
    ss.setdefault("cal_new_sections", [])
    ss.setdefault("cal_new_notes", "")
    # Valeurs devenues invalides (ex. changement de langue) → on les retire
    ss["cal_new_sections"] = [x for x in ss["cal_new_sections"] if x in sections]
    if sites and ss["cal_new_site"] not in sites:
        ss["cal_new_site"] = default_site if default_site in sites else sites[0]


def _reset_new_form():
    ss = st.session_state
    for k in ("cal_new_ref", "cal_new_inspector", "cal_new_email", "cal_new_notes"):
        ss[k] = ""
    ss["cal_new_sections"] = []
    ss["cal_new_date"] = date.today()
    ss["cal_new_time"] = dtime(9, 0)
    ss["calendar_open_form"] = False


def _cb_save_new(db):
    ss = st.session_state
    d: date = ss["cal_new_date"]
    ref = (ss["cal_new_ref"] or "").strip() or _default_ref(d)
    if not (ss["cal_new_site"] or "").strip():
        return _set_msg("error", t("calendar.err_site"))
    email = (ss["cal_new_email"] or "").strip()
    if email and "@" not in email:
        return _set_msg("error", t("calendar.err_email"))
    db.add_scheduled_inspection(
        inspection_id=ref,
        site_name=ss["cal_new_site"],
        scheduled_date=d.isoformat(),
        scheduled_time=ss["cal_new_time"].strftime("%H:%M") if ss["cal_new_time"] else None,
        inspector=(ss["cal_new_inspector"] or "").strip() or None,
        inspector_email=email or None,
        sections=list(ss["cal_new_sections"]),
        notes=(ss["cal_new_notes"] or "").strip() or None,
    )
    ss["cal_selected_day"] = d.isoformat()
    _reset_new_form()
    _set_msg("success", t("calendar.saved"))


def _cb_cancel_new():
    _reset_new_form()


def _cb_start(db, sched: dict):
    """Commencer : statut « en cours » + ouverture de l'Étape 1 avec cette inspection."""
    ss = st.session_state
    ref = sched.get("inspection_id") or _default_ref(date.today())
    db.update_scheduled_inspection(sched["id"], status="in_progress", inspection_id=ref)
    ss["inspection_id_input"] = ref
    if sched.get("site_name"):
        ss["active_site"] = sched["site_name"]
    # Les sections planifiées deviennent les sections à inspecter à l'étape Inspection.
    _ids_by_name = ss.get("_cal_sec_ids") or {}
    _ids = sorted({i for n in (sched.get("sections") or []) for i in _ids_by_name.get(n, [])})
    if _ids:
        ss["insp_sections"] = _ids
    ss["navigation_radio"] = 1
    ss["current_step"] = 1


def _cb_done(db, sid):
    db.update_scheduled_inspection_status(sid, "done")


def _cb_delete(db, sid):
    db.delete_scheduled_inspection(sid)
    st.session_state.pop("cal_edit_id", None)
    _set_msg("success", t("calendar.deleted"))


def _cb_begin_edit(sched: dict):
    ss = st.session_state
    ss["cal_edit_id"] = sched["id"]
    try:
        ss["cal_edit_date"] = date.fromisoformat(sched["scheduled_date"])
    except (TypeError, ValueError):
        ss["cal_edit_date"] = date.today()
    try:
        hh, mm = (sched.get("scheduled_time") or "09:00").split(":")[:2]
        ss["cal_edit_time"] = dtime(int(hh), int(mm))
    except ValueError:
        ss["cal_edit_time"] = dtime(9, 0)
    ss["cal_edit_site"] = sched.get("site_name") or ""
    ss["cal_edit_ref"] = sched.get("inspection_id") or ""
    ss["cal_edit_inspector"] = sched.get("inspector") or ""
    ss["cal_edit_email"] = sched.get("inspector_email") or ""
    ss["cal_edit_sections"] = list(sched.get("sections") or [])
    ss["cal_edit_notes"] = sched.get("notes") or ""


def _cb_save_edit(db):
    ss = st.session_state
    email = (ss["cal_edit_email"] or "").strip()
    if email and "@" not in email:
        return _set_msg("error", t("calendar.err_email"))
    db.update_scheduled_inspection(
        ss["cal_edit_id"],
        inspection_id=(ss["cal_edit_ref"] or "").strip() or None,
        site_name=ss["cal_edit_site"],
        scheduled_date=ss["cal_edit_date"].isoformat(),
        scheduled_time=ss["cal_edit_time"].strftime("%H:%M") if ss["cal_edit_time"] else None,
        inspector=(ss["cal_edit_inspector"] or "").strip() or None,
        inspector_email=email or None,
        sections=list(ss["cal_edit_sections"]),
        notes=(ss["cal_edit_notes"] or "").strip() or None,
    )
    ss["cal_selected_day"] = ss["cal_edit_date"].isoformat()
    ss.pop("cal_edit_id", None)
    _set_msg("success", t("calendar.updated"))


def _cb_cancel_edit():
    st.session_state.pop("cal_edit_id", None)


def _cb_pick_day(iso: str):
    st.session_state["cal_selected_day"] = iso


# ------------------------------------------------------------
# Formulaires
# ------------------------------------------------------------
def _render_new_form(db, sites, sections, default_site):
    if not auth.has_permission("edit_schedule"):
        return          # lecteur : consultation seulement
    _init_form_defaults(sites, sections, default_site)
    with st.expander(
        t("calendar.new"), expanded=bool(st.session_state.get("calendar_open_form"))
    ):
        c1, c2 = st.columns(2)
        c1.date_input(t("calendar.date"), key="cal_new_date", format="DD/MM/YYYY")
        c2.time_input(t("calendar.time"), key="cal_new_time", step=900)

        c1, c2 = st.columns(2)
        if sites:
            c1.selectbox(t("calendar.site"), sites, key="cal_new_site")
        else:
            c1.text_input(t("calendar.site"), key="cal_new_site")
        c2.text_input(t("calendar.ref"), key="cal_new_ref", placeholder=t("calendar.ref_placeholder"))

        c1, c2 = st.columns(2)
        c1.text_input(t("calendar.inspector"), key="cal_new_inspector")
        c2.text_input(t("calendar.inspector_email"), key="cal_new_email")

        st.multiselect(t("calendar.sections"), sections, key="cal_new_sections",
                       help=t("calendar.sections_hint"))
        st.text_area(t("calendar.notes"), key="cal_new_notes", height=80)

        b1, b2, _ = st.columns([1, 1, 3])
        b1.button(t("calendar.save"), type="primary", key="cal_btn_save_new",
                  on_click=_cb_save_new, args=(db,))
        b2.button(t("calendar.cancel"), key="cal_btn_cancel_new", on_click=_cb_cancel_new)


def _render_edit_form(db, sites, sections):
    st.markdown(f"**{t('calendar.edit')}**")
    c1, c2 = st.columns(2)
    c1.date_input(t("calendar.date"), key="cal_edit_date", format="DD/MM/YYYY")
    c2.time_input(t("calendar.time"), key="cal_edit_time", step=900)
    c1, c2 = st.columns(2)
    if sites:
        opts = list(sites)
        cur = st.session_state.get("cal_edit_site")
        if cur and cur not in opts:
            opts.append(cur)
        c1.selectbox(t("calendar.site"), opts, key="cal_edit_site")
    else:
        c1.text_input(t("calendar.site"), key="cal_edit_site")
    c2.text_input(t("calendar.ref"), key="cal_edit_ref")
    c1, c2 = st.columns(2)
    c1.text_input(t("calendar.inspector"), key="cal_edit_inspector")
    c2.text_input(t("calendar.inspector_email"), key="cal_edit_email")
    opts = list(sections)
    for s in st.session_state.get("cal_edit_sections", []):
        if s not in opts:
            opts.append(s)
    st.multiselect(t("calendar.sections"), opts, key="cal_edit_sections")
    st.text_area(t("calendar.notes"), key="cal_edit_notes", height=80)
    b1, b2, _ = st.columns([1, 1, 3])
    b1.button(t("calendar.save"), type="primary", key="cal_btn_save_edit",
              on_click=_cb_save_edit, args=(db,))
    b2.button(t("calendar.cancel"), key="cal_btn_cancel_edit", on_click=_cb_cancel_edit)


# ------------------------------------------------------------
# Calendrier
# ------------------------------------------------------------
def _legend():
    parts = [status_label(k) for k in STATUS_ORDER]
    parts.append(f"{STATUS_EMOJI['none']} {t('calendar.status_none')}")
    st.caption("  ·  ".join(parts))


def _events(all_sched, today):
    events = []
    for s in all_sched:
        key = effective_status(s, today)
        title = f"{s.get('scheduled_time') or ''} {s.get('site_name') or ''}".strip()
        events.append({
            "id": str(s["id"]),
            "title": title or (s.get("inspection_id") or "—"),
            "start": s["scheduled_date"],
            "allDay": True,
            "color": STATUS_COLOR[key],
        })
    return events


def _render_fullcalendar(all_sched, today) -> bool:
    """Retourne True si streamlit-calendar est disponible et a été affiché."""
    try:
        from streamlit_calendar import calendar as st_calendar
    except ImportError:
        return False

    lang = st.session_state.get("language", "fr")
    state = st_calendar(
        events=_events(all_sched, today),
        options={
            "initialView": "dayGridMonth",
            "locale": lang if lang in ("fr", "en", "ar") else "fr",
            "direction": "rtl" if lang == "ar" else "ltr",
            "height": 560,
            "headerToolbar": {"left": "prev,next today", "center": "title", "right": ""},
        },
        key="prog_calendar",
    )
    if isinstance(state, dict):
        clicked = None
        if state.get("dateClick"):
            clicked = str(state["dateClick"].get("date", ""))[:10]
        elif state.get("eventClick"):
            clicked = str(state["eventClick"].get("event", {}).get("start", ""))[:10]
        if clicked and len(clicked) == 10 and clicked != st.session_state.get("cal_last_click"):
            st.session_state["cal_last_click"] = clicked
            st.session_state["cal_selected_day"] = clicked
    return True


def _render_fallback_grid(all_sched, today):
    """Grille mensuelle sans dépendance : un bouton par jour."""
    st.caption(t("calendar.fallback_hint"))
    ss = st.session_state
    ss.setdefault("cal_year", today.year)
    ss.setdefault("cal_month", today.month)

    c1, c2, _ = st.columns([1, 1, 3])
    year = c1.number_input(t("calendar.year"), min_value=2020, max_value=2100, step=1, key="cal_year")
    month = c2.selectbox(
        t("calendar.month"), list(range(1, 13)), key="cal_month",
        format_func=lambda m: _cal.month_name[m],
    )

    by_day = {}
    for s in all_sched:
        by_day.setdefault(s["scheduled_date"], []).append(effective_status(s, today))

    head = st.columns(7)
    for i, name in enumerate(_cal.day_abbr):
        head[i].markdown(f"**{name}**")
    for week in _cal.Calendar(firstweekday=0).monthdatescalendar(int(year), int(month)):
        cols = st.columns(7)
        for i, d in enumerate(week):
            iso = d.isoformat()
            statuses = by_day.get(iso, [])
            dots = "".join(STATUS_EMOJI[k] for k in dict.fromkeys(statuses))
            label = f"{d.day} {dots}".strip() if d.month == int(month) else f"· {d.day}"
            cols[i].button(
                label, key=f"cal_day_{iso}", use_container_width=True,
                type="primary" if iso == ss.get("cal_selected_day") else "secondary",
                on_click=_cb_pick_day, args=(iso,),
            )


# ------------------------------------------------------------
# Fenêtre du jour
# ------------------------------------------------------------
def _render_day_panel(db, sites, sections, all_sched, today):
    iso = st.session_state.get("cal_selected_day") or today.isoformat()
    try:
        shown = date.fromisoformat(iso).strftime("%d/%m/%Y")
    except ValueError:
        shown = iso
    st.markdown(f"#### {t('calendar.day_title', date=shown)}")

    day_items = [s for s in all_sched if s["scheduled_date"] == iso]
    if not day_items:
        st.info(f"{STATUS_EMOJI['none']} {t('calendar.no_day_inspections')}")
        return

    for s in day_items:
        key = effective_status(s, today)
        with st.container(border=True):
            st.markdown(
                f"**{status_label(key)}** — {s.get('scheduled_time') or '—'} · "
                f"{s.get('site_name') or '—'}"
            )
            st.caption(
                f"{t('calendar.ref')} : {s.get('inspection_id') or '—'}  |  "
                f"{t('calendar.inspector')} : {s.get('inspector') or '—'}"
            )
            if s.get("sections"):
                st.caption(f"{t('calendar.sections')} : " + ", ".join(s["sections"]))
            if s.get("notes"):
                st.caption(f"📝 {s['notes']}")

            can_edit = auth.has_permission("edit_schedule")
            can_delete = auth.has_permission("delete_schedule")
            b1, b2, b3, b4 = st.columns(4)
            if s["status"] != "done" and can_edit:
                b1.button(t("calendar.start"), key=f"cal_start_{s['id']}", type="primary",
                          on_click=_cb_start, args=(db, s))
                b2.button(t("calendar.mark_done"), key=f"cal_done_{s['id']}",
                          on_click=_cb_done, args=(db, s["id"]))
            if can_edit:
                b3.button(t("calendar.edit"), key=f"cal_edit_btn_{s['id']}",
                          on_click=_cb_begin_edit, args=(s,))
            if can_delete:
                b4.button(t("calendar.delete"), key=f"cal_del_{s['id']}",
                          on_click=_cb_delete, args=(db, s["id"]))

            if can_edit and st.session_state.get("cal_edit_id") == s["id"]:
                st.markdown("---")
                _render_edit_form(db, sites, sections)


# ------------------------------------------------------------
# Liste
# ------------------------------------------------------------
def _render_list(all_sched, today):
    if not all_sched:
        st.info(t("programme.list_empty"))
        return
    ALL = "__all__"
    all_label = lambda x: t("programme.filter_all") if x == ALL else x  # noqa: E731

    inspectors = sorted({s["inspector"] for s in all_sched if s.get("inspector")})
    sites = sorted({s["site_name"] for s in all_sched if s.get("site_name")})
    secs = sorted({x for s in all_sched for x in (s.get("sections") or [])})
    months = sorted({s["scheduled_date"][:7] for s in all_sched})

    c1, c2, c3 = st.columns(3)
    f_status = c1.multiselect(t("programme.filter_status"), STATUS_ORDER,
                              format_func=status_label, key="prog_f_status")
    f_insp = c2.selectbox(t("programme.filter_inspector"), [ALL] + inspectors,
                          format_func=all_label, key="prog_f_insp")
    f_site = c3.selectbox(t("programme.filter_site"), [ALL] + sites,
                          format_func=all_label, key="prog_f_site")
    c1, c2, _ = st.columns(3)
    f_sec = c1.selectbox(t("programme.filter_section"), [ALL] + secs,
                         format_func=all_label, key="prog_f_sec")
    f_month = c2.selectbox(t("programme.filter_month"), [ALL] + months,
                           format_func=all_label, key="prog_f_month")

    rows = []
    for s in all_sched:
        key = effective_status(s, today)
        if f_status and key not in f_status:
            continue
        if f_insp != ALL and s.get("inspector") != f_insp:
            continue
        if f_site != ALL and s.get("site_name") != f_site:
            continue
        if f_sec != ALL and f_sec not in (s.get("sections") or []):
            continue
        if f_month != ALL and not s["scheduled_date"].startswith(f_month):
            continue
        rows.append({
            t("programme.col_date"): s["scheduled_date"],
            t("programme.col_time"): s.get("scheduled_time") or "",
            t("programme.col_site"): s.get("site_name") or "",
            t("programme.col_ref"): s.get("inspection_id") or "",
            t("programme.col_inspector"): s.get("inspector") or "",
            t("programme.col_sections"): ", ".join(s.get("sections") or []),
            t("programme.col_status"): status_label(key),
        })
    if rows:
        st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)
    else:
        st.info(t("programme.list_empty"))


# ------------------------------------------------------------
# Rappels
# ------------------------------------------------------------
def _render_reminders(db):
    if not auth.has_permission("edit_schedule"):
        return          # enregistrer l'email / lancer les rappels = inspecteur+
    with st.expander(t("calendar.reminders_title"), expanded=False):
        st.caption(t("calendar.reminders_caption"))
        st.text_input(t("calendar.user_email"), key="cal_user_email",
                      value=db.get_setting("user_email", ""))
        c1, c2, _ = st.columns([1, 1, 3])
        if c1.button(t("calendar.user_email_save"), key="cal_user_email_save"):
            db.save_setting("user_email", (st.session_state.get("cal_user_email") or "").strip())
            st.success(t("calendar.user_email_saved"))
        if c2.button(t("calendar.run_reminders"), key="cal_run_reminders"):
            try:
                from scheduler import run_scheduler
                log = run_scheduler(db)
                n_sent = sum(1 for r in log if r["status"] == "sent")
                st.success(t("calendar.reminders_done", n=n_sent))
                errs = [r for r in log if r["status"] in ("error", "email_not_configured")]
                if errs:
                    st.warning(t("calendar.reminders_errors", n=len(errs)))
            except Exception as e:
                st.error(t("calendar.reminders_failed", error=e))


# ------------------------------------------------------------
# Point d'entrée
# ------------------------------------------------------------
def render_calendar_page(db, sites=None, sections=None, default_site=None,
                         section_ids_by_name=None):
    """Page complète « Programme d'inspection ».

    section_ids_by_name : {nom de section affiché -> [section_id]} (facultatif) ; sert à
    reprendre les sections d'une inspection planifiée quand on la démarre.
    """
    sites = list(sites or [])
    sections = list(sections or [])
    st.session_state["_cal_sec_ids"] = dict(section_ids_by_name or {})
    today = date.today()

    st.header(t("calendar.title"))
    st.caption(t("calendar.subtitle"))

    msg = st.session_state.pop("cal_msg", None)
    if msg:
        (st.success if msg[0] == "success" else st.error)(msg[1])

    _render_new_form(db, sites, sections, default_site)

    all_sched = db.get_scheduled_inspections()
    tab_cal, tab_list = st.tabs([t("calendar.tab_calendar"), t("calendar.tab_list")])

    with tab_cal:
        _legend()
        if not _render_fullcalendar(all_sched, today):
            _render_fallback_grid(all_sched, today)
        st.markdown("---")
        _render_day_panel(db, sites, sections, all_sched, today)

    with tab_list:
        _render_list(all_sched, today)

    _render_reminders(db)
