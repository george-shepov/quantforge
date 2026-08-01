from __future__ import annotations

import os

from redis import Redis
from rq import Queue, Worker


def main() -> None:
    connection = Redis.from_url(os.getenv("REDIS_URL", "redis://redis:6379/0"))
    worker = Worker([Queue("quantforge", connection=connection)], connection=connection)
    worker.work(with_scheduler=False)


if __name__ == "__main__":
    main()
