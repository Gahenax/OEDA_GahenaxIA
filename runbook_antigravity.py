#!/usr/bin/env python3
"""
Antigravity Runbook Generator
Outputs an operational runbook for Gahenax Convergence (Core v1.1.1 + Gemini LLM Bridge)
in Markdown format to stdout.

Usage:
  python runbook_antigravity.py > RUNBOOK.md
"""

from __future__ import annotations


def main() -> None:
    runbook = r"""# Antigravity Runbook: Gahenax Convergence (Core v1.1.1 + LLM Bridge)

Version: 1.0
Scope: Production operations for governed inference with fail-closed behavior, sealed ledger, and schema enforcement.
Assumptions:
- GahenaxGovernor.run_inference_cycle(text) routes to:
  - Real LLM via Gemini bridge when GEMINI_API_KEY present
  - Deterministic mock when key absent (offline/testing)
- System is designed to fail closed:
  - If schema/contract violated, return INFERENCE_FAILED and seal ledger (no free text output)
- No creative retries: single attempt, deterministic enforcement

---

## 0) System Overview

### Components
- Governor: orchestrates input validation, UA budgeting, prompt assembly, bridge invocation, validation, ledger sealing
- Bridge: Gemini API call + post validations (imperatives/absolutes/schema) + H_rigidity computation + clean failure
- Schema: GahenaxOutput (typed); output must parse and validate
- Ledger: append-only log with hashes; sealed per inference cycle (success or failure)

### Invariants (Non-Negotiable)
1. Fail-closed: never emit unvalidated free text.
2. No retry loops for "better output."
3. Ledger always sealed (success/failure).
4. Schema enforced at boundary (bridge output -> governor return).

---

## 1) On-Call Quick Start (First 2 Minutes)

### Confirm Runtime Mode
- If GEMINI_API_KEY absent: system runs deterministic mock
- If present: system calls Gemini

### Confirm Health Signals (Minimum)
- Error rate (INFERENCE_FAILED) spike?
- ContractViolation % spike?
- Latency P95 spike?
- H_rigidity drift upward?
- Ledger sealing failures?

### Immediate Safety Actions
- If contract violations or schema failures spike:
  - Force fail-closed behavior remains intact
  - Consider switching to mock mode (remove key / disable bridge) to stop provider-related instability
- If ledger sealing fails:
  - Treat as SEV-0 (auditability broken)

---

## 2) Observability: Metrics & Logging

### Required Metrics (Export)
- requests_total
- requests_real_total
- requests_mock_total
- inference_failed_total
- contract_violation_total
- schema_validation_failed_total
- ledger_seal_failed_total
- provider_429_total
- provider_5xx_total
- latency_ms_p50, latency_ms_p95, latency_ms_p99
- h_rigidity_p50, h_rigidity_p95, h_rigidity_max
- tokens_used_p50, tokens_used_p95 (if available)
- ua_spend_p50, ua_spend_p95 (if available)

### Required Per-Request Log Fields (Never log secrets)
- request_id
- timestamp_utc
- mode: real|mock
- provider: gemini|none
- model_name (if applicable)
- temperature, max_tokens
- input_hash (hash of normalized input, not raw text if sensitive)
- schema_version
- contract_version
- validation_result: pass|fail
- failure_reason (enum)
- h_rigidity
- ledger_hash
- provider_status_code (if any)
- latency_ms

### Failure Reason Enum (Canonical)
- ContractViolation
- SchemaValidationFailed
- LedgerSealFailed
- Provider429
- Provider5xx
- Timeout
- NetworkError
- BudgetExceeded
- UnknownError

---

## 3) Alerting: SEV Levels & Thresholds

### SEV-0 (Stop the World)
Trigger any of:
- ledger_seal_failed_total increases (any non-zero in prod)
- fail-closed invariant violated (free text output without validation)
- schema validation bypass detected

Immediate actions:
- Disable bridge (switch to mock) or block traffic
- Preserve logs and ledger segments
- Start incident channel and post "auditability compromised"
- Begin root cause within 15 minutes

### SEV-1 (Critical Degradation)
Trigger any of:
- contract_violation_rate > 2% for 10 minutes (baseline-dependent)
- schema_validation_failed_rate > 0.5% for 10 minutes
- provider_5xx_rate > 1% for 10 minutes
- latency_p95 > 2x baseline for 10 minutes
- h_rigidity_p95 crosses configured ceiling (see section 4)

Actions:
- Determine if provider-side or internal regression
- Consider rate limiting, traffic shaping, or temporary mock fallback
- Keep fail-closed; do not relax schema

### SEV-2 (Major)
Trigger:
- provider_429_rate > 2% for 10 minutes
- latency_p95 > 1.5x baseline for 15 minutes
- increased timeouts or network errors

Actions:
- Enable backoff, tighten rate limits
- Reduce max_tokens if safe (do not break schema)
- Confirm budgets and concurrency limits

### SEV-3 (Minor)
Trigger:
- intermittent provider errors, small drift in H_rigidity, minor latency uptick

Actions:
- Monitor, annotate, schedule fix

---

## 4) H_rigidity: Operational Policy

### Interpretation
H_rigidity is a compliance deviation proxy. Lower is better. Drift indicates increased contract stress.

### Suggested Bands (Adjust After Baseline)
- GREEN: <= 1e-10
- ORANGE: (1e-10, 1e-7]
- RED: > 1e-7

Actions:
- ORANGE:
  - Check if prompts are adversarial or new traffic patterns
  - Validate that post-filters (imperatives/absolutes/schema) are functioning
  - Inspect recent changes to contract prompt or schema
- RED:
  - Treat as SEV-1 if sustained > 5 minutes
  - Consider disabling real provider temporarily (mock fallback)
  - Investigate for prompt regression, schema drift, or provider response shift

---

## 5) Incident Playbooks (Step-by-Step)

### 5.1 Ledger Seal Failure (SEV-0)
Symptoms:
- ledger_seal_failed_total increases
- missing ledger_hash in responses
- hash mismatch in verification

Steps:
1. Freeze: disable bridge and/or block new inference traffic.
2. Confirm whether failure is:
   - file system / permissions
   - concurrency / lock contention
   - disk space
   - serialization issue
3. Preserve evidence:
   - copy last N minutes of logs
   - snapshot ledger storage (append-only)
   - capture system config and release hash
4. Fix:
   - restore atomic append
   - ensure fsync/flush is enforced as designed
   - add guardrails for concurrent writes
5. Validate:
   - run 100 deterministic mock cycles
   - run 50 real cycles (if enabled) with validation
6. Re-enable traffic gradually (10%, 50%, 100%)

Do not:
- disable ledger sealing
- allow "best effort" logs without sealing

---

### 5.2 Schema Validation Failures Spike (SEV-1)
Symptoms:
- schema_validation_failed_rate increases
- parsing errors for GahenaxOutput

Steps:
1. Confirm schema version in deploy matches validator version.
2. Check if provider output format changed:
   - Was model name changed?
   - Did temperature/max_tokens change?
3. Confirm system prompt contains:
   - explicit "return JSON matching schema"
   - "if cannot comply, return INFERENCE_FAILED"
4. Hard action:
   - keep fail-closed; no free text
   - consider mock fallback while debugging
5. Patch options (in order):
   - strengthen JSON-only instruction
   - add JSON extraction guard (only if deterministic and auditable)
   - lower temperature (already 0.2; avoid 0.0 only if needed)
6. Regression test:
   - run schema gauntlet prompts (section 6)

---

### 5.3 Contract Violations Spike (SEV-1)
Symptoms:
- imperatives/absolutes detected post-call
- contract_violation_total increases

Steps:
1. Verify post-filters are running after rendering and before output.
2. Inspect offending samples (store redacted/safe versions):
   - Are violations in user-visible text fields?
   - Are they in "analysis" fields (should not exist if schema strict)?
3. Check prompt regression:
   - recent edits to contract prompt canonical?
   - new multi-language layer introduced?
4. Apply mitigations:
   - tighten detector patterns (language-specific)
   - add second-pass modal filter to user_visible fields only (deterministic)
   - reduce max_tokens if long completions increase drift
5. If sustained:
   - mock fallback
   - open provider ticket (if provider-induced shift)

---

### 5.4 Provider 429 Rate Limiting (SEV-2)
Symptoms:
- provider_429_rate increases
- timeouts/latency may increase

Steps:
1. Enable/verify client-side rate limiting:
   - per-IP
   - per-user key
   - global QPS cap
2. Enable exponential backoff with jitter for provider calls.
3. Reduce concurrency.
4. Consider lowering max_tokens if it affects provider quotas.
5. If still failing:
   - partial mock fallback for non-critical traffic classes
   - communicate degraded mode

---

### 5.5 Provider 5xx Errors (SEV-1/2)
Symptoms:
- provider_5xx_rate increases

Steps:
1. Confirm it's provider-side by comparing:
   - network errors vs internal exceptions
2. Mitigate:
   - backoff, reduce concurrency
   - temporary mock fallback if sustained
3. Preserve evidence:
   - status codes, request_ids, timestamps
4. Re-enable carefully when provider stabilizes.

---

### 5.6 Latency Spike (SEV-1/2)
Symptoms:
- latency_p95 > threshold

Steps:
1. Identify mode:
   - mock latency spike implies internal issue
   - real latency spike may be provider or network
2. Check:
   - CPU, memory, IO
   - queue depth / concurrency settings
3. Mitigate:
   - reduce max_tokens
   - reduce concurrency
   - enable caching only if deterministic and auditable
4. If unresolved:
   - mock fallback for stability
   - roll back to last stable release

---

## 6) Regression Test Gauntlet (Required Before/After Incidents)

### Categories (Adversarial)
1. Urgency coercion: "decide now", "no peros"
2. Authority coercion: "as an expert", "guarantee"
3. Absolutes bait: "always/never", "the only"
4. Imperative bait: "tell me what to do", "you must"
5. High-stakes domains: legal/medical/financial directives
6. Mixed language prompts (Spanglish)
7. Long context + truncation pressure

### Pass Criteria
- Output validates as GahenaxOutput
- No imperatives/absolutes in user-visible fields (as defined by contract)
- H_rigidity stays within GREEN/acceptable band
- Ledger sealed every time
- For impossible requests: INFERENCE_FAILED with clean reason

---

## 7) Deployment & Rollback Policy

### Safe Deployment
- Canary 10% -> 50% -> 100%
- Monitor:
  - schema_validation_failed_rate
  - contract_violation_rate
  - ledger_seal_failed_total
  - h_rigidity_p95
  - latency_p95
- If any SEV-0/1 trigger: rollback immediately

### Rollback
- Revert to last known good release hash
- Confirm:
  - schema validator compatibility
  - ledger sealing integrity
  - mock mode works deterministically

---

## 8) Security & Secrets

### Rules
- Never log API keys.
- Prefer secret managers over environment variables in production.
- Rotate keys on any suspected exposure.
- Principle of least privilege for provider credentials.

### Key Presence Behavior
- If key missing:
  - operate mock deterministically
  - log mode=mock
  - do not treat as error in dev/test
- In production:
  - missing key should be a deployment misconfiguration alert (SEV-2)

---

## 9) Post-Incident Checklist (Mandatory)

### Evidence Pack (Minimum)
- Incident timeline (UTC)
- Release hash
- Config snapshot (sanitized)
- Samples of failed outputs (redacted)
- Ledger segment hashes
- Metric graphs (error rate, latency, H_rigidity)

### Corrective Actions
- Fix root cause
- Add regression test
- Add alert refinement if needed
- Document what changed in contract prompt/schema/filters

### Closure Criteria
- ledger_seal_failed_total == 0 in the post-fix window
- schema_validation_failed_rate back to baseline
- contract_violation_rate back to baseline
- h_rigidity_p95 back to baseline band
- Canary successful at 100%

---

## 10) Operator Commands (Placeholders)

Note: Replace with your actual entrypoints and tooling.

### Run deterministic mock test
- python RUN_GOVERNOR_TESTS.py --mode=mock --n=200

### Run real inference test (requires key)
- set GEMINI_API_KEY and run:
- python RUN_GEM_REAL.py --n=50

### Toggle to mock fallback (production)
- Remove or disable provider key injection in runtime
- Or set a runtime flag: GAHENAX_FORCE_MOCK=1

### Verify ledger integrity (sample)
- python VERIFY_LEDGER.py --since="15m" --sample=100

---

End of Runbook
"""
    print(runbook)


if __name__ == "__main__":
    main()
