"""
scheduler.py — HSE PYXIS
==========================
Rappels automatiques par email (inspections programmées + actions correctives).

Utilisation :
  • Manuelle   : bouton « Lancer les rappels » dans la page Programme
  • Automatique : tâche planifiée quotidienne (cron / Planificateur de tâches Windows)
                  →  python scheduler.py
                  →  python scheduler.py --dry-run     (affiche sans envoyer)
                  →  python scheduler.py --weekly      (ajoute le rapport hebdomadaire)

Rappels :
  • 7 jours avant  • la veille (envoyé à partir de 12h)  • le jour même
  • actions correctives en retard • rapport hebdomadaire (optionnel)

Chaque rappel n'est envoyé qu'une fois (journal dans la table `settings`).
"""

import sys
from datetime import date, datetime, timedelta
from html import escape

from inspection_db import InspectionDB


# ============================================================
# OUTILS
# ============================================================
def _already_sent(db, key: str) -> bool:
    return db.get_setting(f"reminder:{key}") is not None


def _mark_sent(db, key: str):
    db.save_setting(f"reminder:{key}", datetime.now().isoformat(timespec="seconds"))


def _send(db, key, to, subject, html, dry_run, log):
    """Envoie un email une seule fois. Ajoute une ligne au journal `log`."""
    if not to:
        log.append({"key": key, "status": "skipped_no_email", "subject": subject})
        return
    if _already_sent(db, key):
        log.append({"key": key, "status": "already_sent", "to": to, "subject": subject})
        return
    if dry_run:
        log.append({"key": key, "status": "dry_run", "to": to, "subject": subject})
        return

    import email_service
    if not email_service.is_configured():
        log.append({"key": key, "status": "email_not_configured", "to": to, "subject": subject})
        return
    try:
        res = email_service.send_email(to=to, subject=subject, html_body=html)
    except Exception as e:  # ne jamais interrompre la boucle
        res = {"ok": False, "error": str(e)}
    if res.get("ok"):
        _mark_sent(db, key)
        log.append({"key": key, "status": "sent", "to": to, "subject": subject})
    else:
        log.append({"key": key, "status": "error", "to": to, "subject": subject,
                    "error": res.get("error")})


def _wrap(title: str, body_html: str) -> str:
    return (
        "<div style='font-family:Arial,sans-serif;max-width:600px'>"
        f"<h2 style='color:#0B5FA5'>{escape(title)}</h2>{body_html}"
        "<hr><p style='color:#888;font-size:12px'>HSE PYXIS — rappel automatique</p></div>"
    )


def _insp_html(s: dict) -> str:
    sections = ", ".join(s.get("sections") or []) or "—"
    return (
        f"<p><b>Site :</b> {escape(s.get('site_name') or '—')}<br>"
        f"<b>Date :</b> {escape(s['scheduled_date'])} {escape(s.get('scheduled_time') or '')}<br>"
        f"<b>Référence :</b> {escape(s.get('inspection_id') or '—')}<br>"
        f"<b>Inspecteur :</b> {escape(s.get('inspector') or '—')}<br>"
        f"<b>Sections :</b> {escape(sections)}<br>"
        f"<b>Notes :</b> {escape(s.get('notes') or '—')}</p>"
    )


def _open_inspections_on(db, day: date):
    iso = day.isoformat()
    return [s for s in db.get_scheduled_inspections(date_from=iso, date_to=iso)
            if s["status"] in ("planned", "in_progress")]


# ============================================================
# RAPPELS
# ============================================================
def check_inspections_today(db, today, dry_run=False, log=None):
    log = log if log is not None else []
    for s in _open_inspections_on(db, today):
        _send(db, f"today:{s['id']}:{today}", s.get("inspector_email"),
              f"📅 Inspection aujourd'hui — {s.get('site_name') or ''}",
              _wrap("Inspection prévue aujourd'hui", _insp_html(s)), dry_run, log)
    return log


def check_inspections_tomorrow(db, today, dry_run=False, log=None):
    log = log if log is not None else []
    tomorrow = today + timedelta(days=1)
    for s in _open_inspections_on(db, tomorrow):
        _send(db, f"tomorrow:{s['id']}:{tomorrow}", s.get("inspector_email"),
              f"📅 Inspection demain — {s.get('site_name') or ''}",
              _wrap("Inspection prévue demain", _insp_html(s)), dry_run, log)
    return log


def check_inspections_in_7_days(db, today, dry_run=False, log=None):
    log = log if log is not None else []
    target = today + timedelta(days=7)
    for s in _open_inspections_on(db, target):
        _send(db, f"d7:{s['id']}:{target}", s.get("inspector_email"),
              f"📅 Inspection dans 7 jours — {s.get('site_name') or ''}",
              _wrap("Inspection prévue dans 7 jours", _insp_html(s)), dry_run, log)
    return log


def check_overdue_actions(db, today, dry_run=False, log=None):
    """Une alerte par action en retard et par jour, + un résumé à l'utilisateur."""
    log = log if log is not None else []
    overdue = [a for a in db.get_corrective_actions(status="open")
               if a.get("deadline") and a["deadline"] < today.isoformat()]

    for a in overdue:
        body = (
            f"<p><b>Action :</b> {escape(a['action'])}<br>"
            f"<b>Inspection :</b> {escape(a['inspection_id'])} "
            f"({escape(a.get('item_id') or '—')})<br>"
            f"<b>Échéance :</b> {escape(a['deadline'])} — <b style='color:#c00'>en retard</b><br>"
            f"<b>Priorité :</b> {escape(a.get('priority') or '—')}</p>"
        )
        _send(db, f"overdue:{a['id']}:{today}", a.get("responsible_email"),
              "⚠️ Action corrective en retard",
              _wrap("Action corrective en retard", body), dry_run, log)

    user_email = db.get_setting("user_email")
    if overdue and user_email:
        rows = "".join(
            f"<li>{escape(a['deadline'])} — {escape(a['action'])} "
            f"({escape(a.get('responsible') or '—')})</li>" for a in overdue
        )
        _send(db, f"overdue_summary:{today}", user_email,
              f"⚠️ {len(overdue)} action(s) corrective(s) en retard",
              _wrap("Actions en retard", f"<ul>{rows}</ul>"), dry_run, log)
    return log


def weekly_report(db, today, dry_run=False, log=None, force=False):
    """Rapport hebdomadaire (le lundi, ou force=True) envoyé à l'email utilisateur."""
    log = log if log is not None else []
    if not force and today.weekday() != 0:
        return log
    user_email = db.get_setting("user_email")

    week_end = today + timedelta(days=7)
    upcoming = db.get_scheduled_inspections(date_from=today.isoformat(),
                                            date_to=week_end.isoformat())
    open_actions = db.get_corrective_actions(status="open")
    n_overdue = sum(1 for a in open_actions
                    if a.get("deadline") and a["deadline"] < today.isoformat())

    items = "".join(
        f"<li>{escape(s['scheduled_date'])} — {escape(s.get('site_name') or '—')} "
        f"({escape(s.get('inspector') or '—')})</li>" for s in upcoming
    ) or "<li>Aucune inspection programmée</li>"
    body = (
        f"<h3>Inspections des 7 prochains jours</h3><ul>{items}</ul>"
        f"<p><b>Actions ouvertes :</b> {len(open_actions)} "
        f"(dont <span style='color:#c00'>{n_overdue} en retard</span>)</p>"
    )
    _send(db, f"weekly:{today}", user_email, "📊 Rapport hebdomadaire HSE PYXIS",
          _wrap("Rapport hebdomadaire", body), dry_run, log)
    return log


# ============================================================
# POINT D'ENTRÉE
# ============================================================
def run_scheduler(db=None, now=None, dry_run=False, include_weekly=False):
    """Exécute tous les contrôles. Retourne la liste des actions effectuées (journal)."""
    db = db or InspectionDB()
    now = now or datetime.now()
    today = now.date()
    log = []

    check_inspections_in_7_days(db, today, dry_run, log)
    check_inspections_today(db, today, dry_run, log)
    if now.hour >= 12:  # rappel de la veille : en fin de journée
        check_inspections_tomorrow(db, today, dry_run, log)
    check_overdue_actions(db, today, dry_run, log)
    if include_weekly:
        weekly_report(db, today, dry_run, log)
    return log


if __name__ == "__main__":
    args = set(sys.argv[1:])
    results = run_scheduler(dry_run="--dry-run" in args, include_weekly="--weekly" in args)
    if not results:
        print("Aucun rappel à envoyer.")
    for r in results:
        extra = f" — {r['error']}" if r.get("error") else ""
        print(f"[{r['status']}] {r.get('to', '-')} | {r['subject']}{extra}")
