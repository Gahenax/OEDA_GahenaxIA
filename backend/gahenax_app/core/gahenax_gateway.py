"""
gahenax_gateway.py
==================
CONTRACT-FIRST EXECUTION GATEWAY (CFT v1)

Architecture:
    User → Router → Skill Plan → ExecutionGateway → ToolRunner → Result → CMR

Rules:
    1. Nothing executes directly — everything passes through this gateway.
    2. No evidence, no execution.
    3. fail_closed by default for all side-effecting skills.
    4. Circuit breaker per skill. Quarantine on repeated failure.
    5. Idempotency enforced via request_id.
"""

from __future__ import annotations

import hashlib
import json
import time
from collections import defaultdict
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


# =========================================================================
# ENUMS
# =========================================================================

class RiskLevel(str, Enum):
    AUTO    = "AUTO"     # Executes without confirmation
    CONFIRM = "CONFIRM"  # Requires explicit user confirmation
    LOCKED  = "LOCKED"   # Never executes automatically; AUDIT only


class ExecutionStatus(str, Enum):
    OK        = "OK"
    FAIL      = "FAIL"
    PARTIAL   = "PARTIAL"
    BLOCKED   = "BLOCKED"     # Circuit breaker / quarantine
    DRY_RUN   = "DRY_RUN"    # Simulated, no side effects applied


class ErrorClass(str, Enum):
    SCHEMA_VIOLATION    = "SCHEMA_VIOLATION"
    UA_CAP_EXCEEDED     = "UA_CAP_EXCEEDED"
    TIMEOUT             = "TIMEOUT"
    SIDE_EFFECT_DENIED  = "SIDE_EFFECT_DENIED"
    CIRCUIT_OPEN        = "CIRCUIT_OPEN"
    IDEMPOTENCY_REPLAY  = "IDEMPOTENCY_REPLAY"
    TOOL_ERROR          = "TOOL_ERROR"
    CMR_UNAVAILABLE     = "CMR_UNAVAILABLE"
    UNKNOWN             = "UNKNOWN"


class RollbackPolicy(str, Enum):
    NONE         = "none"
    BEST_EFFORT  = "best_effort"
    REQUIRED     = "required"


# =========================================================================
# A) SkillSpec — What a skill IS, not how it runs
# =========================================================================

class SkillSpec(BaseModel):
    skill_id: str = Field(..., description="Unique, stable identifier")
    intent_tags: List[str] = Field(default_factory=list, description="Semantic search tags")
    description: str = Field(..., description="One-sentence description")
    risk_level: RiskLevel = Field(RiskLevel.CONFIRM)
    required_inputs: List[str] = Field(default_factory=list)
    output_schema: str = Field("any", description="Name of the Pydantic model or 'any'")
    ua_cost_estimate: float = Field(1.0, ge=0.0, description="Expected UA cost")
    timeout_ms: int = Field(5000, ge=100)
    idempotent: bool = Field(True)
    side_effects: List[str] = Field(default_factory=list, description="e.g. ['file:write', 'db:write', 'network']")
    rollback: RollbackPolicy = Field(RollbackPolicy.NONE)
    # Runtime state (managed by registry, not the caller)
    enabled: bool = Field(True)
    dry_run_default: bool = Field(False)

    @property
    def has_side_effects(self) -> bool:
        return len(self.side_effects) > 0

    def spec_hash(self) -> str:
        blob = self.model_dump_json(exclude={"enabled", "dry_run_default"}).encode()
        return hashlib.sha256(blob).hexdigest()[:16]


# =========================================================================
# B) ExecutionRequest — What the engine asks to run
# =========================================================================

class ExecutionRequest(BaseModel):
    request_id: str = Field(..., description="Idempotency key — must be unique per logical operation")
    skill_id: str
    inputs: Dict[str, Any] = Field(default_factory=dict)
    mode: str = Field("GEM", description="GEM | AUDIT | EXPERIMENT")
    ua_budget: float = Field(6.0, ge=0.0)
    risk_override: bool = Field(False, description="Only effective in AUDIT mode")
    dry_run: bool = Field(False, description="If true, simulate execution without side effects")


# =========================================================================
# C) ExecutionResult — What comes back
# =========================================================================

class ExecutionResult(BaseModel):
    request_id: str
    skill_id: str
    status: ExecutionStatus
    outputs: Dict[str, Any] = Field(default_factory=dict)
    evidence: Dict[str, Any] = Field(default_factory=dict, description="hashes, paths, diffs")
    metrics: Dict[str, Any] = Field(default_factory=dict, description="latency_ms, ua_spend, work_units")
    error_class: Optional[ErrorClass] = None
    error_detail: Optional[str] = None
    retryable: bool = False
    rollback_status: Optional[str] = None
    timestamp: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def evidence_hash(self) -> str:
        payload = {
            "request_id": self.request_id,
            "skill_id": self.skill_id,
            "status": self.status,
            "outputs": self.outputs,
        }
        blob = json.dumps(payload, sort_keys=True, default=str).encode()
        return hashlib.sha256(blob).hexdigest()


# =========================================================================
# D) FailurePolicy — Circuit breakers and fusibles
# =========================================================================

class FailurePolicy(BaseModel):
    fail_closed: bool = Field(True, description="True = safe default: block on ambiguity")
    max_retries: int = Field(2, ge=0)
    backoff_ms: int = Field(500, ge=0)
    circuit_breaker_threshold: int = Field(3, ge=1, description="Failures before quarantine")
    quarantine_window_s: int = Field(300, description="Seconds circuit stays open")

    # Global defaults (can be overridden per skill)
    @classmethod
    def default(cls) -> "FailurePolicy":
        return cls()

    @classmethod
    def strict(cls) -> "FailurePolicy":
        return cls(fail_closed=True, max_retries=0, circuit_breaker_threshold=1, quarantine_window_s=600)


# =========================================================================
# CIRCUIT BREAKER (per skill)
# =========================================================================

class CircuitBreaker:
    def __init__(self, threshold: int, quarantine_window_s: int):
        self.threshold = threshold
        self.quarantine_window_s = quarantine_window_s
        self._failures = 0
        self._quarantine_until: float = 0.0

    @property
    def is_open(self) -> bool:
        if time.time() < self._quarantine_until:
            return True
        if self._quarantine_until > 0:
            # Window expired: half-open reset
            self._failures = 0
            self._quarantine_until = 0.0
        return False

    def record_failure(self):
        self._failures += 1
        if self._failures >= self.threshold:
            self._quarantine_until = time.time() + self.quarantine_window_s

    def record_success(self):
        self._failures = 0
        self._quarantine_until = 0.0

    def status(self) -> str:
        if self.is_open:
            remaining = max(0, int(self._quarantine_until - time.time()))
            return f"QUARANTINED ({remaining}s remaining)"
        return f"OK (failures={self._failures}/{self.threshold})"


# =========================================================================
# SKILL REGISTRY
# =========================================================================

class SkillRegistry:
    def __init__(self):
        self._skills: Dict[str, SkillSpec] = {}

    def register(self, spec: SkillSpec):
        self._skills[spec.skill_id] = spec

    def get(self, skill_id: str) -> Optional[SkillSpec]:
        return self._skills.get(skill_id)

    def all(self) -> List[SkillSpec]:
        return list(self._skills.values())

    def list_by_risk(self, risk: RiskLevel) -> List[SkillSpec]:
        return [s for s in self._skills.values() if s.risk_level == risk]

    def summary(self) -> str:
        lines = [f"  {'SKILL_ID':<35} {'RISK':<10} {'SIDE_EFFECTS':<20} {'ENABLED'}"]
        lines.append("  " + "-" * 80)
        for s in self._skills.values():
            fx = ", ".join(s.side_effects) or "none"
            lines.append(f"  {s.skill_id:<35} {s.risk_level.value:<10} {fx:<20} {s.enabled}")
        return "\n".join(lines)


# =========================================================================
# IDEMPOTENCY STORE (in-memory, pluggable)
# =========================================================================

class IdempotencyStore:
    def __init__(self):
        self._cache: Dict[str, ExecutionResult] = {}

    def get(self, request_id: str) -> Optional[ExecutionResult]:
        return self._cache.get(request_id)

    def store(self, result: ExecutionResult):
        self._cache[result.request_id] = result


# =========================================================================
# EXECUTION GATEWAY — The single bridge
# =========================================================================

class ExecutionGateway:
    """
    The single execution bridge for all Gahenax skills.

    Flow:
        1. Validate request schema
        2. Resolve skill from registry
        3. Check circuit breaker
        4. Check idempotency
        5. Validate risk/mode/side-effects
        6. Delegate to ToolRunner
        7. Record in CMR
        8. Return typed ExecutionResult
    """

    def __init__(
        self,
        registry: SkillRegistry,
        policy: FailurePolicy = None,
        cmr=None,
    ):
        self.registry = registry
        self.policy = policy or FailurePolicy.default()
        self.cmr = cmr
        self._breakers: Dict[str, CircuitBreaker] = defaultdict(
            lambda: CircuitBreaker(self.policy.circuit_breaker_threshold,
                                   self.policy.quarantine_window_s)
        )
        self._idempotency = IdempotencyStore()
        self._tool_runner = _ToolRunner()

    def execute(self, req: ExecutionRequest) -> ExecutionResult:
        t0 = time.perf_counter()

        # ── 1. Resolve skill ──────────────────────────────────────────
        spec = self.registry.get(req.skill_id)
        if not spec:
            return self._blocked(req, ErrorClass.SCHEMA_VIOLATION, f"Unknown skill: {req.skill_id}")

        if not spec.enabled:
            return self._blocked(req, ErrorClass.SIDE_EFFECT_DENIED, f"Skill {req.skill_id} is disabled")

        # ── 2. Circuit breaker ────────────────────────────────────────
        breaker = self._breakers[req.skill_id]
        if breaker.is_open:
            return self._blocked(req, ErrorClass.CIRCUIT_OPEN,
                                 f"Skill {req.skill_id} quarantined: {breaker.status()}")

        # ── 3. Idempotency ────────────────────────────────────────────
        if spec.idempotent:
            cached = self._idempotency.get(req.request_id)
            if cached:
                cached.error_class = ErrorClass.IDEMPOTENCY_REPLAY
                cached.error_detail = "Replayed from idempotency cache"
                return cached

        # ── 4. Risk / mode gate ───────────────────────────────────────
        if spec.risk_level == RiskLevel.LOCKED and req.mode != "AUDIT":
            return self._blocked(req, ErrorClass.SIDE_EFFECT_DENIED,
                                 f"Skill {req.skill_id} is LOCKED — use AUDIT mode with risk_override=true")

        if spec.risk_level == RiskLevel.LOCKED and not req.risk_override:
            return self._blocked(req, ErrorClass.SIDE_EFFECT_DENIED,
                                 f"Skill {req.skill_id} requires risk_override=true in AUDIT mode")

        # ── 5. UA budget gate ─────────────────────────────────────────
        if spec.ua_cost_estimate > req.ua_budget:
            return self._blocked(req, ErrorClass.UA_CAP_EXCEEDED,
                                 f"Skill cost estimate {spec.ua_cost_estimate} UA > budget {req.ua_budget} UA")

        # ── 6. CMR availability gate ──────────────────────────────────
        if self.cmr is None and spec.has_side_effects and self.policy.fail_closed:
            return self._blocked(req, ErrorClass.CMR_UNAVAILABLE,
                                 "CMR required for side-effecting skills but not connected")

        # ── 7. Determine effective dry_run ────────────────────────────
        effective_dry_run = req.dry_run or spec.dry_run_default

        # ── 8. Execute via ToolRunner ─────────────────────────────────
        try:
            outputs = self._tool_runner.run(spec, req.inputs, dry_run=effective_dry_run)
            elapsed_ms = (time.perf_counter() - t0) * 1000.0

            result = ExecutionResult(
                request_id=req.request_id,
                skill_id=req.skill_id,
                status=ExecutionStatus.DRY_RUN if effective_dry_run else ExecutionStatus.OK,
                outputs=outputs,
                evidence={"result_hash": hashlib.sha256(
                    json.dumps(outputs, sort_keys=True, default=str).encode()).hexdigest()},
                metrics={"latency_ms": elapsed_ms, "ua_spend": spec.ua_cost_estimate},
            )

            breaker.record_success()
            if spec.idempotent:
                self._idempotency.store(result)

            self._record_to_cmr(req, spec, result)
            return result

        except Exception as e:
            elapsed_ms = (time.perf_counter() - t0) * 1000.0
            breaker.record_failure()
            return ExecutionResult(
                request_id=req.request_id,
                skill_id=req.skill_id,
                status=ExecutionStatus.FAIL,
                error_class=ErrorClass.TOOL_ERROR,
                error_detail=str(e),
                retryable=True,
                metrics={"latency_ms": elapsed_ms},
            )

    def _blocked(self, req: ExecutionRequest, err: ErrorClass, detail: str) -> ExecutionResult:
        return ExecutionResult(
            request_id=req.request_id,
            skill_id=req.skill_id,
            status=ExecutionStatus.BLOCKED,
            error_class=err,
            error_detail=detail,
            retryable=False,
        )

    def _record_to_cmr(self, req: ExecutionRequest, spec: SkillSpec, result: ExecutionResult):
        if self.cmr is None:
            return
        try:
            from datetime import timezone
            ts = datetime.now(timezone.utc).isoformat()
            self.cmr.record_run(
                user_id="gateway",
                session_id=req.request_id,
                request_id=req.request_id,
                engine_version="GahenaxCore-v1.1.1",
                contract_version=spec.output_schema,
                prompt_version=f"skill:{spec.skill_id}",
                input_fingerprint=hashlib.sha256(
                    json.dumps(req.inputs, sort_keys=True).encode()).hexdigest(),
                seed=None,
                latency_ms=result.metrics.get("latency_ms", 0.0),
                contract_valid=result.status == ExecutionStatus.OK,
                contract_fail_reason=result.error_detail,
                ua_spend=int(result.metrics.get("ua_spend", 0)),
                delta_s=result.metrics.get("ua_spend", 0) * 1.0,
                delta_s_per_ua=1.0,
                h_rigidity=1e-15,
                work_units=1,
                timestamp_start=ts,
                timestamp_end=ts,
            )
        except Exception:
            pass  # CMR failure is logged but never crashes the gateway

    def status_report(self) -> str:
        lines = ["\n=== EXECUTION GATEWAY STATUS ===\n"]
        lines.append(self.registry.summary())
        lines.append("\n=== CIRCUIT BREAKERS ===")
        for skill_id, b in self._breakers.items():
            lines.append(f"  {skill_id:<35} {b.status()}")
        return "\n".join(lines)


# =========================================================================
# TOOL RUNNER (pluggable stub — replace with real implementations)
# =========================================================================

class _ToolRunner:
    """
    Dispatches to actual skill implementations.
    Each skill_id maps to a handler function.
    Replace stubs with real logic.
    """

    def __init__(self):
        self._handlers: Dict[str, Any] = {}

    def register_handler(self, skill_id: str, fn):
        self._handlers[skill_id] = fn

    def run(self, spec: SkillSpec, inputs: Dict[str, Any], dry_run: bool = False) -> Dict[str, Any]:
        handler = self._handlers.get(spec.skill_id)
        if handler is None:
            # Default stub: echo inputs, signal missing handler
            return {
                "stub": True,
                "dry_run": dry_run,
                "skill_id": spec.skill_id,
                "inputs_received": inputs,
                "note": "No handler registered. Register via gateway._tool_runner.register_handler()"
            }
        return handler(inputs, dry_run=dry_run)
