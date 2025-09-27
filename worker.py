import os
from rq import Worker, Queue
import redis

REDIS_URL = os.environ.get("REDIS_URL", "redis://localhost:6379/0")
QUEUES = [q.strip() for q in os.environ.get("RQ_QUEUES", "default").split(",") if q.strip()] or ["default"]


def get_redis_connection():
    return redis.from_url(REDIS_URL)


def main():
    conn = get_redis_connection()
    queues = [Queue(name, connection=conn) for name in QUEUES]
    worker = Worker(queues, connection=conn)
    worker.work()


if __name__ == "__main__":
    main()
