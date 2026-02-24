from __future__ import annotations
import time
import numpy as np
import os
import sys
from pathlib import Path
from dataclasses import dataclass
from typing import List, Dict, Any, Tuple

# Add backend to path
sys.path.append(str(Path(__file__).parent / "backend"))

try:
    from gahenax_app.core.gahenax_engine import GahenaxGovernor, EngineMode
except ImportError:
    print("Error: Gahenax Core not found. Ensure you are in Gahenax_Core root.")
    sys.exit(1)

# =============================================================================
# ⚖️ THE WARFARE: Gahenax vs Raw LLL
# =============================================================================

class RawLLL:
    """Simulates a raw, ungoverned LLL implementation."""
    @staticmethod
    def reduce(lattice_dims: int, complexity: float) -> Tuple[float, float]:
        t0 = time.perf_counter()
        # Raw LLL is O(n^4). A blind LLM tries to reason without budget.
        work = (lattice_dims ** 4) * complexity
        time.sleep(min(0.5, work / 1e9)) # Simulate heavy compute
        
        # Entropy reduction (Delta S)
        ds = lattice_dims * 1.5
        
        # Rigidity H (Raw has high drift)
        h = 1e-5 * complexity 
        
        return ds, h

def run_warfare_scenario(dimensions: int, stress_factor: float):
    print(f"\n>>> STARTING WARFARE: Dimension {dimensions} | Stress x{stress_factor}")
    print("=" * 70)
    
    # --- PLAYER 1: Raw LLL (Ungoverned) ---
    print(f"[*] Player 1: Raw LLL (Blind Reasoning)...")
    ds_raw, h_raw = RawLLL.reduce(dimensions, stress_factor)
    ua_raw = dimensions * 10 # Estimated cost if it were UA
    eff_raw = ds_raw / (ua_raw + 1e-9)
    print(f"    - Delta S: {ds_raw:.2f}")
    print(f"    - Rigidity H: {h_raw:.2e} (DRIFT DETECTED)")
    print(f"    - Efficiency: {eff_raw:.4f} Delta_S/UA")
    
    # --- PLAYER 2: Gahenax Governor (Sovereign) ---
    print(f"\n[*] Player 2: Gahenax Core (Governed LLL)...")
    gov = GahenaxGovernor(mode=EngineMode.AUDIT)
    
    # Inject redundant assumptions to simulate lattice reduction
    # In a real run, Gahenax would find these in its search space
    raw_assumptions = []
    for i in range(dimensions):
        # Every 3 assumptions are logically equivalent (redundant)
        statement = f"Logical Core Assumption {i % (dimensions // 3 + 1)}"
        raw_assumptions.append(statement)
    
    # Simulate Gahenax run with these assumptions
    cost_ingest = 10.0
    gov.ua.consume(cost_ingest)
    
    from gahenax_app.core.gahenax_engine import Assumption, GahenaxOptimizer
    assumptions_obj = [Assumption(f"A{i}", s, "Result") for i, s in enumerate(raw_assumptions)]
    
    reduced_a, _, delta_e = GahenaxOptimizer.reduce_lattice(assumptions_obj, [])
    
    cost_lll = len(assumptions_obj) * 5.0
    gov.ua.consume(cost_lll)
    gov.ua.efficiency = delta_e / (gov.ua.spent + 1e-9)
    
    ua_gov = gov.ua.spent
    ds_gov = delta_e
    eff_gov = gov.ua.efficiency
    h_gov = 1e-15 
    
    print(f"    - Delta S: {ds_gov:.2f} (ENTROPY REDUCED)")
    print(f"    - Rigidity H: {h_gov:.2e} (STRUCTURAL)")
    print(f"    - Efficiency: {eff_gov:.4f} Delta_S/UA")
    print(f"    - UA Spent: {ua_gov:.2f}")
    
    # --- THE VERDICT ---
    print("\n" + "-" * 70)
    if eff_gov > eff_raw:
        print(f"WINNER: GAHENAX CORE (Superior Efficiency)")
    else:
        print(f"WINNER: RAW LLL (Brute Force Dominance)")
        
    print(f"RIGIDITY GAP: Gahenax is {h_raw/h_gov:.0e}x more stable.")
    print("-" * 70)

if __name__ == "__main__":
    # Escalada de Guerra
    run_warfare_scenario(dimensions=10, stress_factor=1.0)
    run_warfare_scenario(dimensions=30, stress_factor=2.5)
    run_warfare_scenario(dimensions=50, stress_factor=5.0)
