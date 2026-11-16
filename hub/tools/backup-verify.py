#!/usr/bin/env python3
"""Check a pulled Faculty Hub database copy. Exit 0 only when the copy is usable.
  1. opens read-only and runs SQLite's own integrity check;
  2. prints row counts for the main tables so an empty or truncated copy is noticed;
  3. re-computes the audit log's hash chain, so an edited, deleted or inserted audit row shows up;
  4. with --prev OLD.db, requires every audit row of the previous copy to be unchanged in this one, which catches history that was
     rewritten on the server between two backups (a server that is altered cannot also alter the copy already on this computer).
Usage: backup-verify.py staff-YYYYMMDD-HHMM.db [minimum people, default 1] [--prev previous.db]"""
import hashlib, json, os, sqlite3, sys
from datetime import datetime


def audit_hash(prev, org, user, action, entity, entity_id, detail, at):   # same recipe as models.audit_hash
    body = json.dumps([prev or "", org, user, action, entity, entity_id, detail or {}, at.isoformat() if at else ""], sort_keys=True, default=str)
    return hashlib.sha256(body.encode()).hexdigest()


def chain_rows(con):
    q = "SELECT id, organization_id, user_id, action, entity, entity_id, detail, at, prev_hash, hash FROM audit_log WHERE hash IS NOT NULL ORDER BY id"
    return list(con.execute(q))


def check_chain(con):
    """Returns (rows_checked, problem or None). Rows written before chaining existed have no hash and are skipped."""
    cols = {r[1] for r in con.execute("PRAGMA table_info(audit_log)")}
    if "hash" not in cols:
        return 0, None
    prev, n = None, 0
    for (id_, org, user, action, entity, eid, detail, at, prev_hash, h) in chain_rows(con):
        d = json.loads(detail) if isinstance(detail, str) else (detail or {})
        when = datetime.fromisoformat(at) if at else None
        if prev is not None and prev_hash != prev:
            return n, f"audit row {id_} does not follow the row before it (a row was removed, added or reordered)"
        if audit_hash(prev_hash, org, user, action, entity, eid, d, when) != h:
            return n, f"audit row {id_} ({action}) was changed after it was written"
        prev, n = h, n + 1
    return n, None


def main():
    args = sys.argv[1:]
    prev_path = None
    if "--prev" in args:
        i = args.index("--prev"); prev_path = args[i + 1]; del args[i:i + 2]
    path = args[0]
    need = int(args[1]) if len(args) > 1 else 1
    if not os.path.isfile(path) or os.path.getsize(path) < 4096:
        sys.exit(f"FAIL: {path} is missing or too small to be a database")
    con = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    try:
        res = con.execute("PRAGMA integrity_check").fetchall()
    except sqlite3.DatabaseError as e:
        sys.exit(f"FAIL: not a readable database ({e})")
    if res != [("ok",)]:
        sys.exit(f"FAIL: integrity check reported {res[:3]}")
    tables = {r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    counts = {t: con.execute(f'SELECT COUNT(*) FROM "{t}"').fetchone()[0] for t in ("people", "users", "cv_entries", "reviews", "assignments", "audit_log") if t in tables}
    print("integrity ok;", ", ".join(f"{t}={n}" for t, n in counts.items()))
    if "people" not in tables or counts.get("people", 0) < need:
        sys.exit(f"FAIL: expected at least {need} people, found {counts.get('people', 0)}")
    n, problem = check_chain(con)
    if problem:
        sys.exit(f"FAIL: {problem}. (Two audit writes at the same instant can also cause a break; compare with the previous copy.)")
    print(f"audit chain ok ({n} chained rows)")
    if prev_path and os.path.isfile(prev_path):
        old = sqlite3.connect(f"file:{prev_path}?mode=ro", uri=True)
        if "hash" in {r[1] for r in old.execute("PRAGMA table_info(audit_log)")}:
            have = {r[0]: r[9] for r in chain_rows(con)}
            for r in chain_rows(old):
                if have.get(r[0]) != r[9]:
                    sys.exit(f"FAIL: audit row {r[0]} in the previous backup is missing or different here; history was altered since that backup")
            print("audit history matches the previous copy")


main()
