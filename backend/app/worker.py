"""RQ worker entrypoint: processes generation jobs end-to-end, resumable per step."""
import logging
import uuid
from datetime import datetime, timezone

from redis import Redis
from rq import Worker as RQWorker

from app.config import get_settings
from app.worker_tasks import run_generation_job

log = logging.getLogger(__name__)


def main():
    settings = get_settings()
    conn = Redis.from_url(settings.redis_url)
    worker = RQWorker(
        ["generation"],
        connection=conn,
        name=f"generation-worker@{uuid.uuid4().hex[:8]}",
    )
    log.info("starting generation worker on queue 'generation'")
    worker.work()


def _now():
    return datetime.now(timezone.utc)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    main()
