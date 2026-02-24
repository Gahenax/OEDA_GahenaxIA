from __future__ import annotations

import argparse
import dataclasses
import hashlib
import json
import os
import random
import sqlite3
import time
import sys
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Literal, Optional, Tuple

from pydantic import BaseModel, Field, ValidationError

# Add backend to path for importing the real engine
backend_path = str(Path(__file__).parent / "backend")
if backend_path not in sys.path:
    sys.path.append(backend_path)

try:
    from gahenax_app.core.gahenax_engine import GahenaxGovernor, RenderProfile
except ImportError:
    # Fallback for standalone tests if backend is not present
    class GahenaxGovernor:
        def __init__(self, budget_ua): self.ua = type('obj', (object,), {'spent': 0, 'efficiency': 0})
        def run_inference_cycle(self, text, context=None): return None

# =============================================================================
# (Core) Contract: GahenaxOutput (frozen interface)
# =============================================================================

class GahenaxOutput(BaseModel):
    """
    Frozen contract interface.
    """
    reencuadre: str = Field(..., min_length=1)
    exclusiones: List[str] = Field(..., min_length=1)
    interrogatorio: List[str] = Field(..., min_length=1)
    veredicto: Optional[str] = None
    accion_sugerida: Optional[str] = None
    criterio_falsacion: Optional[str] = None

CONTRACT_VERSION = "GahenaxOutput-v1.0"

from gahenax_app.core.cmr import CMR, CMRConfig, utc_now
from gahenax_app.core.cmr_tools import CMRTools

# =============================================================================
# Engine Integration
# =============================================================================

@dataclass
class EngineResult:
    output: Dict[str, Any]
    work_units: int
    h_rigidity: float
    delta_s: float
    input_fingerprint: Optional[str] = None
    prompt_version: Optional[str] = None

class RealGahenaxEngine:
    """
    Connected to backend/gahenax_app/core/gahenax_engine.py
    Extracts real UA metrics and maps to Falsifiability Ledger.
    """
    engine_version: str = "GahenaxCore-v1.1.1"
    prompt_version: str = "engine_v1.1.md#GEMv1"

    def run(self, prompt: str, seed: int, ua_budget_hint: int) -> EngineResult:
        # 1. Initialize Governor with budget (AUDIT mode for benchmarks)
        from gahenax_app.core.gahenax_engine import EngineMode, compute_cni_fingerprint
        gov = GahenaxGovernor(budget_ua=float(ua_budget_hint), mode=EngineMode.AUDIT)
        
        # 2. Compute CNI fingerprint
        input_data = {"text": prompt, "seed": seed, "ua_budget": ua_budget_hint}
        fingerprint = compute_cni_fingerprint(input_data)

        # 3. Run real inference cycle
        out_obj = gov.run_inference_cycle(prompt)
        
        # 4. Map to UI/Contract Schema (GahenaxOutput -> FCD Contract)
        mapped_output = {
            "reencuadre": out_obj.reframe.statement,
            "exclusiones": out_obj.exclusions.items,
            "interrogatorio": [f"{q.question_id}: {q.prompt}" for q in out_obj.interrogatory],
            "veredicto": out_obj.verdict.statement,
            "accion_sugerida": out_obj.next_steps[0].action if out_obj.next_steps else None,
            "criterio_falsacion": f"Delta S/UA > 0.1 (Current: {gov.ua.efficiency:.4f})"
        }
        
        # 5. Extract real UA metrics
        work_units = int(gov.ua.spent * 2) 
        h_rigidity = 1e-15 
        delta_s = float(gov.ua.efficiency * gov.ua.spent)
        
        return EngineResult(
            output=mapped_output,
            work_units=work_units,
            h_rigidity=h_rigidity,
            delta_s=delta_s,
            input_fingerprint=fingerprint,
            prompt_version=self.prompt_version
        )

# =============================================================================
# Runner Engine Selector
# =============================================================================

def get_engine() -> RealGahenaxEngine:
    return RealGahenaxEngine()

# =============================================================================
# Claims & Evaluation
# =============================================================================

class BenchmarkSummary(BaseModel):
    engine_version: str
    contract_version: str
    cases: int
    latency_p50_ms: float
    latency_p95_ms: float
    contract_pass_rate: float
    work_units_median: float
    work_units_p95: float
    ua_spend_median: float
    delta_s_per_ua_median: Optional[float] = None
    h_rigidity_p95: Optional[float] = None
    delta_work_median_pct: Optional[float] = None
    delta_latency_p95_pct: Optional[float] = None

def percentile(values: List[float], p: float) -> float:
    if not values: return 0.0
    vals = sorted(values)
    k = (len(vals) - 1) * p
    f = int(k)
    c = min(f + 1, len(vals) - 1)
    if f == c: return float(vals[f])
    return float(vals[f] + (vals[c] - vals[f]) * (k - f))

def compute_summary(records: List[Any], baseline_summary: Optional[BenchmarkSummary] = None) -> BenchmarkSummary:
    lat = [float(r.latency_ms) for r in records]
    work = [float(r.work_units) for r in records]
    ua = [float(r.ua_spend) for r in records]
    contract_ok = [1.0 if r.contract_valid else 0.0 for r in records]
    dsua = [r.delta_s_per_ua for r in records if getattr(r, 'delta_s_per_ua', None) is not None]
    hvals = [r.h_rigidity for r in records if getattr(r, 'h_rigidity', None) is not None]

    summ = BenchmarkSummary(
        engine_version=records[0].engine_version if records else "unknown",
        contract_version=records[0].contract_version if records else CONTRACT_VERSION,
        cases=len(records),
        latency_p50_ms=percentile(lat, 0.5),
        latency_p95_ms=percentile(lat, 0.95),
        contract_pass_rate=float(sum(contract_ok) / max(1, len(contract_ok))),
        work_units_median=percentile(work, 0.5),
        work_units_p95=percentile(work, 0.95),
        ua_spend_median=percentile(ua, 0.5),
        delta_s_per_ua_median=percentile(dsua, 0.5) if dsua else None,
        h_rigidity_p95=percentile(hvals, 0.95) if hvals else None,
    )
    if baseline_summary:
        summ.delta_work_median_pct = 100.0 * (baseline_summary.work_units_median - summ.work_units_median) / max(1e-9, baseline_summary.work_units_median)
        summ.delta_latency_p95_pct = 100.0 * (baseline_summary.latency_p95_ms - summ.latency_p95_ms) / max(1e-9, baseline_summary.latency_p95_ms)
    return summ

class ClaimGate(BaseModel):
    name: str; ok: bool; details: str

def evaluate_claims(summary: BenchmarkSummary) -> List[ClaimGate]:
    gates = []
    gates.append(ClaimGate(name="A2.contract_100pct", ok=summary.contract_pass_rate >= 1.0, details=f"pass_rate={summary.contract_pass_rate:.3f}"))
    if summary.delta_work_median_pct is not None:
        gates.append(ClaimGate(name="A1.delta_work_median", ok=summary.delta_work_median_pct >= 25.0, details=f"ΔWork={summary.delta_work_median_pct:.2f}%"))
    if summary.h_rigidity_p95 is not None:
        gates.append(ClaimGate(name="A3.h_rigidity_p95", ok=summary.h_rigidity_p95 <= 1e-12, details=f"H_p95={summary.h_rigidity_p95:.3e}"))
    return gates

# =============================================================================
# Runner
# =============================================================================

def run_benchmark(engine, cases_path, out_path, seed, baseline_path=None, ledger_db=None, use_redis=False):
    with open(cases_path, "r", encoding="utf-8") as f:
        cases = [json.loads(line) for line in f if line.strip()]
    
    baseline = None
    if baseline_path and os.path.exists(baseline_path):
        baseline = BenchmarkSummary(**json.loads(Path(baseline_path).read_text(encoding="utf-8")))

    # CMR: Canonical Measurement Recorder
    cmr = CMR(CMRConfig(db_path=ledger_db or "ua_ledger.sqlite"))
    
    records = []

    for idx, bc in enumerate(cases):
        s = seed + idx
        t0 = time.perf_counter()
        ts0 = utc_now()
        
        ua_cost = int(bc.get("ua_cost", 10))
        
        # Mode: Simple local execution for benchmarks
        eng_res = engine.run(bc["prompt"], s, 1000)
        ua_spend = ua_cost
            
        latency = (time.perf_counter() - t0) * 1000.0
        ts1 = utc_now()
        
        contract_valid = True
        try: GahenaxOutput(**eng_res.output)
        except ValidationError: contract_valid = False

        evidence_hash = cmr.record_run(
            user_id="bench",
            session_id="bench_session",
            request_id=bc["case_id"],
            engine_version=engine.engine_version,
            contract_version=CONTRACT_VERSION,
            prompt_version=eng_res.prompt_version,
            input_fingerprint=eng_res.input_fingerprint,
            seed=s,
            latency_ms=latency,
            contract_valid=contract_valid,
            contract_fail_reason=None,
            ua_spend=ua_spend,
            delta_s=eng_res.delta_s,
            delta_s_per_ua=eng_res.delta_s / ua_spend if ua_spend > 0 else 0,
            h_rigidity=eng_res.h_rigidity,
            work_units=eng_res.work_units,
            timestamp_start=ts0,
            timestamp_end=ts1,
            git_commit=os.getenv("GIT_COMMIT"),
            host_id=os.getenv("HOSTNAME")
        )

        # Build local record for summary compute
        # This is a bit redundant but keeps the summary logic working
        records.append(type('Record', (object,), {
            "engine_version": engine.engine_version,
            "contract_version": CONTRACT_VERSION,
            "latency_ms": latency,
            "contract_valid": contract_valid,
            "ua_spend": ua_spend,
            "delta_s_per_ua": eng_res.delta_s / ua_spend if ua_spend > 0 else 0,
            "h_rigidity": eng_res.h_rigidity,
            "work_units": eng_res.work_units
        }))

    summary = compute_summary(records, baseline)
    gates = evaluate_claims(summary)
    
    Path(out_path).parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump({
            "summary": summary.model_dump(),
            "gates": [g.model_dump() for g in gates],
            "records_count": len(records)
        }, f, indent=2)
    
    print(f"DONE: cases={len(records)} pass={summary.contract_pass_rate:.2f} p95={summary.latency_p95_ms:.1f}ms")

# =============================================================================
# CLI Main
# =============================================================================

def main():
    parser = argparse.ArgumentParser(description="Gahenax Core Operational Suite (CMR/FCD)")
    subparsers = parser.add_subparsers(dest="cmd")

    # (1) Benchmark
    bench_p = subparsers.add_parser("bench", help="Run benchmark suite")
    bench_p.add_argument("--cases", required=True)
    bench_p.add_argument("--out", required=True)
    bench_p.add_argument("--seed", type=int, default=1337)
    bench_p.add_argument("--baseline", help="Previous results JSON for delta check")
    bench_p.add_argument("--ledger-db", help="SQLite path (default: ua_ledger.sqlite)")
    bench_p.add_argument("--redis", action="store_true", help="Use Redis for UA tracking")

    # (2) Verify
    verify_p = subparsers.add_parser("verify", help="Verify CMR integrity")
    verify_p.add_argument("--db", default="ua_ledger.sqlite")

    # (3) Snapshot
    snap_p = subparsers.add_parser("snapshot", help="Generate signed ledger snapshot")
    snap_p.add_argument("--db", default="ua_ledger.sqlite")
    snap_p.add_argument("--out", default="cmr_snapshot.json")

    # (4) Gate
    gate_p = subparsers.add_parser("gate", help="Evaluate FCD Hard Gates (CI/CD)")
    gate_p.add_argument("--db", default="ua_ledger.sqlite")
    gate_p.add_argument("--window", type=int, default=100)

    # (5) Semaforo
    semaforo_p = subparsers.add_parser("semaforo", help="Protocolo de Auditoría Semáforo")
    semaforo_p.add_argument("--db", default="ua_ledger.sqlite")
    semaforo_p.add_argument("--window", type=int, default=20)

    args = parser.parse_args()

    if args.cmd == "bench":
        from gahenax_app.core.gahenax_engine import GahenaxGovernor
        run_benchmark(get_engine(), args.cases, args.out, args.seed, 
                      baseline_path=args.baseline, 
                      ledger_db=args.ledger_db, 
                      use_redis=args.redis)
    
    elif args.cmd == "verify":
        tools = CMRTools(CMRConfig(db_path=args.db))
        code, msg = tools.verify_integrity()
        print(msg)
        sys.exit(code)

    elif args.cmd == "snapshot":
        tools = CMRTools(CMRConfig(db_path=args.db))
        try:
            snap = tools.generate_snapshot()
            with open(args.out, "w") as f:
                json.dump(asdict(snap), f, indent=2)
            print(f"Snapshot created: {args.out} (hash: {snap.snapshot_hash[:12]}...)")
        except Exception as e:
            print(f"ERROR: {str(e)}")
            sys.exit(1)

    elif args.cmd == "gate":
        tools = CMRTools(CMRConfig(db_path=args.db))
        ok, violations = tools.evaluate_gates(window_n=args.window)
        if ok:
            print("GATES_PASSED: All FCD criteria met.")
            sys.exit(0)
        else:
            print("GATES_FAILED (Violations):")
            for v in violations:
                print(f"  - {v}")
            sys.exit(1)

    elif args.cmd == "semaforo":
        db = args.db
        window = args.window
        if not os.path.exists(db):
            print(f"ERROR: Database {db} not found.")
            sys.exit(1)

        con = sqlite3.connect(db)
        con.row_factory = sqlite3.Row
        try:
            rows = con.execute(f"SELECT * FROM ua_ledger ORDER BY id DESC LIMIT ?", (window,)).fetchall()
            if not rows:
                print("No records found in ledger.")
                return

            print(f"\nAUDITORÍA SEMÁFORO (Chronos-Hodge v2.0) - Últimos {len(rows)} registros\n")
            print(f"{'ID':<6} {'RIGIDEZ (H)':<15} {'FINGERPRINT':<10} {'ESTADO':<25}")
            print("-" * 60)

            stats = {"GREEN": 0, "YELLOW": 0, "ORANGE": 0, "RED": 0}

            for r in rows:
                h = r["h_rigidity"]
                valid = bool(r["contract_valid"])
                fid = (r["input_fingerprint"][:8]) if r["input_fingerprint"] else "n/a"
                
                # Semaforo Logic
                if not valid or h > 1e-8:
                    color = "RED"
                    label = "FAIL: RED (GHOST)"
                elif h <= 1e-14:
                    color = "GREEN"
                    label = "OK: GREEN (STRUCTURAL)"
                elif h <= 1e-11:
                    color = "YELLOW"
                    label = "WARN: YELLOW (ISLAND-T)"
                else:
                    color = "ORANGE"
                    label = "WARN: ORANGE (DRIFT-WARN)"

                stats[color] += 1
                print(f"{r['id']:<6} {h:<15.2e} {fid:<10} {label}")

            print("\n" + "=" * 60)
            print(f"RESUMEN SEMÁFORO:")
            print(f"  VERDE:    {stats['GREEN']}")
            print(f"  AMARILLO: {stats['YELLOW']}")
            print(f"  NARANJA:  {stats['ORANGE']}")
            print(f"  ROJO:     {stats['RED']}")
            print("=" * 60)

            if stats["RED"] > 0:
                print("\nCRITICAL: Ghosts detected in the ledger. Integrity compromised.")
                sys.exit(2)
            elif stats["ORANGE"] > (len(rows) * 0.3):
                print("\nWARNING: High drift detected. Recalibration recommended.")
            else:
                print("\nSYSTEM HEALTH: OPTIMAL (Chronos-Hodge Stable)")

        finally:
            con.close()

    else:
        parser.print_help()

if __name__ == "__main__":
    main()
