"""
gahenax_llm_bridge.py
======================
THE BRIDGE — GahenaxGovernor <-> Gemini API

Architecture:
    GahenaxGovernor.run_inference_cycle(text)
        ├─ validate_input_contract()
        ├─ allocate_UA_budget()
        ├─ build_system_prompt(GahenaxPromptCanonical)
        ├─ GahenaxLLMBridge.call(text)   ← THIS FILE
        │      ├─ call Gemini API with contract system prompt
        │      ├─ parse JSON response → GahenaxOutput
        │      ├─ validate schema (no imperatives, no absolutes)
        │      ├─ compute H_rigidity
        │      └─ return ValidatedResponse | BridgeFailure
        ├─ seal_ledger(hash)
        └─ return GahenaxOutput

Rules (non-negotiable):
    - No retries on contract violation. Abort, seal, return failure.
    - No prompt engineering to "fix" a bad response. Fail clean.
    - H_rigidity computed from schema compliance deviation.
    - Every call sealed in CMR regardless of outcome.
"""

from __future__ import annotations

import json
import re
import os
import hashlib
import time
from dataclasses import dataclass
from typing import Optional, Any, Dict

from google import genai
from google.genai import types as genai_types

from gahenax_app.core.gahenax_engine import (
    GahenaxOutput, Reframe, Exclusions, Finding, FindingStatus,
    Assumption, AssumptionStatus, ValidationQuestion, ValidationAnswerType,
    NextStep, FinalVerdict, VerdictStrength, IMPERATIVE_BLOCKLIST,
)
from gahenax_app.core.gahenax_prompt_canonical import (
    GAHENAX_SYSTEM_PROMPT, INFERENCE_FAILED_TEMPLATE
)

# =====================================================================
# CONSTANTS
# =====================================================================

GEMINI_MODEL        = "gemini-1.5-flash"  # Fast, governed, available
IMPERATIVE_RE       = re.compile(
    "|".join(re.escape(w) for w in IMPERATIVE_BLOCKLIST), re.IGNORECASE
)
ABSOLUTE_SIGNALS    = [
    "siempre", "nunca", "definitivamente", "100%", "sin duda",
    "el unico", "el único", "garantizado", "imposible", "certeza absoluta"
]
SCHEMA_SECTIONS     = ["reframe", "exclusions", "findings", "assumptions",
                        "interrogatory", "next_steps", "verdict"]


# =====================================================================
# BRIDGE DATA STRUCTURES
# =====================================================================

@dataclass
class BridgeMetrics:
    latency_ms: float
    input_tokens: Optional[int]
    output_tokens: Optional[int]
    imperatives_found: list
    absolutes_found: list
    schema_complete: bool
    contract_valid: bool
    h_rigidity: float
    raw_response_hash: str


@dataclass
class BridgeResult:
    success: bool
    output: GahenaxOutput
    metrics: BridgeMetrics
    error_reason: Optional[str] = None


# =====================================================================
# VALIDATORS
# =====================================================================

def _check_imperatives(text: str) -> list:
    return IMPERATIVE_RE.findall(text)

def _check_absolutes(text: str) -> list:
    return [w for w in ABSOLUTE_SIGNALS if w.lower() in text.lower()]

def _schema_complete(data: dict) -> bool:
    return all(k in data for k in SCHEMA_SECTIONS)

def _compute_h_rigidity(imperatives: list, absolutes: list, schema_ok: bool) -> float:
    """
    H rigidity: lower = more rigid = better.
    Structural (1e-15) only when zero violations.
    Each violation adds an order of magnitude of drift.
    """
    if not schema_ok:
        return 1.0      # Maximum drift: schema not even present
    violations = len(imperatives) + len(absolutes)
    if violations == 0:
        return 1e-15    # Full structural rigidity
    return min(1.0, violations * 1e-4)


# =====================================================================
# JSON EXTRACTOR
# =====================================================================

def _extract_json(text: str) -> Optional[dict]:
    """
    Extracts the first valid JSON object from the LLM response.
    Handles markdown code blocks (```json ... ```) and raw JSON.
    """
    # Try stripping markdown fences
    cleaned = re.sub(r"```json\s*", "", text)
    cleaned = re.sub(r"```\s*", "", cleaned)
    cleaned = cleaned.strip()

    # Try direct parse
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        pass

    # Try finding first {...} block
    match = re.search(r"\{[\s\S]+\}", cleaned)
    if match:
        try:
            return json.loads(match.group(0))
        except json.JSONDecodeError:
            pass

    return None


# =====================================================================
# OUTPUT BUILDER
# =====================================================================

def _build_gahenax_output(data: dict, ua_spent: float, ua_efficiency: float) -> GahenaxOutput:
    """
    Parses the raw dict from Gemini into a typed GahenaxOutput.
    If fields are malformed, uses safe defaults (never crashes).
    """
    def safe_str(d, key, default=""):
        return str(d.get(key, default)) if isinstance(d, dict) else default

    # Reframe
    reframe_raw = data.get("reframe", {})
    reframe = Reframe(statement=safe_str(reframe_raw, "statement", "Reframe not provided."))

    # Exclusions
    excl_raw = data.get("exclusions", {})
    items = excl_raw.get("items", []) if isinstance(excl_raw, dict) else []
    exclusions = Exclusions(items=[str(i) for i in items])

    # Findings
    findings = []
    for f in data.get("findings", []):
        if not isinstance(f, dict): continue
        status_str = str(f.get("status", "PROVISIONAL")).upper()
        fs = FindingStatus.RIGOROUS if status_str == "RIGOROUS" else FindingStatus.PROVISIONAL
        findings.append(Finding(
            statement=safe_str(f, "statement"),
            status=fs,
            support=f.get("support", []),
            depends_on=f.get("depends_on", []),
        ))

    # Assumptions
    assumptions = []
    for a in data.get("assumptions", []):
        if not isinstance(a, dict): continue
        assumptions.append(Assumption(
            assumption_id=safe_str(a, "assumption_id", "A?"),
            statement=safe_str(a, "statement"),
            unlocks_conclusion=safe_str(a, "unlocks_conclusion"),
            status=AssumptionStatus.OPEN,
            closing_question_ids=a.get("closing_question_ids", []),
        ))

    # Interrogatory
    interrogatory = []
    for q in data.get("interrogatory", []):
        if not isinstance(q, dict): continue
        at_str = str(q.get("answer_type", "binary")).lower()
        at_map = {"binary": ValidationAnswerType.BINARY, "numeric": ValidationAnswerType.NUMERIC,
                  "fact": ValidationAnswerType.FACT, "choice": ValidationAnswerType.CHOICE}
        at = at_map.get(at_str, ValidationAnswerType.BINARY)
        interrogatory.append(ValidationQuestion(
            question_id=safe_str(q, "question_id", "Q?"),
            targets_assumption_id=safe_str(q, "targets_assumption_id", "A?"),
            prompt=safe_str(q, "prompt"),
            answer_type=at,
        ))

    # Next Steps
    next_steps = []
    for ns in data.get("next_steps", []):
        if not isinstance(ns, dict): continue
        next_steps.append(NextStep(
            action=safe_str(ns, "action"),
            evidence_required=safe_str(ns, "evidence_required"),
        ))

    # Verdict
    verdict_raw = data.get("verdict", {})
    strength_str = str(verdict_raw.get("strength", "conditional")).lower()
    strength_map = {
        "no_verdict": VerdictStrength.NO_VERDICT,
        "conditional": VerdictStrength.CONDITIONAL,
        "rigorous": VerdictStrength.RIGOROUS,
    }
    strength = strength_map.get(strength_str, VerdictStrength.CONDITIONAL)

    # Override ua_audit with actual governor values
    verdict = FinalVerdict(
        strength=strength,
        statement=safe_str(verdict_raw, "statement", "Veredicto no emitido."),
        conditions=verdict_raw.get("conditions", []),
        ua_audit={"spent": ua_spent, "efficiency": ua_efficiency},
    )

    return GahenaxOutput(
        reframe=reframe,
        exclusions=exclusions,
        findings=findings,
        assumptions=assumptions,
        interrogatory=interrogatory,
        next_steps=next_steps,
        verdict=verdict,
    )


def _build_failure_output(reason: str, ua_spent: float) -> GahenaxOutput:
    data = INFERENCE_FAILED_TEMPLATE.copy()
    data["verdict"]["statement"] = f"INFERENCE_FAILED: {reason}"
    data["verdict"]["ua_audit"] = {"spent": ua_spent, "efficiency": 0.0}
    return _build_gahenax_output(data, ua_spent=ua_spent, ua_efficiency=0.0)


# =====================================================================
# THE BRIDGE
# =====================================================================

class GahenaxLLMBridge:
    """
    Single-function bridge between GahenaxGovernor and Gemini API.

    Responsibilities:
      - Format the system prompt (canonical contract).
      - Call Gemini with schema enforcement.
      - Validate the output (imperatives, absolutes, schema).
      - Compute H_rigidity.
      - Return typed BridgeResult.

    It does NOT retry on failure. It does NOT soften violations.
    Contract violation → BridgeResult(success=False).
    """

    def __init__(self, api_key: str, model: str = GEMINI_MODEL):
        self.client = genai.Client(api_key=api_key)
        self.model_name = model
        self._config = genai_types.GenerateContentConfig(
            system_instruction=GAHENAX_SYSTEM_PROMPT,
            temperature=0.2,      # Low: we want determinism, not creativity
            max_output_tokens=1500,
        )

    def call(self, text: str, ua_spent: float, ua_budget: float) -> BridgeResult:
        ua_remaining = ua_budget - ua_spent
        t0 = time.perf_counter()

        # Inject UA context into the user message
        augmented_input = (
            f"{text}\n\n"
            f"[GAHENAX CONTEXT]\n"
            f"UA Remaining: {ua_remaining:.1f} / {ua_budget:.1f}\n"
            f"Mode: GEM (concise, governed)\n"
            f"Respond ONLY with the JSON schema. No prose before or after."
        )

        try:
            response = self.client.models.generate_content(
                model=self.model_name,
                contents=augmented_input,
                config=self._config,
            )
            elapsed_ms = (time.perf_counter() - t0) * 1000.0

            raw_text = response.text
            raw_hash = hashlib.sha256(raw_text.encode()).hexdigest()

            # --- Extract JSON ---
            data = _extract_json(raw_text)
            if data is None:
                metrics = BridgeMetrics(
                    latency_ms=elapsed_ms, input_tokens=None, output_tokens=None,
                    imperatives_found=[], absolutes_found=[],
                    schema_complete=False, contract_valid=False, h_rigidity=1.0,
                    raw_response_hash=raw_hash,
                )
                return BridgeResult(
                    success=False,
                    output=_build_failure_output("JSON parse failure", ua_spent),
                    metrics=metrics,
                    error_reason="JSON_PARSE_FAILURE",
                )

            # --- Schema check ---
            schema_ok = _schema_complete(data)

            # --- Contract checks (on full raw text) ---
            imperatives = _check_imperatives(raw_text)
            absolutes = _check_absolutes(raw_text)

            h = _compute_h_rigidity(imperatives, absolutes, schema_ok)
            contract_valid = schema_ok and len(imperatives) == 0 and len(absolutes) == 0

            # Usage metadata (if available)
            input_tokens = output_tokens = None
            try:
                usage = response.usage_metadata
                input_tokens = usage.prompt_token_count
                output_tokens = usage.candidates_token_count
            except Exception:
                pass


            # Efficiency: schema compliance is the "delta S" proxy
            compliance_score = (
                (1.0 if schema_ok else 0.0)
                + (1.0 if len(imperatives) == 0 else 0.0)
                + (1.0 if len(absolutes) == 0 else 0.0)
            ) / 3.0
            ua_efficiency = compliance_score / (ua_spent + 1e-9)

            metrics = BridgeMetrics(
                latency_ms=elapsed_ms,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                imperatives_found=imperatives,
                absolutes_found=absolutes,
                schema_complete=schema_ok,
                contract_valid=contract_valid,
                h_rigidity=h,
                raw_response_hash=raw_hash,
            )

            if not contract_valid:
                reason_parts = []
                if imperatives: reason_parts.append(f"imperatives={imperatives}")
                if absolutes:   reason_parts.append(f"absolutes={absolutes}")
                if not schema_ok: reason_parts.append("schema_incomplete")
                return BridgeResult(
                    success=False,
                    output=_build_failure_output("; ".join(reason_parts), ua_spent),
                    metrics=metrics,
                    error_reason="CONTRACT_VIOLATION",
                )

            output = _build_gahenax_output(data, ua_spent=ua_spent, ua_efficiency=ua_efficiency)
            return BridgeResult(success=True, output=output, metrics=metrics)

        except Exception as e:
            elapsed_ms = (time.perf_counter() - t0) * 1000.0
            metrics = BridgeMetrics(
                latency_ms=elapsed_ms, input_tokens=None, output_tokens=None,
                imperatives_found=[], absolutes_found=[],
                schema_complete=False, contract_valid=False, h_rigidity=1.0,
                raw_response_hash="",
            )
            return BridgeResult(
                success=False,
                output=_build_failure_output(f"API_ERROR: {e}", ua_spent),
                metrics=metrics,
                error_reason=str(e),
            )
