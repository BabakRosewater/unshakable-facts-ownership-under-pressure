from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

DB_PATH = Path("training_app.db")
MODULE_COUNT = 32
HOST = "0.0.0.0"
PORT = 8000


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def get_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    conn = get_conn()
    cur = conn.cursor()
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL UNIQUE,
            created_at TEXT NOT NULL
        )
        """
    )
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS progress (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            module_number INTEGER NOT NULL,
            completed INTEGER NOT NULL DEFAULT 0,
            updated_at TEXT NOT NULL,
            UNIQUE(user_id, module_number)
        )
        """
    )
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS scores (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            scenario TEXT NOT NULL,
            score INTEGER NOT NULL,
            notes TEXT,
            created_at TEXT NOT NULL
        )
        """
    )
    conn.commit()
    conn.close()


class Handler(BaseHTTPRequestHandler):
    def _send_json(self, code: int, payload: dict | list) -> None:
        body = json.dumps(payload).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _send_html(self, html: str) -> None:
        body = html.encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _read_json_body(self) -> dict:
        content_length = int(self.headers.get("Content-Length", "0"))
        raw = self.rfile.read(content_length) if content_length else b"{}"
        return json.loads(raw.decode("utf-8"))

    def do_GET(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        path = parsed.path

        if path == "/":
            self._send_html(INDEX_HTML)
            return

        conn = get_conn()

        if path == "/api/users":
            rows = conn.execute("SELECT id, name, created_at FROM users ORDER BY id DESC").fetchall()
            conn.close()
            self._send_json(200, [dict(r) for r in rows])
            return

        if path.startswith("/api/progress/"):
            user_id = path.split("/")[-1]
            if not user_id.isdigit():
                conn.close()
                self._send_json(400, {"detail": "Invalid user id"})
                return
            uid = int(user_id)
            user = conn.execute("SELECT id, name FROM users WHERE id = ?", (uid,)).fetchone()
            if not user:
                conn.close()
                self._send_json(404, {"detail": "User not found"})
                return
            rows = conn.execute(
                "SELECT module_number, completed, updated_at FROM progress WHERE user_id = ? ORDER BY module_number ASC",
                (uid,),
            ).fetchall()
            conn.close()
            completed_modules = [r["module_number"] for r in rows if r["completed"] == 1]
            percent = round((len(completed_modules) / MODULE_COUNT) * 100, 1)
            self._send_json(
                200,
                {
                    "user": dict(user),
                    "module_count": MODULE_COUNT,
                    "completed_modules": completed_modules,
                    "completion_percent": percent,
                    "records": [dict(r) for r in rows],
                },
            )
            return

        if path.startswith("/api/scores/"):
            user_id = path.split("/")[-1]
            if not user_id.isdigit():
                conn.close()
                self._send_json(400, {"detail": "Invalid user id"})
                return
            uid = int(user_id)
            user = conn.execute("SELECT id, name FROM users WHERE id = ?", (uid,)).fetchone()
            if not user:
                conn.close()
                self._send_json(404, {"detail": "User not found"})
                return
            rows = conn.execute(
                "SELECT id, scenario, score, notes, created_at FROM scores WHERE user_id = ? ORDER BY id DESC",
                (uid,),
            ).fetchall()
            conn.close()
            avg = round(sum(r["score"] for r in rows) / len(rows), 2) if rows else None
            self._send_json(200, {"user": dict(user), "average_score": avg, "history": [dict(r) for r in rows]})
            return

        conn.close()
        self._send_json(404, {"detail": "Not found"})

    def do_POST(self) -> None:  # noqa: N802
        path = urlparse(self.path).path
        data = self._read_json_body()
        conn = get_conn()

        if path == "/api/users":
            name = (data.get("name") or "").strip()
            if len(name) < 2:
                conn.close()
                self._send_json(400, {"detail": "Name must be at least 2 chars"})
                return
            try:
                cur = conn.execute("INSERT INTO users(name, created_at) VALUES(?, ?)", (name, utc_now_iso()))
                conn.commit()
            except sqlite3.IntegrityError:
                conn.close()
                self._send_json(400, {"detail": "User already exists"})
                return
            row = conn.execute("SELECT id, name, created_at FROM users WHERE id = ?", (cur.lastrowid,)).fetchone()
            conn.close()
            self._send_json(200, dict(row))
            return

        if path == "/api/progress":
            try:
                user_id = int(data.get("user_id"))
                module_number = int(data.get("module_number"))
                completed = 1 if bool(data.get("completed")) else 0
            except (TypeError, ValueError):
                conn.close()
                self._send_json(400, {"detail": "Invalid payload"})
                return
            if module_number < 1 or module_number > MODULE_COUNT:
                conn.close()
                self._send_json(400, {"detail": "module_number must be between 1 and 32"})
                return
            user = conn.execute("SELECT id FROM users WHERE id = ?", (user_id,)).fetchone()
            if not user:
                conn.close()
                self._send_json(404, {"detail": "User not found"})
                return
            conn.execute(
                """
                INSERT INTO progress(user_id, module_number, completed, updated_at)
                VALUES(?, ?, ?, ?)
                ON CONFLICT(user_id, module_number)
                DO UPDATE SET completed=excluded.completed, updated_at=excluded.updated_at
                """,
                (user_id, module_number, completed, utc_now_iso()),
            )
            conn.commit()
            row = conn.execute(
                "SELECT user_id, module_number, completed, updated_at FROM progress WHERE user_id = ? AND module_number = ?",
                (user_id, module_number),
            ).fetchone()
            conn.close()
            self._send_json(200, dict(row))
            return

        if path == "/api/scores":
            try:
                user_id = int(data.get("user_id"))
                score = int(data.get("score"))
            except (TypeError, ValueError):
                conn.close()
                self._send_json(400, {"detail": "Invalid payload"})
                return
            scenario = (data.get("scenario") or "").strip()
            notes = (data.get("notes") or "").strip() or None
            if len(scenario) < 3:
                conn.close()
                self._send_json(400, {"detail": "Scenario must be at least 3 chars"})
                return
            if score < 1 or score > 5:
                conn.close()
                self._send_json(400, {"detail": "Score must be between 1 and 5"})
                return
            user = conn.execute("SELECT id FROM users WHERE id = ?", (user_id,)).fetchone()
            if not user:
                conn.close()
                self._send_json(404, {"detail": "User not found"})
                return
            cur = conn.execute(
                "INSERT INTO scores(user_id, scenario, score, notes, created_at) VALUES(?, ?, ?, ?, ?)",
                (user_id, scenario, score, notes, utc_now_iso()),
            )
            conn.commit()
            row = conn.execute(
                "SELECT id, user_id, scenario, score, notes, created_at FROM scores WHERE id = ?", (cur.lastrowid,)
            ).fetchone()
            conn.close()
            self._send_json(200, dict(row))
            return

        conn.close()
        self._send_json(404, {"detail": "Not found"})


INDEX_HTML = """<!doctype html>
<html>
<head>
  <meta charset=\"utf-8\" />
  <meta name=\"viewport\" content=\"width=device-width, initial-scale=1\" />
  <title>UF Training App</title>
  <style>
    body { font-family: Arial, sans-serif; margin: 0; background: #f7f8fb; color: #1d2433; }
    header { background: #1f3a8a; color: white; padding: 16px 24px; }
    main { padding: 20px; max-width: 1080px; margin: 0 auto; }
    .grid { display: grid; grid-template-columns: repeat(auto-fit,minmax(300px,1fr)); gap: 16px; }
    .card { background: white; border-radius: 10px; box-shadow: 0 2px 10px rgba(0,0,0,.08); padding: 14px; }
    input, select, button, textarea { width: 100%; margin-top: 6px; margin-bottom: 10px; padding: 8px; box-sizing: border-box; }
    button { background: #1f3a8a; color: white; border: 0; border-radius: 6px; cursor: pointer; }
    .muted { color: #5b6476; font-size: 14px; }
    .pill { display:inline-block; font-size:12px; padding:2px 8px; border-radius:999px; background:#e7eefc; margin:2px; }
    .ok { color: #14532d; }
    .error { color: #991b1b; }
    table { width: 100%; border-collapse: collapse; }
    th, td { border-bottom: 1px solid #e5e7eb; text-align: left; padding: 6px; font-size: 14px; }
  </style>
</head>
<body>
<header>
  <h1>Unshakable Facts Training App</h1>
  <div class=\"muted\" style=\"color:#dbe4ff\">Users • 32-Module Progress • Certification Scoring History</div>
</header>
<main>
  <div id=\"msg\"></div>
  <div class=\"grid\">
    <section class=\"card\">
      <h3>Create User</h3>
      <label>Name</label>
      <input id=\"userName\" placeholder=\"e.g., Alex Johnson\" />
      <button onclick=\"createUser()\">Add User</button>
      <h4>Users</h4>
      <select id=\"userSelect\"></select>
      <button onclick=\"refreshAll()\">Refresh Data</button>
    </section>

    <section class=\"card\">
      <h3>Module Progress</h3>
      <label>Module # (1-32)</label>
      <input id=\"moduleNum\" type=\"number\" min=\"1\" max=\"32\" value=\"1\" />
      <label>Completed</label>
      <select id=\"moduleComplete\"><option value=\"true\">Yes</option><option value=\"false\">No</option></select>
      <button onclick=\"saveProgress()\">Save Progress</button>
      <div id=\"progressSummary\" class=\"muted\"></div>
      <div id=\"completedPills\"></div>
    </section>

    <section class=\"card\">
      <h3>Add Certification Score</h3>
      <label>Scenario</label>
      <input id=\"scenario\" placeholder=\"Role-play escalation case\" />
      <label>Score (1-5)</label>
      <input id=\"score\" type=\"number\" min=\"1\" max=\"5\" value=\"4\" />
      <label>Notes</label>
      <textarea id=\"notes\" rows=\"3\" placeholder=\"Strengths and coaching notes\"></textarea>
      <button onclick=\"addScore()\">Add Score</button>
      <div id=\"scoreSummary\" class=\"muted\"></div>
      <table>
        <thead><tr><th>Date</th><th>Scenario</th><th>Score</th></tr></thead>
        <tbody id=\"scoresTable\"></tbody>
      </table>
    </section>
  </div>
</main>
<script>
const msg = (text, ok=true) => {
  const el = document.getElementById('msg');
  el.className = ok ? 'ok' : 'error';
  el.textContent = text;
  setTimeout(() => { el.textContent = ''; }, 2500);
}

async function api(path, opts={}) {
  const r = await fetch(path, { headers: {'Content-Type':'application/json'}, ...opts });
  const data = await r.json();
  if (!r.ok) throw new Error(data.detail || 'Request failed');
  return data;
}

function selectedUserId() { return Number(document.getElementById('userSelect').value); }

async function loadUsers() {
  const users = await api('/api/users');
  const sel = document.getElementById('userSelect');
  const prev = sel.value;
  sel.innerHTML = '';
  users.forEach(u => {
    const opt = document.createElement('option');
    opt.value = u.id;
    opt.textContent = `#${u.id} ${u.name}`;
    sel.appendChild(opt);
  });
  if (prev) sel.value = prev;
  if (!sel.value && users[0]) sel.value = String(users[0].id);
}

async function createUser() {
  const name = document.getElementById('userName').value.trim();
  if (!name) return msg('Name is required', false);
  try {
    await api('/api/users', { method:'POST', body: JSON.stringify({name}) });
    document.getElementById('userName').value = '';
    await refreshAll();
    msg('User created');
  } catch (e) { msg(e.message, false); }
}

async function saveProgress() {
  const user_id = selectedUserId();
  const module_number = Number(document.getElementById('moduleNum').value);
  const completed = document.getElementById('moduleComplete').value === 'true';
  try {
    await api('/api/progress', { method:'POST', body: JSON.stringify({ user_id, module_number, completed }) });
    await loadProgress();
    msg('Progress updated');
  } catch (e) { msg(e.message, false); }
}

async function loadProgress() {
  const user_id = selectedUserId();
  if (!user_id) return;
  const p = await api(`/api/progress/${user_id}`);
  document.getElementById('progressSummary').textContent = `${p.user.name}: ${p.completed_modules.length}/${p.module_count} modules complete (${p.completion_percent}%)`;
  const pills = document.getElementById('completedPills');
  pills.innerHTML = p.completed_modules.map(n => `<span class=\"pill\">M${n}</span>`).join('') || '<span class=\"muted\">No modules marked complete yet.</span>';
}

async function addScore() {
  const user_id = selectedUserId();
  const scenario = document.getElementById('scenario').value.trim();
  const score = Number(document.getElementById('score').value);
  const notes = document.getElementById('notes').value.trim();
  if (!scenario) return msg('Scenario is required', false);
  try {
    await api('/api/scores', { method:'POST', body: JSON.stringify({ user_id, scenario, score, notes }) });
    document.getElementById('scenario').value = '';
    document.getElementById('notes').value = '';
    await loadScores();
    msg('Score saved');
  } catch (e) { msg(e.message, false); }
}

async function loadScores() {
  const user_id = selectedUserId();
  if (!user_id) return;
  const s = await api(`/api/scores/${user_id}`);
  document.getElementById('scoreSummary').textContent = `${s.user.name}: avg score ${s.average_score ?? 'N/A'} (${s.history.length} records)`;
  const tbody = document.getElementById('scoresTable');
  tbody.innerHTML = s.history.map(r => `<tr><td>${new Date(r.created_at).toLocaleString()}</td><td>${r.scenario}</td><td>${r.score}</td></tr>`).join('') || '<tr><td colspan=\"3\" class=\"muted\">No scores yet.</td></tr>';
}

async function refreshAll() {
  await loadUsers();
  if (selectedUserId()) { await loadProgress(); await loadScores(); }
}

document.getElementById('userSelect').addEventListener('change', refreshAll);
refreshAll().catch(err => msg(err.message, false));
</script>
</body>
</html>
"""


def run() -> None:
    init_db()
    server = ThreadingHTTPServer((HOST, PORT), Handler)
    print(f"Serving UF Training app on http://{HOST}:{PORT}")
    server.serve_forever()


if __name__ == "__main__":
    run()
