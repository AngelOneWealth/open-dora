"""
In-memory job store for async sync jobs.

Each sync (repo or org) gets a SyncJob with:
  - An append-only replay buffer (`lines`) so late-connecting clients catch up
  - A set of subscriber queues for live fan-out
  - A done_event so already-finished jobs immediately signal new subscribers
"""
import asyncio
import time
import uuid
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class SyncJob:
    job_id: str
    status: str = "running"                          # running | done | error
    created_at: float = field(default_factory=time.monotonic)
    lines: list[bytes] = field(default_factory=list) # append-only replay buffer
    waiters: set[asyncio.Queue] = field(default_factory=set)
    done_event: asyncio.Event = field(default_factory=asyncio.Event)
    return_code: Optional[int] = None


_jobs: dict[str, SyncJob] = {}


def create_job() -> SyncJob:
    """Allocate a new SyncJob, register it, and return it."""
    job = SyncJob(job_id=str(uuid.uuid4()))
    _jobs[job.job_id] = job
    return job


def get_job(job_id: str) -> Optional[SyncJob]:
    return _jobs.get(job_id)


async def publish_line(job: SyncJob, line: bytes) -> None:
    """Append line to the replay buffer and fan-out to all active subscribers."""
    job.lines.append(line)
    for q in list(job.waiters):
        q.put_nowait(line)


async def finish_job(job: SyncJob, return_code: int) -> None:
    """Mark the job finished and send a sentinel None to all subscribers."""
    job.status = "done" if return_code == 0 else "error"
    job.return_code = return_code
    job.done_event.set()
    for q in list(job.waiters):
        q.put_nowait(None)


def subscribe(job: SyncJob) -> tuple[asyncio.Queue, int]:
    """
    Register a new subscriber.

    Returns (queue, replay_offset).  The caller should first yield
    job.lines[:replay_offset] (already-seen history), then drain the queue
    until it receives None (the done sentinel).

    If the job is already finished, None is pushed into the queue immediately
    so the consumer exits after replaying the full history.
    """
    q: asyncio.Queue = asyncio.Queue()
    offset = len(job.lines)   # snapshot *before* registering so there's no gap
    job.waiters.add(q)
    if job.done_event.is_set():
        q.put_nowait(None)
    return q, offset


def unsubscribe(job: SyncJob, q: asyncio.Queue) -> None:
    job.waiters.discard(q)


async def cleanup_old_jobs(max_age_seconds: float = 3600.0) -> None:
    """Remove completed jobs older than max_age_seconds from memory."""
    cutoff = time.monotonic() - max_age_seconds
    stale = [
        jid for jid, j in list(_jobs.items())
        if j.status != "running" and j.created_at < cutoff
    ]
    for jid in stale:
        del _jobs[jid]


async def periodic_cleanup_loop() -> None:
    """Background task: clean up old jobs every hour."""
    while True:
        await asyncio.sleep(3600)
        await cleanup_old_jobs()
