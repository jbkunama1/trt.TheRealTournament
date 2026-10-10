"""Legt ADMIN_USER mit ADMIN_PASSWORD an oder aktualisiert ihn (vor dem Serverstart)."""
import hashlib
import os
import secrets
import sqlite3

DATA_DIR = os.environ.get("DATA_DIR", "/data")
DB_PATH = os.environ.get("DB_PATH", os.path.join(DATA_DIR, "trt.db"))
ADMIN_USER = os.environ.get("ADMIN_USER", "admin")
ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "")


def hash_pw(pw, salt):
    return hashlib.sha256((salt + pw).encode()).hexdigest()


def main():
    if not ADMIN_PASSWORD:
        print("[bootstrap] ADMIN_PASSWORD nicht gesetzt - uebersprungen", flush=True)
        return
    if not os.path.exists(DB_PATH):
        print("[bootstrap] keine DB vorhanden - App legt den Admin beim ersten Start an", flush=True)
        return
    con = sqlite3.connect(DB_PATH)
    try:
        has_users = con.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='users'").fetchone()
        if not has_users:
            print("[bootstrap] users-Tabelle fehlt - uebersprungen", flush=True)
            return
        salt = secrets.token_hex(8)
        pw_hash = hash_pw(ADMIN_PASSWORD, salt)
        row = con.execute("SELECT id FROM users WHERE username=?", (ADMIN_USER,)).fetchone()
        if row:
            con.execute("UPDATE users SET pw_hash=?, salt=?, role='admin' WHERE id=?",
                        (pw_hash, salt, row[0]))
            print(f"[bootstrap] Admin '{ADMIN_USER}' aktualisiert", flush=True)
        else:
            con.execute(
                "INSERT INTO users(username,pw_hash,salt,role,display_name) VALUES(?,?,?,?,?)",
                (ADMIN_USER, pw_hash, salt, "admin", "Admin"))
            print(f"[bootstrap] Admin '{ADMIN_USER}' neu angelegt", flush=True)
        con.commit()
    finally:
        con.close()


if __name__ == "__main__":
    main()
