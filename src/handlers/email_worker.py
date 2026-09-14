"""Purelymail IMAP Background Worker Daemon for Payaam.

Continuously polls the configured Purelymail inbox for incoming emails,
passes unread messages into the Strands Agent core engine, and routes
responses automatically.
"""

import asyncio
import logging
import signal
import sys
from typing import Optional
from src.agent.core import payaam_agent
from src.config import settings
from src.services.email_service import email_service

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("payaam.handlers.worker")


class EmailWorker:
    """IMAP background polling worker."""

    def __init__(self, poll_interval_seconds: int = 15) -> None:
        self.poll_interval = poll_interval_seconds
        self.is_running = False

    async def run_once(self) -> int:
        """Runs a single poll cycle across the IMAP inbox."""
        logger.info("Checking Purelymail IMAP for unread messages...")
        unread_emails = email_service.fetch_unread_emails(mark_as_read=True)
        if not unread_emails:
            logger.info("Inbox check complete: 0 unread messages.")
            return 0

        logger.info(f"Processing {len(unread_emails)} unread message(s)...")
        for em in unread_emails:
            try:
                result = await payaam_agent.process_inbound_email(em)
                logger.info(f"Processed email from {em.from_address}: route={result.get('route')}")
            except Exception as exc:
                logger.error(f"Error processing email from {em.from_address}: {exc}", exc_info=True)

        return len(unread_emails)

    async def start(self) -> None:
        """Starts the infinite background polling loop."""
        self.is_running = True
        logger.info(f"Payaam Email Worker started (Poll interval: {self.poll_interval}s)")

        while self.is_running:
            try:
                await self.run_once()
            except Exception as exc:
                logger.error(f"Unexpected worker poll error: {exc}", exc_info=True)

            await asyncio.sleep(self.poll_interval)

    def stop(self) -> None:
        """Stops the worker loop."""
        logger.info("Stopping Payaam Email Worker...")
        self.is_running = False


worker = EmailWorker()


def handle_exit(sig, frame):
    worker.stop()
    sys.exit(0)


if __name__ == "__main__":
    signal.signal(signal.SIGINT, handle_exit)
    signal.signal(signal.SIGTERM, handle_exit)
    asyncio.run(worker.start())
