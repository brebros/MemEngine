"""MemEngine CLI — argparse front-end. All commands print one JSON object per invocation."""
import argparse
import datetime
import json
import os
import re
import shutil
import sqlite3
import sys
import time

from memengine.db import TYPES, connect, db_path
from memengine.dedup import similar_exists
from memengine.quality import quality_gate

STOPWORDS = {
    "the", "a", "an", "at", "on", "in", "is", "are", "to", "of", "for", "and", "or", "with",
    "this", "that", "all", "by", "be", "it", "its", "yang", "dan", "atau", "dengan", "itu",
    "ini", "untuk", "dari", "ke", "pada", "adalah", "di", "tidak", "gak", "udah", "sudah",
}


def now() -> float:
    return time.time()


def out(ok=True, **kw):
    kw["ok"] = ok
    print(json.dumps(kw, ensure_ascii=False))


def backup_dir() -> str:
    return os.path.join(os.path.dirname(db_path()), "backups")


def cmd_daily(a):
    """Daily memory: keputusan/fakta penting per tanggal (WIB), bank 'daily'."""
    t = datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=7)))
    date_tag = f"date:{t.strftime('%Y-%m-%d')}"
    ok, reason = quality_gate(a.content)
    if not ok:
        print(json.dumps({"ok": False, "rejected": reason}))
        return 1
    if not a.source:
        print(json.dumps({"ok": False, "error": "--source required (konteks sumber)"}))
        return 1
    tags = ",".join(x for x in [date_tag, (a.tags or "")] if x)
    con = connect()
    dup_id, score = similar_exists(con, "daily", a.content)
    if dup_id and score >= 0.82 and not a.force:
        print(json.dumps({"ok": False, "duplicate": True, "similar_id": dup_id,
                          "similarity": round(score, 2),
                          "hint": f"similar memory #{dup_id} exists; use --force to add anyway"}))
        return 1
    cur = con.execute(
        "INSERT INTO memories (bank, type, content, tags, source, created_at) VALUES (?,?,?,?,?,?)",
        ("daily", a.type, a.content, tags, a.source, now()))
    con.commit()
    out(id=cur.lastrowid, bank="daily", type=a.type, date=date_tag,
        wib_time=t.strftime("%H:%M"), duplicate_check=round(score, 2) if dup_id else None)
    return 0


def cmd_add(a):
    if a.type not in TYPES or a.type == "observation":
        print(json.dumps({"ok": False,
                          "error": "type must be fact|experience|decision (use 'observe' for observations)"}))
        return 1
    ok, reason = quality_gate(a.content)
    if not ok:
        print(json.dumps({"ok": False, "rejected": reason}))
        return 1
    con = connect()
    dup_id, score = similar_exists(con, a.bank, a.content)
    if dup_id and score >= 0.82 and not a.force:
        print(json.dumps({"ok": False, "duplicate": True, "similar_id": dup_id,
                          "similarity": round(score, 2),
                          "hint": f"similar memory #{dup_id} exists; use --force to add anyway"}))
        return 1
    cur = con.execute(
        "INSERT INTO memories (bank, type, content, tags, source, created_at) VALUES (?,?,?,?,?,?)",
        (a.bank, a.type, a.content, a.tags or "", a.source or "", now()))
    con.commit()
    out(id=cur.lastrowid, bank=a.bank, type=a.type,
        duplicate_check=round(score, 2) if dup_id else None)
    return 0


def cmd_observe(a):
    con = connect()
    cur = con.execute(
        "INSERT INTO memories (bank, type, content, tags, source, created_at) VALUES (?,?,?,?,?,?)",
        (a.bank, "observation", a.content, a.tags or "", a.source or "consolidation", now()))
    oid = cur.lastrowid
    linked = []
    for raw in (a.refs or "").split(","):
        raw = raw.strip()
        if not raw:
            continue
        try:
            rid = int(raw)
        except ValueError:
            continue
        if con.execute("SELECT 1 FROM memories WHERE id=? AND bank=?", (rid, a.bank)).fetchone():
            con.execute("INSERT OR IGNORE INTO links (from_id, to_id, created_at) VALUES (?,?,?)",
                        (oid, rid, now()))
            linked.append(rid)
    con.commit()
    out(id=oid, type="observation", links_added=linked)
    return 0


def cmd_recall(a):
    con = connect()
    q = " ".join(a.query).strip()
    q_clean = re.sub(r"[^\w\s]", " ", q).strip() or q
    where, params = [], []
    if a.bank != "all":
        where.append("m.bank = ?")
        params.append(a.bank)
    if a.type:
        where.append("m.type = ?")
        params.append(a.type)
    if a.days:
        where.append("m.created_at >= ?")
        params.append(now() - a.days * 86400)
    where_sql = " AND ".join(where) or "1=1"
    sql = f"""SELECT m.id, m.bank, m.type, m.content, m.tags, m.source, m.created_at
              FROM memories m JOIN memories_fts f ON f.rowid = m.id
              WHERE memories_fts MATCH ? AND {where_sql}
              ORDER BY CASE m.type WHEN 'observation' THEN 0 WHEN 'decision' THEN 1
                                   WHEN 'fact' THEN 2 ELSE 3 END,
                       bm25(memories_fts)
              LIMIT ?"""
    try:
        rows = con.execute(sql, [q_clean] + params + [a.limit]).fetchall()
        # Multi-term recall: FTS bare query = implicit AND. Fallback OR + >=2 distinct
        # term overlap so multi-word queries still hit without single-token noise.
        terms = [t for t in re.findall(r"\w+", q_clean.lower()) if t and t not in STOPWORDS]
        if not rows and len(terms) >= 2:
            or_q = " OR ".join(terms)
            rows_or = con.execute(sql, [or_q] + params + [a.limit * 4]).fetchall()

            def _overlap(content):
                words = set(re.findall(r"\w+", content.lower()))
                return sum(1 for t in terms if t in words)

            rows = [r for r in rows_or if _overlap(r[3]) >= 2][:a.limit]
    except sqlite3.OperationalError:
        rows = con.execute(
            f"SELECT id, bank, type, content, tags, source, created_at FROM memories m "
            f"WHERE content LIKE ? AND {where_sql} ORDER BY created_at DESC LIMIT ?",
            [f"%{q}%"] + params + [a.limit]).fetchall()
    results = [{"id": r[0], "bank": r[1], "type": r[2], "content": r[3], "tags": r[4],
                "source": r[5], "age_days": round((now() - r[6]) / 86400, 1)} for r in rows]
    out(query=q, bank=a.bank, count=len(results), results=results)
    return 0


def cmd_link(a):
    con = connect()
    for x in (a.from_id, a.to_id):
        if not con.execute("SELECT 1 FROM memories WHERE id=? AND bank=?", (x, a.bank)).fetchone():
            out(ok=False, error=f"memory #{x} not found in bank '{a.bank}'")
            return 1
    if a.from_id == a.to_id:
        out(ok=False, error="cannot link a memory to itself")
        return 1
    try:
        con.execute("INSERT INTO links (from_id, to_id, created_at) VALUES (?,?,?)",
                    (a.from_id, a.to_id, now()))
        con.commit()
    except sqlite3.IntegrityError:
        out(ok=False, error="link already exists")
        return 1
    out(link=f"#{a.from_id} -> #{a.to_id}")
    return 0


def cmd_backlinks(a):
    con = connect()
    rows = con.execute(
        """SELECT m.id, m.type, m.content FROM links l
           JOIN memories m ON m.id = l.from_id
           WHERE l.to_id = ? AND m.bank = ? ORDER BY m.created_at DESC""", (a.id, a.bank)).fetchall()
    refs = [{"id": r[0], "type": r[1], "content": r[2]} for r in rows]
    out(memory=a.id, bank=a.bank, count=len(refs), referenced_by=refs)
    return 0


def cmd_graph(a):
    con = connect()
    where = "WHERE bank = ?" if a.bank else ""
    params = (a.bank,) if a.bank else ()
    nodes = [{"id": r[0], "bank": r[1], "type": r[2], "content": r[3][:120],
              "tags": r[4], "age_days": round((now() - r[5]) / 86400, 1)}
             for r in con.execute(
                 f"SELECT id, bank, type, content, tags, created_at FROM memories {where}", params).fetchall()]
    edges = [{"from": r[0], "to": r[1]}
             for r in con.execute(
                 f"""SELECT l.from_id, l.to_id FROM links l
                     JOIN memories m ON m.id = l.from_id {where}""", params).fetchall()]
    out(nodes=len(nodes), edges=len(edges), data={"nodes": nodes, "edges": edges})
    return 0


def cmd_list(a):
    con = connect()
    where, params = ["bank = ?"], [a.bank]
    if a.type:
        where.append("type = ?")
        params.append(a.type)
    rows = con.execute(
        f"SELECT id, type, content, tags, source, created_at FROM memories "
        f"WHERE {' AND '.join(where)} ORDER BY created_at DESC LIMIT ?",
        params + [a.limit]).fetchall()
    memories = [{"id": r[0], "type": r[1], "content": r[2], "tags": r[3],
                 "source": r[4], "age_days": round((now() - r[5]) / 86400, 1)} for r in rows]
    out(bank=a.bank, count=len(memories), memories=memories)
    return 0


def cmd_stats(a):
    con = connect()
    if a.bank:
        rows = con.execute("SELECT type, COUNT(*) FROM memories WHERE bank=? GROUP BY type", (a.bank,)).fetchall()
        by = {r[0]: r[1] for r in rows}
        total = sum(by.values())
        exp, obs = by.get("experience", 0), by.get("observation", 0)
        health = "learning" if (obs > 0 or exp == 0) else "NOT consolidating (experiences but no observations)"
        out(bank=a.bank, total=total, by_type=by,
            observation_ratio=round(obs / exp, 2) if exp else None, health=health)
    else:
        rows = con.execute("SELECT bank, COUNT(*) FROM memories GROUP BY bank").fetchall()
        out(total=sum(r[1] for r in rows), by_bank={r[0]: r[1] for r in rows})
    return 0


def cmd_banks(a):
    con = connect()
    rows = con.execute("SELECT bank, COUNT(*), MAX(created_at) FROM memories GROUP BY bank").fetchall()
    out(banks=[{"bank": r[0], "count": r[1],
                "last_write_days_ago": round((now() - r[2]) / 86400, 1)} for r in rows])
    return 0


def cmd_delete(a):
    con = connect()
    row = con.execute("SELECT content FROM memories WHERE bank=? AND id=?", (a.bank, a.id)).fetchone()
    if not row:
        out(ok=False, error=f"memory #{a.id} not found in bank '{a.bank}'")
        return 1
    con.execute("DELETE FROM links WHERE from_id=? OR to_id=?", (a.id, a.id))
    con.execute("DELETE FROM memories WHERE id=?", (a.id,))
    con.commit()
    out(deleted=a.id, content=row[0][:80])
    return 0


def cmd_backup(a):
    stamp = time.strftime("%Y-%m-%d_%H%M%S")
    dest = os.path.join(backup_dir(), stamp)
    os.makedirs(dest, exist_ok=True)
    shutil.copy2(db_path(), os.path.join(dest, "mem.db"))
    total = connect().execute("SELECT COUNT(*) FROM memories").fetchone()[0]
    dirs = sorted(os.listdir(backup_dir()))
    for old in dirs[:-30]:  # keep last 30
        shutil.rmtree(os.path.join(backup_dir(), old), ignore_errors=True)
    out(path=os.path.join(dest, "mem.db"), memories=total, kept_backups=len(dirs))
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="mem")
    sub = p.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("daily")
    s.add_argument("type")
    s.add_argument("content", nargs="+")
    s.add_argument("--source", required=True)
    s.add_argument("--tags")
    s.add_argument("--force", action="store_true")
    s.set_defaults(fn=cmd_daily)

    s = sub.add_parser("add")
    s.add_argument("bank")
    s.add_argument("type")
    s.add_argument("content", nargs="+")
    s.add_argument("--tags", default="")
    s.add_argument("--source", default="")
    s.add_argument("--force", action="store_true")
    s.set_defaults(fn=cmd_add)

    s = sub.add_parser("observe")
    s.add_argument("bank")
    s.add_argument("content", nargs="+")
    s.add_argument("--refs", default="")
    s.add_argument("--tags", default="")
    s.add_argument("--source", default="consolidation")
    s.set_defaults(fn=cmd_observe)

    s = sub.add_parser("recall")
    s.add_argument("bank")
    s.add_argument("query", nargs="+")
    s.add_argument("--limit", type=int, default=5)
    s.add_argument("--type", default=None)
    s.add_argument("--days", type=int, default=0)
    s.set_defaults(fn=cmd_recall)

    s = sub.add_parser("link")
    s.add_argument("bank")
    s.add_argument("from_id", type=int)
    s.add_argument("to_id", type=int)
    s.set_defaults(fn=cmd_link)

    s = sub.add_parser("backlinks")
    s.add_argument("bank")
    s.add_argument("id", type=int)
    s.set_defaults(fn=cmd_backlinks)

    s = sub.add_parser("graph")
    s.add_argument("bank", nargs="?", default=None)
    s.set_defaults(fn=cmd_graph)

    s = sub.add_parser("list")
    s.add_argument("bank")
    s.add_argument("--limit", type=int, default=20)
    s.add_argument("--type", default=None)
    s.set_defaults(fn=cmd_list)

    s = sub.add_parser("stats")
    s.add_argument("bank", nargs="?", default=None)
    s.set_defaults(fn=cmd_stats)

    sub.add_parser("banks").set_defaults(fn=cmd_banks)

    s = sub.add_parser("delete")
    s.add_argument("bank")
    s.add_argument("id", type=int)
    s.set_defaults(fn=cmd_delete)

    sub.add_parser("backup").set_defaults(fn=cmd_backup)
    return p


def main(argv=None):
    p = build_parser()
    a = p.parse_args(argv)
    if hasattr(a, "content"):
        a.content = " ".join(a.content)
    sys.exit(a.fn(a))


if __name__ == "__main__":
    main()
