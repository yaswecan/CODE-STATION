#!/usr/bin/env python3
"""PédagoLab × CODE//STATION — API compatible Vercel.

Production (Vercel): FastAPI + PostgreSQL (Neon/Supabase/etc.) via DATABASE_URL.
Local: FastAPI + SQLite si DATABASE_URL n'est pas défini.

Le contrat HTTP reste compatible avec src/accounts.js V6.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import secrets
import sqlite3
import threading
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Dict, Iterable, Optional

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, FileResponse

ROOT = Path(__file__).resolve().parent
IS_VERCEL = bool(os.environ.get("VERCEL"))

# Vercel Functions ne doivent pas dépendre d'un stockage persistant local.
# Le fallback SQLite sert uniquement au développement local. Sur Vercel,
# PostgreSQL/Neon via DATABASE_URL est obligatoire.
if IS_VERCEL:
    LOCAL_DB = Path("/tmp/pedagolab.sqlite3")
else:
    DATA = ROOT / "data"
    DATA.mkdir(parents=True, exist_ok=True)
    LOCAL_DB = DATA / "pedagolab.sqlite3"

DATABASE_URL = os.environ.get("DATABASE_URL", "").strip()
SESSION_SECRET = os.environ.get("SESSION_SECRET", "").strip()

def env_int(name: str, default: int, *, minimum: int | None = None, maximum: int | None = None) -> int:
    """Lit un entier d'environnement sans jamais faire planter l'import.

    Vercel peut contenir une variable vide ou mal remplie (par exemple
    MAX_PROGRESS_BYTES=MAX_PROGRESS_BYTES). Dans ce cas on reprend le défaut.
    """
    raw = os.environ.get(name)
    if raw is None or not str(raw).strip():
        value = default
    else:
        try:
            value = int(str(raw).strip())
        except (TypeError, ValueError):
            value = default
    if minimum is not None:
        value = max(minimum, value)
    if maximum is not None:
        value = min(maximum, value)
    return value

SESSION_TTL_SECONDS = env_int("SESSION_TTL_SECONDS", 43200, minimum=300, maximum=604800)
ITERATIONS = env_int("PIN_PBKDF2_ITERATIONS", 260000, minimum=100000, maximum=2000000)
MAX_PROGRESS_BYTES = env_int("MAX_PROGRESS_BYTES", 2_000_000, minimum=100000, maximum=20_000_000)

# Secret de développement uniquement. En production Vercel, SESSION_SECRET
# doit être explicitement défini et les routes API renverront 503 sinon.
if not SESSION_SECRET and not IS_VERCEL:
    SESSION_SECRET = "code-station-local-dev-secret-change-me"

app = FastAPI(title="PédagoLab × CODE//STATION API", version="6.3-vercel-root-fix")
_schema_lock = threading.Lock()
_schema_ready = False


def now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def json_dumps(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def json_loads(value: Any, default: Any) -> Any:
    if value is None:
        return default
    if isinstance(value, (dict, list)):
        return value
    try:
        return json.loads(value)
    except Exception:
        return default


def hash_pin(pin: str, salt: Optional[str] = None) -> Dict[str, Any]:
    salt = salt or secrets.token_hex(16)
    dk = hashlib.pbkdf2_hmac(
        "sha256", str(pin).encode("utf-8"), bytes.fromhex(salt), ITERATIONS
    )
    return {"salt": salt, "hash": dk.hex(), "iterations": ITERATIONS}


def check_pin(pin: str, salt: str, expected_hash: str, iterations: int) -> bool:
    try:
        dk = hashlib.pbkdf2_hmac(
            "sha256",
            str(pin).encode("utf-8"),
            bytes.fromhex(salt),
            int(iterations or ITERATIONS),
        ).hex()
        return hmac.compare_digest(dk, expected_hash)
    except Exception:
        return False


def _b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def _unb64(data: str) -> bytes:
    return base64.urlsafe_b64decode(data + "=" * (-len(data) % 4))


def issue_token(role: str, user_id: str) -> str:
    if not SESSION_SECRET:
        raise RuntimeError("SESSION_SECRET manquant.")
    payload = {
        "role": role,
        "userId": user_id,
        "iat": int(time.time()),
        "exp": int(time.time()) + SESSION_TTL_SECONDS,
        "nonce": secrets.token_hex(8),
    }
    body = _b64(json_dumps(payload).encode("utf-8"))
    sig = _b64(hmac.new(SESSION_SECRET.encode("utf-8"), body.encode("ascii"), hashlib.sha256).digest())
    return f"{body}.{sig}"


def verify_token(token: str, role: Optional[str] = None) -> Optional[Dict[str, Any]]:
    if not SESSION_SECRET:
        return None
    try:
        body, sig = token.split(".", 1)
        expected = _b64(hmac.new(SESSION_SECRET.encode("utf-8"), body.encode("ascii"), hashlib.sha256).digest())
        if not hmac.compare_digest(sig, expected):
            return None
        payload = json.loads(_unb64(body))
        if int(payload.get("exp", 0)) < int(time.time()):
            return None
        if role and payload.get("role") != role:
            return None
        return payload
    except Exception:
        return None


def bearer(request: Request) -> str:
    value = request.headers.get("authorization", "")
    return value[7:] if value.startswith("Bearer ") else ""


def auth(request: Request, role: Optional[str] = None) -> Optional[Dict[str, Any]]:
    return verify_token(bearer(request), role)


def clean_progress(progress: Any) -> Dict[str, Any]:
    if not isinstance(progress, dict):
        raise ValueError("Progression invalide.")
    raw = json_dumps(progress).encode("utf-8")
    if len(raw) > MAX_PROGRESS_BYTES:
        raise ValueError("Progression trop volumineuse.")
    return progress


def normalize_overrides(value: Any) -> Dict[str, bool]:
    value = json_loads(value, {})
    return {str(n): bool(value.get(str(n), value.get(n, False))) for n in range(1, 5)}


# ----------------------------- Database -----------------------------------

def db_kind() -> str:
    return "postgres" if DATABASE_URL else "sqlite"


@contextmanager
def db_conn():
    if DATABASE_URL:
        try:
            import psycopg
            from psycopg.rows import dict_row
        except ImportError as exc:  # pragma: no cover - production dependency
            raise RuntimeError("psycopg n'est pas installé. Installe requirements.txt") from exc
        conn = psycopg.connect(DATABASE_URL, row_factory=dict_row)
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()
    else:
        conn = sqlite3.connect(LOCAL_DB, timeout=15)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()


def sql(query: str) -> str:
    return query.replace("?", "%s") if DATABASE_URL else query


def one(conn, query: str, params: Iterable[Any] = ()) -> Optional[Dict[str, Any]]:
    cur = conn.execute(sql(query), tuple(params)) if not DATABASE_URL else conn.execute(sql(query), tuple(params))
    row = cur.fetchone()
    return dict(row) if row is not None else None


def all_rows(conn, query: str, params: Iterable[Any] = ()) -> list[Dict[str, Any]]:
    cur = conn.execute(sql(query), tuple(params)) if not DATABASE_URL else conn.execute(sql(query), tuple(params))
    return [dict(r) for r in cur.fetchall()]


def execute(conn, query: str, params: Iterable[Any] = ()):
    return conn.execute(sql(query), tuple(params))


def init_schema() -> None:
    global _schema_ready
    if _schema_ready:
        return
    with _schema_lock:
        if _schema_ready:
            return
        statements = [
            """
            CREATE TABLE IF NOT EXISTS teacher_config (
                id INTEGER PRIMARY KEY,
                pin_salt TEXT NOT NULL,
                pin_hash TEXT NOT NULL,
                iterations INTEGER NOT NULL,
                created_at TEXT NOT NULL
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS students (
                id TEXT PRIMARY KEY,
                username TEXT NOT NULL UNIQUE,
                display_name TEXT NOT NULL,
                pin_salt TEXT NOT NULL,
                pin_hash TEXT NOT NULL,
                iterations INTEGER NOT NULL,
                override_decks TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                last_login_at TEXT
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS student_progress (
                student_id TEXT PRIMARY KEY,
                payload TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                FOREIGN KEY(student_id) REFERENCES students(id) ON DELETE CASCADE
            )
            """,
            "CREATE INDEX IF NOT EXISTS idx_students_username ON students(username)",
        ]
        with db_conn() as conn:
            for stmt in statements:
                execute(conn, stmt)
        _schema_ready = True


def teacher_record() -> Optional[Dict[str, Any]]:
    init_schema()
    with db_conn() as conn:
        return one(conn, "SELECT * FROM teacher_config WHERE id = 1")


def student_by_username(username: str) -> Optional[Dict[str, Any]]:
    init_schema()
    with db_conn() as conn:
        return one(conn, "SELECT * FROM students WHERE username = ?", (username,))


def student_by_id(student_id: str) -> Optional[Dict[str, Any]]:
    init_schema()
    with db_conn() as conn:
        return one(conn, "SELECT * FROM students WHERE id = ?", (student_id,))


def student_progress(student_id: str) -> Optional[Dict[str, Any]]:
    init_schema()
    with db_conn() as conn:
        row = one(conn, "SELECT payload FROM student_progress WHERE student_id = ?", (student_id,))
    return json_loads(row["payload"], None) if row else None


def public_student(student: Dict[str, Any], progress: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    return {
        "id": student["id"],
        "username": student["username"],
        "displayName": student["display_name"],
        "overrideDecks": normalize_overrides(student.get("override_decks")),
        "createdAt": student.get("created_at"),
        "updatedAt": student.get("updated_at"),
        "progress": progress,
    }


def error(message: str, status: int = 400) -> JSONResponse:
    return JSONResponse({"error": message}, status_code=status, headers={"Cache-Control": "no-store"})


def ok(payload: Dict[str, Any], status: int = 200) -> JSONResponse:
    return JSONResponse(payload, status_code=status, headers={"Cache-Control": "no-store"})


@app.middleware("http")
async def runtime_config_guard(request: Request, call_next):
    if request.url.path.startswith("/api/") or request.url.path == "/api":
        if IS_VERCEL and not DATABASE_URL:
            return error("DATABASE_URL manquant. Connecte Neon/PostgreSQL au projet Vercel.", 503)
        if IS_VERCEL and not SESSION_SECRET:
            return error("SESSION_SECRET manquant dans les variables d'environnement Vercel.", 503)
    return await call_next(request)


@app.middleware("http")
async def no_store_api(request: Request, call_next):
    response = await call_next(request)
    if request.url.path.startswith("/api/"):
        response.headers["Cache-Control"] = "no-store"
    return response


# ----------------------------- API routes ---------------------------------
@app.get("/", include_in_schema=False)
def frontend_root():
    """Sert le jeu à la racine du domaine Vercel."""
    game_file = ROOT / "JOUER.html"
    if not game_file.exists():
        game_file = ROOT / "index.html"
    if not game_file.exists():
        return JSONResponse(
            {"detail": "Frontend introuvable: JOUER.html/index.html absent du déploiement."},
            status_code=500,
        )
    return FileResponse(game_file, media_type="text/html")


@app.get("/JOUER.html", include_in_schema=False)
def frontend_jouer():
    game_file = ROOT / "JOUER.html"
    if not game_file.exists():
        return JSONResponse({"detail": "JOUER.html introuvable."}, status_code=404)
    return FileResponse(game_file, media_type="text/html")


@app.get("/index.html", include_in_schema=False)
def frontend_index():
    game_file = ROOT / "index.html"
    if not game_file.exists():
        game_file = ROOT / "JOUER.html"
    if not game_file.exists():
        return JSONResponse({"detail": "Frontend introuvable."}, status_code=404)
    return FileResponse(game_file, media_type="text/html")


@app.get("/api/status")
def api_status():
    # Ne pas tenter une fausse persistance SQLite sur Vercel.
    if IS_VERCEL and not DATABASE_URL:
        return error("DATABASE_URL manquant. Connecte Neon/PostgreSQL au projet Vercel.", 503)
    if IS_VERCEL and not SESSION_SECRET:
        return error("SESSION_SECRET manquant dans les variables d'environnement Vercel.", 503)
    try:
        init_schema()
        with db_conn() as conn:
            teacher = one(conn, "SELECT id FROM teacher_config WHERE id = 1")
            count = one(conn, "SELECT COUNT(*) AS n FROM students")
        return ok({
            "codeStationServer": True,
            "version": "6.2-fixed",
            "storage": db_kind(),
            "teacherConfigured": bool(teacher),
            "students": int(count["n"] if count else 0),
        })
    except Exception as exc:
        return error(f"Stockage indisponible: {exc}", 503)


@app.get("/api/teacher/students")
def api_teacher_students(request: Request):
    if not auth(request, "teacher"):
        return error("Accès professeur requis.", 401)
    init_schema()
    with db_conn() as conn:
        students = all_rows(conn, "SELECT * FROM students ORDER BY display_name, username")
        progress_rows = all_rows(conn, "SELECT student_id, payload FROM student_progress")
    progress_map = {r["student_id"]: json_loads(r["payload"], None) for r in progress_rows}
    return ok({"students": [public_student(s, progress_map.get(s["id"])) for s in students]})


@app.get("/api/me/access")
def api_me_access(request: Request):
    sess = auth(request, "student")
    if not sess:
        return error("Session élève requise.", 401)
    student = student_by_id(sess["userId"])
    if not student:
        return error("Compte introuvable.", 404)
    return ok({"overrideDecks": normalize_overrides(student.get("override_decks"))})


@app.post("/api/teacher/setup")
async def api_teacher_setup(request: Request):
    data = await request.json()
    pin = str(data.get("pin", ""))
    if len(pin) < 4:
        return error("PIN trop court.")
    init_schema()
    if teacher_record():
        return error("Espace professeur déjà initialisé.", 409)
    rec = hash_pin(pin)
    try:
        with db_conn() as conn:
            execute(conn, "INSERT INTO teacher_config(id,pin_salt,pin_hash,iterations,created_at) VALUES(1,?,?,?,?)",
                    (rec["salt"], rec["hash"], rec["iterations"], now()))
    except Exception:
        return error("Espace professeur déjà initialisé.", 409)
    return ok({"ok": True})


@app.post("/api/login/teacher")
async def api_login_teacher(request: Request):
    data = await request.json()
    teacher = teacher_record()
    if not teacher or not check_pin(str(data.get("pin", "")), teacher["pin_salt"], teacher["pin_hash"], teacher["iterations"]):
        return error("PIN professeur incorrect.", 401)
    return ok({
        "token": issue_token("teacher", "teacher"),
        "user": {"id": "teacher", "displayName": "Professeur", "role": "teacher"},
    })


@app.post("/api/login/student")
async def api_login_student(request: Request):
    data = await request.json()
    username = str(data.get("username", "")).strip().lower()
    student = student_by_username(username)
    if not student or not check_pin(str(data.get("pin", "")), student["pin_salt"], student["pin_hash"], student["iterations"]):
        return error("Identifiant ou code incorrect.", 401)
    stamp = now()
    with db_conn() as conn:
        execute(conn, "UPDATE students SET last_login_at=?, updated_at=? WHERE id=?", (stamp, stamp, student["id"]))
    return ok({
        "token": issue_token("student", student["id"]),
        "user": {"id": student["id"], "username": student["username"], "displayName": student["display_name"], "role": "student"},
        "overrideDecks": normalize_overrides(student.get("override_decks")),
        "progress": student_progress(student["id"]),
    })


@app.post("/api/progress")
async def api_progress(request: Request):
    sess = auth(request, "student")
    if not sess:
        return error("Session élève requise.", 401)
    data = await request.json()
    try:
        progress = clean_progress(data.get("progress"))
    except ValueError as exc:
        return error(str(exc))
    stamp = now()
    progress["updatedAt"] = stamp
    raw = json_dumps(progress)
    init_schema()
    with db_conn() as conn:
        if DATABASE_URL:
            execute(conn, """
                INSERT INTO student_progress(student_id,payload,updated_at) VALUES(?,?,?)
                ON CONFLICT(student_id) DO UPDATE SET payload=EXCLUDED.payload, updated_at=EXCLUDED.updated_at
            """, (sess["userId"], raw, stamp))
        else:
            execute(conn, """
                INSERT INTO student_progress(student_id,payload,updated_at) VALUES(?,?,?)
                ON CONFLICT(student_id) DO UPDATE SET payload=excluded.payload, updated_at=excluded.updated_at
            """, (sess["userId"], raw, stamp))
        execute(conn, "UPDATE students SET updated_at=? WHERE id=?", (stamp, sess["userId"]))
    return ok({"ok": True, "updatedAt": stamp})


@app.post("/api/teacher/students")
async def api_create_student(request: Request):
    if not auth(request, "teacher"):
        return error("Accès professeur requis.", 401)
    data = await request.json()
    display = str(data.get("displayName", "")).strip()[:40]
    username = str(data.get("username", "")).strip().lower()[:32]
    pin = str(data.get("pin", ""))
    if not display or not username or len(pin) < 4:
        return error("Nom, identifiant et code (4+) requis.")
    if not all(c.isalnum() or c in "._-" for c in username):
        return error("Identifiant : lettres, chiffres, . _ - uniquement.")
    rec = hash_pin(pin)
    student_id = "stu_" + secrets.token_hex(8)
    stamp = now()
    overrides = json_dumps({str(n): False for n in range(1, 5)})
    try:
        with db_conn() as conn:
            execute(conn, """
                INSERT INTO students(id,username,display_name,pin_salt,pin_hash,iterations,override_decks,created_at,updated_at,last_login_at)
                VALUES(?,?,?,?,?,?,?,?,?,NULL)
            """, (student_id, username, display, rec["salt"], rec["hash"], rec["iterations"], overrides, stamp, stamp))
    except Exception as exc:
        # L'unicité username est garantie par PostgreSQL/SQLite.
        if "unique" in str(exc).lower() or "duplicate" in str(exc).lower():
            return error("Identifiant déjà utilisé.", 409)
        raise
    student = student_by_id(student_id)
    return ok({"student": public_student(student, None)}, 201)


@app.post("/api/teacher/students/{student_id}/overrides")
async def api_student_overrides(student_id: str, request: Request):
    if not auth(request, "teacher"):
        return error("Accès professeur requis.", 401)
    data = await request.json()
    try:
        deck = int(data.get("deck"))
    except Exception:
        return error("Deck invalide.")
    if deck not in (1, 2, 3, 4):
        return error("Deck invalide.")
    student = student_by_id(student_id)
    if not student:
        return error("Élève introuvable.", 404)
    overrides = normalize_overrides(student.get("override_decks"))
    overrides[str(deck)] = bool(data.get("value"))
    with db_conn() as conn:
        execute(conn, "UPDATE students SET override_decks=?, updated_at=? WHERE id=?",
                (json_dumps(overrides), now(), student_id))
    return ok({"ok": True, "overrideDecks": overrides})


@app.post("/api/teacher/students/{student_id}/pin")
async def api_student_pin(student_id: str, request: Request):
    if not auth(request, "teacher"):
        return error("Accès professeur requis.", 401)
    data = await request.json()
    pin = str(data.get("pin", ""))
    if len(pin) < 4:
        return error("Code trop court.")
    if not student_by_id(student_id):
        return error("Élève introuvable.", 404)
    rec = hash_pin(pin)
    with db_conn() as conn:
        execute(conn, "UPDATE students SET pin_salt=?, pin_hash=?, iterations=?, updated_at=? WHERE id=?",
                (rec["salt"], rec["hash"], rec["iterations"], now(), student_id))
    return ok({"ok": True})


@app.post("/api/teacher/students/{student_id}/reset-progress")
def api_reset_progress(student_id: str, request: Request):
    if not auth(request, "teacher"):
        return error("Accès professeur requis.", 401)
    if not student_by_id(student_id):
        return error("Élève introuvable.", 404)
    with db_conn() as conn:
        execute(conn, "DELETE FROM student_progress WHERE student_id=?", (student_id,))
        execute(conn, "UPDATE students SET updated_at=? WHERE id=?", (now(), student_id))
    return ok({"ok": True})


@app.get("/api")
def api_root():
    return ok({"service": "PédagoLab × CODE//STATION", "version": "6.3-vercel-root-fix"})


if __name__ == "__main__":
    # Développement local : python server.py
    import uvicorn

    host = os.environ.get("HOST", "127.0.0.1")
    port = env_int("PORT", 8765, minimum=1, maximum=65535)
    print(f"CODE//STATION PédagoLab API : http://{host}:{port}/api/status")
    print("Frontend : ouvre index.html via `vercel dev` pour tester le même origin.")
    uvicorn.run("server:app", host=host, port=port, reload=False)
