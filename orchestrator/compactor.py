# orchestrator/compactor.py
"""
Ledger compactor — secondary utility, NOT core.

Converts ledger.jsonl → merged_clean.jsonl by:
  1. Reading all events
  2. Dedup by canonical payload hash
  3. Emitting clean payloads only

This is a "polisher", not the heart. The ledger is always
the source of truth; this produces a clean derivative.
"""
from __future__ import annotations
import json
from typing import Dict, Any
from orchestrator.contracts import sha256_json


def compact(ledger_path: str, out_path: str) -> Dict[str, int]:
    """
    Read ledger, deduplicate by payload hash, write clean output.

    Returns:
        {"kept": int, "dropped": int}
    """
    seen: set[str] = set()
    kept = 0
    dropped = 0

    with open(ledger_path, "r", encoding="utf-8") as fin, \
         open(out_path, "w", encoding="utf-8") as fout:
        for line in fin:
            line = line.strip()
            if not line:
                continue
            obj = json.loads(line)
            payload = obj.get("payload", {})
            if not isinstance(payload, dict):
                continue
            h = sha256_json(payload)
            if h in seen:
                dropped += 1
                continue
            seen.add(h)
            fout.write(
                json.dumps(payload, separators=(",", ":"), ensure_ascii=True)
                + "\n"
            )
            kept += 1

    return {"kept": kept, "dropped": dropped}


if __name__ == "__main__":
    import sys

    ledger = sys.argv[1] if len(sys.argv) > 1 else "run_latido/ledger.jsonl"
    output = sys.argv[2] if len(sys.argv) > 2 else "run_latido/merged_clean.jsonl"

    stats = compact(ledger, output)
    print(f"Compacted: {stats}")
