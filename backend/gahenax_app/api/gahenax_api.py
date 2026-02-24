from fastapi import APIRouter, HTTPException
from gahenax_app.schemas.gahenax_contract import GahenaxRequest, GahenaxOutputSchema
from gahenax_app.core.gahenax_engine import GahenaxGovernor, RenderProfile, EngineMode, compute_cni_fingerprint
from gahenax_app.core.cmr import CMR, CMRConfig, utc_now
from typing import Dict, Any
import time
import os

PROMPT_VERSION = "engine_v1.1.md#GEMv1"
ENGINE_VERSION = "GahenaxCore-v1.1.1"
Contract_VERSION = "GahenaxOutput-v1.0"

router = APIRouter(prefix="/api/gahenax", tags=["Gahenax Core"])

# CMR: Canonical Measurement Recorder (FCD-1.0 compliant)
cmr_cfg = CMRConfig(db_path=os.path.join(os.getcwd(), "ua_ledger.sqlite"))
CMR_INST = CMR(cmr_cfg)

# Persistent Governors (Mock Session Store)
GOVERNORS: Dict[str, GahenaxGovernor] = {}

@router.post("/infer", response_model=GahenaxOutputSchema)
async def infer(request: GahenaxRequest):
    """
    Main inference cycle for Gahenax Core.
    Logs every interaction to the Canonical Measurement Recorder (CMR).
    """
    t0 = time.perf_counter()
    ts0 = utc_now()
    session_id = request.session_id
    
    # CNI v1: Canonical Normalized Input
    input_fingerprint = compute_cni_fingerprint(request.model_dump())

    try:
        mode = EngineMode(request.mode)
    except ValueError:
        mode = EngineMode.EVERYDAY

    if request.turn_index == 1 or not session_id:
        gov = GahenaxGovernor(budget_ua=request.ua_budget, mode=mode)
        session_id = gov.session_id
        GOVERNORS[session_id] = gov
    else:
        if session_id not in GOVERNORS:
            gov = GahenaxGovernor(budget_ua=request.ua_budget, mode=mode)
            GOVERNORS[session_id] = gov
        else:
            gov = GOVERNORS[session_id]
            gov.turn = request.turn_index

    try:
        profile = RenderProfile(request.render_profile)
    except ValueError:
        profile = RenderProfile.DAILY

    output_obj = gov.run_inference_cycle(request.text, request.context_answers)
    
    ts1 = utc_now()
    latency_ms = (time.perf_counter() - t0) * 1000.0

    # --- CMR RECORDING (FCD-1.1.1) ---
    CMR_INST.record_run(
        user_id="default_user",
        session_id=session_id,
        request_id=f"REQ_{int(time.time())}",
        engine_version=ENGINE_VERSION,
        contract_version=Contract_VERSION,
        prompt_version=PROMPT_VERSION,
        input_fingerprint=input_fingerprint,
        seed=0,
        latency_ms=latency_ms,
        contract_valid=True,
        contract_fail_reason=None,
        ua_spend=int(gov.ua.spent),
        delta_s=float(gov.ua.efficiency * gov.ua.spent),
        delta_s_per_ua=float(gov.ua.efficiency),
        h_rigidity=1e-15,
        work_units=int(gov.ua.spent * 2),
        timestamp_start=ts0,
        timestamp_end=ts1,
        git_commit=os.getenv("GIT_COMMIT"),
        host_id=os.getenv("HOSTNAME")
    )
    # -------------------------------

    return output_obj.to_dict()

@router.get("/status/{session_id}")
async def get_status(session_id: str):
    if session_id not in GOVERNORS:
        raise HTTPException(status_code=404, detail="Session not found.")
    gov = GOVERNORS[session_id]
    return {
        "session_id": gov.session_id,
        "turn": gov.turn,
        "ua_status": {
            "spent": gov.ua.spent,
            "budget": gov.ua.budget,
            "efficiency": gov.ua.efficiency
        }
    }
