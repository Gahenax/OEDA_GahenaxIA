"""
Gahenax Core - The Sovereign Inference Engine
---------------------------------------------
High-Speed Operational Suite using LLL Optimization and P over NP (UA) Physics.
Author: Antigravity / Gahenax Team
"""

from __future__ import annotations
from dataclasses import dataclass, field, asdict
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple, Union
import hashlib
import json
import time
import uuid
from dataclasses import dataclass, field, asdict
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple, Union

# =============================================================================
# CNI v1 - Canonical Normalized Input
# =============================================================================

def compute_cni_fingerprint(payload: Dict[str, Any]) -> str:
    """
    Produces a stable SHA256 hash of the input payload.
    Cleans strings and sorts keys for determinism.
    """
    def _clean(obj):
        if isinstance(obj, str): return obj.strip()
        if isinstance(obj, dict): return {k: _clean(v) for k, v in sorted(obj.items())}
        if isinstance(obj, list): return [_clean(x) for x in obj]
        return obj

    canon = _clean(payload)
    blob = json.dumps(canon, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(blob).hexdigest()

@dataclass
class UAMetrics:
    """Athena Units measurement for computational honesty."""
    budget: float
    spent: float = 0.0
    efficiency: float = 0.0 # Delta Entropy / UA Spent

    def consume(self, amount: float):
        if self.spent + amount > self.budget:
            raise ResourceWarning("UA_CAP_REACHED: Optimization aborted to maintain integrity.")
        self.spent += amount

# =============================================================================
# 1) Core Enums & SSOT Constants
# =============================================================================

class RenderProfile(str, Enum):
    DAILY = "daily"   # "Amigo culto"
    DENSE = "dense"   # "Lattice reduced" (maximum information density)

class VerdictStrength(str, Enum):
    NO_VERDICT = "no_verdict"
    CONDITIONAL = "conditional"
    RIGOROUS = "rigorous"  # Shortest Vector found and validated

class ValidationAnswerType(str, Enum):
    BINARY = "binary"
    NUMERIC = "numeric"
    FACT = "fact"
    CHOICE = "choice"

class AssumptionStatus(str, Enum):
    OPEN = "open"
    VALIDATED = "validated"
    INVALIDATED = "invalidated"
    REDUCED = "reduced" # Optimized away via LLL reasoning

class FindingStatus(str, Enum):
    PROVISIONAL = "provisional"
    RIGOROUS = "rigorous"

class EngineMode(str, Enum):
    EVERYDAY = "everyday"    # GEM v1: High efficiency, minimal UA (default)
    AUDIT = "audit"          # Deep precision, strict gates
    EXPERIMENT = "experiment" # Exploratory, higher entropy tolerance

# Hard System Limits
MAX_CRITICAL_ASSUMPTIONS = 3
IMPERATIVE_BLOCKLIST = ["deberías", "compra", "vende", "haz", "recomiendo", "invierte"]
UA_BUDGET_EVERYDAY = 6.0
UA_SPEND_TARGET_EVERYDAY = 4.0

# =============================================================================
# 2) Data Models (Gahenax Contract)
# =============================================================================

@dataclass(frozen=True)
class Reframe:
    statement: str

@dataclass(frozen=True)
class Exclusions:
    items: List[str]

@dataclass
class Finding:
    statement: str
    status: FindingStatus = FindingStatus.PROVISIONAL
    support: List[str] = field(default_factory=list)
    depends_on: List[str] = field(default_factory=list)

@dataclass
class Assumption:
    assumption_id: str
    statement: str
    unlocks_conclusion: str
    status: AssumptionStatus = AssumptionStatus.OPEN
    closing_question_ids: List[str] = field(default_factory=list)

@dataclass(frozen=True)
class ValidationQuestion:
    question_id: str
    targets_assumption_id: str
    prompt: str
    answer_type: ValidationAnswerType
    choices: Optional[List[str]] = None
    numeric_unit: Optional[str] = None

@dataclass(frozen=True)
class NextStep:
    action: str
    evidence_required: str

@dataclass
class FinalVerdict:
    strength: VerdictStrength
    statement: str
    ua_audit: Dict[str, float]
    conditions: List[str] = field(default_factory=list)

@dataclass
class GahenaxOutput:
    """The final emission of the engine."""
    reframe: Reframe
    exclusions: Exclusions
    findings: List[Finding]
    assumptions: List[Assumption]
    interrogatory: List[ValidationQuestion]
    next_steps: List[NextStep]
    verdict: FinalVerdict

    def to_markdown(self, profile: RenderProfile) -> str:
        lines = []
        if profile == RenderProfile.DAILY:
            lines.append("> **Gahenax Core**: Inferencia gobernada por Unidades Athena (UA).\n")
        
        lines.append(f"## Reencuadre Técnico\n{self.reframe.statement}\n")
        
        lines.append("## Exclusiones de Rigor")
        for item in self.exclusions.items: lines.append(f"- {item}")
        lines.append("")

        lines.append("## Hallazgos (Lattice Status)")
        for f in self.findings:
            tag = "RIGUROSO" if f.status == FindingStatus.RIGOROUS else "PROVISIONAL"
            lines.append(f"- **[{tag}]** {f.statement}")
        lines.append("")

        lines.append("## Supuestos Críticos (Shortest Vector Candidates)")
        for a in self.assumptions:
            lines.append(f"- **{a.assumption_id}**: {a.statement} $\rightarrow$ {a.unlocks_conclusion}")
        lines.append("")

        lines.append("## Interrogatorio de Cierre")
        for q in self.interrogatory:
            lines.append(f"- **{q.question_id}** ({q.answer_type.value}): {q.prompt}")
        lines.append("")

        lines.append("## Veredicto Gahenax")
        lines.append(f"**[{self.verdict.strength.value}]** {self.verdict.statement}")
        lines.append(f"*Auditoría UA: Coste {self.verdict.ua_audit['spent']:.2f} | Eficiencia {self.verdict.ua_audit['efficiency']:.4f}*")
        
        return "\n".join(lines)

# =============================================================================
# 3) LLL Optimizer (The Brain)
# =============================================================================

class GahenaxOptimizer:
    """
    Simulates LLL/Deep-LLL lattice reduction on reasoning.
    Finds the shortest path (Shortest Vector) from facts to conclusion.
    """
    @staticmethod
    def reduce_lattice(assumptions: List[Assumption], findings: List[Finding]) -> Tuple[List[Assumption], List[Finding], float]:
        """
        In a real LLM integration, this would use a transformer to map the vector space
        of logic and reduce it. 
        Returns (Reduced Assumptions, Enhanced Findings, Entropy Reduction Value).
        """
        # Mocking entropy reduction logic
        entropy_init = len(assumptions) * 10
        # If we have redundant assumptions, we "reduce" them
        unique_assumptions = {a.statement: a for a in assumptions}.values()
        entropy_final = len(unique_assumptions) * 10
        delta_entropy = entropy_init - entropy_final
        
        return list(unique_assumptions), findings, delta_entropy

# =============================================================================
# 4) The Governor (Orchestrator)
# =============================================================================

class GahenaxGovernor:
    def __init__(self, budget_ua: Optional[float] = None, mode: EngineMode = EngineMode.EVERYDAY):
        self.mode = mode
        if budget_ua is None:
            budget_ua = UA_BUDGET_EVERYDAY if mode == EngineMode.EVERYDAY else 1000.0
        
        self.ua = UAMetrics(budget=budget_ua)
        self.session_id = str(uuid.uuid4())
        self.turn = 1

    def run_inference_cycle(self, text: str, context: Dict[str, Any] = None) -> GahenaxOutput:
        import os
        api_key = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")

        if api_key:
            return self._run_real(text, api_key)
        else:
            return self._run_mock(text)

    def _run_real(self, text: str, api_key: str) -> GahenaxOutput:
        """Live path: Gemini API under Gahenax contract."""
        # Import here to avoid circular import at module load
        from gahenax_app.core.gahenax_llm_bridge import GahenaxLLMBridge

        # UA: cost to engage the bridge
        cost_ingest = 2.0 if self.mode == EngineMode.EVERYDAY else 10.0
        self.ua.consume(cost_ingest)

        bridge = GahenaxLLMBridge(api_key=api_key)
        result = bridge.call(
            text=text,
            ua_spent=self.ua.spent,
            ua_budget=self.ua.budget,
        )

        # Deduct LLM call cost
        cost_llm = 1.5 if self.mode == EngineMode.EVERYDAY else 3.0
        self.ua.consume(cost_llm)

        # Record compliance metrics
        m = result.metrics
        compliance = (
            (1.0 if m.schema_complete else 0.0)
            + (1.0 if len(m.imperatives_found) == 0 else 0.0)
            + (1.0 if len(m.absolutes_found) == 0 else 0.0)
        ) / 3.0
        self.ua.efficiency = compliance / (self.ua.spent + 1e-9)

        if not result.success:
            print(f"[GAHENAX BRIDGE] Contract violation: {result.error_reason}")
            print(f"[GAHENAX BRIDGE] Imperatives: {m.imperatives_found}")
            print(f"[GAHENAX BRIDGE] Absolutes:   {m.absolutes_found}")

        return result.output

    def _run_mock(self, text: str) -> GahenaxOutput:
        """Offline path: deterministic mock (no LLM call)."""
        cost_ingest = 2.0 if self.mode == EngineMode.EVERYDAY else 10.0
        self.ua.consume(cost_ingest)

        assumptions = [
            Assumption("A1", "El usuario acepta el riesgo de incertidumbre en P vs NP",
                       "Cierre de veredicto filosofico", AssumptionStatus.OPEN, ["Q1"])
        ]
        if self.mode != EngineMode.EVERYDAY:
            assumptions.append(Assumption(
                "A2", "Existe una metrica de UA para este dominio",
                "Cuantificacion de honestidad computacional", AssumptionStatus.OPEN, ["Q2"]))

        reduced_a, enhanced_f, delta_e = GahenaxOptimizer.reduce_lattice(assumptions, [])
        cost_lll = 1.0 if self.mode == EngineMode.EVERYDAY else (len(assumptions) * 5.0)
        self.ua.consume(cost_lll)
        self.ua.efficiency = delta_e / (self.ua.spent + 1e-9)

        return GahenaxOutput(
            reframe=Reframe(statement=f"[MOCK] Optimizacion de sistema decisional para: {text[:50]}..."),
            exclusions=Exclusions(items=["No se prometen soluciones a problemas NP-completos.",
                                         "Veredicto limitado por presupuesto UA."]),
            findings=enhanced_f,
            assumptions=reduced_a,
            interrogatory=[ValidationQuestion(
                "Q1", "A1", "Acepta que esta conclusion es solo la mas rigurosa posible?",
                ValidationAnswerType.BINARY)],
            next_steps=[NextStep("Definir umbral de UA para el siguiente ciclo.", "Presupuesto declarado.")],
            verdict=FinalVerdict(
                strength=VerdictStrength.CONDITIONAL,
                statement="[MOCK] Veredicto suspendido. Set GEMINI_API_KEY para inferencia real.",
                ua_audit={"spent": self.ua.spent, "efficiency": self.ua.efficiency},
                conditions=["Validar Q1 para cerrar el ciclo."]
            )
        )

# =============================================================================
# 5) API Utilities
# =============================================================================

def _as_jsonable(obj: Any) -> Any:
    if isinstance(obj, Enum): return obj.value
    if hasattr(obj, "__dataclass_fields__"):
        return {k: _as_jsonable(v) for k, v in asdict(obj).items()}
    if isinstance(obj, dict): return {k: _as_jsonable(v) for k, v in obj.items()}
    if isinstance(obj, list): return [_as_jsonable(x) for x in obj]
    return obj

if __name__ == "__main__":
    gov = GahenaxGovernor()
    out = gov.run_inference_cycle("¿Cómo optimizar mi tesis sobre sistemas gobernados?")
    print(out.to_markdown(RenderProfile.DAILY))
