import os, sqlite3
from datetime import datetime, timezone

DB_PATH = os.getenv("DATABASE_PATH", "./data/monitor.db")

def connect():
    if DB_PATH != ":memory:": os.makedirs(os.path.dirname(os.path.abspath(DB_PATH)), exist_ok=True)
    db=sqlite3.connect(DB_PATH, timeout=10)
    db.row_factory=sqlite3.Row
    db.execute("PRAGMA foreign_keys=ON")
    return db

def init():
    with connect() as d:
        d.executescript('''CREATE TABLE IF NOT EXISTS targets(id INTEGER PRIMARY KEY, url TEXT UNIQUE NOT NULL, created_at TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS checks(id INTEGER PRIMARY KEY, target_id INTEGER NOT NULL REFERENCES targets(id) ON DELETE CASCADE, http_code INTEGER, elapsed_ms INTEGER NOT NULL, checked_at TEXT NOT NULL, status TEXT NOT NULL CHECK(status IN ('UP','DOWN')), error TEXT);
        CREATE INDEX IF NOT EXISTS checks_target_id_id ON checks(target_id,id DESC);''')

def add(url):
    try:
        with connect() as d:
            cur=d.execute("INSERT INTO targets(url,created_at) VALUES (?,?)",(url,datetime.now(timezone.utc).isoformat()))
            return cur.lastrowid
    except sqlite3.IntegrityError: return None

def delete(target_id):
    with connect() as d: return d.execute("DELETE FROM targets WHERE id=?",(target_id,)).rowcount > 0

def targets():
    with connect() as d:
        rows=d.execute('''SELECT t.*,c.http_code,c.elapsed_ms,c.checked_at,c.status,c.error FROM targets t LEFT JOIN checks c ON c.id=(SELECT id FROM checks WHERE target_id=t.id ORDER BY id DESC LIMIT 1) ORDER BY t.id''').fetchall()
        return [dict(x) for x in rows]

def history(target_id):
    with connect() as d: return [dict(x) for x in d.execute("SELECT http_code,elapsed_ms,checked_at,status,error FROM checks WHERE target_id=? ORDER BY id DESC LIMIT 20",(target_id,))]

def record(target_id, code, elapsed, status, error=None):
    with connect() as d:
        exists=d.execute("SELECT 1 FROM targets WHERE id=?",(target_id,)).fetchone()
        if not exists:return False
        d.execute("INSERT INTO checks(target_id,http_code,elapsed_ms,checked_at,status,error) VALUES (?,?,?,?,?,?)",(target_id,code,elapsed,datetime.now(timezone.utc).isoformat(),status,error))
        d.execute("DELETE FROM checks WHERE target_id=? AND id NOT IN (SELECT id FROM checks WHERE target_id=? ORDER BY id DESC LIMIT 20)",(target_id,target_id))
        return True
