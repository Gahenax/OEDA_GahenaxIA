# orchestrator/orchestrator.py
"""
Single-Orchestrator / Multi-Worker core.

Architecture invariants:
  1. SINGLE WRITER: Only this orchestrator writes to ledger.jsonl.
  2. LOCK ENFORCEMENT: orchestrator.lock prevents concurrent instances.
  3. RESUME-SAFE: State reconstructed from ledger replay on startup.
  4. DEDUP BY HASH: Canonical payload hash, not magic or faith.
  5. ATOMIC ACCEPTANCE: append → mark → save (in that order).
"""
from __future__ import annotations
import os
import json
import queue
import threading
from typing import Dict, Any, List, Optional, Set
from orchestrator.contracts import (
    Job, LedgerEvent, ResultPayload,
    AcceptVerdict, to_jsonl_line, sha256_json,
)


class SingleWriterOrchestrator:
    """
    Single-Orchestrator / Multi-Worker

    - Único writer de ledger.jsonl
    - State resume-safe (state.json)
    - Dedup por hash del payload canónico
    """

    def __init__(
        self,
        run_dir: str,
        run_id: str,
        eps_root: float = 1e-10,
        max_attempts: int = 3,
        checkpoint_every: int = 200,
    ):
        self.run_dir = run_dir
        self.run_id = run_id
        self.eps_root = eps_root
        self.max_attempts = max_attempts
        self.checkpoint_every = checkpoint_every

        os.makedirs(self.run_dir, exist_ok=True)
        os.makedirs(os.path.join(self.run_dir, "checkpoints"), exist_ok=True)

        self.state_path = os.path.join(self.run_dir, "state.json")
        self.ledger_path = os.path.join(self.run_dir, "ledger.jsonl")
        self.lock_path = os.path.join(self.run_dir, "orchestrator.lock")

        self.q: "queue.Queue[Optional[Dict[str, Any]]]" = queue.Queue()
        self.stop_event = threading.Event()

        self.seq: int = 0
        self.state: Dict[str, Any] = {
            "run_id": run_id,
            "jobs": {},       # job_id -> Job dict
            "done": 0,
            "failed": 0,
            "rejected": 0,
            "seq": 0,
        }

        # Dedup set: hashes of canonical payloads already accepted
        self.accepted_payload_hashes: Set[str] = set()

    # ─────────────── locking ───────────────
    def acquire_lock(self) -> None:
        """Acquire exclusive orchestrator lock. Raises if already held."""
        if os.path.exists(self.lock_path):
            raise RuntimeError(
                f"Lock exists ({self.lock_path}). "
                "Another orchestrator is running or a previous run crashed. "
                "Delete the lock manually only if you are certain no other instance is active."
            )
        with open(self.lock_path, "w", encoding="utf-8") as f:
            f.write(str(os.getpid()))

    def release_lock(self) -> None:
        """Release orchestrator lock."""
        try:
            os.remove(self.lock_path)
        except FileNotFoundError:
            pass

    # ─────────────── persistence ───────────────
    def load_state(self) -> None:
        """Load state from disk (if exists)."""
        if os.path.exists(self.state_path):
            with open(self.state_path, "r", encoding="utf-8") as f:
                self.state = json.load(f)
            self.seq = int(self.state.get("seq", 0))

    def save_state(self) -> None:
        """Atomic state save. Windows-safe with retry for OneDrive/antivirus locks."""
        tmp = self.state_path + ".tmp"
        data = json.dumps(self.state, indent=2, sort_keys=True)

        with open(tmp, "w", encoding="utf-8") as f:
            f.write(data)

        # os.replace can fail on Windows if OneDrive/antivirus holds a lock
        import time as _time
        for attempt in range(5):
            try:
                os.replace(tmp, self.state_path)
                return
            except PermissionError:
                _time.sleep(0.05 * (attempt + 1))

        # Fallback: direct write (non-atomic but functional)
        try:
            os.remove(tmp)
        except OSError:
            pass
        with open(self.state_path, "w", encoding="utf-8") as f:
            f.write(data)

    def append_ledger(self, evt: LedgerEvent) -> None:
        """Append a single event to the append-only ledger."""
        with open(self.ledger_path, "a", encoding="utf-8") as f:
            f.write(to_jsonl_line(evt) + "\n")

    def replay_ledger_for_dedup(self) -> None:
        """
        Reconstruct accepted_payload_hashes from existing ledger.
        This is the REAL resume mechanism — not state.json, which is
        a convenience cache. Ledger is source of truth.
        """
        if not os.path.exists(self.ledger_path):
            return
        with open(self.ledger_path, "r", encoding="utf-8") as f:
            for line_num, line in enumerate(f, 1):
                line = line.strip()
                if not line:
                    continue
                try:
                    obj = json.loads(line)
                    payload = obj.get("payload")
                    if isinstance(payload, dict):
                        ph = sha256_json(payload)
                        self.accepted_payload_hashes.add(ph)
                    self.seq = max(self.seq, int(obj.get("seq", 0)))
                except (json.JSONDecodeError, KeyError, TypeError) as exc:
                    raise RuntimeError(
                        f"Ledger parse failed at line {line_num} "
                        f"(possible corruption): {exc}. "
                        "Fix ledger before resume."
                    ) from exc

        self.state["seq"] = self.seq

    # ─────────────── job management ───────────────
    def register_jobs(self, jobs: List[Job]) -> None:
        """Register new jobs (idempotent — skips already-known job_ids)."""
        for j in jobs:
            if j.job_id not in self.state["jobs"]:
                self.state["jobs"][j.job_id] = {
                    "job_id": j.job_id,
                    "t_start": j.t_start,
                    "t_end": j.t_end,
                    "stride": j.stride,
                    "attempts": j.attempts,
                    "status": j.status,
                    "last_error": j.last_error,
                }
        self.save_state()

    def get_next_job(self) -> Optional[Job]:
        """Simple FIFO scheduler: return first PENDING job, mark RUNNING."""
        for job_id, jd in self.state["jobs"].items():
            if jd["status"] == "PENDING":
                jd["status"] = "RUNNING"
                self.save_state()
                return Job(**{k: jd[k] for k in Job.__dataclass_fields__})
        return None

    def mark_job_done(self, job_id: str) -> None:
        """Mark job as completed."""
        self.state["jobs"][job_id]["status"] = "DONE"
        self.state["done"] += 1
        self.save_state()

    def mark_job_failed(self, job_id: str, err: str) -> None:
        """Mark job failed. Retry if attempts < max_attempts, else FAILED."""
        jd = self.state["jobs"][job_id]
        jd["attempts"] = int(jd.get("attempts", 0)) + 1
        jd["last_error"] = err
        if jd["attempts"] >= self.max_attempts:
            jd["status"] = "FAILED"
            self.state["failed"] += 1
        else:
            jd["status"] = "PENDING"  # retry
        self.save_state()

    # ─────────────── acceptance gate ───────────────
    def accept_result(
        self,
        worker_id: int,
        job_id: str,
        payload: Dict[str, Any],
    ) -> AcceptVerdict:
        """
        The core acceptance pipeline:
          1. Schema validation
          2. Tolerance check (|root_val| < eps)
          3. Dedup by canonical hash
          4. Atomic: append → mark → save
        """
        # Gate 1: Schema
        if not ResultPayload.validate(payload):
            self.state["rejected"] += 1
            self.save_state()
            return "REJECTED_SCHEMA"

        # Gate 2: Tolerance
        root_val = float(payload["root_val"])
        if abs(root_val) > self.eps_root:
            self.state["rejected"] += 1
            self.save_state()
            return "REJECTED_TOL"

        # Gate 3: Dedup
        ph = sha256_json(payload)
        if ph in self.accepted_payload_hashes:
            return "REJECTED_DUP"

        # Atomic acceptance
        self.seq += 1
        evt = LedgerEvent.from_parts(self.run_id, worker_id, job_id, self.seq, payload)

        self.append_ledger(evt)
        self.accepted_payload_hashes.add(ph)
        self.state["seq"] = self.seq
        self.save_state()

        return "ACCEPTED"

    # ─────────────── reducer loop ───────────────
    def reducer_loop(self) -> None:
        """
        Single-threaded reducer: drains the queue and processes messages.
        This is the ONLY code path that writes to the ledger.
        """
        accepted_since_ckpt = 0

        while not self.stop_event.is_set():
            item = self.q.get()
            if item is None:
                break

            kind = item.get("kind")

            if kind == "RESULT":
                verdict = self.accept_result(
                    worker_id=int(item["worker_id"]),
                    job_id=str(item["job_id"]),
                    payload=item["payload"],
                )
                if verdict == "ACCEPTED":
                    accepted_since_ckpt += 1
                    if item.get("job_done", False):
                        self.mark_job_done(str(item["job_id"]))

                # Checkpoint at interval
                if accepted_since_ckpt >= self.checkpoint_every:
                    ckpt_path = os.path.join(
                        self.run_dir, "checkpoints",
                        f"checkpoint_seq_{self.seq}.json",
                    )
                    with open(ckpt_path, "w", encoding="utf-8") as f:
                        json.dump({
                            "seq": self.seq,
                            "done": self.state["done"],
                            "failed": self.state["failed"],
                        }, f)
                    accepted_since_ckpt = 0

            elif kind == "ERROR":
                self.mark_job_failed(
                    str(item["job_id"]),
                    str(item.get("error", "unknown")),
                )

    # ─────────────── worker interface ───────────────
    def submit_from_worker(self, msg: Dict[str, Any]) -> None:
        """Workers push messages here. Orchestrator drains them in reducer_loop."""
        self.q.put(msg)

    def shutdown(self) -> None:
        """Signal the reducer loop to exit."""
        self.stop_event.set()
        self.q.put(None)
