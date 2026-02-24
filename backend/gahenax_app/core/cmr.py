from __future__ import annotations

import hashlib
import json
import os
import sqlite3
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Dict, Optional, Tuple


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def canonical_hash(payload: Dict[str, Any]) -> str:
    canon = dict(payload)
    canon.pop("evidence_hash", None)
    blob = json.dumps(canon, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(blob).hexdigest()


@dataclass
class CMRConfig:
    db_path: str = "ua_ledger.sqlite"
    table: str = "ua_ledger"
    chain_hash: bool = True  # add prev_hash chaining


class CMR:
    """
    Canonical Measurement Recorder (append-only).
    Captures falsifiable evidence for each engine run.
    """

    def __init__(self, cfg: CMRConfig):
        self.cfg = cfg
        self._init_db()

    def _init_db(self) -> None:
        con = sqlite3.connect(self.cfg.db_path)
        try:
            con.execute(f"""
            CREATE TABLE IF NOT EXISTS {self.cfg.table} (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp_start TEXT NOT NULL,
                timestamp_end TEXT NOT NULL,
                user_id TEXT NOT NULL,
                session_id TEXT NOT NULL,
                request_id TEXT NOT NULL,

                engine_version TEXT NOT NULL,
                contract_version TEXT NOT NULL,
                prompt_version TEXT,
                input_fingerprint TEXT,
                git_commit TEXT,
                host_id TEXT,

                seed INTEGER,
                latency_ms REAL NOT NULL,

                contract_valid INTEGER NOT NULL,
                contract_fail_reason TEXT,

                ua_spend INTEGER NOT NULL,
                delta_s REAL,
                delta_s_per_ua REAL,
                h_rigidity REAL,
                work_units INTEGER NOT NULL,

                prev_hash TEXT,
                evidence_hash TEXT NOT NULL
            )
            """)
            con.execute(f"CREATE INDEX IF NOT EXISTS idx_{self.cfg.table}_time ON {self.cfg.table}(timestamp_end)")
            con.execute(f"CREATE INDEX IF NOT EXISTS idx_{self.cfg.table}_fingerprint ON {self.cfg.table}(input_fingerprint)")
            con.commit()
        finally:
            con.close()

    def _last_hash(self) -> Optional[str]:
        if not self.cfg.chain_hash:
            return None
        con = sqlite3.connect(self.cfg.db_path)
        try:
            row = con.execute(
                f"SELECT evidence_hash FROM {self.cfg.table} ORDER BY id DESC LIMIT 1"
            ).fetchone()
            return row[0] if row else None
        finally:
            con.close()

    def record_run(
        self,
        *,
        user_id: str,
        session_id: str,
        request_id: str,
        engine_version: str,
        contract_version: str,
        prompt_version: Optional[str] = None,
        input_fingerprint: Optional[str] = None,
        seed: Optional[int],
        latency_ms: float,
        contract_valid: bool,
        contract_fail_reason: Optional[str],
        ua_spend: int,
        delta_s: Optional[float],
        delta_s_per_ua: Optional[float],
        h_rigidity: Optional[float],
        work_units: int,
        timestamp_start: str,
        timestamp_end: str,
        git_commit: Optional[str] = None,
        host_id: Optional[str] = None,
    ) -> str:
        prev = self._last_hash()

        payload = {
            "timestamp_start": timestamp_start,
            "timestamp_end": timestamp_end,
            "user_id": user_id,
            "session_id": session_id,
            "request_id": request_id,
            "engine_version": engine_version,
            "contract_version": contract_version,
            "prompt_version": prompt_version,
            "input_fingerprint": input_fingerprint,
            "git_commit": git_commit,
            "host_id": host_id,
            "seed": seed,
            "latency_ms": float(latency_ms),
            "contract_valid": bool(contract_valid),
            "contract_fail_reason": contract_fail_reason,
            "ua_spend": int(ua_spend),
            "delta_s": delta_s,
            "delta_s_per_ua": delta_s_per_ua,
            "h_rigidity": h_rigidity,
            "work_units": int(work_units),
            "prev_hash": prev,
            "evidence_hash": "",
        }
        payload["evidence_hash"] = canonical_hash(payload)

        con = sqlite3.connect(self.cfg.db_path)
        try:
            con.execute(
                f"""
                INSERT INTO {self.cfg.table} (
                    timestamp_start, timestamp_end, user_id, session_id, request_id,
                    engine_version, contract_version, prompt_version, input_fingerprint,
                    git_commit, host_id,
                    seed, latency_ms,
                    contract_valid, contract_fail_reason,
                    ua_spend, delta_s, delta_s_per_ua, h_rigidity, work_units,
                    prev_hash, evidence_hash
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    payload["timestamp_start"], payload["timestamp_end"],
                    payload["user_id"], payload["session_id"], payload["request_id"],
                    payload["engine_version"], payload["contract_version"],
                    payload["prompt_version"], payload["input_fingerprint"],
                    payload["git_commit"], payload["host_id"],
                    payload["seed"], payload["latency_ms"],
                    1 if payload["contract_valid"] else 0, payload["contract_fail_reason"],
                    payload["ua_spend"], payload["delta_s"], payload["delta_s_per_ua"],
                    payload["h_rigidity"], payload["work_units"],
                    payload["prev_hash"], payload["evidence_hash"],
                )
            )
            con.commit()
        finally:
            con.close()

        return payload["evidence_hash"]
