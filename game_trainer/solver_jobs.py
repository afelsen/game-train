from __future__ import annotations

import json
import subprocess
import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Sequence
from uuid import uuid4


@dataclass
class SolverJob:
    job_id: str
    request: dict[str, Any]
    status: str = "queued"
    events: list[dict[str, Any]] = field(default_factory=list)
    error: str | None = None


class SolverJobManager:
    """Runs the native solver out of process and retains JSON-line progress events."""

    def __init__(self, command: Sequence[str]) -> None:
        if not command:
            raise ValueError("solver command cannot be empty")
        self.command = tuple(command)
        self._jobs: dict[str, SolverJob] = {}
        self._lock = threading.Lock()

    @classmethod
    def from_binary(cls, path: Path) -> "SolverJobManager":
        if not path.is_file():
            raise FileNotFoundError(path)
        return cls((str(path),))

    def submit(self, request: dict[str, Any]) -> dict[str, Any]:
        self._validate(request)
        job = SolverJob(f"solve-{uuid4().hex[:12]}", dict(request))
        with self._lock:
            self._jobs[job.job_id] = job
        threading.Thread(target=self._run, args=(job.job_id,), daemon=True).start()
        return self.snapshot(job.job_id)

    def snapshot(self, job_id: str) -> dict[str, Any]:
        with self._lock:
            try:
                job = self._jobs[job_id]
            except KeyError as error:
                raise KeyError(f"unknown solver job: {job_id}") from error
            return {
                "jobId": job.job_id,
                "status": job.status,
                "mode": job.request["mode"],
                "events": list(job.events),
                "error": job.error,
            }

    def wait(self, job_id: str, timeout: float = 10.0) -> dict[str, Any]:
        deadline = threading.Event()
        remaining = timeout
        while remaining > 0:
            snapshot = self.snapshot(job_id)
            if snapshot["status"] in ("complete", "failed"):
                return snapshot
            step = min(0.01, remaining)
            deadline.wait(step)
            remaining -= step
        return self.snapshot(job_id)

    def _run(self, job_id: str) -> None:
        with self._lock:
            job = self._jobs[job_id]
            job.status = "running"
            request_bytes = json.dumps(job.request, separators=(",", ":")).encode()
        try:
            process = subprocess.Popen(
                self.command,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=False,
            )
            assert process.stdin is not None and process.stdout is not None
            process.stdin.write(request_bytes)
            process.stdin.close()
            for line in process.stdout:
                event = json.loads(line)
                with self._lock:
                    self._jobs[job_id].events.append(event)
            return_code = process.wait(timeout=5)
            stderr = process.stderr.read().decode(errors="replace") if process.stderr else ""
            process.stdout.close()
            if process.stderr is not None:
                process.stderr.close()
            with self._lock:
                job = self._jobs[job_id]
                if return_code == 0 and job.events and job.events[-1].get("event") == "complete":
                    job.status = "complete"
                else:
                    job.status = "failed"
                    job.error = job.events[-1].get("error") if job.events else stderr.strip() or f"worker exited {return_code}"
        except Exception as error:  # Worker failures must not escape the background thread.
            with self._lock:
                self._jobs[job_id].status = "failed"
                self._jobs[job_id].error = str(error)

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
