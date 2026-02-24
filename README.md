# Gahenax Core: Sovereign Inference Engine

Gahenax Core is a High-Speed Operational Suite designed for governed reasoning. It leverages **Lattice Reduction (LLL)** to optimize inference paths and treats computation as a physical process governed by **Athena Units (UA)** through the **P over NP** paradigm.

## 1. Project Objective
To provide a non-narrative, verifiable engine that reduces decision entropy while maintaining absolute computational honesty. Gahenax Core does not "hallucinate" or "please" the user; it reduces the logical lattice to find the shortest provable vector (SV).

## 2. Governed Contract
All emissions follow the [Gahenax Contract](docs/CONTRACT.md). Responses are strictly structured into:
- **Technical Reframe**: Neutral variable-based restatement.
- **Rigor Exclusions**: Explicit boundaries of what cannot be concluded.
- **Lattice Status**: Provisional vs. Rigorous findings.
- **Critical Assumptions**: Candidates for lattice reduction.
- **Closure Interrogatory**: High-precision validation questions.
- **Gahenax Verdict**: Decisions conditioned by UA audit.

## 3. UA Physics (P over NP)
Computations are measured in **Athena Units (UA)**.
- **Goal**: Maximize entropy reduction ($\Delta S$) per unit of effort ($UA$).
- **Paradigm**: We do not solve NP-Hard problems globally. We optimize local decidability paths where $P \approx NP$ under a fixed budget.
- **Metadata**: Every response includes an audit of `spent_ua` and `efficiency_ratio`.

## 4. LLL Optimizer
The engine treats reasoning as a high-dimensional lattice.
- **Reduction**: Uses algorithms inspired by **Deep-LLL** to prune redundant logical branches.
- **Speed**: Optimized velocity by "calculating less garbage" through structural pruning.
- **Termination**: If $\Delta S/UA$ drops below the threshold defined in `policy.yaml`, the optimization cycle terminates to prevent computational stall.

## 5. Operational Audit & Persistence (gahenax_ops)
The system includes `gahenax_ops.py` for high-speed operational management:
- **UA Persistence**: Redis (HOT) for real-time budgets and SQLite (COLD) for append-only audit logs.
- **Falsifiability Ledger**: Every execution is hashed and recorded to prevent narrative drift.
- **Rigor Console**: A unified contract that strips CoT and focus on falsifiable claims.

To run the operational benchmark:
```bash
python gahenax_ops.py bench --cases benchmarks/bench_cases.jsonl --out benchmarks/results/gahenax_core_operational.json
```

## 6. Benchmarks & Evidence
We do not publish claims without a ledger.
- **Latency**: p50/p95 tracking of reduction cycles.
- **Efficiency**: $\Delta S/UA$ distribution across the test suite.
- **Compliance**: 100% adherence to the Gahenax Contract.

To run benchmarks:
```bash
python benchmarks/run_bench.py
```
Check `benchmarks/results/` for the latest "ledger" of measurable evidence.

---
*Author: Antigravity / Gahenax Team*  
*License: Governed Intellectual Property*
