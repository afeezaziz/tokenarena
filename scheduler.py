import os
import json
import logging
from datetime import timedelta

import redis
from rq import Queue
from rq_scheduler import Scheduler

# Env
REDIS_URL = os.environ.get("REDIS_URL", "redis://localhost:6379/0")
RQ_QUEUES = [q.strip() for q in os.environ.get("RQ_QUEUES", "default").split(",") if q.strip()] or ["default"]
SCHEDULE_SECONDS = int(os.environ.get("NOSTR_SCHEDULE_SECONDS", "60") or 60)
FUNDS_SCHEDULE_SECONDS = int(os.environ.get("FUNDS_SCHEDULE_SECONDS", "60") or 60)

# Nostr poll defaults (these are passed to the job; the job also reads env)
NOSTR_RELAY_URL = os.environ.get("NOSTR_RELAY_URL", "wss://relay.damus.io")
NOSTR_FILTERS = None
try:
    NOSTR_FILTERS = json.loads(os.environ.get("NOSTR_FILTERS", "{}") or "{}")
except Exception:
    NOSTR_FILTERS = None

logging.basicConfig(level=os.environ.get("LOG_LEVEL", "INFO"))
log = logging.getLogger("scheduler")


def main():
    conn = redis.from_url(REDIS_URL)
    # Use the first queue for scheduling by default
    queue_name = (RQ_QUEUES[0] if RQ_QUEUES else "default")
    scheduler = Scheduler(queue_name=queue_name, connection=conn)

    # Avoid duplicates and schedule Nostr poll
    tag_nostr = "nostr_poll_periodic"
    tag_funds = "funds_reconcile_periodic"
    for job in scheduler.get_jobs():
        if job.meta.get("tag") in {tag_nostr, tag_funds}:
            log.info("Clearing existing scheduled job: %s", job)
            scheduler.cancel(job)

    log.info("Scheduling app.tasks.nostr_poll every %s seconds on queue '%s'", SCHEDULE_SECONDS, queue_name)
    job1 = scheduler.schedule(
        scheduled_time=None,
        func="app.tasks.nostr_poll",
        args=[],
        kwargs={"relay_url": NOSTR_RELAY_URL, "filters": NOSTR_FILTERS},
        interval=SCHEDULE_SECONDS,
        repeat=None,
        queue_name=queue_name,
    )
    job1.meta["tag"] = tag_nostr
    job1.save_meta()

    log.info("Scheduling app.tasks.reconcile_funds every %s seconds on queue '%s'", FUNDS_SCHEDULE_SECONDS, queue_name)
    job2 = scheduler.schedule(
        scheduled_time=None,
        func="app.tasks.reconcile_funds",
        args=[],
        kwargs={},
        interval=FUNDS_SCHEDULE_SECONDS,
        repeat=None,
        queue_name=queue_name,
    )
    job2.meta["tag"] = tag_funds
    job2.save_meta()

    # Keep process alive to allow the scheduler's internal loop to run
    try:
        scheduler.run()
    except KeyboardInterrupt:
        log.info("Scheduler stopped")


if __name__ == "__main__":
    main()
