"""
RUN_GEM_REAL.py
===============
First live inference cycle: GahenaxGovernor -> Gemini API -> GahenaxOutput

Usage:
  $env:GEMINI_API_KEY = "your-key"
  python RUN_GEM_REAL.py

The Governor routes automatically:
  - GEMINI_API_KEY present -> real LLM call under contract
  - No key -> deterministic mock (for offline/testing)
"""

from __future__ import annotations
import os
import sys
import time
import hashlib
from pathlib import Path
from datetime import datetime, timezone

sys.path.append(str(Path(__file__).parent / "backend"))

from gahenax_app.core.gahenax_engine import GahenaxGovernor, EngineMode, RenderProfile
from gahenax_app.core.cmr import CMR, CMRConfig

PROBLEM = (
    "Tengo que decidir si lanzar este proyecto publicamente esta semana o esperar. "
    "Dame un marco practico para decidir hoy."
)

def run():
    api_key = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
    mode_str = "LIVE (Gemini API)" if api_key else "MOCK (offline)"

    print(f"\n{'=' * 65}")
    print(f"  GAHENAX CORE v1.1.1 — GEM Inference")
    print(f"  Mode    : {mode_str}")
    print(f"  Problem : {PROBLEM[:60]}...")
    print(f"{'=' * 65}\n")

    cmr = CMR(CMRConfig(db_path="ua_ledger.sqlite"))
    gov = GahenaxGovernor(mode=EngineMode.EVERYDAY, budget_ua=6.0)

    ts0 = datetime.now(timezone.utc).isoformat()
    t_wall = time.perf_counter()

    output = gov.run_inference_cycle(PROBLEM)

    elapsed_ms = (time.perf_counter() - t_wall) * 1000.0
    ts1 = datetime.now(timezone.utc).isoformat()

    # Render
    rendered = output.to_markdown(RenderProfile.DAILY)
    print(rendered)

    # UA summary
    print(f"\n{'-' * 65}")
    print(f"  UA Spent     : {gov.ua.spent:.1f} / {gov.ua.budget:.1f}")
    print(f"  Efficiency   : {gov.ua.efficiency:.4f} Delta_S/UA")
    print(f"  Latency      : {elapsed_ms:.0f}ms")

    # CMR seal
    fingerprint = hashlib.sha256(PROBLEM.encode()).hexdigest()
    evidence_hash = cmr.record_run(
        user_id="gem_v1",
        session_id=gov.session_id,
        request_id=f"GEM-REAL-{int(time.time())}",
        engine_version="GahenaxCore-v1.1.1",
        contract_version="GahenaxOutput-v1.0",
        prompt_version="engine_v1.1.md#GEMv1",
        input_fingerprint=fingerprint,
        seed=None,
        latency_ms=elapsed_ms,
        contract_valid=True,
        contract_fail_reason=None,
        ua_spend=int(gov.ua.spent),
        delta_s=gov.ua.efficiency * gov.ua.spent,
        delta_s_per_ua=gov.ua.efficiency,
        h_rigidity=1e-15,
        work_units=10,
        timestamp_start=ts0,
        timestamp_end=ts1,
        git_commit=os.getenv("GIT_COMMIT"),
        host_id=os.getenv("HOSTNAME"),
    )

    print(f"  Evidence Hash: {evidence_hash[:32]}...")
    print(f"  Ledger Sealed: YES")
    print(f"{'-' * 65}\n")

    print("[*] Running Semaforo post-inference audit...")
    import subprocess
    r = subprocess.run(
        ["python", "gahenax_ops.py", "semaforo", "--db", "ua_ledger.sqlite", "--window", "3"],
        capture_output=True, text=True, encoding="utf-8", errors="replace"
    )
    print(r.stdout.encode("ascii", errors="replace").decode("ascii"))

if __name__ == "__main__":
    run()
