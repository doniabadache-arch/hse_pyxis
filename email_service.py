"""
email_service.py — HSE PYXIS
==============================
Service d'envoi d'emails avec 2 modes :

  1. SMTP classique (Gmail, Outlook, Brevo SMTP, ...)
     → Configuré via SMTP_SERVER, SMTP_PORT, SMTP_LOGIN, SMTP_KEY

  2. Brevo HTTP API (recommandé si SMTP est bloqué)
     → Configuré via BREVO_API_KEY
     → Utilise HTTPS (port 443) → passe tous les firewalls

Configuration dans .env :

    # ── Mode 1 : SMTP classique ──
    SMTP_SERVER=smtp-relay.brevo.com
    SMTP_PORT=587
    SMTP_LOGIN=your_email@gmail.com
    SMTP_KEY=xkeysib-xxxx
    SMTP_FROM=HSE PYXIS <your_email@gmail.com>

    # ── Mode 2 : Brevo HTTP API (à préférer si SMTP bloqué) ──
    BREVO_API_KEY=xkeysib-xxxx           # même clé que SMTP
    BREVO_SENDER_EMAIL=your_email@gmail.com
    BREVO_SENDER_NAME=HSE PYXIS

    # ── Fallback SMTP (optionnel) ──
    SMTP_FALLBACK_1_SERVER=smtp.gmail.com
    SMTP_FALLBACK_1_PORT=465
    SMTP_FALLBACK_1_LOGIN=...
    SMTP_FALLBACK_1_KEY=...
    SMTP_FALLBACK_1_FROM=...

Usage :
    from email_service import send_email, send_report, test_connection
"""

import os
import re
import smtplib
import ssl
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.application import MIMEApplication
from pathlib import Path
from typing import Optional

import requests
from dotenv import load_dotenv

# ---- Charger .env ----
_ENV_PATH = Path(__file__).parent / ".env"
load_dotenv(dotenv_path=_ENV_PATH)


# ============================================================
# CONFIGURATION BREVO API
# ============================================================
BREVO_API_KEY = os.getenv("BREVO_API_KEY", "").strip()
BREVO_SENDER_EMAIL = os.getenv("BREVO_SENDER_EMAIL", "").strip()
BREVO_SENDER_NAME = os.getenv("BREVO_SENDER_NAME", "HSE PYXIS").strip()
BREVO_API_URL = "https://api.brevo.com/v3/smtp/email"


# ============================================================
# DÉCOUVERTE DES FOURNISSEURS SMTP
# ============================================================
def _read_provider(prefix: str = "SMTP") -> Optional[dict]:
    """Lit un fournisseur SMTP depuis les variables d'environnement."""
    server = os.getenv(f"{prefix}_SERVER", "").strip()
    login = os.getenv(f"{prefix}_LOGIN", "").strip()
    key = os.getenv(f"{prefix}_KEY", "").strip()
    if not (server and login and key):
        return None

    try:
        port = int(os.getenv(f"{prefix}_PORT", "587"))
    except ValueError:
        port = 587

    from_addr = os.getenv(f"{prefix}_FROM", login).strip() or login
    label = _label_for(server)

    return {
        "label": label,
        "server": server,
        "port": port,
        "login": login,
        "key": key,
        "from": from_addr,
        "is_fallback": prefix != "SMTP",
    }


def _label_for(server: str) -> str:
    s = server.lower()
    if "brevo" in s: return "Brevo"
    if "gmail" in s: return "Gmail"
    if "outlook" in s or "office365" in s: return "Outlook"
    if "yahoo" in s: return "Yahoo"
    if "sendgrid" in s: return "SendGrid"
    if "mailjet" in s: return "Mailjet"
    return server


def _get_providers() -> list:
    providers = []
    p = _read_provider("SMTP")
    if p:
        providers.append(p)
    for i in range(1, 6):
        f = _read_provider(f"SMTP_FALLBACK_{i}")
        if f:
            providers.append(f)
    return providers


# ============================================================
# CONFIGURATION / STATUT
# ============================================================
def is_configured() -> bool:
    """Vrai si au moins un mode d'envoi est configuré."""
    return bool(BREVO_API_KEY) or len(_get_providers()) > 0


def get_status() -> dict:
    """État de la configuration (sans exposer les clés)."""
    providers = _get_providers()
    return {
        "configured": is_configured(),
        "api_configured": bool(BREVO_API_KEY and BREVO_SENDER_EMAIL),
        "api_sender": BREVO_SENDER_EMAIL or "—",
        "smtp_providers": [
            {
                "label": p["label"],
                "server": p["server"],
                "port": p["port"],
                "login": p["login"],
                "from": p["from"],
                "is_fallback": p["is_fallback"],
                "mode": "SSL" if p["port"] == 465 else "STARTTLS",
            }
            for p in providers
        ],
        "env_path": str(_ENV_PATH),
        "env_exists": _ENV_PATH.exists(),
    }


# ============================================================
# BREVO HTTP API (443) — Mode recommandé
# ============================================================
def _send_via_brevo_api(
    to: str,
    subject: str,
    html_body: str,
    text_body: Optional[str] = None,
    attachments: Optional[list] = None,
    cc: Optional[list] = None,
) -> dict:
    """Envoie un email via l'API HTTP de Brevo (HTTPS 443)."""
    result = {"ok": False, "error": None, "provider": "Brevo API"}

    if not BREVO_API_KEY:
        result["error"] = "BREVO_API_KEY manquante dans .env"
        return result
    if not BREVO_SENDER_EMAIL:
        result["error"] = "BREVO_SENDER_EMAIL manquante dans .env"
        return result

    # Destinataires
    to_list = [{"email": e.strip()} for e in to.split(",") if "@" in e]
    if not to_list:
        result["error"] = "Adresse destinataire invalide"
        return result

    payload = {
        "sender": {
            "name": BREVO_SENDER_NAME,
            "email": BREVO_SENDER_EMAIL,
        },
        "to": to_list,
        "subject": subject,
        "htmlContent": html_body,
    }
    if text_body:
        payload["textContent"] = text_body
    if cc:
        payload["cc"] = [{"email": e.strip()} for e in cc if "@" in e]

    # Pièces jointes (encodées en base64)
    if attachments:
        import base64
        att_list = []
        for fp in attachments:
            path = Path(fp)
            if not path.exists():
                continue
            with open(path, "rb") as f:
                content = base64.b64encode(f.read()).decode("ascii")
            att_list.append({"name": path.name, "content": content})
        if att_list:
            payload["attachment"] = att_list

    try:
        r = requests.post(
            BREVO_API_URL,
            headers={
                "accept": "application/json",
                "api-key": BREVO_API_KEY,
                "content-type": "application/json",
            },
            json=payload,
            timeout=15,
        )
        if r.status_code in (200, 201, 202):
            result["ok"] = True
            return result

        # Erreur HTTP
        try:
            err = r.json()
            msg = err.get("message", r.text[:200])
        except Exception:
            msg = r.text[:200]
        result["error"] = f"HTTP {r.status_code} : {msg}"
        return result
    except requests.Timeout:
        result["error"] = "Timeout HTTP (api.brevo.com)"
        return result
    except Exception as e:
        result["error"] = f"{type(e).__name__} : {e}"
        return result


# ============================================================
# SMTP CLASSIQUE (avec support 465 SSL / 587 STARTTLS)
# ============================================================
def _open_smtp(provider: dict, timeout: int):
    ctx = ssl.create_default_context()
    port = provider["port"]

    if port == 465:
        s = smtplib.SMTP_SSL(provider["server"], port,
                              timeout=timeout, context=ctx)
        s.ehlo()
        s.login(provider["login"], provider["key"])
        return s

    s = smtplib.SMTP(provider["server"], port, timeout=timeout)
    s.ehlo()
    s.starttls(context=ctx)
    s.ehlo()
    s.login(provider["login"], provider["key"])
    return s


def _test_one(provider: dict) -> dict:
    try:
        s = _open_smtp(provider, timeout=10)
        s.quit()
        return {"ok": True, "error": None}
    except smtplib.SMTPAuthenticationError as e:
        return {"ok": False, "error": f"Auth échouée : {e}"}
    except smtplib.SMTPException as e:
        return {"ok": False, "error": f"Erreur SMTP : {e}"}
    except Exception as e:
        return {"ok": False, "error": f"{type(e).__name__} : {e}"}


def test_connection() -> dict:
    """Teste Brevo API puis tous les SMTP."""
    results = []
    active = None

    # 1. Brevo API
    if BREVO_API_KEY and BREVO_SENDER_EMAIL:
        results.append({"label": "Brevo API", "ok": True, "error": None})
        active = "Brevo API"

    # 2. SMTP
    providers = _get_providers()
    for p in providers:
        r = _test_one(p)
        results.append({"label": p["label"], **r})
        if r["ok"] and active is None:
            active = p["label"]

    return {
        "ok": active is not None,
        "results": results,
        "active": active,
        "error": None if active else (results[-1]["error"] if results else "Aucun"),
    }


# ============================================================
# ENVOI D'EMAIL (API d'abord, puis SMTP)
# ============================================================
def send_email(
    to: str,
    subject: str,
    html_body: str,
    text_body: Optional[str] = None,
    attachments: Optional[list] = None,
    cc: Optional[list] = None,
) -> dict:
    """
    Envoie un email. Essaie Brevo API d'abord, puis SMTP.

    Returns:
        dict avec ok, error, provider, attempts, to, subject
    """
    result = {
        "ok": False, "error": None, "provider": None,
        "attempts": [], "to": to, "subject": subject,
    }

    if not to or "@" not in to:
        result["error"] = "Adresse destinataire invalide"
        return result

    # ─── 1. Brevo HTTP API (si configurée) ───
    if BREVO_API_KEY and BREVO_SENDER_EMAIL:
        r = _send_via_brevo_api(to, subject, html_body, text_body, attachments, cc)
        result["attempts"].append({"label": "Brevo API", "ok": r["ok"], "error": r["error"]})
        if r["ok"]:
            result["ok"] = True
            result["provider"] = "Brevo API"
            return result

    # ─── 2. SMTP classique ───
    providers = _get_providers()
    if providers:
        msg = _build_message(to, subject, html_body, text_body, attachments, cc)
        for p in providers:
            r = _try_send(p, to, cc, msg)
            result["attempts"].append({"label": p["label"], **r})
            if r["ok"]:
                result["ok"] = True
                result["provider"] = p["label"]
                return result

    # Aucun mode n'a réussi
    if not result["attempts"]:
        result["error"] = "Aucun mode d'envoi configuré dans .env"
    else:
        result["error"] = result["attempts"][-1]["error"] or "Échec"

    return result


def _build_message(to, subject, html_body, text_body, attachments, cc):
    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["To"] = to
    if cc:
        msg["Cc"] = ", ".join(cc)

    if not text_body:
        text_body = re.sub(r"<[^>]+>", "", html_body)
    msg.attach(MIMEText(text_body, "plain", "utf-8"))
    msg.attach(MIMEText(html_body, "html", "utf-8"))

    if attachments:
        for fp in attachments:
            path = Path(fp)
            if not path.exists():
                continue
            with open(path, "rb") as f:
                part = MIMEApplication(f.read(), Name=path.name)
            part["Content-Disposition"] = f'attachment; filename="{path.name}"'
            msg.attach(part)

    return msg


def _try_send(provider: dict, to: str, cc, msg) -> dict:
    msg["From"] = provider["from"]
    recipients = [to] + (cc or [])

    try:
        s = _open_smtp(provider, timeout=15)
        try:
            s.sendmail(provider["from"], recipients, msg.as_string())
        finally:
            try:
                s.quit()
            except Exception:
                pass
        return {"ok": True, "error": None}
    except smtplib.SMTPAuthenticationError as e:
        return {"ok": False, "error": f"Auth échouée : {e}"}
    except smtplib.SMTPRecipientsRefused as e:
        return {"ok": False, "error": f"Destinataire refusé : {e}"}
    except smtplib.SMTPException as e:
        return {"ok": False, "error": f"Erreur SMTP : {e}"}
    except Exception as e:
        return {"ok": False, "error": f"{type(e).__name__} : {e}"}


# ============================================================
# RAPPORT D'INSPECTION
# ============================================================
def send_report(
    to: str,
    site_name: str,
    inspection_id: str,
    html_report: str,
    summary: Optional[dict] = None,
    attachments: Optional[list] = None,
    cc: Optional[list] = None,
) -> dict:
    subject = f"📊 Rapport d'inspection {inspection_id} — {site_name}"

    summary_html = ""
    if summary:
        summary_html = f"""
        <div style="background:#f0f4f8;padding:15px;border-radius:8px;margin:15px 0;">
            <h3 style="margin:0 0 10px 0;color:#1e3a5f;">📋 Résumé</h3>
            <table style="border-collapse:collapse;width:100%;">
                <tr>
                    <td style="padding:5px;"><b>Total:</b> {summary.get('total', '—')}</td>
                    <td style="padding:5px;color:#c0392b;"><b>NC:</b> {summary.get('nc', '—')}</td>
                    <td style="padding:5px;color:#e67e22;"><b>PC:</b> {summary.get('pc', '—')}</td>
                    <td style="padding:5px;color:#27ae60;"><b>C:</b> {summary.get('c', '—')}</td>
                </tr>
            </table>
        </div>
        """

    full_html = f"""
    <!DOCTYPE html><html><head><meta charset="UTF-8">
    <style>
        body {{ font-family: Arial, sans-serif; color: #333; line-height: 1.6; }}
        h1 {{ color: #1e3a5f; }}
        .header {{ background: linear-gradient(135deg, #1e3a5f, #00C853);
                   color: white; padding: 20px; border-radius: 8px; }}
        .footer {{ font-size: 12px; color: #888; margin-top: 30px;
                   border-top: 1px solid #ddd; padding-top: 10px; }}
    </style></head><body>
        <div class="header">
            <h1>🛡️ HSE PYXIS — Rapport d'Inspection</h1>
            <p><b>Site:</b> {site_name} · <b>Référence:</b> {inspection_id}</p>
        </div>
        {summary_html}
        <div>{html_report}</div>
        <div class="footer">
            <p>📧 Email envoyé automatiquement par HSE PYXIS</p>
            <p>© 2026 HSE PYXIS — SMARTER SAFETY</p>
        </div>
    </body></html>
    """
    return send_email(to=to, subject=subject, html_body=full_html,
                      attachments=attachments, cc=cc)


# ============================================================
# RAPPELS (pour scheduler.py)
# ============================================================
def send_reminder(to: str, reminder_type: str, data: dict) -> dict:
    subjects = {
        "inspection_d1": "📅 Rappel : Inspection demain",
        "inspection_d0": "⏰ Rappel : Inspection aujourd'hui",
        "action_overdue": "⚠️ Action corrective en retard",
        "weekly_report": "📊 Rapport HSE hebdomadaire",
    }
    subject = subjects.get(reminder_type, "📧 Rappel HSE PYXIS")
    html = _build_reminder_html(reminder_type, data)
    return send_email(to=to, subject=subject, html_body=html)


def _build_reminder_html(reminder_type: str, data: dict) -> str:
    if reminder_type in ("inspection_d1", "inspection_d0"):
        when = "demain" if reminder_type == "inspection_d1" else "AUJOURD'HUI"
        color = "#e67e22" if reminder_type == "inspection_d1" else "#c0392b"
        return f"""<html><body style="font-family:Arial;">
        <div style="background:{color};color:white;padding:20px;border-radius:8px;">
            <h1>📅 Inspection {when}</h1>
        </div>
        <div style="padding:20px;">
            <p><b>📋 Référence :</b> {data.get('inspection_id', '—')}</p>
            <p><b>📍 Site :</b> {data.get('site_name', '—')}</p>
            <p><b>📅 Date :</b> {data.get('date', '—')} à {data.get('time', '—')}</p>
            <p><b>👤 Inspecteur :</b> {data.get('inspector', '—')}</p>
            <p><b>📝 Notes :</b> {data.get('notes', '—')}</p>
        </div></body></html>"""

    if reminder_type == "action_overdue":
        return f"""<html><body style="font-family:Arial;">
        <div style="background:#c0392b;color:white;padding:20px;border-radius:8px;">
            <h1>⚠️ Action corrective en retard</h1>
        </div>
        <div style="padding:20px;">
            <p><b>📝 Action :</b> {data.get('action', '—')}</p>
            <p><b>📋 Référence :</b> {data.get('item_id', '—')}</p>
            <p><b>📅 Échéance :</b> {data.get('deadline', '—')}</p>
            <p><b>⏱️ Retard :</b> <span style="color:#c0392b;"><b>{data.get('days_late', 0)} jours</b></span></p>
            <p><b>👤 Responsable :</b> {data.get('responsible', '—')}</p>
            <p><b>🔴 Priorité :</b> {data.get('priority', '—')}</p>
        </div></body></html>"""

    if reminder_type == "weekly_report":
        return f"""<html><body style="font-family:Arial;">
        <div style="background:linear-gradient(135deg,#1e3a5f,#00C853);color:white;padding:20px;border-radius:8px;">
            <h1>📊 Rapport HSE hebdomadaire</h1>
        </div>
        <div style="padding:20px;">
            <p><b>📅 Période :</b> {data.get('period', '—')}</p>
            <p><b>🔍 Inspections réalisées :</b> {data.get('inspections_count', 0)}</p>
            <p><b>⚠️ NC nouvelles :</b> {data.get('new_nc', 0)}</p>
            <p><b>✅ NC clôturées :</b> {data.get('closed_nc', 0)}</p>
            <p><b>⏰ Actions en retard :</b> {data.get('overdue_actions', 0)}</p>
            <p><b>📈 Risque moyen :</b> {data.get('avg_risk', '—')}/25</p>
        </div></body></html>"""

    return f"<p>Rappel HSE PYXIS : {data}</p>"


# ============================================================
# TEST RAPIDE
# ============================================================
if __name__ == "__main__":
    print("=" * 70)
    print("🧪 Test du service email HSE PYXIS")
    print("=" * 70)

    status = get_status()
    print(f"\n📧 Configuration :")
    print(f"   Brevo API  : {'✅ configurée' if status['api_configured'] else '❌ non configurée'}")
    if status["api_configured"]:
        print(f"   API sender : {status['api_sender']}")
    print(f"   SMTP       : {len(status['smtp_providers'])} fournisseur(s)")
    for i, p in enumerate(status["smtp_providers"], 1):
        role = "fallback" if p["is_fallback"] else "principal"
        print(f"      {i}. [{role}] {p['label']} — {p['server']}:{p['port']} ({p['mode']})")

    if not status["configured"]:
        print("\n⚠️  Aucun mode d'envoi configuré dans .env")
        exit(1)

    print("\n📤 Test d'envoi d'email...")
    to = input("📧 Adresse destinataire : ").strip()
    if not to:
        print("⏭️  Ignoré")
        exit(0)

    result = send_email(
        to=to,
        subject="🎉 HSE PYXIS — Test",
        html_body="""
        <html><body style="font-family:Arial;">
        <h1 style="color:#00C853;">🎉 Test réussi !</h1>
        <p>Votre configuration email fonctionne.</p>
        <p><b>Provider utilisé :</b> (voir console)</p>
        </body></html>
        """,
    )

    print(f"\n📊 Résultat :")
    print(f"   Envoyé : {'✅ Oui' if result['ok'] else '❌ Non'}")
    print(f"   Provider : {result['provider'] or '—'}")
    print(f"\n📋 Tentatives :")
    for att in result["attempts"]:
        icon = "✅" if att["ok"] else "❌"
        print(f"   {icon} {att['label']}: {att['error'] or 'OK'}")

    if result["error"]:
        print(f"\n❌ Erreur finale : {result['error']}")