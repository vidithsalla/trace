import dramatiq
from dramatiq.brokers.redis import RedisBroker

from worker.settings import settings
from worker.tasks import export_job, ingest_document

broker = RedisBroker(url=settings.redis_url)
dramatiq.set_broker(broker)


def main() -> None:
    print("Trace worker configured with Redis broker at", settings.redis_url)
    print("Registered tasks:", ingest_document.actor_name, export_job.actor_name)


if __name__ == "__main__":
    main()
