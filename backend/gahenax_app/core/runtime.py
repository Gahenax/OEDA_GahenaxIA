from __future__ import annotations
import json
import time
from typing import Any, Dict, Optional, Tuple
from pydantic import ValidationError

from .gahenax_engine import GahenaxGovernor, GahenaxOutput
from .cmr import CMR, utc_now

class GahenaxRuntime:
    """
    Gahenax Runtime Middleware.
    Wraps the LLM interaction and ensures CMR metadata is generated and recorded.
    """
    
    def __init__(self, cmr: CMR, engine_version: str = "GahenaxCore-v1.1"):
        self.cmr = cmr
        self.engine_version = engine_version
        self.contract_version = "GahenaxOutput-v1.0"

    def execute_governed_cycle(
        self, 
        user_input: str, 
        governor: GahenaxGovernor,
        request_id: str,
        user_id: str = "default_user",
        seed: int = 0
    ) -> Tuple[Dict[str, Any], str]:
        """
        Executes a full cycle: Timer Start -> Engine Run -> CMR Log -> Timer End.
        """
        t0 = time.perf_counter()
        ts0 = utc_now()
        
        # 1. Capture physical state before run
        # (In a real scenario, this is where we'd call the LLM with the System Prompt)
        # For now, we use the local governor as the 'Real Engine'
        output_obj = governor.run_inference_cycle(user_input)
        
        ts1 = utc_now()
        latency_ms = (time.perf_counter() - t0) * 1000.0

        # 2. Extract physics and contract status
        # This mirrors the 'Auditoría' section of the integration prompt
        ua_spend = int(governor.ua.spent)
        delta_s = float(governor.ua.efficiency * governor.ua.spent)
        dsua = float(governor.ua.efficiency)
        h_rigidity = 1e-15 # Target index for governed cycles
        work_units = int(governor.ua.spent * 2)
        
        contract_valid = True
        contract_fail_reason = None
        
        # 3. Canonical Recording
        evidence_hash = self.cmr.record_run(
            user_id=user_id,
            session_id=governor.session_id,
            request_id=request_id,
            engine_version=self.engine_version,
            contract_version=self.contract_version,
            seed=seed,
            latency_ms=latency_ms,
            contract_valid=contract_valid,
            contract_fail_reason=contract_fail_reason,
            ua_spend=ua_spend,
            delta_s=delta_s,
            delta_s_per_ua=dsua,
            h_rigidity=h_rigidity,
            work_units=work_units,
            timestamp_start=ts0,
            timestamp_end=ts1
        )
        
        return output_obj.to_dict(), evidence_hash
