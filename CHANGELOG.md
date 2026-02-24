# Changelog - Gahenax Core

All notable changes to this project will be documented in this file.
The project adheres to **Falsifiable Contractual Design (FCD)**.

## [1.1.1] - 2026-02-19
### Baseline Sealed & Birth Certificate Anexed 🛡️🧬
- **Snapshot Hash**: `e0feed40b647...` (See `snapshots/gahenax_core_v1.1.1_baseline.snapshot.json`)
- **Birth Certificate Hash**: `fb99e024c1fb...` (See `snapshots/gahenax_core_v1.1.1_acta_nacimiento.json`)
- **Audit Mode**: Protocolo Semáforo v2.0 (Chronos-Hodge).
- **Ledger State**: 1,005 records (cumulative), 100% integrity verified.
- **FCD Criteria Active**:
  - A1: Entropy Reduction per UA.
  - A2: Schema Adherence & Latency Stability.
  - A3: Chronos-Hodge Structural Rigidity.
  - A4: Athena Unit (UA) Budgeting.

### Added
- **CMR (Canonical Measurement Recorder)**: Headless, immutable, append-only ledger with cryptographic chaining.
- **CMR Tools**: CLI for verification, signed snapshots, and FCD gate evaluation.
- **Rigor Console**: Streamlit-based auditor with microsecond precision and hard governance gates.
- **Stress & Tamper Suite**: High-speed validation of chain integrity.

### Changed
- Refactored `gahenax_ops.py` to use institucionalized CMR.
- API now automatically logs every inference to the sovereign ledger.
- Latency measurement upgraded to float (ms/µs precision).

---
*Author: Antigravity / Gahenax Team*
