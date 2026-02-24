# orchestrator/contracts.py
"""
Typed contracts for the Single-Orchestrator architecture.
Every result entering the system passes through these validators.

Laws:
  - No payload enters the ledger without schema validation.
  - No duplicate payload enters (hash-based dedup).
  - Every event is immutable and hashable.
"""
from __future__ import annotations
from dataclasses import dataclass, asdict, field
from typing import Any, Dict, Optional, Literal, List
import json
import hashlib
from datetime import datetime

JobStatus = Literal["PENDING", "RUNNING", "DONE", "FAILED"]
AcceptVerdict = Literal["ACCEPTED", "REJECTED_SCHEMA", "REJECTED_TOL", "REJECTED_DUP"]


def now_iso() -> str:
    """UTC-aware ISO timestamp, second precision."""
    return datetime.now().astimezone().isoformat(timespec="seconds")


def sha256_json(obj: Dict[str, Any]) -> str:
    """Deterministic SHA-256 of a JSON-serializable dict."""
    b = json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("utf-8")
    return "sha256:" + hashlib.sha256(b).hexdigest()


@dataclass(frozen=True)
class Job:
    """Immutable work unit dispatched to a worker."""
    job_id: str
    t_start: float
    t_end: float
    stride: float
    attempts: int = 0
    status: JobStatus = "PENDING"
    last_error: Optional[str] = None


@dataclass(frozen=True)
class ResultPayload:
    """
    Canonical schema for a mined result.
    Adjust fields to match your real miner output.
    """
    t: float
    root_val: float
    meta: Dict[str, Any]  # e.g. iterations, method, bracket, etc.

    @staticmethod
    def validate(d: Dict[str, Any]) -> bool:
        """Strict schema gate. Returns False on any violation."""
        if not isinstance(d, dict):
            return False
        if "t" not in d or "root_val" not in d or "meta" not in d:
            return False
        if not isinstance(d["meta"], dict):
            return False
        try:
            float(d["t"])
            float(d["root_val"])
        except (ValueError, TypeError):
            return False
        return True


@dataclass(frozen=True)
class LedgerEvent:
    """
    Immutable, hashable ledger entry.
    The hash covers everything EXCEPT itself (self-referential integrity).
    """
    run_id: str
    worker_id: int
    job_id: str
    seq: int
    payload: Dict[str, Any]
    ts: str
    hash: str

    @staticmethod
    def from_parts(
        run_id: str,
        worker_id: int,
        job_id: str,
        seq: int,
        payload: Dict[str, Any],
    ) -> "LedgerEvent":
        """Factory: builds event and computes integrity hash."""
        base = {
            "run_id": run_id,
            "worker_id": worker_id,
            "job_id": job_id,
            "seq": seq,
            "payload": payload,
            "ts": now_iso(),
        }
        h = sha256_json(base)
        return LedgerEvent(**base, hash=h)


def to_jsonl_line(obj: Any) -> str:
    """Serialize dataclass or dict to a single JSONL line."""
    if hasattr(obj, "__dataclass_fields__"):
        obj = asdict(obj)
    return json.dumps(obj, separators=(",", ":"), ensure_ascii=True)
