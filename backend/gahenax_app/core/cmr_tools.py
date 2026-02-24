from __future__ import annotations

import sqlite3
import json
import hashlib
import os
import statistics
from dataclasses import dataclass, asdict
from typing import Dict, Any, List, Optional, Tuple
from datetime import datetime, timezone
from pathlib import Path

from .cmr import CMR, CMRConfig, canonical_hash

@dataclass
class Snapshot:
    timestamp: str
    row_count: int
    head_hash: Optional[str]
    tail_hash: Optional[str]
    pass_rate: float
    latency_p50: float
    latency_p95: float
    ua_median: float
    dsua_median: float
    git_commit: str
    snapshot_hash: str
    prompt_version: Optional[str] = None

class CMRTools:
    """
    Operational toolset for CMR (Canonical Measurement Recorder).
    Handles verification, snapshots, and FCD gate evaluations.
    """

    def __init__(self, cfg: CMRConfig):
        self.cfg = cfg

    def verify_integrity(self) -> Tuple[int, str]:
        """
        Full chain verification.
        Exit codes: 0 (OK), 2 (FAIL_CHAIN), 3 (FAIL_HASH)
        """
        con = sqlite3.connect(self.cfg.db_path)
        con.row_factory = sqlite3.Row
        try:
            rows = con.execute(f"SELECT * FROM {self.cfg.table} ORDER BY id ASC").fetchall()
            if not rows:
                return 0, "Ledger empty"

            prev_hash = None
            for i, row in enumerate(rows):
                # 1. Chain Check
                if i > 0 and row["prev_hash"] != prev_hash:
                    return 2, f"CHAIN_BREAK at row {row['id']}: prev_hash mismatch"
                
                # 2. Hash Check
                # Reconstruct payload for re-hashing
                payload = {
                    "timestamp_start": row["timestamp_start"],
                    "timestamp_end": row["timestamp_end"],
                    "user_id": row["user_id"],
                    "session_id": row["session_id"],
                    "request_id": row["request_id"],
                    "engine_version": row["engine_version"],
                    "contract_version": row["contract_version"],
                    "prompt_version": row["prompt_version"],
                    "input_fingerprint": row["input_fingerprint"],
                    "git_commit": row["git_commit"],
                    "host_id": row["host_id"],
                    "seed": row["seed"],
                    "latency_ms": float(row["latency_ms"]),
                    "contract_valid": bool(row["contract_valid"]),
                    "contract_fail_reason": row["contract_fail_reason"],
                    "ua_spend": int(row["ua_spend"]),
                    "delta_s": row["delta_s"],
                    "delta_s_per_ua": row["delta_s_per_ua"],
                    "h_rigidity": row["h_rigidity"],
                    "work_units": int(row["work_units"]),
                    "prev_hash": row["prev_hash"],
                    "evidence_hash": ""
                }
                recalc = canonical_hash(payload)
                if recalc != row["evidence_hash"]:
                    return 3, f"HASH_CORRUPTION at row {row['id']}: recalculated hash mismatch"

                prev_hash = row["evidence_hash"]

            return 0, f"OK: Integrity verified for {len(rows)} records"
        except Exception as e:
            return 4, f"SYSTEM_ERROR: {str(e)}"
        finally:
            con.close()

    def generate_snapshot(self) -> Snapshot:
        """Generates a signed summary of the current ledger state."""
        con = sqlite3.connect(self.cfg.db_path)
        con.row_factory = sqlite3.Row
        try:
            rows = con.execute(f"SELECT * FROM {self.cfg.table} ORDER BY id ASC").fetchall()
            if not rows:
                raise ValueError("Cannot snapshot empty ledger")
            
            latencies = [r["latency_ms"] for r in rows]
            uas = [r["ua_spend"] for r in rows]
            dsuas = [r["delta_s_per_ua"] for r in rows if r["delta_s_per_ua"] is not None]
            pass_rate = sum(1 for r in rows if r["contract_valid"]) / len(rows)

            snap_data = {
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "row_count": len(rows),
                "head_hash": rows[0]["evidence_hash"],
                "tail_hash": rows[-1]["evidence_hash"],
                "pass_rate": pass_rate,
                "latency_p50": statistics.median(latencies) if latencies else 0,
                "latency_p95": sorted(latencies)[int(len(latencies)*0.95)] if latencies else 0,
                "ua_median": statistics.median(uas) if uas else 0,
                "dsua_median": statistics.median(dsuas) if dsuas else 0,
                "git_commit": os.getenv("GIT_COMMIT", "unknown"),
                "prompt_version": rows[-1]["prompt_version"] if rows else None
            }
            
            # Sign the snapshot data
            blob = json.dumps(snap_data, sort_keys=True).encode("utf-8")
            snap_data["snapshot_hash"] = hashlib.sha256(blob).hexdigest()
            
            return Snapshot(**snap_data)
        finally:
            con.close()

    def evaluate_gates(self, window_n: int = 100) -> Tuple[bool, List[str]]:
        """
        Hard FCD Gates evaluation for CI/CD usage.
        Returns (Pass/Fail, List of violations)
        """
        con = sqlite3.connect(self.cfg.db_path)
        con.row_factory = sqlite3.Row
        try:
            rows = con.execute(f"SELECT * FROM {self.cfg.table} ORDER BY id DESC LIMIT ?", (window_n,)).fetchall()
            if not rows:
                return False, ["No data to evaluate"]

            violations = []
            
            # Gate A2: Contract 100% Correctness
            pass_rate = sum(1 for r in rows if r["contract_valid"]) / len(rows)
            if pass_rate < 1.0:
                violations.append(f"DEATH_CONTRACT: Pass-rate {pass_rate:.2%} < 100%")

            # Gate A2: P95 Latency Stability
            lats = [r["latency_ms"] for r in rows]
            p95 = sorted(lats)[int(len(lats)*0.95)]
            if p95 > 1000.0: # 1 second hard gate for governed cycles
                violations.append(f"REGRESSION_LATENCY: P95 {p95:.2f}ms exceeds 1000ms threshold")

            # Gate A3: Structural Rigidity
            h_vals = [r["h_rigidity"] for r in rows if r["h_rigidity"] is not None]
            if h_vals:
                avg_h = sum(h_vals) / len(h_vals)
                if avg_h > 1e-10: # Rigidity loss threshold
                    violations.append(f"RIGIDITY_LOSS: Average H {avg_h:.2e} > 1e-10")

            return len(violations) == 0, violations
        finally:
            con.close()
