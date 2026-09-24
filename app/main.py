"""🏆 TheRealTournament - FastAPI + SQLite Backend"""
import io
import os
import re
import hashlib
import secrets
import sqlite3
from datetime import datetime

from fastapi import Depends, FastAPI, File, Header, HTTPException, UploadFile
from fastapi.responses import Response, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

BASE_DIR = os.path.dirname(__file__)
DATA_DIR = os.environ.get("DATA_DIR", "/data")
DB_PATH = os.environ.get("DB_PATH", os.path.join(DATA_DIR, "trt.db"))
UPLOAD_DIR = os.environ.get("UPLOAD_DIR", os.path.join(DATA_DIR, "uploads"))
ADMIN_USER = os.environ.get("ADMIN_USER", "admin")
ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "bitte-aendern!")
SEED_DEMO = os.environ.get("SEED_DEMO", "true").lower() != "false"

os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
os.makedirs(UPLOAD_DIR, exist_ok=True)

ROUND_NAMES = {1: "Finale 🏆", 2: "Halbfinale", 3: "Viertelfinale",
               4: "Achtelfinale", 5: "Sechzehntelfinale", 6: "32tel-Finale"}
SPORTS = ["⚽ Fußball", "🏐 Volleyball", "🏀 Basketball", "🤾 Handball",
          "🏸 Badminton", "🏑 Hockey", "🎾 Tischtennis", "🏃 Völkerball", "🎯 Sonstiges"]
FORMATS = {"liga": "⚽ Jeder gegen Jeden (Liga)",
           "ko": "🏆 K.o.-System",
           "gruppen": "🌍 Gruppenphase + K.o."}

SCHEMA = """
CREATE TABLE IF NOT EXISTS users(
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  username TEXT UNIQUE NOT NULL,
  pw_hash TEXT NOT NULL,
  salt TEXT NOT NULL,
  role TEXT NOT NULL DEFAULT 'leser' CHECK(role IN ('admin','lehrer','leser')),
  display_name TEXT DEFAULT '',
  theme TEXT DEFAULT 'ksc',
  created_at TEXT DEFAULT (datetime('now')));
CREATE TABLE IF NOT EXISTS sessions(
  token TEXT PRIMARY KEY,
  user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  created_at TEXT DEFAULT (datetime('now')));
CREATE TABLE IF NOT EXISTS teams(
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  name TEXT NOT NULL,
  klasse TEXT DEFAULT '',
  sport TEXT DEFAULT '',
  color TEXT DEFAULT '#2563eb',
  emoji TEXT DEFAULT '🏅',
  logo TEXT);
CREATE TABLE IF NOT EXISTS tournaments(
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  name TEXT NOT NULL,
  sport TEXT DEFAULT 'Fußball',
  format TEXT DEFAULT 'liga' CHECK(format IN ('liga','ko','gruppen')),
  start_date TEXT DEFAULT '',
  end_date TEXT DEFAULT '',
  points_win INTEGER DEFAULT 3,
  points_draw INTEGER DEFAULT 1,
  num_groups INTEGER DEFAULT 2,
  status TEXT DEFAULT 'entwurf',
  created_at TEXT DEFAULT (datetime('now')));
CREATE TABLE IF NOT EXISTS tournament_teams(
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  tournament_id INTEGER NOT NULL REFERENCES tournaments(id) ON DELETE CASCADE,
  team_id INTEGER NOT NULL REFERENCES teams(id) ON DELETE CASCADE,
  group_name TEXT,
  UNIQUE(tournament_id, team_id));
CREATE TABLE IF NOT EXISTS matches(
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  tournament_id INTEGER NOT NULL REFERENCES tournaments(id) ON DELETE CASCADE,
  r_idx INTEGER DEFAULT 0,
  round_name TEXT DEFAULT '',
  group_name TEXT,
  home_id INTEGER,
  away_id INTEGER,
  home_score INTEGER,
  away_score INTEGER,
  home_pen INTEGER,
  away_pen INTEGER,
  date TEXT DEFAULT '',
  time TEXT DEFAULT '',
  court TEXT DEFAULT '',
  status TEXT DEFAULT 'offen' CHECK(status IN ('offen','bye','erledigt')));
"""


def db():
    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row
    return con


def hash_pw(pw, salt):
    return hashlib.sha256((salt + pw).encode()).hexdigest()


# --- BEGIN PURE LOGIC (stdlib only, testbar ohne FastAPI) ---

def rr_pairs(ids):
    teams = list(ids)
    if len(teams) % 2 == 1:
        teams.append(None)
    n = len(teams)
    ro = teams[1:]
    out = []
    for _ in range(n - 1):
        left = [teams[0]] + ro[: (n // 2 - 1)]
        right = list(reversed(ro[(n // 2 - 1):]))
        out.append([(a, b) for a, b in zip(left, right)
                    if a is not None and b is not None])
        ro = [ro[-1]] + ro[:-1]
    return out


def bracket_order(n):
    slots = [1, 2]
    while len(slots) < n:
        m = len(slots) * 2 + 1
        nxt = []
        for s in slots:
            nxt += [s, m - s]
        slots = nxt
    return slots


def snake_groups(ids, g):
    groups = [[] for _ in range(g)]
    for idx, t in enumerate(ids):
        cyc = (idx // g) % 2
        pos = idx % g
        i = pos if cyc == 0 else g - 1 - pos
        groups[i].append(t)
    return groups


def winner_of(m):
    if m["status"] == "bye":
        return m["home_id"]
    if m["status"] == "erledigt" and m["home_score"] is not None and m["away_score"] is not None:
        if m["home_score"] > m["away_score"]:
            return m["home_id"]
        if m["away_score"] > m["home_score"]:
            return m["away_id"]
        hp, ap = m["home_pen"], m["away_pen"]
        if hp is not None and ap is not None:
            return m["home_id"] if hp > ap else m["away_id"]
    return None


def insert_bracket(con, tid, entries):
    """entries = geordnete Liste der Erstrunden-Teilnehmer (Laenge beliebig)."""
    n = 1
    while n < len(entries):
        n *= 2
    entries = list(entries) + [None] * (n - len(entries))
    total = n.bit_length() - 1
    for r in range(total):
        cnt = n // (2 ** (r + 1))
        name = ROUND_NAMES.get(total - r, f"Runde {r + 1}")
        for i in range(cnt):
            if r == 0:
                a, b = entries[2 * i], entries[2 * i + 1]
                status = "offen" if (a and b) else ("bye" if a else "offen")
            else:
                a = b = None
                status = "offen"
            con.execute(
                "INSERT INTO matches(tournament_id,r_idx,round_name,group_name,home_id,away_id,status)"
                " VALUES(?,?,?,?,?,?,?)", (tid, r, name, None, a, b, status))


def advance(con, tid):
    rounds = [r[0] for r in con.execute(
        "SELECT DISTINCT r_idx FROM matches WHERE tournament_id=? AND group_name IS NULL ORDER BY r_idx",
        (tid,))]
    for i, r in enumerate(rounds[:-1]):
        cur = con.execute(
            "SELECT * FROM matches WHERE tournament_id=? AND r_idx=? AND group_name IS NULL ORDER BY id",
            (tid, r)).fetchall()
        for j, m in enumerate(cur):
            w = winner_of(m)
            if not w:
                continue
            targets = con.execute(
                "SELECT * FROM matches WHERE tournament_id=? AND r_idx=? AND group_name IS NULL ORDER BY id",
                (tid, rounds[i + 1])).fetchall()
            t = targets[j // 2]
            col = "home_id" if j % 2 == 0 else "away_id"
            con.execute(f"UPDATE matches SET {col}=? WHERE id=?", (w, t["id"]))


def gen_tournament(con, tid):
    t = con.execute("SELECT * FROM tournaments WHERE id=?", (tid,)).fetchone()
    teams = [r["team_id"] for r in con.execute(
        "SELECT team_id FROM tournament_teams WHERE tournament_id=? ORDER BY id", (tid,))]
    if len(teams) < 2:
        raise ValueError("Mindestens 2 Teams noetig ⚠️")
    con.execute("DELETE FROM matches WHERE tournament_id=?", (tid,))
    con.execute("UPDATE tournament_teams SET group_name=NULL WHERE tournament_id=?", (tid,))
    if t["format"] == "liga":
        for k, pairs in enumerate(rr_pairs(teams), 1):
            for h, a in pairs:
                con.execute(
                    "INSERT INTO matches(tournament_id,r_idx,round_name,group_name,home_id,away_id)"
                    " VALUES(?,?,?,?,?,?)", (tid, k, f"Spieltag {k}", "Liga", h, a))
    elif t["format"] == "ko":
        n = 1
        while n < len(teams):
            n *= 2
        seeds = list(teams) + [None] * (n - len(teams))
        entries = [seeds[o - 1] for o in bracket_order(n)]
        insert_bracket(con, tid, entries)
        advance(con, tid)
    else:  # gruppen
        g = max(1, min(int(t["num_groups"] or 2), len(teams)))
        letters = "ABCDEFGH"[:g]
        for letter, members in zip(letters, snake_groups(teams, g)):
            for tm in members:
                con.execute(
                    "UPDATE tournament_teams SET group_name=? WHERE tournament_id=? AND team_id=?",
                    (letter, tid, tm))
            for k, pairs in enumerate(rr_pairs(members), 1):
                for h, a in pairs:
                    con.execute(
                        "INSERT INTO matches(tournament_id,r_idx,round_name,group_name,home_id,away_id)"
                        " VALUES(?,?,?,?,?,?)", (tid, k, f"Spieltag {k}", letter, h, a))


def compute_standings(con, tid):
    t = con.execute("SELECT * FROM tournaments WHERE id=?", (tid,)).fetchone()
    pw, pd = t["points_win"] or 3, t["points_draw"] or 1
    stats = {}
    for r in con.execute(
            "SELECT tt.team_id, tt.group_name, tm.name, tm.emoji, tm.color, tm.klasse"
            " FROM tournament_teams tt JOIN teams tm ON tm.id=tt.team_id"
            " WHERE tt.tournament_id=?", (tid,)):
        stats[r["team_id"]] = dict(team_id=r["team_id"], name=r["name"], emoji=r["emoji"],
                                   color=r["color"], klasse=r["klasse"], group=r["group_name"],
                                   sp=0, w=0, d=0, l=0, gs=0, gc=0, pts=0)
    for m in con.execute(
            "SELECT * FROM matches WHERE tournament_id=? AND status='erledigt'"
            " AND group_name IS NOT NULL AND home_score IS NOT NULL AND away_score IS NOT NULL",
            (tid,)):
        h, a = stats.get(m["home_id"]), stats.get(m["away_id"])
        if not h or not a:
            continue
        hs, as_ = m["home_score"], m["away_score"]
        for s, fs, gs in ((h, hs, as_), (a, as_, hs)):
            s["sp"] += 1
            s["gs"] += fs
            s["gc"] += gs
        if hs > as_:
            h["w"] += 1
            a["l"] += 1
            h["pts"] += pw
        elif hs < as_:
            a["w"] += 1
            h["l"] += 1
            a["pts"] += pw
        else:
            h["d"] += 1
            a["d"] += 1
            h["pts"] += pd
            a["pts"] += pd
    out = sorted(stats.values(),
                 key=lambda s: (-s["pts"], -(s["gs"] - s["gc"]), -s["gs"], s["name"]))
    return out


def maybe_finals(con, tid):
    t = con.execute("SELECT * FROM tournaments WHERE id=?", (tid,)).fetchone()
    if t["format"] != "gruppen":
        return
    done = con.execute(
        "SELECT COUNT(*) c FROM matches WHERE tournament_id=? AND group_name IS NOT NULL AND status='offen'",
        (tid,)).fetchone()["c"]
    exist = con.execute(
        "SELECT COUNT(*) c FROM matches WHERE tournament_id=? AND group_name IS NULL",
        (tid,)).fetchone()["c"]
    if done or exist:
        return
    groups = [g[0] for g in con.execute(
        "SELECT DISTINCT group_name FROM matches WHERE tournament_id=? AND group_name IS NOT NULL ORDER BY group_name",
        (tid,))]
    if len(groups) < 2:
        return
    st = compute_standings(con, tid)
    by_group = {g: [s for s in st if s["group"] == g] for g in groups}
    if any(len(by_group[g]) < 2 for g in groups):
        return
    pairs = []
    for i, g in enumerate(groups):
        nxt = groups[(i + 1) % len(groups)]
        pairs.append(by_group[g][0]["team_id"])
        pairs.append(by_group[nxt][1]["team_id"])
    insert_bracket(con, tid, pairs)
    con.execute("UPDATE tournaments SET status='finalrunde' WHERE id=?", (tid,))
    advance(con, tid)


def latin1(s):
    return re.sub(r"[^\x00-\xff]", " ", str(s if s is not None else "")).strip()

# --- END PURE LOGIC ---


app = FastAPI(title="TheRealTournament 🏆", version="1.0.0")


def create_user(con, username, pw, role, display_name=""):
    salt = secrets.token_hex(8)
    return con.execute(
        "INSERT INTO users(username,pw_hash,salt,role,display_name) VALUES(?,?,?,?,?)",
        (username, hash_pw(pw, salt), salt, role, display_name)).lastrowid


def init_db():
    con = db()
    con.executescript(SCHEMA)
    if not con.execute("SELECT 1 FROM users").fetchone():
        create_user(con, ADMIN_USER, ADMIN_PASSWORD, "admin", "Admin 👑")
        if SEED_DEMO:
            demo = [("Löwen 7a 🦁", "7a", "Fußball", "#eab308", "🦁"),
                    ("Tiger 7b 🐯", "7b", "Fußball", "#f97316", "🐯"),
                    ("Adler 8a 🦅", "8a", "Volleyball", "#3b82f6", "🦅"),
                    ("Haie 8b 🦈", "8b", "Volleyball", "#06b6d4", "🦈"),
                    ("Falken 9a 🪶", "9a", "Basketball", "#8b5cf6", "🪶"),
                    ("Bären 9b 🐻", "9b", "Basketball", "#ef4444", "🐻")]
            for name, kl, sp, col, em in demo:
                con.execute("INSERT INTO teams(name,klasse,sport,color,emoji) VALUES(?,?,?,?,?)",
                            (name, kl, sp, col, em))
    con.commit()
    con.close()


# ---------- Auth ----------
def current_user(x_token: str = Header(default="")):
    con = db()
    row = con.execute(
        "SELECT u.* FROM sessions s JOIN users u ON u.id=s.user_id WHERE s.token=?",
        (x_token,)).fetchone()
    con.close()
    if not row:
        raise HTTPException(401, "🔒 Bitte einloggen")
    return dict(row)


def need(*roles):
    def dep(u=Depends(current_user)):
        if u["role"] not in roles:
            raise HTTPException(403, f"⛔ Keine Berechtigung (Rolle: {u['role']})")
        return u
    return dep


class LoginIn(BaseModel):
    username: str
    password: str


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/api/auth/login")
def login(inp: LoginIn):
    con = db()
    u = con.execute("SELECT * FROM users WHERE username=?", (inp.username,)).fetchone()
    if not u or u["pw_hash"] != hash_pw(inp.password, u["salt"]):
        con.close()
        raise HTTPException(401, "❌ Falscher Benutzername oder Passwort")
    token = secrets.token_hex(24)
    con.execute("INSERT INTO sessions(token,user_id) VALUES(?,?)", (token, u["id"]))
    con.commit()
    con.close()
    return {"token": token}


@app.post("/api/auth/logout")
def logout(x_token: str = Header(default=""), u=Depends(current_user)):
    con = db()
    con.execute("DELETE FROM sessions WHERE token=?", (x_token,))
    con.commit()
    con.close()
    return {"ok": True}


@app.get("/api/auth/me")
def me(u=Depends(current_user)):
    return {k: u[k] for k in ("id", "username", "role", "display_name", "theme")}


class ThemeIn(BaseModel):
    theme: str


@app.put("/api/auth/me/theme")
def set_theme(t: ThemeIn, u=Depends(current_user)):
    con = db()
    con.execute("UPDATE users SET theme=? WHERE id=?", (t.theme, u["id"]))
    con.commit()
    con.close()
    return {"ok": True}


# ---------- Benutzer (admin) ----------
class UserIn(BaseModel):
    username: str
    password: str
    role: str = "leser"
    display_name: str = ""


@app.get("/api/users")
def list_users(u=Depends(need("admin"))):
    con = db()
    rows = [{"id": r["id"], "username": r["username"], "role": r["role"],
             "display_name": r["display_name"]} for r in con.execute("SELECT * FROM users ORDER BY username")]
    con.close()
    return rows


@app.post("/api/users")
def add_user(inp: UserIn, u=Depends(need("admin"))):
    if inp.role not in ("admin", "lehrer", "leser"):
        raise HTTPException(400, "Ungültige Rolle")
    con = db()
    if con.execute("SELECT 1 FROM users WHERE username=?", (inp.username,)).fetchone():
        con.close()
        raise HTTPException(400, "Benutzername existiert bereits ⚠️")
    uid = create_user(con, inp.username, inp.password, inp.role, inp.display_name)
    con.commit()
    con.close()
    return {"id": uid}


@app.put("/api/users/{uid}")
def edit_user(uid: int, inp: dict, u=Depends(need("admin"))):
    con = db()
    row = con.execute("SELECT * FROM users WHERE id=?", (uid,)).fetchone()
    if not row:
        con.close()
        raise HTTPException(404, "Benutzer nicht gefunden")
    if inp.get("password"):
        salt = secrets.token_hex(8)
        con.execute("UPDATE users SET pw_hash=?, salt=? WHERE id=?",
                    (hash_pw(inp["password"], salt), salt, uid))
    if inp.get("role") in ("admin", "lehrer", "leser"):
        con.execute("UPDATE users SET role=? WHERE id=?", (inp["role"], uid))
    if inp.get("display_name") is not None:
        con.execute("UPDATE users SET display_name=? WHERE id=?", (inp["display_name"], uid))
    con.commit()
    con.close()
    return {"ok": True}


@app.delete("/api/users/{uid}")
def del_user(uid: int, u=Depends(need("admin"))):
    if uid == u["id"]:
        raise HTTPException(400, "Dich selbst kannst du nicht löschen 😅")
    con = db()
    con.execute("DELETE FROM users WHERE id=?", (uid,))
    con.commit()
    con.close()
    return {"ok": True}


# ---------- Teams ----------
class TeamIn(BaseModel):
    name: str
    klasse: str = ""
    sport: str = ""
    color: str = "#2563eb"
    emoji: str = "🏅"


@app.get("/api/teams")
def list_teams(u=Depends(current_user)):
    con = db()
    rows = [dict(r) for r in con.execute("SELECT * FROM teams ORDER BY klasse, name")]
    con.close()
    return rows


@app.post("/api/teams")
def add_team(inp: TeamIn, u=Depends(need("admin", "lehrer"))):
    con = db()
    tid = con.execute(
        "INSERT INTO teams(name,klasse,sport,color,emoji) VALUES(?,?,?,?,?)",
        (inp.name, inp.klasse, inp.sport, inp.color, inp.emoji)).lastrowid
    con.commit()
    con.close()
    return {"id": tid}


@app.put("/api/teams/{tid}")
def edit_team(tid: int, inp: TeamIn, u=Depends(need("admin", "lehrer"))):
    con = db()
    con.execute("UPDATE teams SET name=?,klasse=?,sport=?,color=?,emoji=? WHERE id=?",
                (inp.name, inp.klasse, inp.sport, inp.color, inp.emoji, tid))
    con.commit()
    con.close()
    return {"ok": True}


@app.delete("/api/teams/{tid}")
def del_team(tid: int, u=Depends(need("admin", "lehrer"))):
    con = db()
    used = con.execute(
        "SELECT (SELECT COUNT(*) FROM tournament_teams WHERE team_id=?) +"
        " (SELECT COUNT(*) FROM matches WHERE home_id=? OR away_id=?) c",
        (tid, tid, tid)).fetchone()["c"]
    if used:
        con.close()
        raise HTTPException(400, "Team wird bereits verwendet ⚠️")
    con.execute("DELETE FROM teams WHERE id=?", (tid,))
    con.commit()
    con.close()
    return {"ok": True}


@app.post("/api/teams/{tid}/logo")
def upload_logo(tid: int, file: UploadFile = File(...), u=Depends(need("admin", "lehrer"))):
    ext = os.path.splitext(file.filename or "")[1].lower()
    if ext not in (".png", ".jpg", ".jpeg", ".webp", ".gif", ".svg"):
        raise HTTPException(400, "Nur Bilddateien erlaubt (png/jpg/webp/gif/svg) ⚠️")
    fname = f"logo_{tid}_{secrets.token_hex(4)}{ext}"
    with open(os.path.join(UPLOAD_DIR, fname), "wb") as fh:
        fh.write(file.file.read())
    con = db()
    con.execute("UPDATE teams SET logo=? WHERE id=?", (fname, tid))
    con.commit()
    con.close()
    return {"logo": fname}


# ---------- Turniere ----------
class TournamentIn(BaseModel):
    name: str
    sport: str = "Fußball"
    format: str = "liga"
    start_date: str = ""
    end_date: str = ""
    points_win: int = 3
    points_draw: int = 1
    num_groups: int = 2


@app.get("/api/tournaments")
def list_tournaments(u=Depends(current_user)):
    con = db()
    out = []
    for t in con.execute("SELECT * FROM tournaments ORDER BY id DESC"):
        d = dict(t)
        d["team_count"] = con.execute(
            "SELECT COUNT(*) c FROM tournament_teams WHERE tournament_id=?", (t["id"],)).fetchone()["c"]
        d["match_count"] = con.execute(
            "SELECT COUNT(*) c FROM matches WHERE tournament_id=?", (t["id"],)).fetchone()["c"]
        out.append(d)
    con.close()
    return out


@app.post("/api/tournaments")
def add_tournament(inp: TournamentIn, u=Depends(need("admin", "lehrer"))):
    if inp.format not in FORMATS:
        raise HTTPException(400, "Unbekanntes Format")
    con = db()
    tid = con.execute(
        "INSERT INTO tournaments(name,sport,format,start_date,end_date,points_win,points_draw,num_groups)"
        " VALUES(?,?,?,?,?,?,?,?)",
        (inp.name, inp.sport, inp.format, inp.start_date, inp.end_date,
         inp.points_win, inp.points_draw, inp.num_groups)).lastrowid
    con.commit()
    con.close()
    return {"id": tid}


@app.put("/api/tournaments/{tid}")
def edit_tournament(tid: int, inp: TournamentIn, u=Depends(need("admin", "lehrer"))):
    con = db()
    con.execute(
        "UPDATE tournaments SET name=?,sport=?,format=?,start_date=?,end_date=?,points_win=?,points_draw=?,"
        "num_groups=? WHERE id=?",
        (inp.name, inp.sport, inp.format, inp.start_date, inp.end_date,
         inp.points_win, inp.points_draw, inp.num_groups, tid))
    con.commit()
    con.close()
    return {"ok": True}


@app.delete("/api/tournaments/{tid}")
def del_tournament(tid: int, u=Depends(need("admin", "lehrer"))):
    con = db()
    con.execute("DELETE FROM matches WHERE tournament_id=?", (tid,))
    con.execute("DELETE FROM tournament_teams WHERE tournament_id=?", (tid,))
    con.execute("DELETE FROM tournaments WHERE id=?", (tid,))
    con.commit()
    con.close()
    return {"ok": True}


@app.get("/api/tournaments/{tid}")
def get_tournament(tid: int, u=Depends(current_user)):
    con = db()
    t = con.execute("SELECT * FROM tournaments WHERE id=?", (tid,)).fetchone()
    if not t:
        con.close()
        raise HTTPException(404, "Turnier nicht gefunden")
    teams = [dict(r) for r in con.execute(
        "SELECT t.*, tt.group_name FROM tournament_teams tt JOIN teams t ON t.id=tt.team_id"
        " WHERE tt.tournament_id=? ORDER BY tt.group_name, t.name", (tid,))]
    con.close()
    d = dict(t)
    d["teams"] = teams
    return d


@app.post("/api/tournaments/{tid}/teams/{team_id}")
def assign_team(tid: int, team_id: int, u=Depends(need("admin", "lehrer"))):
    con = db()
    try:
        con.execute("INSERT INTO tournament_teams(tournament_id,team_id) VALUES(?,?)", (tid, team_id))
        con.commit()
    except sqlite3.IntegrityError:
        pass
    con.close()
    return {"ok": True}


@app.delete("/api/tournaments/{tid}/teams/{team_id}")
def unassign_team(tid: int, team_id: int, u=Depends(need("admin", "lehrer"))):
    con = db()
    con.execute("DELETE FROM tournament_teams WHERE tournament_id=? AND team_id=?", (tid, team_id))
    con.commit()
    con.close()
    return {"ok": True}


@app.post("/api/tournaments/{tid}/generate")
def generate_plan(tid: int, u=Depends(need("admin", "lehrer"))):
    con = db()
    try:
        gen_tournament(con, tid)
        con.execute("UPDATE tournaments SET status='laeuft' WHERE id=?", (tid,))
        con.commit()
    except ValueError as ex:
        con.close()
        raise HTTPException(400, str(ex))
    con.close()
    return {"ok": True}


# ---------- Spiele & Ergebnisse ----------
class ScheduleIn(BaseModel):
    date: str = ""
    start_time: str = "09:00"
    duration: int = 10
    courts: str = "Platz 1"


@app.post("/api/tournaments/{tid}/schedule")
def schedule_matches(tid: int, inp: ScheduleIn, u=Depends(need("admin", "lehrer"))):
    con = db()
    t = con.execute("SELECT * FROM tournaments WHERE id=?", (tid,)).fetchone()
    date = inp.date or t["start_date"]
    courts = [c.strip() for c in inp.courts.split(",") if c.strip()] or ["Platz 1"]
    try:
        hh, mm = map(int, inp.start_time.split(":"))
    except Exception:
        con.close()
        raise HTTPException(400, "Ungueltige Startzeit ⏰")
    matches = con.execute(
        "SELECT id FROM matches WHERE tournament_id=? AND status='offen' ORDER BY r_idx, id",
        (tid,)).fetchall()
    for i, m in enumerate(matches):
        slot = i // len(courts)
        total = hh * 60 + mm + slot * max(1, inp.duration)
        con.execute("UPDATE matches SET date=?, time=?, court=? WHERE id=?",
                    (date, f"{total // 60:02d}:{total % 60:02d}", courts[i % len(courts)], m["id"]))
    con.commit()
    con.close()
    return {"ok": True, "count": len(matches)}


@app.get("/api/tournaments/{tid}/matches")
def list_matches(tid: int, u=Depends(current_user)):
    con = db()
    rows = [dict(r) for r in con.execute(
        "SELECT m.*, h.name home_name, h.emoji home_emoji, h.color home_color, h.logo home_logo,"
        " a.name away_name, a.emoji away_emoji, a.color away_color, a.logo away_logo"
        " FROM matches m"
        " LEFT JOIN teams h ON h.id=m.home_id"
        " LEFT JOIN teams a ON a.id=m.away_id"
        " WHERE m.tournament_id=? ORDER BY m.group_name, m.r_idx, m.id", (tid,))]
    con.close()
    return rows


@app.get("/api/tournaments/{tid}/standings")
def get_standings(tid: int, u=Depends(current_user)):
    con = db()
    out = compute_standings(con, tid)
    con.close()
    return out


@app.get("/api/tournaments/{tid}/champion")
def get_champion(tid: int, u=Depends(current_user)):
    con = db()
    t = con.execute("SELECT * FROM tournaments WHERE id=?", (tid,)).fetchone()
    champ = None
    if t["format"] == "liga":
        st = compute_standings(con, tid)
        played = [m for m in con.execute(
            "SELECT 1 FROM matches WHERE tournament_id=? AND status='erledigt'", (tid,))]
        total = con.execute(
            "SELECT COUNT(*) c FROM matches WHERE tournament_id=?", (tid,)).fetchone()["c"]
        if st and total and len(played) == total:
            champ = st[0]
    else:
        fin = con.execute(
            "SELECT * FROM matches WHERE tournament_id=? AND group_name IS NULL AND round_name LIKE 'Finale%'",
            (tid,)).fetchone()
        wid = winner_of(fin) if fin else None
        if wid:
            row = con.execute(
                "SELECT t.*, tt.group_name FROM teams t LEFT JOIN tournament_teams tt"
                " ON tt.team_id=t.id AND tt.tournament_id=? WHERE t.id=?", (tid, wid)).fetchone()
            champ = dict(row) if row else None
    con.close()
    return {"champion": champ}


class ResultIn(BaseModel):
    home_score: int | None = None
    away_score: int | None = None
    home_pen: int | None = None
    away_pen: int | None = None


@app.patch("/api/matches/{mid}")
def set_result(mid: int, inp: ResultIn, u=Depends(need("admin", "lehrer"))):
    con = db()
    m = con.execute("SELECT * FROM matches WHERE id=?", (mid,)).fetchone()
    if not m:
        con.close()
        raise HTTPException(404, "Spiel nicht gefunden")
    status = "erledigt" if inp.home_score is not None and inp.away_score is not None else "offen"
    con.execute(
        "UPDATE matches SET home_score=?,away_score=?,home_pen=?,away_pen=?,status=? WHERE id=?",
        (inp.home_score, inp.away_score, inp.home_pen, inp.away_pen, status, mid))
    advance(con, m["tournament_id"])
    if status == "erledigt":
        maybe_finals(con, m["tournament_id"])
    con.commit()
    con.close()
    return {"ok": True}


# ---------- Exporte ----------
@app.get("/api/tournaments/{tid}/export.ics")
def export_ics(tid: int, u=Depends(current_user)):
    con = db()
    t = con.execute("SELECT * FROM tournaments WHERE id=?", (tid,)).fetchone()
    matches = con.execute(
        "SELECT m.*, h.name hn, a.name an FROM matches m"
        " LEFT JOIN teams h ON h.id=m.home_id LEFT JOIN teams a ON a.id=m.away_id"
        " WHERE m.tournament_id=? ORDER BY m.date, m.time, m.id", (tid,)).fetchall()
    con.close()
    lines = ["BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//TheRealTournament//DE",
             f"X-WR-CALNAME:{t['name']}"]
    now = datetime.utcnow().strftime("%Y%m%dT%H%M%SZ")
    for m in matches:
        if not m["date"]:
            continue
        try:
            d = m["date"].replace("-", "")
            tm = (m["time"] or "09:00").replace(":", "") + "00"
        except Exception:
            continue
        title = f"{m['round_name']}: {m['hn'] or 'TBD'} vs {m['an'] or 'TBD'}"
        lines += [
            "BEGIN:VEVENT",
            f"UID:match-{m['id']}@therealtournament",
            f"DTSTAMP:{now}",
            f"DTSTART:{d}T{tm}",
            f"SUMMARY:{title}",
            f"LOCATION:{m['court'] or 'Sporthalle'}",
            "END:VEVENT"]
    lines.append("END:VCALENDAR")
    return Response("\r\n".join(lines), media_type="text/calendar",
                    headers={"Content-Disposition": 'attachment; filename="turnier.ics"'})


@app.get("/api/tournaments/{tid}/export.pdf")
def export_pdf(tid: int, u=Depends(current_user)):
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4, landscape
    from reportlab.lib.styles import getSampleStyleSheet
    from reportlab.lib.units import cm
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle

    con = db()
    t = con.execute("SELECT * FROM tournaments WHERE id=?", (tid,)).fetchone()
    if not t:
        con.close()
        raise HTTPException(404, "Turnier nicht gefunden")
    matches = con.execute(
        "SELECT m.*, h.name hn, a.name an FROM matches m"
        " LEFT JOIN teams h ON h.id=m.home_id LEFT JOIN teams a ON a.id=m.away_id"
        " WHERE m.tournament_id=? ORDER BY m.group_name, m.r_idx, m.id", (tid,)).fetchall()
    standings = compute_standings(con, tid)
    con.close()

    styles = getSampleStyleSheet()
    el = [Paragraph(f"TheRealTournament: {latin1(t['name'])}", styles["Title"]),
          Paragraph(f"Sportart: {latin1(t['sport'])} | Format: {latin1(FORMATS.get(t['format'], t['format']))}"
                    f" | Zeitraum: {t['start_date']} - {t['end_date']}", styles["Normal"]),
          Spacer(1, 0.5 * cm)]

    el.append(Paragraph("Spielplan", styles["Heading2"]))
    data = [["Datum", "Zeit", "Runde/Gruppe", "Heim", "Gast", "Ergebnis", "Platz"]]
    for m in matches:
        erg = "-"
        if m["status"] == "erledigt" and m["home_score"] is not None:
            erg = f"{m['home_score']}:{m['away_score']}"
            if m["home_pen"] is not None and m["away_pen"] is not None:
                erg += f" ({m['home_pen']}:{m['away_pen']} n.E.)"
        grp = f"Gruppe {m['group_name']} | " if m["group_name"] not in (None, "", "Liga") else ""
        data.append([m["date"] or "", m["time"] or "", grp + latin1(m["round_name"]),
                     latin1(m["hn"] or "TBD"), latin1(m["an"] or "TBD"), erg, m["court"] or ""])
    tbl = Table(data, repeatRows=1)
    tbl.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1e3a8a")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTSIZE", (0, 0), (-1, -1), 8),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.whitesmoke, colors.white]),
        ("GRID", (0, 0), (-1, -1), 0.25, colors.lightgrey),
    ]))
    el += [tbl, Spacer(1, 0.5 * cm)]

    if standings and t["format"] in ("liga", "gruppen"):
        el.append(Paragraph("Tabelle", styles["Heading2"]))
        groups = sorted({s["group"] or "-" for s in standings})
        for g in groups:
            rows = [s for s in standings if (s["group"] or "-") == g]
            if not rows:
                continue
            el.append(Paragraph(f"Gruppe {g}", styles["Heading3"]))
            td = [["#", "Team", "Klasse", "Sp", "S", "U", "N", "Tore", "Diff", "Pkt"]]
            for i, s in enumerate(rows, 1):
                td.append([i, latin1(s["name"]), s["klasse"], s["sp"], s["w"], s["d"], s["l"],
                           f"{s['gs']}:{s['gc']}", s["gs"] - s["gc"], s["pts"]])
            st_tbl = Table(td)
            st_tbl.setStyle(TableStyle([
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#166534")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("FONTSIZE", (0, 0), (-1, -1), 8),
                ("GRID", (0, 0), (-1, -1), 0.25, colors.lightgrey),
                ("BACKGROUND", (0, 1), (-1, 1), colors.HexColor("#bbf7d0")),
            ]))
            el += [st_tbl, Spacer(1, 0.3 * cm)]

    el.append(Paragraph(f"Erstellt mit TheRealTournament am {datetime.now():%d.%m.%Y %H:%M}",
                        styles["Italic"]))
    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=landscape(A4), title=latin1(t["name"]),
                            leftMargin=1 * cm, rightMargin=1 * cm)
    doc.build(el)
    buf.seek(0)
    fname = re.sub(r"[^\w-]+", "_", t["name"]) + ".pdf"
    return StreamingResponse(buf, media_type="application/pdf",
                             headers={"Content-Disposition": f'attachment; filename="{fname}"'})


app.mount("/logos", StaticFiles(directory=UPLOAD_DIR), name="logos")
app.mount("/", StaticFiles(directory=os.path.join(BASE_DIR, "static"), html=True), name="static")

init_db()
