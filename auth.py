"""
auth.py — Authentification, rôles et journal d'audit (HSE PYXIS)
=================================================================

Trois rôles
-----------
  • admin       : tout (utilisateurs, journal d'audit, suppressions, configuration)
  • inspecteur  : crée et modifie (inspections, actions correctives, programme, matrice)
  • lecteur     : lecture seule (résultats, PDCA, rapport, programme)

Ce que fait ce module
---------------------
  1. Tables `users` et `audit_log` dans la base `inspection.db` (création automatique,
     aucune table existante n'est touchée).
  2. Mots de passe hachés (PBKDF2-HMAC-SHA256 + sel aléatoire) — aucune dépendance en plus.
  3. Verrouillage temporaire après 5 échecs de connexion, expiration de session,
     changement de mot de passe obligatoire pour les comptes créés / réinitialisés par l'admin.
  4. Journal d'audit en ajout seul (des triggers SQLite interdisent UPDATE et DELETE).
  5. `guard_db()` / `guard_matrice()` : enveloppes autour d'InspectionDB et MatriceManager qui
     (a) vérifient la permission côté serveur avant chaque écriture et
     (b) enregistrent automatiquement l'action dans le journal d'audit.
     Même si un bouton est oublié dans l'interface, un lecteur ne peut pas écrire.

v5 — Ajouts :
  • Étapes négatives STEP_DASHBOARD, STEP_COMPARISON, STEP_ACTIONS_CORR
    dans STEP_PERMISSIONS pour couvrir les pages v5 (Dashboard, Comparaison,
    Actions correctives).
  • __all__ explicite (documentation + IDE).

Variables d'environnement (facultatives, dans `.env`)
-----------------------------------------------------
  PYXIS_SETUP_KEY            clé exigée pour créer le TOUT PREMIER compte admin
                             (recommandé si l'application est accessible sur un réseau)
  PYXIS_SESSION_TIMEOUT_MIN  inactivité avant déconnexion automatique (défaut 120, 0 = jamais)
"""

from __future__ import annotations

import base64
import functools
import hashlib
import hmac
import inspect
import json
import logging
import math
import os
import re
import secrets
import sqlite3
import string
import time
from contextlib import closing
from datetime import datetime, timedelta

import streamlit as st

try:  # python-dotenv fait déjà partie des dépendances du projet
    from dotenv import load_dotenv
    from pathlib import Path as _Path
    load_dotenv(dotenv_path=_Path(__file__).parent / ".env")
except Exception:  # pragma: no cover - le .env est facultatif
    pass

log = logging.getLogger("hse_pyxis.auth")

# ============================================================
# CONSTANTES
# ============================================================
DB_PATH = "inspection.db"

ROLE_ADMIN = "admin"
ROLE_INSPECTEUR = "inspecteur"
ROLE_LECTEUR = "lecteur"
ROLES = (ROLE_ADMIN, ROLE_INSPECTEUR, ROLE_LECTEUR)

# permission -> rôles autorisés.  C'est LE seul endroit à modifier pour changer les droits.
PERMISSIONS: dict[str, tuple[str, ...]] = {
    "view":             ROLES,                                # consulter résultats / PDCA / rapport / programme
    "generate_report":  ROLES,                                # générer + télécharger un rapport / plan PDCA (n'écrit rien en base)
    "edit_inspection":  (ROLE_ADMIN, ROLE_INSPECTEUR),        # étapes 1-2 : saisie, Monte Carlo, vérification IA
    "edit_matrix":      (ROLE_ADMIN, ROLE_INSPECTEUR),        # étape 0 : créer / modifier une matrice
    "delete_matrix":    (ROLE_ADMIN,),
    "delete_inspection": (ROLE_ADMIN,),
    "edit_actions":     (ROLE_ADMIN, ROLE_INSPECTEUR),        # actions correctives : ajouter / clôturer
    "delete_actions":   (ROLE_ADMIN,),
    "edit_schedule":    (ROLE_ADMIN, ROLE_INSPECTEUR),        # programme d'inspection : créer / modifier
    "delete_schedule":  (ROLE_ADMIN,),
    "send_email":       (ROLE_ADMIN, ROLE_INSPECTEUR),
    "manage_templates": (ROLE_ADMIN, ROLE_INSPECTEUR),        # modèles de rapport de l'entreprise
    "manage_users":     (ROLE_ADMIN,),
    "view_audit":       (ROLE_ADMIN,),
}

# étape de la navigation -> permission nécessaire pour l'ouvrir
STEP_ADMIN = 7

# 🆕 v5 — Étapes négatives pour les pages additionnelles
STEP_DASHBOARD = -1
STEP_COMPARISON = -2
STEP_ACTIONS_CORR = -3

# Étape « Profil entreprise » (avant la configuration de la matrice)
STEP_COMPANY = 8

STEP_PERMISSIONS: dict[int, str] = {
    0: "edit_matrix",
    1: "edit_inspection",
    2: "edit_inspection",
    3: "view",
    4: "view",
    5: "view",
    6: "view",
    # 🆕 v5 — Nouvelles pages
    STEP_DASHBOARD:   "view",           # Tout utilisateur connecté peut voir le tableau de bord
    STEP_COMPARISON:  "view",           # Tout utilisateur connecté peut comparer des inspections
    STEP_ACTIONS_CORR: "view",          # La page est accessible à tous ; les écritures sont bloquées
                                        # par guard_db() pour les lecteurs (permission edit_actions)
    STEP_COMPANY:     "view",           # Profil entreprise + domaine d'activité : accessible à tout utilisateur connecté
    STEP_ADMIN: "manage_users",
}

MAX_FAILED_ATTEMPTS = 5
LOCK_MINUTES = 15
MIN_PASSWORD_LEN = 8
MAX_PASSWORD_LEN = 128
PBKDF2_ITERATIONS = 600_000
USERNAME_RE = re.compile(r"^[a-z0-9][a-z0-9._-]{2,31}$")

SESSION_USER_KEY = "auth_user"
SESSION_ACTIVITY_KEY = "auth_last_activity"
SESSION_NOTICE_KEY = "auth_notice"
try:
    SESSION_TIMEOUT_MIN = int(os.getenv("PYXIS_SESSION_TIMEOUT_MIN", "120"))
except ValueError:
    SESSION_TIMEOUT_MIN = 120

# Clés de session conservées à la déconnexion (langue, thème, écran d'accueil, widgets d'en-tête)
_KEEP_KEYS = {"language", "theme", "welcome_done", SESSION_NOTICE_KEY}
_KEEP_PREFIXES = ("header_", "welcome_", "layout_")


class AuthError(Exception):
    """Erreur métier. `key` est une clé de traduction (auth.err_*), `params` ses variables."""

    def __init__(self, key: str, **params):
        super().__init__(key)
        self.key = key
        self.params = params


# ============================================================
# MOTS DE PASSE
# ============================================================
def _b64(raw: bytes) -> str:
    return base64.b64encode(raw).decode("ascii")


def hash_password(password: str, iterations: int = PBKDF2_ITERATIONS) -> str:
    salt = secrets.token_bytes(16)
    dk = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, iterations)
    return f"pbkdf2_sha256${iterations}${_b64(salt)}${_b64(dk)}"


def verify_password(password: str, stored: str) -> bool:
    try:
        scheme, iters, salt_b64, hash_b64 = stored.split("$")
        if scheme != "pbkdf2_sha256":
            return False
        salt = base64.b64decode(salt_b64)
        expected = base64.b64decode(hash_b64)
        dk = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, int(iters))
        return hmac.compare_digest(dk, expected)
    except Exception:
        return False


def needs_rehash(stored: str) -> bool:
    try:
        return int(stored.split("$")[1]) < PBKDF2_ITERATIONS
    except Exception:
        return True


_dummy_hash: str | None = None


def _burn_time(password: str):
    """Vérifie contre un faux hash : même durée de réponse que pour un vrai compte."""
    global _dummy_hash
    if _dummy_hash is None:
        _dummy_hash = hash_password("pyxis-dummy-password")
    verify_password(password, _dummy_hash)


def check_password_policy(password: str, username: str = ""):
    if not isinstance(password, str) or len(password) < MIN_PASSWORD_LEN:
        raise AuthError("auth.err_password_weak", n=MIN_PASSWORD_LEN)
    if len(password) > MAX_PASSWORD_LEN:
        raise AuthError("auth.err_password_too_long", n=MAX_PASSWORD_LEN)
    if not (re.search(r"[A-Za-z]", password) and re.search(r"\d", password)):
        raise AuthError("auth.err_password_weak", n=MIN_PASSWORD_LEN)
    if username and password.lower() == username.lower():
        raise AuthError("auth.err_password_is_username")


def generate_temp_password(length: int = 12) -> str:
    """Mot de passe temporaire lisible (sans 0/O/1/l/I) respectant la politique."""
    letters = "".join(c for c in string.ascii_letters if c not in "lIO")
    digits = "".join(c for c in string.digits if c not in "01")
    alphabet = letters + digits
    while True:
        pw = "".join(secrets.choice(alphabet) for _ in range(length))
        if any(c in letters for c in pw) and any(c in digits for c in pw):
            return pw


def normalize_username(username: str) -> str:
    return (username or "").strip().lower()


# ============================================================
# BASE DE DONNÉES : utilisateurs + audit
# ============================================================
_USER_PUBLIC_COLS = ("id", "username", "full_name", "role", "active", "must_change_password",
                     "failed_attempts", "locked_until", "created_at", "last_login")


class AuthDB:
    """Accès SQLite aux tables `users` et `audit_log` (indépendant de Streamlit)."""

    def __init__(self, db_path: str = DB_PATH):
        self.db_path = db_path
        self._init_db()

    # ---------- infrastructure ----------
    def _connect(self):
        conn = sqlite3.connect(self.db_path, timeout=10)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self):
        with closing(self._connect()) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS users (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    username TEXT NOT NULL UNIQUE COLLATE NOCASE,
                    full_name TEXT,
                    password_hash TEXT NOT NULL,
                    role TEXT NOT NULL CHECK (role IN ('admin', 'inspecteur', 'lecteur')),
                    active INTEGER NOT NULL DEFAULT 1,
                    must_change_password INTEGER NOT NULL DEFAULT 0,
                    failed_attempts INTEGER NOT NULL DEFAULT 0,
                    locked_until TEXT,
                    created_at TEXT NOT NULL DEFAULT (datetime('now', 'localtime')),
                    last_login TEXT
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS audit_log (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    ts TEXT NOT NULL DEFAULT (datetime('now', 'localtime')),
                    username TEXT NOT NULL,
                    role TEXT,
                    action TEXT NOT NULL,
                    entity TEXT,
                    entity_id TEXT,
                    details TEXT
                )
            """)
            conn.execute("CREATE INDEX IF NOT EXISTS idx_audit_ts ON audit_log(ts)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_audit_user ON audit_log(username)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_audit_action ON audit_log(action)")
            # Journal en ajout seul : ni modification ni suppression, même par l'admin.
            conn.execute("""
                CREATE TRIGGER IF NOT EXISTS audit_log_no_update
                BEFORE UPDATE ON audit_log
                BEGIN SELECT RAISE(ABORT, 'audit_log est en ajout seul'); END
            """)
            conn.execute("""
                CREATE TRIGGER IF NOT EXISTS audit_log_no_delete
                BEFORE DELETE ON audit_log
                BEGIN SELECT RAISE(ABORT, 'audit_log est en ajout seul'); END
            """)
            conn.commit()

    @staticmethod
    def _now() -> datetime:
        return datetime.now()

    @staticmethod
    def _iso(dt: datetime) -> str:
        return dt.isoformat(sep=" ", timespec="seconds")

    @staticmethod
    def _public(row) -> dict | None:
        if row is None:
            return None
        d = {c: row[c] for c in _USER_PUBLIC_COLS}
        d["active"] = bool(d["active"])
        d["must_change_password"] = bool(d["must_change_password"])
        return d

    # ---------- lecture ----------
    def has_users(self) -> bool:
        with closing(self._connect()) as conn:
            return conn.execute("SELECT 1 FROM users LIMIT 1").fetchone() is not None

    def count_active_admins(self, conn=None) -> int:
        sql = "SELECT COUNT(*) FROM users WHERE role = 'admin' AND active = 1"
        if conn is not None:
            return conn.execute(sql).fetchone()[0]
        with closing(self._connect()) as c:
            return c.execute(sql).fetchone()[0]

    def get_user(self, user_id: int) -> dict | None:
        with closing(self._connect()) as conn:
            return self._public(conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone())

    def list_users(self) -> list[dict]:
        with closing(self._connect()) as conn:
            rows = conn.execute("SELECT * FROM users ORDER BY username COLLATE NOCASE").fetchall()
            return [self._public(r) for r in rows]

    def is_locked(self, user: dict) -> bool:
        lu = user.get("locked_until")
        if not lu:
            return False
        try:
            return datetime.fromisoformat(lu) > self._now()
        except ValueError:
            return False

    # ---------- création ----------
    def create_user(self, username: str, password: str, role: str, full_name: str = "",
                    must_change_password: bool = False, actor: str = "system",
                    actor_role: str | None = None, only_if_empty: bool = False) -> int:
        uname = normalize_username(username)
        if not USERNAME_RE.match(uname):
            raise AuthError("auth.err_username_invalid")
        if role not in ROLES:
            raise AuthError("auth.err_role_invalid")
        check_password_policy(password, uname)
        pw_hash = hash_password(password)

        with closing(self._connect()) as conn:
            conn.execute("BEGIN IMMEDIATE")
            try:
                if only_if_empty and conn.execute("SELECT 1 FROM users LIMIT 1").fetchone():
                    raise AuthError("auth.err_setup_done")
                cur = conn.execute(
                    "INSERT INTO users (username, full_name, password_hash, role, must_change_password) "
                    "VALUES (?, ?, ?, ?, ?)",
                    (uname, (full_name or "").strip()[:80], pw_hash, role, 1 if must_change_password else 0))
                new_id = cur.lastrowid
                conn.commit()
            except sqlite3.IntegrityError:
                conn.rollback()
                raise AuthError("auth.err_username_exists")
            except Exception:
                conn.rollback()
                raise
        self.log("setup_admin" if only_if_empty else "user_create", "user", uname,
                 f"rôle={role}", username=actor, role=actor_role)
        return new_id

    # ---------- connexion ----------
    def authenticate(self, username: str, password: str) -> dict:
        uname = normalize_username(username)
        password = password or ""
        if not uname or not password or len(password) > MAX_PASSWORD_LEN:
            _burn_time(password[:MAX_PASSWORD_LEN])
            raise AuthError("auth.err_invalid_credentials")

        with closing(self._connect()) as conn:
            row = conn.execute("SELECT * FROM users WHERE username = ?", (uname,)).fetchone()
            if row is None:
                _burn_time(password)
                self.log("login_failed", "user", uname[:64], "utilisateur inconnu", username=uname[:64])
                raise AuthError("auth.err_invalid_credentials")

            user = self._public(row)
            now = self._now()

            if self.is_locked(user):
                minutes = max(1, math.ceil((datetime.fromisoformat(user["locked_until"]) - now).total_seconds() / 60))
                self.log("login_blocked", "user", uname, "compte verrouillé", username=uname, role=user["role"])
                raise AuthError("auth.err_locked", minutes=minutes)

            if not verify_password(password, row["password_hash"]):
                attempts = user["failed_attempts"] + 1
                if attempts >= MAX_FAILED_ATTEMPTS:
                    until = self._iso(now + timedelta(minutes=LOCK_MINUTES))
                    conn.execute("UPDATE users SET failed_attempts = 0, locked_until = ? WHERE id = ?",
                                 (until, user["id"]))
                    conn.commit()
                    self.log("login_failed", "user", uname, f"échec {attempts}/{MAX_FAILED_ATTEMPTS} — compte verrouillé {LOCK_MINUTES} min",
                             username=uname, role=user["role"])
                    raise AuthError("auth.err_locked", minutes=LOCK_MINUTES)
                conn.execute("UPDATE users SET failed_attempts = ? WHERE id = ?", (attempts, user["id"]))
                conn.commit()
                self.log("login_failed", "user", uname, f"échec {attempts}/{MAX_FAILED_ATTEMPTS}",
                         username=uname, role=user["role"])
                raise AuthError("auth.err_invalid_credentials")

            # mot de passe correct
            if not user["active"]:
                self.log("login_failed", "user", uname, "compte désactivé", username=uname, role=user["role"])
                raise AuthError("auth.err_inactive")

            new_hash = hash_password(password) if needs_rehash(row["password_hash"]) else row["password_hash"]
            conn.execute(
                "UPDATE users SET failed_attempts = 0, locked_until = NULL, last_login = ?, password_hash = ? WHERE id = ?",
                (self._iso(now), new_hash, user["id"]))
            conn.commit()
            fresh = self._public(conn.execute("SELECT * FROM users WHERE id = ?", (user["id"],)).fetchone())

        self.log("login_ok", "user", uname, None, username=uname, role=fresh["role"])
        return fresh

    # ---------- mots de passe ----------
    def change_password(self, user_id: int, old_password: str, new_password: str):
        with closing(self._connect()) as conn:
            row = conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
            if row is None:
                raise AuthError("auth.err_not_found")
            if not verify_password(old_password or "", row["password_hash"]):
                raise AuthError("auth.err_wrong_old_password")
            if new_password == old_password:
                raise AuthError("auth.err_password_same")
            check_password_policy(new_password, row["username"])
            conn.execute("UPDATE users SET password_hash = ?, must_change_password = 0 WHERE id = ?",
                         (hash_password(new_password), user_id))
            conn.commit()
        self.log("password_changed", "user", row["username"], None, username=row["username"], role=row["role"])

    def admin_reset_password(self, user_id: int, new_password: str, actor: str, actor_role: str | None = None):
        with closing(self._connect()) as conn:
            row = conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
            if row is None:
                raise AuthError("auth.err_not_found")
            check_password_policy(new_password, row["username"])
            conn.execute(
                "UPDATE users SET password_hash = ?, must_change_password = 1, failed_attempts = 0, locked_until = NULL "
                "WHERE id = ?", (hash_password(new_password), user_id))
            conn.commit()
        self.log("password_reset", "user", row["username"], None, username=actor, role=actor_role)

    # ---------- gestion des comptes ----------
    def set_role(self, user_id: int, role: str, actor_id: int, actor: str, actor_role: str | None = None):
        if role not in ROLES:
            raise AuthError("auth.err_role_invalid")
        with closing(self._connect()) as conn:
            conn.execute("BEGIN IMMEDIATE")
            row = conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
            if row is None:
                conn.rollback()
                raise AuthError("auth.err_not_found")
            if row["role"] == role:
                conn.rollback()
                return
            if user_id == actor_id:
                conn.rollback()
                raise AuthError("auth.err_self_change")
            if row["role"] == ROLE_ADMIN and row["active"] and self.count_active_admins(conn) <= 1:
                conn.rollback()
                raise AuthError("auth.err_last_admin")
            conn.execute("UPDATE users SET role = ? WHERE id = ?", (role, user_id))
            conn.commit()
        self.log("user_role_change", "user", row["username"], f"{row['role']} → {role}",
                 username=actor, role=actor_role)

    def set_active(self, user_id: int, active: bool, actor_id: int, actor: str, actor_role: str | None = None):
        with closing(self._connect()) as conn:
            conn.execute("BEGIN IMMEDIATE")
            row = conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
            if row is None:
                conn.rollback()
                raise AuthError("auth.err_not_found")
            if bool(row["active"]) == bool(active):
                conn.rollback()
                return
            if not active:
                if user_id == actor_id:
                    conn.rollback()
                    raise AuthError("auth.err_self_change")
                if row["role"] == ROLE_ADMIN and self.count_active_admins(conn) <= 1:
                    conn.rollback()
                    raise AuthError("auth.err_last_admin")
            conn.execute("UPDATE users SET active = ? WHERE id = ?", (1 if active else 0, user_id))
            conn.commit()
        self.log("user_activate" if active else "user_deactivate", "user", row["username"], None,
                 username=actor, role=actor_role)

    def unlock_user(self, user_id: int, actor: str, actor_role: str | None = None):
        with closing(self._connect()) as conn:
            row = conn.execute("SELECT username FROM users WHERE id = ?", (user_id,)).fetchone()
            if row is None:
                raise AuthError("auth.err_not_found")
            conn.execute("UPDATE users SET failed_attempts = 0, locked_until = NULL WHERE id = ?", (user_id,))
            conn.commit()
        self.log("user_unlock", "user", row["username"], None, username=actor, role=actor_role)

    # ---------- audit ----------
    def log(self, action: str, entity: str | None = None, entity_id=None, details: str | None = None,
            username: str = "system", role: str | None = None):
        try:
            with closing(self._connect()) as conn:
                conn.execute(
                    "INSERT INTO audit_log (ts, username, role, action, entity, entity_id, details) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?)",
                    (self._iso(self._now()), username or "system", role, action, entity,
                     None if entity_id is None else str(entity_id)[:200],
                     None if details is None else str(details)[:500]))
                conn.commit()
        except Exception as exc:  # le journal ne doit jamais faire planter l'application
            log.warning("audit_log: écriture impossible (%s)", exc)

    @staticmethod
    def _audit_where(username=None, action=None, date_from=None, date_to=None, search=None):
        where, args = ["1=1"], []
        if username:
            where.append("username = ?"); args.append(username)
        if action:
            where.append("action = ?"); args.append(action)
        if date_from:
            where.append("ts >= ?"); args.append(f"{date_from} 00:00:00")
        if date_to:
            where.append("ts <= ?"); args.append(f"{date_to} 23:59:59")
        if search:
            like = f"%{search.strip()}%"
            where.append("(entity_id LIKE ? OR details LIKE ? OR entity LIKE ?)")
            args += [like, like, like]
        return " AND ".join(where), args

    def get_audit(self, limit: int = 100, offset: int = 0, **filters) -> list[dict]:
        where, args = self._audit_where(**filters)
        with closing(self._connect()) as conn:
            rows = conn.execute(
                f"SELECT id, ts, username, role, action, entity, entity_id, details FROM audit_log "
                f"WHERE {where} ORDER BY id DESC LIMIT ? OFFSET ?", args + [int(limit), int(offset)]).fetchall()
            return [dict(r) for r in rows]

    def count_audit(self, **filters) -> int:
        where, args = self._audit_where(**filters)
        with closing(self._connect()) as conn:
            return conn.execute(f"SELECT COUNT(*) FROM audit_log WHERE {where}", args).fetchone()[0]

    def audit_users(self) -> list[str]:
        with closing(self._connect()) as conn:
            return [r[0] for r in conn.execute("SELECT DISTINCT username FROM audit_log ORDER BY username")]

    def audit_actions(self) -> list[str]:
        with closing(self._connect()) as conn:
            return [r[0] for r in conn.execute("SELECT DISTINCT action FROM audit_log ORDER BY action")]


# ============================================================
# SESSION STREAMLIT
# ============================================================
@st.cache_resource(show_spinner=False)
def get_auth_db(db_path: str = DB_PATH) -> AuthDB:
    return AuthDB(db_path)


def current_user() -> dict | None:
    return st.session_state.get(SESSION_USER_KEY)


def current_username() -> str:
    u = current_user()
    return u["username"] if u else "system"


def current_role() -> str | None:
    u = current_user()
    return u["role"] if u else None


def has_permission(perm: str, user: dict | None = None) -> bool:
    u = user if user is not None else current_user()
    return bool(u) and u.get("role") in PERMISSIONS.get(perm, ())


def can_access_step(step: int) -> bool:
    perm = STEP_PERMISSIONS.get(step)
    return perm is not None and has_permission(perm)


def allowed_steps() -> list[int]:
    return [s for s in STEP_PERMISSIONS if can_access_step(s)]


def audit(action: str, entity: str | None = None, entity_id=None, details: str | None = None):
    """Écrit dans le journal au nom de l'utilisateur connecté. Ne lève jamais d'exception."""
    try:
        get_auth_db().log(action, entity, entity_id, details,
                          username=current_username(), role=current_role())
    except Exception as exc:  # pragma: no cover
        log.warning("audit: %s", exc)


def deny(perm: str, what: str = ""):
    """Refus d'accès : journalise, affiche une erreur et arrête le script."""
    from ui.i18n import t
    audit("access_denied", None, what or perm, f"permission requise : {perm}")
    st.error(f"🔒 {t('auth.access_denied')}")
    st.stop()


def require_permission(perm: str, what: str = ""):
    if not has_permission(perm):
        deny(perm, what)


def login_user(user: dict):
    ss = st.session_state
    ss[SESSION_USER_KEY] = {k: user[k] for k in ("id", "username", "full_name", "role", "must_change_password")}
    ss[SESSION_ACTIVITY_KEY] = time.time()


def logout(reason: str = "logout", notice: str | None = None):
    """Vide la session (sauf langue / thème / accueil). L'appelant gère le rerun."""
    if current_user():
        audit(reason, "user", current_username())
    ss = st.session_state
    for key in list(ss.keys()):
        if key in _KEEP_KEYS or (isinstance(key, str) and key.startswith(_KEEP_PREFIXES)):
            continue
        try:
            del ss[key]
        except Exception:
            pass
    if notice:
        ss[SESSION_NOTICE_KEY] = notice


def require_login() -> dict:
    """À appeler une fois en haut de l'application. Retourne l'utilisateur connecté,
    sinon affiche la page de connexion et arrête le script."""
    ss = st.session_state
    user = current_user()

    if user is not None:
        idle = time.time() - ss.get(SESSION_ACTIVITY_KEY, time.time())
        if SESSION_TIMEOUT_MIN > 0 and idle > SESSION_TIMEOUT_MIN * 60:
            logout("session_expired", notice="auth.session_expired")
            st.rerun()

        fresh = get_auth_db().get_user(user["id"])      # rôle / activation toujours à jour
        if fresh is None or not fresh["active"]:
            logout("session_revoked", notice="auth.session_revoked")
            st.rerun()

        user = {k: fresh[k] for k in ("id", "username", "full_name", "role", "must_change_password")}
        ss[SESSION_USER_KEY] = user
        ss[SESSION_ACTIVITY_KEY] = time.time()

        if user["must_change_password"]:
            from ui.pages.login import render_force_password_change
            render_force_password_change()
            st.stop()
        return user

    from ui.pages.login import render_login
    render_login()
    st.stop()


# ============================================================
# ENVELOPPES : permission + audit automatiques sur les écritures
# ============================================================
def _digest(obj) -> str:
    try:
        raw = json.dumps(obj, sort_keys=True, default=str, ensure_ascii=False)
    except Exception:
        raw = repr(obj)
    return hashlib.md5(raw.encode("utf-8")).hexdigest()


def _short(value, n=120) -> str:
    s = "" if value is None else str(value)
    return s if len(s) <= n else s[: n - 1] + "…"


class _Rule:
    """perm : permission exigée (None = pas de contrôle, ex. chargement automatique de la checklist)
    action / entity : libellés du journal
    entity_id(b, r) / details(b, r) : fonctions (arguments liés, résultat) -> str
    fingerprint(b, r) : si défini, l'action n'est journalisée que lorsque l'empreinte change
                        (évite 118 lignes identiques à chaque rerun Streamlit)
    skip(b) : True -> on ne journalise pas (ex. clés de rappels automatiques)"""

    def __init__(self, perm, action, entity, entity_id=None, details=None, fingerprint=None, skip=None):
        self.perm, self.action, self.entity = perm, action, entity
        self.entity_id, self.details = entity_id, details
        self.fingerprint, self.skip = fingerprint, skip


def _arg(name):
    return lambda b, r: b.get(name)


def _item_details(b, r):
    return f"item={b.get('item_id')}"


DB_RULES: dict[str, _Rule] = {
    "save_checklist_items": _Rule(None, "checklist_import", "checklist",
                                  details=lambda b, r: f"{len(b.get('items') or [])} éléments"),
    "save_conformity_only": _Rule("edit_inspection", "inspection_conformity", "inspection", _arg("inspection_id"),
                                  lambda b, r: f"item={b.get('item_id')} → {b.get('conformite')}",
                                  fingerprint=lambda b, r: (b.get("item_id"), b.get("conformite"))),
    "save_inspection_data": _Rule("edit_inspection", "inspection_data", "inspection", _arg("inspection_id"),
                                  lambda b, r: f"item={b.get('item_id')}; site={b.get('site_name')}",
                                  fingerprint=lambda b, r: (b.get("item_id"), _digest(b.get("data")))),
    "save_mc_result": _Rule("edit_inspection", "inspection_compute", "inspection", _arg("inspection_id"),
                            lambda b, r: f"Monte Carlo; item={b.get('item_id')}",
                            fingerprint=lambda b, r: ("mc", b.get("item_id"), _digest(b.get("r")))),
    "save_human_risk": _Rule("edit_inspection", "inspection_compute", "inspection", _arg("inspection_id"),
                             lambda b, r: f"Risque humain; item={b.get('item_id')}",
                             fingerprint=lambda b, r: ("hr", b.get("item_id"), _digest(b.get("r")))),
    "save_cost_benefit": _Rule("edit_inspection", "inspection_compute", "inspection", _arg("inspection_id"),
                               lambda b, r: f"Coût-bénéfice; item={b.get('item_id')}",
                               fingerprint=lambda b, r: ("cb", b.get("item_id"), _digest(b.get("r")))),
    "save_dispersion": _Rule("edit_inspection", "inspection_compute", "inspection", _arg("inspection_id"),
                             lambda b, r: f"Dispersion; item={b.get('item_id')}",
                             fingerprint=lambda b, r: ("disp", b.get("item_id"), _digest(b.get("r")))),
    "save_ai_verification": _Rule("edit_inspection", "inspection_ai", "inspection", _arg("inspection_id"),
                                  _item_details,
                                  fingerprint=lambda b, r: (b.get("item_id"), _digest(b.get("result")))),
    "save_inspection_date": _Rule("edit_inspection", "inspection_date", "inspection", _arg("inspection_id"),
                                  lambda b, r: f"date={b.get('iso_date')}"),
    "delete_inspection": _Rule("delete_inspection", "inspection_delete", "inspection", _arg("inspection_id"),
                               lambda b, r: "inspection et toutes ses données supprimées"),
    "add_corrective_action": _Rule(
        "edit_actions", "action_add", "corrective_action", lambda b, r: r,
        lambda b, r: (f"inspection={b.get('inspection_id')}; item={b.get('item_id') or '—'}; "
                      f"priorité={b.get('priority')}; échéance={b.get('deadline')}; "
                      f"responsable={b.get('responsible') or '—'}; action={_short(b.get('action'))}")),
    "complete_corrective_action": _Rule("edit_actions", "action_complete", "corrective_action", _arg("action_id")),
    "delete_corrective_action": _Rule("delete_actions", "action_delete", "corrective_action", _arg("action_id")),
    "add_scheduled_inspection": _Rule(
        "edit_schedule", "schedule_add", "schedule", lambda b, r: r,
        lambda b, r: (f"inspection={b.get('inspection_id')}; site={b.get('site_name')}; "
                      f"date={b.get('scheduled_date')} {b.get('scheduled_time') or ''}".strip())),
    "update_scheduled_inspection": _Rule(
        "edit_schedule", "schedule_update", "schedule", _arg("sched_id"),
        lambda b, r: _short("; ".join(f"{k}={v}" for k, v in (b.get("fields") or {}).items()), 300)),
    "update_scheduled_inspection_status": _Rule("edit_schedule", "schedule_status", "schedule", _arg("sched_id"),
                                                lambda b, r: f"status={b.get('status')}"),
    "delete_scheduled_inspection": _Rule("delete_schedule", "schedule_delete", "schedule", _arg("sched_id")),
    "save_setting": _Rule("edit_schedule", "setting_save", "setting", _arg("key"),
                          skip=lambda b: str(b.get("key", "")).startswith("reminder:")),
}

_MATRIX_SAVE = dict(entity="matrix", entity_id=_arg("site_name"))
MATRICE_RULES: dict[str, _Rule] = {
    "save_matrix": _Rule("edit_matrix", "matrix_save", details=lambda b, r: "sévérité", **_MATRIX_SAVE),
    "save_probability": _Rule("edit_matrix", "matrix_save", details=lambda b, r: "probabilité", **_MATRIX_SAVE),
    "save_thresholds": _Rule("edit_matrix", "matrix_save", details=lambda b, r: "seuils", **_MATRIX_SAVE),
    "save_full_matrix": _Rule("edit_matrix", "matrix_save", details=lambda b, r: "matrice complète", **_MATRIX_SAVE),
    "delete_matrix": _Rule("delete_matrix", "matrix_delete", **_MATRIX_SAVE),
}


def _seen_store() -> dict:
    store = st.session_state.get("_audit_seen")
    if store is None:
        store = {}
        st.session_state["_audit_seen"] = store
    if len(store) > 5000:
        store.clear()
    return store


class _Guarded:
    """Proxy transparent : toutes les méthodes passent, celles listées dans `rules`
    sont contrôlées (permission) puis journalisées."""

    def __init__(self, target, rules: dict[str, _Rule]):
        object.__setattr__(self, "_target", target)
        object.__setattr__(self, "_rules", rules)

    def __getattr__(self, name):
        attr = getattr(self._target, name)
        rule = self._rules.get(name)
        if rule is None or not callable(attr):
            return attr
        try:
            sig = inspect.signature(attr)
        except (TypeError, ValueError):
            sig = None

        @functools.wraps(attr)
        def wrapper(*args, **kwargs):
            if rule.perm:
                require_permission(rule.perm, name)
            result = attr(*args, **kwargs)
            try:
                if sig is not None:
                    bound = sig.bind_partial(*args, **kwargs)
                    bound.apply_defaults()
                    b = dict(bound.arguments)
                else:
                    b = dict(kwargs)
                if rule.skip and rule.skip(b):
                    return result
                if rule.fingerprint:
                    key = (rule.action, str(rule.entity_id(b, result)) if rule.entity_id else "", rule.fingerprint(b, result))
                    seen = _seen_store()
                    if key in seen:
                        return result
                    seen[key] = True
                audit(rule.action, rule.entity,
                      rule.entity_id(b, result) if rule.entity_id else None,
                      rule.details(b, result) if rule.details else None)
            except Exception as exc:  # l'audit ne doit jamais casser l'action déjà effectuée
                log.warning("audit wrapper %s: %s", name, exc)
            return result

        return wrapper

    def __setattr__(self, name, value):
        setattr(self._target, name, value)


def guard_db(db):
    """Enveloppe InspectionDB : permissions + audit sur les écritures."""
    return _Guarded(db, DB_RULES)


def guard_matrice(manager):
    """Enveloppe MatriceManager : permissions + audit sur les écritures."""
    return _Guarded(manager, MATRICE_RULES)


# ============================================================
# EXPORTS
# ============================================================
__all__ = [
    # constantes
    "ROLE_ADMIN", "ROLE_INSPECTEUR", "ROLE_LECTEUR", "ROLES",
    "PERMISSIONS", "STEP_ADMIN", "STEP_PERMISSIONS", "STEP_COMPANY",
    "STEP_DASHBOARD", "STEP_COMPARISON", "STEP_ACTIONS_CORR",  # 🆕 v5
    # AuthDB
    "AuthDB", "AuthError",
    # helpers mots de passe
    "hash_password", "verify_password", "needs_rehash",
    "check_password_policy", "generate_temp_password", "normalize_username",
    # session
    "get_auth_db", "current_user", "current_username", "current_role",
    "has_permission", "can_access_step", "allowed_steps",
    "audit", "deny", "require_permission", "require_login",
    "login_user", "logout",
    # guards
    "guard_db", "guard_matrice",
]