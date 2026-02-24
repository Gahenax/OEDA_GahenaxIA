# Orchestrator — Single-Orchestrator / Multi-Worker / Append-only Ledger

## Architecture

```
┌────────────────────────────────────────────────────────────┐
│                   ORCHESTRATOR (Single Writer)             │
│                                                            │
│  ┌──────────┐   ┌──────────┐   ┌──────────────────────┐   │
│  │ Scheduler│──▶│ Reducer  │──▶│  Append-Only Ledger  │   │
│  │ (Jobs)   │   │ (Accept) │   │  (ledger.jsonl)      │   │
│  └──────────┘   └──────────┘   └──────────────────────┘   │
│       │              ▲              │                      │
│       │              │              ▼                      │
│       │         ┌────┴────┐   ┌──────────┐                │
│       │         │  Queue  │   │  State   │                │
│       │         └────┬────┘   │  (.json) │                │
│       │              │        └──────────┘                │
└───────┼──────────────┼────────────────────────────────────┘
        │              │
        ▼              │
   ┌─────────┐    ┌─────────┐    ┌─────────┐
   │Worker 0 │    │Worker 1 │    │Worker N │
   │ (dumb)  │    │ (dumb)  │    │ (dumb)  │
   └─────────┘    └─────────┘    └─────────┘
```

## Core Invariants

1. **Single Writer or Die**: Only the orchestrator writes to `ledger.jsonl`. Workers NEVER touch persistence.
2. **Workers Don't Write Canonical Persistence**: They compute and push results to a queue.
3. **Dedup is Not Core**: Hash-based dedup is a gate inside the orchestrator, not a crutch. The compactor is a separate utility.
4. **Every Result Passes Contract + Tolerance + Hash**: No exceptions.

## Files

| File | Purpose |
|---|---|
| `contracts.py` | Typed dataclasses (Job, ResultPayload, LedgerEvent), validators, SHA-256 hashing |
| `orchestrator.py` | Single-writer core: lock, state, ledger, acceptance pipeline, reducer loop |
| `worker_entry.py` | Worker stub — replace `compute_zero_candidates()` with your real miner |
| `run_orchestrator.py` | Execution harness: 1 orchestrator + N workers via multiprocessing |
| `compactor.py` | Secondary utility: `ledger.jsonl` → `merged_clean.jsonl` (dedup + clean) |

## Quick Start

```bash
# From the Tesis root directory:
python -m orchestrator.run_orchestrator
```

## Resume

If the process crashes:
1. The lock file (`run_latido/orchestrator.lock`) must be manually deleted if the process didn't clean up.
2. On restart, the orchestrator replays `ledger.jsonl` to reconstruct the dedup hash set.
3. Jobs marked `RUNNING` in `state.json` are NOT automatically retried — they stay as-is. (Future: add a "stale RUNNING" detector.)

## Compactor

```bash
# Generate clean merged output from ledger:
python -m orchestrator.compactor run_latido/ledger.jsonl run_latido/merged_clean.jsonl
```

## Connecting Your Real Miner

Edit `worker_entry.py` and replace the stub `compute_zero_candidates()` with your actual zero-finding logic. The function must return:

```python
[
    {"t": 5000.123, "root_val": 1.2e-12, "meta": {"method": "secant", "iters": 8}},
    {"t": 5000.456, "root_val": -3.4e-13, "meta": {"method": "secant", "iters": 11}},
    ...
]
```

The orchestrator validates schema, checks `|root_val| < eps_root`, and deduplicates by canonical hash. The worker does NOT need to worry about any of this.

## Migration from Legacy

If you have an existing `merged_results.jsonl`:
1. **Do NOT use it as source of truth.**
2. Import it to the ledger once via a migration script, or keep it as legacy.
3. From now on, `ledger.jsonl` is truth, and the clean merged file comes from the compactor.

---

**Architecture**: Single-Orchestrator / Multi-Worker / Append-only Ledger  
**Date**: 2026-02-20  
**Status**: OPERATIONAL ✅
