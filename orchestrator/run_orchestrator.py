# orchestrator/run_orchestrator.py
"""
Execution harness: 1 Orchestrator + N Workers.

Runs locally with multiprocessing. The same logical architecture
applies if workers run on remote machines (swap transport layer).

Usage:
    python -m orchestrator.run_orchestrator
"""
from __future__ import annotations
from typing import List
import multiprocessing as mp
import threading
import time
import sys
import os

# Ensure parent directory is importable
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from orchestrator.contracts import Job
from orchestrator.orchestrator import SingleWriterOrchestrator
from orchestrator.worker_entry import compute_zero_candidates


def worker_proc(
    worker_id: int,
    job_q: "mp.Queue",
    out_q: "mp.Queue",
) -> None:
    """
    Worker process: pulls jobs, computes candidates, streams results.
    NEVER writes to disk. Only pushes to out_q.
    """
    while True:
        job = job_q.get()
        if job is None:
            break  # poison pill

        job_id, t_start, t_end, stride = job
        try:
            payloads = compute_zero_candidates(t_start, t_end, stride)

            # Stream results one by one
            for p in payloads:
                out_q.put({
                    "kind": "RESULT",
                    "worker_id": worker_id,
                    "job_id": job_id,
                    "payload": p,
                    "job_done": False,
                })

            # Signal job completion with the last payload
            out_q.put({
                "kind": "RESULT",
                "worker_id": worker_id,
                "job_id": job_id,
                "payload": payloads[-1] if payloads else {
                    "t": t_start, "root_val": 0.0, "meta": {"empty": True}
                },
                "job_done": True,
            })
        except Exception as e:
            out_q.put({
                "kind": "ERROR",
                "worker_id": worker_id,
                "job_id": job_id,
                "error": repr(e),
            })

    # Worker signals exit
    out_q.put({"kind": "WORKER_EXIT", "worker_id": worker_id})


def main() -> None:
    """Main entry: configure, dispatch, reduce, shutdown."""
    run_dir = "run_latido"
    run_id = "Latido_20260220_SINGLE_ORCH"
    n_workers = min(4, os.cpu_count() or 2)

    print(f"+{'='*46}+", flush=True)
    print(f"|  SINGLE-ORCHESTRATOR / MULTI-WORKER ENGINE   |", flush=True)
    print(f"|  Workers: {n_workers}  |  Run: {run_id:<20s}   |", flush=True)
    print(f"+{'='*46}+", flush=True)

    orch = SingleWriterOrchestrator(
        run_dir=run_dir,
        run_id=run_id,
        eps_root=1e-10,
        checkpoint_every=200,
    )
    orch.acquire_lock()

    try:
        # Resume from previous state + ledger replay
        orch.load_state()
        orch.replay_ledger_for_dedup()
        print(f"[RESUME] seq={orch.seq}, "
              f"accepted_hashes={len(orch.accepted_payload_hashes)}", flush=True)

        # Define jobs: 20 chunks of T-space
        jobs: List[Job] = []
        t0 = 5000.0
        for i in range(20):
            a = t0 + i * 10.0
            b = a + 10.0
            jobs.append(Job(
                job_id=f"chunk_{a:.0f}_{b:.0f}",
                t_start=a,
                t_end=b,
                stride=0.5,
            ))
        orch.register_jobs(jobs)
        total_jobs = len(orch.state["jobs"])
        print(f"[JOBS] {total_jobs} registered", flush=True)

        # Multiprocessing queues
        job_q: mp.Queue = mp.Queue()
        out_q: mp.Queue = mp.Queue()

        # Start reducer thread (single writer)
        reducer_t = threading.Thread(target=orch.reducer_loop, daemon=True)
        reducer_t.start()

        # Start worker processes
        workers = []
        for wid in range(n_workers):
            p = mp.Process(
                target=worker_proc,
                args=(wid, job_q, out_q),
                daemon=True,
            )
            p.start()
            workers.append(p)

        # Phase 1: Dispatch all jobs
        dispatched = 0
        while True:
            job = orch.get_next_job()
            if job is None:
                break
            job_q.put((job.job_id, job.t_start, job.t_end, job.stride))
            dispatched += 1
        print(f"[DISPATCH] {dispatched} jobs sent to workers", flush=True)

        # Send poison pills to workers
        for _ in workers:
            job_q.put(None)

        # Phase 2: Drain results until all workers exit
        workers_exited = 0
        drain_count = 0
        while workers_exited < n_workers:
            try:
                msg = out_q.get(timeout=5.0)
            except Exception:
                # Check if workers are still alive
                alive = sum(1 for p in workers if p.is_alive())
                if alive == 0:
                    break
                continue

            if msg.get("kind") == "WORKER_EXIT":
                workers_exited += 1
                print(f"  [EXIT] Worker {msg['worker_id']} finished", flush=True)
            else:
                orch.submit_from_worker(msg)
                drain_count += 1
                if drain_count % 100 == 0:
                    print(f"  [DRAIN] {drain_count} messages processed, "
                          f"seq={orch.state['seq']}", flush=True)

        # Final drain — anything left in the queue
        while True:
            try:
                msg = out_q.get_nowait()
                if msg.get("kind") != "WORKER_EXIT":
                    orch.submit_from_worker(msg)
                    drain_count += 1
            except Exception:
                break

        print(f"[DRAIN] Total: {drain_count} messages processed", flush=True)

        # Wait for workers to fully terminate
        for p in workers:
            p.join(timeout=5)

        # Give reducer time to finish processing the queue
        time.sleep(1.0)

        # Shutdown reducer
        orch.shutdown()
        reducer_t.join(timeout=5)

        # Summary
        print(f"\n{'='*50}", flush=True)
        print(f"  DONE:     {orch.state['done']}", flush=True)
        print(f"  FAILED:   {orch.state['failed']}", flush=True)
        print(f"  REJECTED: {orch.state['rejected']}", flush=True)
        print(f"  SEQ:      {orch.state['seq']}", flush=True)
        print(f"  HASHES:   {len(orch.accepted_payload_hashes)}", flush=True)
        print(f"{'='*50}", flush=True)

    finally:
        orch.release_lock()
        print("[LOCK] Released.", flush=True)


if __name__ == "__main__":
    main()
