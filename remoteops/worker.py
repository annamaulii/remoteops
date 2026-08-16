import logging
import signal
from collections.abc import Callable
from threading import Event

from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session

from remoteops.config import settings
from remoteops.database import SessionFactory
from remoteops.webhooks import process_due_deliveries

logger = logging.getLogger(__name__)


def run_worker(
    *,
    stop_event: Event,
    poll_seconds: float,
    session_factory: Callable = SessionFactory,
    processor: Callable[[Session], int] = process_due_deliveries,
) -> None:
    """Process due webhooks until shutdown is requested."""
    while not stop_event.is_set():
        try:
            with session_factory() as session:
                processed = processor(session)
                if processed:
                    logger.info("webhook_deliveries_processed count=%d", processed)
        except OperationalError:
            logger.warning("webhook worker database operation failed")
        if stop_event.wait(poll_seconds):
            return


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    stop_event = Event()

    def request_stop(_signum: int, _frame: object) -> None:
        stop_event.set()

    signal.signal(signal.SIGTERM, request_stop)
    signal.signal(signal.SIGINT, request_stop)
    logger.info("webhook_worker_started")
    run_worker(
        stop_event=stop_event,
        poll_seconds=settings.webhook_worker_poll_seconds,
    )
    logger.info("webhook_worker_stopped")


if __name__ == "__main__":
    main()
