from pydantic import BaseModel, Field
from typing import List, Optional, Tuple, Any, Dict
from enum import Enum

class VerdictStrength(str, Enum):
    NO_VERDICT = "no_verdict"
    CONDITIONAL = "conditional"
    RIGOROUS = "rigorous"

class ValidationAnswerType(str, Enum):
    BINARY = "binary"
    NUMERIC = "numeric"
    FACT = "fact"
    CHOICE = "choice"

class AssumptionStatus(str, Enum):
    OPEN = "open"
    VALIDATED = "validated"
    INVALIDATED = "invalidated"
    REDUCED = "reduced"

class FindingStatus(str, Enum):
    PROVISIONAL = "provisional"
    RIGOROUS = "rigorous"

class ReframeSchema(BaseModel):
    statement: str

class ExclusionsSchema(BaseModel):
    items: List[str]

class FindingSchema(BaseModel):
    statement: str
    status: FindingStatus
    support: List[str] = []
    depends_on: List[str] = []

class AssumptionSchema(BaseModel):
    assumption_id: str
    statement: str
    unlocks_conclusion: str
    status: AssumptionStatus
    closing_question_ids: List[str] = []

class ValidationQuestionSchema(BaseModel):
    question_id: str
    targets_assumption_id: str
    prompt: str
    answer_type: ValidationAnswerType
    choices: Optional[List[str]] = None
    numeric_unit: Optional[str] = None

class NextStepSchema(BaseModel):
    action: str
    evidence_required: str

class VerdictSchema(BaseModel):
    strength: VerdictStrength
    statement: str
    ua_audit: Dict[str, float]
    conditions: List[str] = []

class GahenaxOutputSchema(BaseModel):
    reframe: ReframeSchema
    exclusions: ExclusionsSchema
    findings: List[FindingSchema]
    assumptions: List[AssumptionSchema]
    interrogatory: List[ValidationQuestionSchema]
    next_steps: List[NextStepSchema]
    verdict: VerdictSchema

class GahenaxRequest(BaseModel):
    text: str
    session_id: Optional[str] = None
    turn_index: int = 1
    ua_budget: Optional[float] = None
    mode: str = "everyday"
    context_answers: Dict[str, Any] = {}
    render_profile: str = "daily"
