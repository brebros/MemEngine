"""SQLite connection + schema. Single file, zero dependencies."""
import os
import sqlite3

DEFAULT_DB_PATH = os.environ.get("MEMENGINE_DB", "/root/memengine/mem.db")
TYPES = ("fact", "experience", "observation", "decision")

SCHEMA = """
CREATE TABLE IF NOT EXISTS memories (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    bank TEXT NOT NULL,
    type TEXT NOT NULL DEFAULT 'fact',
    content TEXT NOT NULL,
    tags TEXT DEFAULT '',
    source TEXT DEFAULT '',
    created_at REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_bank ON memories(bank);
CREATE INDEX IF NOT EXISTS idx_bank_type ON memories(bank, type);
CREATE TABLE IF NOT EXISTS links (
    from_id INTEGER NOT NULL REFERENCES memories(id) ON DELETE CASCADE,
    to_id   INTEGER NOT NULL REFERENCES memories(id) ON DELETE CASCADE,
    created_at REAL NOT NULL,
    PRIMARY KEY (from_id, to_id)
);
CREATE VIRTUAL TABLE IF NOT EXISTS memories_fts USING fts5(
    content, tags, source,
    content='memories', content_rowid='id',
    tokenize='porter unicode61'
);
CREATE TRIGGER IF NOT EXISTS trg_ai AFTER INSERT ON memories BEGIN
    INSERT INTO memories_fts(rowid, content, tags, source)
    VALUES (new.id, new.content, new.tags, new.source);
END;
CREATE TRIGGER IF NOT EXISTS trg_ad AFTER DELETE ON memories BEGIN
    INSERT INTO memories_fts(memories_fts, rowid, content, tags, source)
    VALUES ('delete', old.id, old.content, old.tags, old.source);
END;
CREATE TRIGGER IF NOT EXISTS trg_au AFTER UPDATE ON memories BEGIN
    INSERT INTO memories_fts(memories_fts, rowid, content, tags, source)
    VALUES ('delete', old.id, old.content, old.tags, old.source);
    INSERT INTO memories_fts(rowid, content, tags, source)
    VALUES (new.id, new.content, new.tags, new.source);
END;
"""


def db_path() -> str:
    """Effective DB path: MEMENGINE_DB env overrides the default."""
    return os.environ.get("MEMENGINE_DB", DEFAULT_DB_PATH)


def connect(path: str | None = None) -> sqlite3.Connection:
    """Open (and initialize) the memory database."""
    path = path or db_path()
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    con = sqlite3.connect(path)
    con.execute("PRAGMA foreign_keys = ON")
    con.executescript(SCHEMA)
    return con
