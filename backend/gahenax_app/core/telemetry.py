import sqlite3
import json
import hashlib
import time
from datetime import datetime, timezone
from typing import Any, Dict, Optional
from pydantic import BaseModel

class LedgerRecord(BaseModel):
    case_id: str
    timestamp: str
    engine_version: str
    contract_version: str
    seed: int
    latency_ms: int
    contract_valid: bool
    ua_spend: int
    delta_s: Optional[float] = None
    delta_s_per_ua: Optional[float] = None
    h_rigidity: Optional[float] = None
    work_units: int
    evidence_hash: str

def compute_evidence_hash(payload: Dict[str, Any]) -> str:
    canon = dict(payload)
    canon.pop("evidence_hash", None)
    blob = json.dumps(canon, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(blob).hexdigest()

class UALedgerDB:
    def __init__(self, db_path: str = "ua_ledger.sqlite"):
        self.db_path = db_path
        self._init()

    def _init(self) -> None:
        con = sqlite3.connect(self.db_path)
        try:
            con.execute("""
                CREATE TABLE IF NOT EXISTS ua_ledger (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT NOT NULL,
                    user_id TEXT NOT NULL,
                    session_id TEXT NOT NULL,
                    request_id TEXT NOT NULL,
                    engine_version TEXT NOT NULL,
                    contract_version TEXT NOT NULL,
                    ua_spend INTEGER NOT NULL,
                    delta_s REAL,
                    delta_s_per_ua REAL,
                    latency_ms INTEGER NOT NULL,
                    contract_valid INTEGER NOT NULL,
                    h_rigidity REAL,
                    work_units INTEGER NOT NULL,
                    evidence_hash TEXT NOT NULL
                )
            """)
            con.commit()
        finally: con.close()

    def append(self, *, user_id: str, session_id: str, request_id: str, rec: LedgerRecord) -> None:
        con = sqlite3.connect(self.db_path)
        try:
            con.execute("""
                INSERT INTO ua_ledger (
                    timestamp, user_id, session_id, request_id, engine_version, contract_version,
                    ua_spend, delta_s, delta_s_per_ua, latency_ms, contract_valid, h_rigidity, work_units, evidence_hash
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (rec.timestamp, user_id, session_id, request_id, rec.engine_version, rec.contract_version,
                  rec.ua_spend, rec.delta_s, rec.delta_s_per_ua, rec.latency_ms, 1 if rec.contract_valid else 0,
                  rec.h_rigidity, rec.work_units, rec.evidence_hash))
            con.commit()
        finally: con.close()
