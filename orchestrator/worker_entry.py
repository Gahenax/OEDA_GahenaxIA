# orchestrator/worker_entry.py
"""
Worker entry point — "dumb" producer.

The worker computes results but NEVER writes to the canonical ledger.
It pushes payloads to the orchestrator's queue. The orchestrator
decides acceptance, dedup, and persistence.

TODO: Replace compute_zero_candidates() with your real miner logic.
"""
from __future__ import annotations
from typing import Dict, Any, List
import random
import time


def compute_zero_candidates(
    t_start: float,
    t_end: float,
    stride: float,
) -> List[Dict[str, Any]]:
    """
    Stub miner — replace with your real zero-finding engine.

    Must return payloads in canonical schema:
      {"t": float, "root_val": float, "meta": {...}}

    The orchestrator validates schema + tolerance + uniqueness.
    The worker does NOT need to worry about dedup.
    """
    out: List[Dict[str, Any]] = []
    t = t_start
    while t < t_end:
        # Placeholder: small root_val means "acceptable zero"
        root_val = (random.random() - 0.5) * 1e-11
        out.append({
            "t": float(t),
            "root_val": float(root_val),
            "meta": {"method": "stub", "iters": 12},
        })
        t += stride
        time.sleep(0.001)  # simulate compute cost
    return out
