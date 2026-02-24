"""
skill_registry_bootstrap.py
============================
Canonical SkillRegistry — 3 example skills, graduated by risk.

  INFORMATIONAL  → AUTO     (no side effects, safe)
  PRODUCTIVE     → CONFIRM  (writes to filesystem)
  SYSTEMIC       → LOCKED   (modifies CMR ledger schema)

All skills start enabled but can be quarantined by the circuit breaker.
Side-effecting skills start with dry_run_default=False (production ready)
but callers can override with dry_run=True.
"""

from __future__ import annotations

from gahenax_app.core.gahenax_gateway import (
    SkillSpec, SkillRegistry, RiskLevel, RollbackPolicy
)


def build_registry() -> SkillRegistry:
    registry = SkillRegistry()

    # ── SKILL 1: INFORMATIONAL (AUTO) ────────────────────────────────────
    # Safe to auto-execute. Read-only. No side effects.
    # Example: answer a governance question from the CMR ledger.
    registry.register(SkillSpec(
        skill_id="gahenax.query_ledger",
        intent_tags=["audit", "query", "ledger", "status", "stats"],
        description="Read-only query of the CMR ledger. Returns stats and latest hash.",
        risk_level=RiskLevel.AUTO,
        required_inputs=["window_n"],
        output_schema="LedgerQueryResult",
        ua_cost_estimate=0.5,
        timeout_ms=2000,
        idempotent=True,
        side_effects=[],
        rollback=RollbackPolicy.NONE,
        enabled=True,
        dry_run_default=False,
    ))

    # ── SKILL 2: PRODUCTIVE (CONFIRM) ────────────────────────────────────
    # Writes a snapshot JSON to disk. Requires user confirmation.
    # Idempotent: same inputs → same file (deterministic hash).
    registry.register(SkillSpec(
        skill_id="gahenax.generate_snapshot",
        intent_tags=["snapshot", "seal", "export", "record", "sign"],
        description="Generates a signed CMR snapshot JSON and writes it to snapshots/.",
        risk_level=RiskLevel.CONFIRM,
        required_inputs=["snapshot_label"],
        output_schema="Snapshot",
        ua_cost_estimate=1.5,
        timeout_ms=5000,
        idempotent=True,
        side_effects=["file:write"],
        rollback=RollbackPolicy.BEST_EFFORT,
        enabled=True,
        dry_run_default=False,
    ))

    # ── SKILL 3: SYSTEMIC / READ-ONLY START (LOCKED) ─────────────────────
    # Alters the CMR database schema (e.g. adds columns).
    # Starts LOCKED. Only executable in AUDIT mode + risk_override=True.
    # Rollback REQUIRED — the system must be able to undo.
    registry.register(SkillSpec(
        skill_id="gahenax.migrate_ledger_schema",
        intent_tags=["migration", "schema", "db", "upgrade", "alter"],
        description="Applies a migration to the CMR SQLite schema. Irreversible without backup.",
        risk_level=RiskLevel.LOCKED,
        required_inputs=["migration_id", "sql_patch"],
        output_schema="MigrationResult",
        ua_cost_estimate=4.0,
        timeout_ms=15000,
        idempotent=True,  # migration_id prevents double-application
        side_effects=["db:write", "db:schema"],
        rollback=RollbackPolicy.REQUIRED,
        enabled=True,
        dry_run_default=True,   # Always starts simulated
    ))

    return registry


if __name__ == "__main__":
    reg = build_registry()
    print("=== SKILL REGISTRY (v1.1.1) ===\n")
    print(reg.summary())

    print("\n=== SPEC HASHES (tamper-evident) ===")
    for s in reg.all():
        print(f"  {s.skill_id:<40} {s.spec_hash()}")
