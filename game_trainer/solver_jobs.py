from __future__ import annotations

import hashlib
import json
import sqlite3
import subprocess
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Sequence
from uuid import uuid4


@dataclass
class SolverJob:
    job_id: str
    request: dict[str, Any]
    cache_key: str
    status: str = "queued"
    events: list[dict[str, Any]] = field(default_factory=list)
    error: str | None = None
    cache_hit: bool = False


class SolverJobStore:
    """SQLite persistence for job recovery and completed-result caching."""

    def __init__(self, path: Path) -> None:
        self.path = path
        path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS solver_jobs (
                    job_id TEXT PRIMARY KEY,
                    cache_key TEXT NOT NULL,
                    request_json TEXT NOT NULL,
                    status TEXT NOT NULL,
                    events_json TEXT NOT NULL,
                    error TEXT,
                    cache_hit INTEGER NOT NULL DEFAULT 0,
                    created_at REAL NOT NULL,
                    updated_at REAL NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_solver_jobs_cache
                    ON solver_jobs(cache_key, status, updated_at DESC);
                """
            )
            connection.execute(
                "UPDATE solver_jobs SET status = 'failed', error = 'solver process interrupted by restart', updated_at = ? WHERE status IN ('queued', 'running')",
                (time.time(),),
            )

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path, timeout=10)
        connection.row_factory = sqlite3.Row
        return connection

    def save(self, job: SolverJob) -> None:
        now = time.time()
        with self._connect() as connection:
            connection.execute(
                """INSERT INTO solver_jobs
                   (job_id, cache_key, request_json, status, events_json, error, cache_hit, created_at, updated_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                   ON CONFLICT(job_id) DO UPDATE SET
                     status=excluded.status, events_json=excluded.events_json,
                     error=excluded.error, cache_hit=excluded.cache_hit, updated_at=excluded.updated_at""",
                (
                    job.job_id, job.cache_key, json.dumps(job.request), job.status,
                    json.dumps(job.events), job.error, int(job.cache_hit), now, now,
                ),
            )

    def load(self, job_id: str) -> SolverJob | None:
        with self._connect() as connection:
            row = connection.execute("SELECT * FROM solver_jobs WHERE job_id = ?", (job_id,)).fetchone()
        return self._job(row) if row else None

    def cached(self, cache_key: str) -> SolverJob | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM solver_jobs WHERE cache_key = ? AND status = 'complete' ORDER BY updated_at DESC LIMIT 1",
                (cache_key,),
            ).fetchone()
        return self._job(row) if row else None

    @staticmethod
    def _job(row: sqlite3.Row) -> SolverJob:
        return SolverJob(
            row["job_id"], json.loads(row["request_json"]), row["cache_key"], row["status"],
            json.loads(row["events_json"]), row["error"], bool(row["cache_hit"]),
        )


class SolverJobManager:
    """Runs the native solver out of process with durable cache and cancellation."""

    CACHE_FIELDS = (
        "schemaVersion", "oopRange", "ipRange", "flop", "turn", "startingPot",
        "effectiveStack", "betSizes", "raiseSizes", "maxIterations", "targetExploitability",
    )

    def __init__(self, command: Sequence[str], database_path: Path | None = None) -> None:
        if not command:
            raise ValueError("solver command cannot be empty")
        self.command = tuple(command)
        self.store = SolverJobStore(database_path) if database_path is not None else None
        self._jobs: dict[str, SolverJob] = {}
        self._processes: dict[str, subprocess.Popen[bytes]] = {}
        self._lock = threading.Lock()

    @classmethod
    def from_binary(cls, path: Path, database_path: Path | None = None) -> "SolverJobManager":
        if not path.is_file():
            raise FileNotFoundError(path)
        return cls((str(path),), database_path)

    def submit(self, request: dict[str, Any]) -> dict[str, Any]:
        self._validate(request)
        cache_key = self._cache_key(request)
        cached = self.store.cached(cache_key) if self.store else None
        job = SolverJob(f"solve-{uuid4().hex[:12]}", dict(request), cache_key)
        if cached is not None:
            complete = dict(cached.events[-1])
            complete["mode"] = request["mode"]
            job.status = "complete"
            job.events = [complete]
            job.cache_hit = True
        with self._lock:
            self._jobs[job.job_id] = job
            self._persist(job)
        if not job.cache_hit:
            threading.Thread(target=self._run, args=(job.job_id,), daemon=True).start()
        return self.snapshot(job.job_id)

    def snapshot(self, job_id: str) -> dict[str, Any]:
        with self._lock:
            job = self._jobs.get(job_id)
            if job is None and self.store is not None:
                job = self.store.load(job_id)
                if job is not None:
                    self._jobs[job_id] = job
            if job is None:
                raise KeyError(f"unknown solver job: {job_id}")
            return {
                "jobId": job.job_id, "status": job.status, "mode": job.request["mode"],
                "cacheKey": job.cache_key, "cacheHit": job.cache_hit,
                "events": list(job.events), "error": job.error,
            }

    def cancel(self, job_id: str) -> dict[str, Any]:
        with self._lock:
            job = self._jobs.get(job_id)
            if job is None and self.store is not None:
                job = self.store.load(job_id)
                if job is not None:
                    self._jobs[job_id] = job
            if job is None:
                raise KeyError(f"unknown solver job: {job_id}")
            if job.status not in ("complete", "failed", "cancelled"):
                job.status = "cancelled"
                job.error = "cancelled by user"
                self._persist(job)
            process = self._processes.get(job_id)
        if process is not None and process.poll() is None:
            process.terminate()
        return self.snapshot(job_id)

    def wait(self, job_id: str, timeout: float = 10.0) -> dict[str, Any]:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            snapshot = self.snapshot(job_id)
            if snapshot["status"] in ("complete", "failed", "cancelled"):
                return snapshot
            time.sleep(0.01)
        return self.snapshot(job_id)

    def _run(self, job_id: str) -> None:
        with self._lock:
            job = self._jobs[job_id]
            if job.status == "cancelled":
                return
            job.status = "running"
            self._persist(job)
            request_bytes = json.dumps(job.request, separators=(",", ":")).encode()
        try:
            process = subprocess.Popen(
                self.command, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                stderr=subprocess.PIPE, text=False,
            )
            with self._lock:
                self._processes[job_id] = process
                cancelled = self._jobs[job_id].status == "cancelled"
            if cancelled:
                process.terminate()
            assert process.stdin is not None and process.stdout is not None
            if not cancelled:
                process.stdin.write(request_bytes)
            process.stdin.close()
            for line in process.stdout:
                event = json.loads(line)
                with self._lock:
                    job = self._jobs[job_id]
                    if job.status == "cancelled":
                        break
                    job.events.append(event)
                    self._persist(job)
            return_code = process.wait(timeout=5)
            stderr = process.stderr.read().decode(errors="replace") if process.stderr else ""
            process.stdout.close()
            if process.stderr is not None:
                process.stderr.close()
            with self._lock:
                job = self._jobs[job_id]
                if job.status != "cancelled":
                    if return_code == 0 and job.events and job.events[-1].get("event") == "complete":
                        job.status = "complete"
                    else:
                        job.status = "failed"
                        job.error = job.events[-1].get("error") if job.events else stderr.strip() or f"worker exited {return_code}"
                    self._persist(job)
                self._processes.pop(job_id, None)
        except Exception as error:
            with self._lock:
                job = self._jobs[job_id]
                if job.status != "cancelled":
                    job.status = "failed"
                    job.error = str(error)
                    self._persist(job)
                self._processes.pop(job_id, None)

    def _persist(self, job: SolverJob) -> None:
        if self.store is not None:
            self.store.save(job)

    @classmethod
    def _cache_key(cls, request: dict[str, Any]) -> str:
        canonical = {field: request[field] for field in cls.CACHE_FIELDS}
        return hashlib.sha256(json.dumps(canonical, separators=(",", ":"), sort_keys=True).encode()).hexdigest()

    @staticmethod
    def _validate(request: dict[str, Any]) -> None:
        required = {
            "schemaVersion", "mode", "oopRange", "ipRange", "flop", "turn",
            "startingPot", "effectiveStack", "betSizes", "raiseSizes",
            "maxIterations", "targetExploitability", "reportEvery",
        }
        missing = required - request.keys()
        if missing:
            raise ValueError(f"missing solver fields: {', '.join(sorted(missing))}")
        if request["mode"] not in ("visual", "headless"):
            raise ValueError("mode must be visual or headless")
        if type(request["maxIterations"]) is not int or not 1 <= request["maxIterations"] <= 100_000:
            raise ValueError("maxIterations must be between 1 and 100000")
        if type(request["reportEvery"]) is not int or request["reportEvery"] <= 0 or request["reportEvery"] % 10:
            raise ValueError("reportEvery must be a positive multiple of 10")
        if len(str(request["oopRange"])) > 10_000 or len(str(request["ipRange"])) > 10_000:
            raise ValueError("range input is too large")
