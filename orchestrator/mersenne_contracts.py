# orchestrator/mersenne_contracts.py
"""
Mersenne-specific contracts for the Single-Orchestrator architecture.
This defines the schema for Lucas-Lehmer certification events.
"""
from __future__ import annotations
from dataclasses import dataclass, asdict
from typing import Any, Dict, Optional
import hashlib
from .contracts import Job, ResultPayload

@dataclass(frozen=True)
class MersenneJob(Job):
    """Job definition for Mersenne exponent search."""
    p_start: int = 0
    p_end: int = 0
    # Overriding Job just to be explicit about p_start/p_end if needed
    # but Job already has t_start/t_end which can be p_start/p_end.

@dataclass(frozen=True)
class MersenneResultPayload:
    """
    Canonical schema for a Mersenne certification result.
    Matches the 'mersenne-v1' schema.
    """
    p: int
    residue_hash: str
    roundoff_max: float
    engine_version: str
    wall_time: float
    is_prime: bool
    meta: Dict[str, Any]

    @staticmethod
    def validate(d: Dict[str, Any]) -> bool:
        """Strict schema gate for Mersenne results."""
        if not isinstance(d, dict):
            return False
        required = {"p", "residue_hash", "roundoff_max", "engine_version", "wall_time", "is_prime", "meta"}
        if not all(k in d for k in required):
            return False
        try:
            int(d["p"])
            float(d["roundoff_max"])
            float(d["wall_time"])
            bool(d["is_prime"])
            if not isinstance(d["residue_hash"], str) or len(d["residue_hash"]) != 64:
                return False
        except (ValueError, TypeError):
            return False
        return True
