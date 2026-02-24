from __future__ import annotations

import argparse
import hashlib
import json
import os
import random
import sqlite3
import string
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple


# -----------------------------
# Helpers
# -----------------------------

def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()

def canonical_hash(payload: Dict[str, Any]) -> str:
    canon = dict(payload)
    canon.pop("evidence_hash", None)
    blob = json.dumps(canon, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(blob).hexdigest()

def rand_id(n: int = 12) -> str:
    return "".join(random.choice(string.ascii_lowercase + string.digits) for _ in range(n))


# -----------------------------
# DB config
# -----------------------------

@dataclass
class DB:
    path: str
    table: str = "ua_ledger"


# -----------------------------
# Introspection
# -----------------------------

def get_columns(db: DB) -> List[str]:
    con = sqlite3.connect(db.path)
    try:
        rows = con.execute(f"PRAGMA table_info({db.table})").fetchall()
        # row: (cid, name, type, notnull, dflt_value, pk)
        return [r[1] for r in rows]
    finally:
        con.close()

def table_exists(db: DB) -> bool:
    con = sqlite3.connect(db.path)
    try:
        row = con.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
            (db.table,),
        ).fetchone()
        return row is not None
    finally:
        con.close()


# -----------------------------
# CMR record generator (synthetic)
# Match your CMR v1 schema fields.
# -----------------------------

def insert_synthetic_event(db: DB, prev_hash: Optional[str], engine_version: str, contract_version: str) -> str:
    """
    Inserts a synthetic row following the CMR v1 pattern:
      - computes evidence_hash deterministically
      - includes prev_hash chaining
    Returns the new evidence_hash.
    """
    ts0 = utc_now()
    t0 = time.perf_counter()

    # simulate work
    ua_spend = random.randint(1, 50)
    work_units = random.randint(10, 500)
    delta_s = random.random() * 2.0
    dsua = delta_s / ua_spend
    h = 1e-15
    contract_valid = 1
    fail_reason = None

    # precise end timestamp
    time.sleep(0.0)
    ts1 = utc_now()
    latency_ms = (time.perf_counter() - t0) * 1000.0

    payload = {
        "timestamp_start": ts0,
        "timestamp_end": ts1,
        "user_id": "stress_user",
        "session_id": "stress_session",
        "request_id": f"stress:{rand_id()}",
        "engine_version": engine_version,
        "contract_version": contract_version,
        "git_commit": os.getenv("GIT_COMMIT", "unknown"),
        "host_id": os.getenv("HOSTNAME", "unknown"),
        "seed": random.randint(0, 10_000_000),
        "latency_ms": float(latency_ms),
        "contract_valid": bool(contract_valid),
        "contract_fail_reason": fail_reason,
        "ua_spend": int(ua_spend),
        "delta_s": float(delta_s),
        "delta_s_per_ua": float(dsua),
        "h_rigidity": float(h),
        "work_units": int(work_units),
        "prev_hash": prev_hash,
        "evidence_hash": "",
    }
    payload["evidence_hash"] = canonical_hash(payload)

    cols = get_columns(db)
    # Build insert with only columns that exist (lets this work across minor schema variants)
    insert_fields = []
    insert_values = []
    for k, v in payload.items():
        if k in cols:
            insert_fields.append(k)
            insert_values.append(v)

    if "contract_valid" in cols:
        # If stored as int in sqlite, convert (some schemas store 0/1)
        idx = insert_fields.index("contract_valid")
        insert_values[idx] = 1 if payload["contract_valid"] else 0

    placeholders = ",".join(["?"] * len(insert_fields))
    fieldlist = ",".join(insert_fields)

    con = sqlite3.connect(db.path, timeout=30)
    try:
        con.execute("BEGIN IMMEDIATE")
        con.execute(
            f"INSERT INTO {db.table} ({fieldlist}) VALUES ({placeholders})",
            tuple(insert_values),
        )
        con.commit()
    finally:
        con.close()

    return payload["evidence_hash"]


# -----------------------------
# Chain verifier
# -----------------------------

def fetch_chain(db: DB, limit: Optional[int] = None) -> List[Dict[str, Any]]:
    con = sqlite3.connect(db.path)
    con.row_factory = sqlite3.Row
    try:
        q = f"SELECT * FROM {db.table} ORDER BY id ASC"
        if limit:
            q += " LIMIT ?"
            rows = con.execute(q, (limit,)).fetchall()
        else:
            rows = con.execute(q).fetchall()
        return [dict(r) for r in rows]
    finally:
        con.close()

def compute_row_hash_from_db_row(row: Dict[str, Any]) -> str:
    """
    Recompute evidence_hash from the DB row by using the canonical payload fields.
    Assumes DB contains the CMR v1 columns. Ignores columns not in the canonical set.
    """
    canonical_fields = [
        "timestamp_start", "timestamp_end",
        "user_id", "session_id", "request_id",
        "engine_version", "contract_version",
        "git_commit", "host_id",
        "seed", "latency_ms",
        "contract_valid", "contract_fail_reason",
        "ua_spend", "delta_s", "delta_s_per_ua",
        "h_rigidity", "work_units",
        "prev_hash",
        "evidence_hash",
    ]

    payload: Dict[str, Any] = {}
    for f in canonical_fields:
        if f in row:
            payload[f] = row[f]

    # normalize contract_valid -> bool in hashing payload if your canonical hashing uses bool
    # if your canonical implementation hashes 0/1 as-is, comment out this block.
    if "contract_valid" in payload:
        payload["contract_valid"] = bool(payload["contract_valid"])

    payload["evidence_hash"] = ""  # ensure excluded
    return canonical_hash(payload)

def verify_chain(db: DB, max_rows: Optional[int] = None) -> Tuple[bool, str]:
    rows = fetch_chain(db, limit=max_rows)
    if not rows:
        return False, "Ledger vacío."

    # verify each row hash & chaining
    prev_eh: Optional[str] = None
    for i, row in enumerate(rows):
        eh = row.get("evidence_hash")
        ph = row.get("prev_hash")

        if eh is None:
            return False, f"Fila {i} sin evidence_hash."

        # chaining
        if i == 0:
            # first row may have NULL prev_hash; accept None/''
            if ph not in (None, "", "NULL"):
                # Accept if your system uses explicit genesis prev_hash, else fail:
                # return False, f"Genesis prev_hash inesperado: {ph}"
                pass
        else:
            if ph != prev_eh:
                return False, f"Ruptura de cadena en fila {i}: prev_hash={ph} != prev_evidence_hash={prev_eh}"

        # recompute hash
        recomputed = compute_row_hash_from_db_row(row)
        if recomputed != eh:
            return False, f"Evidence hash inválido en fila {i}: recomputed={recomputed} db={eh}"

        prev_eh = eh

    return True, f"OK: cadena íntegra ({len(rows)} filas verificadas)."


# -----------------------------
# Tamper test
# -----------------------------

def tamper_one_row(db: DB, row_id: int, field: str, new_value: Any) -> None:
    con = sqlite3.connect(db.path, timeout=30)
    try:
        con.execute("BEGIN IMMEDIATE")
        con.execute(f"UPDATE {db.table} SET {field}=? WHERE id=?", (new_value, row_id))
        con.commit()
    finally:
        con.close()


# -----------------------------
# Main: stress routine
# -----------------------------

def stress(db: DB, n: int, verify_every: int, engine_version: str, contract_version: str) -> None:
    # find last evidence_hash as prev
    con = sqlite3.connect(db.path)
    try:
        row = con.execute(f"SELECT evidence_hash FROM {db.table} ORDER BY id DESC LIMIT 1").fetchone()
        prev = row[0] if row else None
    finally:
        con.close()

    t0 = time.perf_counter()
    for i in range(1, n + 1):
        prev = insert_synthetic_event(db, prev, engine_version, contract_version)

        if verify_every > 0 and (i % verify_every == 0):
            ok, msg = verify_chain(db)
            if not ok:
                raise SystemExit(f"[FAIL] {msg}")
            print(f"[OK] {i}/{n} {msg}")

    dt = time.perf_counter() - t0
    print(f"[DONE] Inserted {n} events in {dt:.2f}s ({n/dt:.1f} events/s)")
    ok, msg = verify_chain(db)
    print(f"[FINAL] {msg}" if ok else f"[FINAL FAIL] {msg}")


def main() -> None:
    ap = argparse.ArgumentParser(description="CMR chain stress + verification")
    ap.add_argument("--db", required=True, help="Path to ua_ledger.sqlite")
    ap.add_argument("--table", default="ua_ledger")
    ap.add_argument("--stress", type=int, default=0, help="Insert N synthetic events")
    ap.add_argument("--verify-every", type=int, default=0, help="Verify chain every K inserts (0=only final)")
    ap.add_argument("--verify-only", action="store_true", help="Only verify current chain")
    ap.add_argument("--tamper", action="store_true", help="Tamper test: mutate one row and verify should fail")
    ap.add_argument("--tamper-id", type=int, default=1, help="Row id to tamper")
    ap.add_argument("--tamper-field", default="ua_spend", help="Field to mutate")
    ap.add_argument("--tamper-value", default="9999", help="New value (string; best-effort cast)")
    ap.add_argument("--engine-version", default="GahenaxCore-v1.0")
    ap.add_argument("--contract-version", default="GahenaxOutput-v1.0")
    args = ap.parse_args()

    db = DB(path=args.db, table=args.table)

    if not os.path.exists(db.path):
        raise SystemExit(f"DB no existe: {db.path}")
    if not table_exists(db):
        raise SystemExit(f"Tabla no existe: {db.table}")

    if args.verify_only:
        ok, msg = verify_chain(db)
        print(msg if ok else f"[FAIL] {msg}")
        raise SystemExit(0 if ok else 2)

    if args.tamper:
        # Best-effort cast
        v: Any = args.tamper_value
        if v.isdigit():
            v = int(v)
        else:
            try:
                v = float(v)
            except Exception:
                pass

        print(f"[TAMPER] Updating id={args.tamper_id} field={args.tamper_field} -> {v}")
        tamper_one_row(db, args.tamper_id, args.tamper_field, v)
        ok, msg = verify_chain(db)
        if ok:
            raise SystemExit("[FAIL] Tamper did NOT break chain (unexpected). Check canonical hashing fields.")
        print(f"[EXPECTED FAIL] {msg}")
        raise SystemExit(0)

    if args.stress > 0:
        stress(db, args.stress, args.verify_every, args.engine_version, args.contract_version)
        raise SystemExit(0)

    ap.print_help()


if __name__ == "__main__":
    main()
