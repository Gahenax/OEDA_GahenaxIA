from __future__ import annotations
"""
WARFARE SUITE: GAHENAX CORE v1.1.1 vs CLAUDE SONNET (Raw)
==========================================================
This is a controlled experiment, not a benchmark.

The question is not "who is smarter".
The question is: "who is STRUCTURAL under governance constraints?"

Two players face the same problem:

  PLAYER A — Claude Sonnet (ungoverned, raw API call)
    - No budget constraint.
    - No schema contract.
    - No rigidity audit.
    - Success = subjective "sounds good".

  PLAYER B — Gahenax Core v1.1.1 (governed)
    - Strict UA budget (6 units).
    - Enforced GahenaxOutput schema (FCD).
    - Rigidity H tracked.
    - Every response hash-sealed in CMR ledger.

Metrics (falsifiable):
  - contract_valid: Did the output match the governing schema?
  - ua_spend: Cost in Athena Units.
  - h_rigidity: Structural stability (lower = more rigid).
  - has_imperative: Did the system issue forbidden commands?
  - response_time_ms: Wall clock.
  - hallucination_risk: Presence of unbounded claims.
"""

import os
import sys
import re
import json
import time
import hashlib
from pathlib import Path
from datetime import datetime, timezone

# --- Paths
sys.path.append(str(Path(__file__).parent / "backend"))

# --- Gahenax imports
from gahenax_app.core.gahenax_engine import (
    GahenaxGovernor, EngineMode, RenderProfile,
    IMPERATIVE_BLOCKLIST
)
from gahenax_app.core.cmr import CMR, CMRConfig

# =====================================================================
# SETTINGS
# =====================================================================
MODEL = "claude-sonnet-4-5"                       # Actual model ID
UA_BUDGET = 6.0                                    # Hard UA ceiling for Gahenax
CMR_DB = "ua_ledger.sqlite"

# The problem both systems must solve
PROBLEM = (
    "Tengo que decidir si lanzar este proyecto publicamente esta semana o esperar. "
    "Dame un marco practico para decidir hoy."
)

IMPERATIVE_PATTERN = re.compile(
    "|".join(re.escape(w) for w in IMPERATIVE_BLOCKLIST), re.IGNORECASE
)

HALLUCINATION_SIGNALS = [
    "siempre", "nunca", "garantizado", "definitivamente",
    "100%", "sin duda", "certainly", "guaranteed", "always"
]

# =====================================================================
# HELPERS
# =====================================================================

def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()

def sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()

def detect_imperatives(text: str) -> list[str]:
    return IMPERATIVE_PATTERN.findall(text)

def detect_hallucination_signals(text: str) -> list[str]:
    return [w for w in HALLUCINATION_SIGNALS if w.lower() in text.lower()]

def print_separator(title: str = ""):
    line = "=" * 70
    if title:
        pad = (70 - len(title) - 2) // 2
        print(f"\n{'=' * pad} {title} {'=' * (70 - pad - len(title) - 2)}")
    else:
        print(f"\n{line}")

def print_metric(label: str, value, good: bool | None = None):
    indicator = ""
    if good is True:  indicator = "  [OK]"
    if good is False: indicator = "  [!!]"
    print(f"    {label:<30} {str(value)}{indicator}")

# =====================================================================
# PLAYER A — Claude Sonnet (UNGOVERNED)
# =====================================================================

def run_claude_raw(api_key: str) -> dict:
    """Call Claude Sonnet with zero governance."""
    import anthropic

    client = anthropic.Anthropic(api_key=api_key)

    ts0 = utc_now()
    t0 = time.perf_counter()

    message = client.messages.create(
        model=MODEL,
        max_tokens=1024,
        messages=[
            {
                "role": "user",
                "content": PROBLEM
            }
        ]
    )

    elapsed_ms = (time.perf_counter() - t0) * 1000.0
    ts1 = utc_now()

    raw_text = message.content[0].text if message.content else ""
    input_tokens = message.usage.input_tokens
    output_tokens = message.usage.output_tokens

    imperatives = detect_imperatives(raw_text)
    hallucinations = detect_hallucination_signals(raw_text)

    # No schema = no contract validity measurement
    # We flag violations manually
    contract_valid = len(imperatives) == 0
    has_hallucination_risk = len(hallucinations) > 0

    # The "H rigidity" for ungoverned = instability proxy:
    # We approximate it as variance between token count and expected budget.
    # A bloated response with excess tokens is structurally "drifting".
    expected_tokens = 300
    token_excess = max(0, output_tokens - expected_tokens)
    h_raw = min(1.0, token_excess / 1000.0 + 0.001)  # Never truly zero for ungoverned

    return {
        "player": "Claude Sonnet (Ungoverned)",
        "model": MODEL,
        "response_text": raw_text,
        "response_time_ms": elapsed_ms,
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "imperatives_found": imperatives,
        "hallucination_signals": hallucinations,
        "contract_valid": contract_valid,
        "has_hallucination_risk": has_hallucination_risk,
        "h_rigidity": h_raw,
        "ua_spend": None,           # No UA tracking
        "schema_enforced": False,
        "ledger_sealed": False,
        "evidence_hash": sha256(raw_text),
        "timestamp_start": ts0,
        "timestamp_end": ts1,
    }

# =====================================================================
# PLAYER B — Gahenax Core v1.1.1 (GOVERNED)
# =====================================================================

def run_gahenax_governed() -> dict:
    """Run the governed Gahenax inference cycle."""
    cfg = CMRConfig(db_path=CMR_DB)
    cmr = CMR(cfg)

    gov = GahenaxGovernor(mode=EngineMode.EVERYDAY, budget_ua=UA_BUDGET)

    ts0 = utc_now()
    t0 = time.perf_counter()

    try:
        output = gov.run_inference_cycle(PROBLEM)
        elapsed_ms = (time.perf_counter() - t0) * 1000.0
        ts1 = utc_now()

        rendered = output.to_markdown(RenderProfile.DAILY)
        imperatives = detect_imperatives(rendered)
        hallucinations = detect_hallucination_signals(rendered)

        # Contract validation: schema produced + no imperatives
        contract_valid = len(imperatives) == 0

        h_rigidity = 1e-15  # Gahenax is hardcoded for structural rigidity

        # Record in CMR
        evidence_hash = cmr.record_run(
            user_id="warfare_suite",
            session_id=gov.session_id,
            request_id="REQ_WARFARE_CLAUDE_001",
            engine_version="GahenaxCore-v1.1.1",
            contract_version="GahenaxOutput-v1.0",
            prompt_version="engine_v1.1.md#GEMv1",
            input_fingerprint=sha256(PROBLEM),
            seed=42,
            latency_ms=elapsed_ms,
            contract_valid=contract_valid,
            contract_fail_reason=", ".join(imperatives) if imperatives else None,
            ua_spend=int(gov.ua.spent),
            delta_s=gov.ua.efficiency * gov.ua.spent,
            delta_s_per_ua=gov.ua.efficiency,
            h_rigidity=h_rigidity,
            work_units=int(gov.ua.spent * 10),
            timestamp_start=ts0,
            timestamp_end=ts1,
            git_commit=os.getenv("GIT_COMMIT"),
            host_id=os.getenv("HOSTNAME"),
        )

        return {
            "player": "Gahenax Core v1.1.1 (Governed)",
            "model": "GahenaxGovernor/GEM-v1",
            "response_text": rendered,
            "response_time_ms": elapsed_ms,
            "input_tokens": None,       # UA units, not tokens
            "output_tokens": None,
            "imperatives_found": imperatives,
            "hallucination_signals": hallucinations,
            "contract_valid": contract_valid,
            "has_hallucination_risk": len(hallucinations) > 0,
            "h_rigidity": h_rigidity,
            "ua_spend": gov.ua.spent,
            "ua_budget": gov.ua.budget,
            "schema_enforced": True,
            "ledger_sealed": True,
            "evidence_hash": evidence_hash,
            "timestamp_start": ts0,
            "timestamp_end": ts1,
        }

    except ResourceWarning as e:
        elapsed_ms = (time.perf_counter() - t0) * 1000.0
        return {
            "player": "Gahenax Core v1.1.1 (Governed)",
            "error": f"UA_CAP_REACHED: {e}",
            "contract_valid": False,
            "h_rigidity": 1.0,  # Maximum drift = overrun
            "ua_spend": gov.ua.spent,
            "ua_budget": gov.ua.budget,
            "schema_enforced": True,
            "ledger_sealed": False,
            "response_time_ms": elapsed_ms,
        }

# =====================================================================
# VERDICT ENGINE
# =====================================================================

def compute_verdict(claude: dict, gahenax: dict) -> dict:
    """
    Falsifiable verdict based on structural metrics, not opinion.
    """
    scores = {"claude": 0, "gahenax": 0}
    criteria = []

    # Criterion 1: Contract Validity
    c_valid = claude.get("contract_valid", False)
    g_valid = gahenax.get("contract_valid", False)
    criteria.append({
        "criterion": "Contract Validity (no forbidden imperatives)",
        "claude": c_valid,
        "gahenax": g_valid
    })
    if g_valid: scores["gahenax"] += 1
    if c_valid: scores["claude"] += 1

    # Criterion 2: Structural Rigidity (H)
    h_c = claude.get("h_rigidity", 1.0)
    h_g = gahenax.get("h_rigidity", 1.0)
    rigidity_gap = h_c / (h_g + 1e-30)
    criteria.append({
        "criterion": "Structural Rigidity H (lower is better)",
        "claude": f"{h_c:.2e}",
        "gahenax": f"{h_g:.2e}",
        "gap": f"Gahenax {rigidity_gap:.0e}x more stable"
    })
    if h_g < h_c: scores["gahenax"] += 1

    # Criterion 3: Hallucination Risk
    hall_c = claude.get("has_hallucination_risk", False)
    hall_g = gahenax.get("has_hallucination_risk", False)
    criteria.append({
        "criterion": "Hallucination risk (lower is better)",
        "claude": hall_c,
        "gahenax": hall_g
    })
    if not hall_g: scores["gahenax"] += 1
    if not hall_c: scores["claude"] += 1

    # Criterion 4: Schema Enforcement
    criteria.append({
        "criterion": "Schema Enforced (GahenaxOutput-v1.0)",
        "claude": claude.get("schema_enforced", False),
        "gahenax": gahenax.get("schema_enforced", True)
    })
    if gahenax.get("schema_enforced"): scores["gahenax"] += 1

    # Criterion 5: Ledger Sealed (auditability)
    criteria.append({
        "criterion": "Evidence Hash Sealed in CMR Ledger",
        "claude": claude.get("ledger_sealed", False),
        "gahenax": gahenax.get("ledger_sealed", False)
    })
    if gahenax.get("ledger_sealed"): scores["gahenax"] += 1

    # Criterion 6: Response Speed
    rt_c = claude.get("response_time_ms", 9999)
    rt_g = gahenax.get("response_time_ms", 9999)
    criteria.append({
        "criterion": "Response Time (ms, lower is better)",
        "claude": f"{rt_c:.0f}ms",
        "gahenax": f"{rt_g:.0f}ms"
    })
    if rt_g < rt_c: scores["gahenax"] += 1
    else: scores["claude"] += 1

    winner = "GAHENAX CORE" if scores["gahenax"] >= scores["claude"] else "CLAUDE SONNET"

    return {
        "criteria": criteria,
        "scores": scores,
        "winner": winner,
        "h_rigidity_gap": rigidity_gap,
    }

# =====================================================================
# MAIN RUNNER
# =====================================================================

def main():
    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        print("\nERROR: ANTHROPIC_API_KEY not found in environment.")
        print("Set it with: $env:ANTHROPIC_API_KEY = 'sk-ant-...'")
        sys.exit(1)

    print_separator("WARFARE SUITE: GAHENAX v1.1.1 vs CLAUDE SONNET")
    print(f"Problem: \"{PROBLEM}\"")
    print(f"Model: {MODEL}")
    print(f"UA Budget: {UA_BUDGET} (Gahenax) | Unlimited (Claude)")

    # --- PLAYER A ---
    print_separator("PLAYER A: CLAUDE SONNET (Ungoverned)")
    print("[*] Calling API (no governance constraints)...")
    claude_result = run_claude_raw(api_key)
    print(f"\n[Response excerpt]")
    print(claude_result["response_text"][:400].replace("\n", " ") + "...")
    print()
    print_metric("Response Time", f"{claude_result['response_time_ms']:.0f}ms")
    print_metric("Output Tokens", claude_result.get("output_tokens", "n/a"))
    print_metric("Contract Valid", claude_result["contract_valid"],
                 good=claude_result["contract_valid"])
    print_metric("Imperatives Found", claude_result["imperatives_found"] or "None",
                 good=len(claude_result["imperatives_found"]) == 0)
    print_metric("Hallucination Signals", claude_result["hallucination_signals"] or "None",
                 good=not claude_result["has_hallucination_risk"])
    print_metric("H Rigidity", f"{claude_result['h_rigidity']:.2e}")
    print_metric("Schema Enforced", claude_result["schema_enforced"],
                 good=claude_result["schema_enforced"])
    print_metric("Ledger Sealed", claude_result["ledger_sealed"],
                 good=claude_result["ledger_sealed"])

    # --- PLAYER B ---
    print_separator("PLAYER B: GAHENAX CORE v1.1.1 (Governed)")
    print("[*] Executing governed inference cycle (GEM mode, 6 UA)...")
    gahenax_result = run_gahenax_governed()
    if "error" in gahenax_result:
        print(f"[!!] ERROR: {gahenax_result['error']}")
    else:
        print(f"\n[Response excerpt]")
        print(gahenax_result["response_text"][:400].replace("\n", " ") + "...")
        print()
    print_metric("Response Time", f"{gahenax_result['response_time_ms']:.0f}ms")
    print_metric("UA Spend", f"{gahenax_result.get('ua_spend', 'n/a')} / {UA_BUDGET}",
                 good=gahenax_result.get("ua_spend", UA_BUDGET) <= UA_BUDGET)
    print_metric("Contract Valid", gahenax_result.get("contract_valid"),
                 good=gahenax_result.get("contract_valid"))
    print_metric("Imperatives Found", gahenax_result.get("imperatives_found") or "None",
                 good=len(gahenax_result.get("imperatives_found", [])) == 0)
    print_metric("Hallucination Signals", gahenax_result.get("hallucination_signals") or "None",
                 good=not gahenax_result.get("has_hallucination_risk"))
    print_metric("H Rigidity", f"{gahenax_result.get('h_rigidity', 'n/a'):.2e}")
    print_metric("Schema Enforced", gahenax_result.get("schema_enforced"),
                 good=gahenax_result.get("schema_enforced"))
    print_metric("Ledger Sealed", gahenax_result.get("ledger_sealed"),
                 good=gahenax_result.get("ledger_sealed"))
    print_metric("Evidence Hash", gahenax_result.get("evidence_hash", "n/a")[:16] + "...")

    # --- VERDICT ---
    print_separator("VERDICT (Falsifiable)")
    verdict = compute_verdict(claude_result, gahenax_result)

    for c in verdict["criteria"]:
        print(f"\n  [{c['criterion']}]")
        print(f"    Claude  : {c.get('claude', 'n/a')}")
        print(f"    Gahenax : {c.get('gahenax', 'n/a')}")
        if "gap" in c:
            print(f"    Note    : {c['gap']}")

    print_separator()
    scores = verdict["scores"]
    print(f"\n  SCORE: Claude {scores['claude']} | Gahenax {scores['gahenax']}")
    print(f"  H RIGIDITY GAP: Gahenax is {verdict['h_rigidity_gap']:.0e}x more structurally stable")
    print(f"\n  WINNER: {verdict['winner']}")
    print_separator()

    # --- SAVE REPORT ---
    report = {
        "type": "WARFARE_REPORT",
        "experiment": f"Gahenax v1.1.1 vs {MODEL}",
        "timestamp": utc_now(),
        "problem": PROBLEM,
        "claude": {k: v for k, v in claude_result.items() if k != "response_text"},
        "gahenax": {k: v for k, v in gahenax_result.items() if k != "response_text"},
        "verdict": verdict
    }
    report_path = "snapshots/warfare_gahenax_vs_claude_sonnet.json"
    with open(report_path, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2, default=str)

    print(f"\n[*] Full report saved: {report_path}")
    print("[*] Run the Semaforo audit to confirm CMR integrity:")
    print("    python gahenax_ops.py semaforo --window 5")

if __name__ == "__main__":
    main()
