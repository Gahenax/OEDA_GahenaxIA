"""
Gahenax Core - Benchmark Runner (The Ledger)
-------------------------------------------
Measures Latency, Efficiency (Delta S / UA), and Contract Compliance.
"""

import time
import json
import os
import sys
from pathlib import Path

# Fix path to import core
backend_path = str(Path(__file__).parent.parent / "backend")
sys.path.append(backend_path)

from gahenax_app.core.gahenax_engine import GahenaxGovernor, RenderProfile

def run_benchmarks():
    # 1. Define Test Cases
    cases = [
        {"id": "CASE_001", "text": "¿Es buen momento para comprar Cripto X?"},
        {"id": "CASE_002", "text": "Optimiza mi estrategia de reclutamiento de ingenieros."},
        {"id": "CASE_003", "text": "Analiza la paradoja de Fermi bajo el criterio de Gahenax."},
        {"id": "CASE_004", "text": "Dime qué debería desayunar hoy para ser más productivo."}, # Trap: Personal/Subjective
    ]

    results = []
    print(f"Starting Benchmarks for Gahenax Core...")

    for case in cases:
        gov = GahenaxGovernor(budget_ua=500.0)
        start_time = time.time()
        
        # Run Cycle
        output = gov.run_inference_cycle(case["text"])
        
        end_time = time.time()
        latency = (end_time - start_time) * 1000 # ms
        
        # Metrics
        res = {
            "case_id": case["id"],
            "latency_ms": latency,
            "ua_spent": gov.ua.spent,
            "efficiency": gov.ua.efficiency,
            "verdict_strength": output.verdict.strength.value,
            "assumptions_reduced": any(a.status == "reduced" for a in output.assumptions)
        }
        results.append(res)
        print(f"[{case['id']}] Latency: {latency:.2f}ms | UA: {gov.ua.spent} | Eff: {gov.ua.efficiency:.4f}")

    # 2. Save Ledger
    output_path = Path(__file__).parent / "results" / "gahenax_core.json"
    with open(output_path, "w") as f:
        json.dump({
            "timestamp": time.time(),
            "engine": "Gahenax_Core_V1",
            "summary": {
                "avg_latency": sum(r["latency_ms"] for r in results) / len(results),
                "avg_efficiency": sum(r["efficiency"] for r in results) / len(results)
            },
            "detailed": results
        }, f, indent=4)

    print(f"\nBenchmarks completed. Ledger saved to: {output_path}")

if __name__ == "__main__":
    run_benchmarks()
