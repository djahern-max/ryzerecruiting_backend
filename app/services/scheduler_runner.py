# app/services/scheduler_runner.py
"""
Standalone APScheduler process — runs independently of gunicorn.
Started and managed by systemd (ryze-scheduler.service).

This ensures only ONE scheduler process runs, preventing duplicate
reminder emails caused by multiple gunicorn workers each starting
their own scheduler instance.
"""
import logging
import sys
import os

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s — %(message)s",
)

from apscheduler.schedulers.blocking import BlockingScheduler
from app.services.scheduler import send_upcoming_reminders

logger = logging.getLogger(__name__)

if __name__ == "__main__":
    logger.info("RYZE Scheduler starting...")

    scheduler = BlockingScheduler()
    scheduler.add_job(send_upcoming_reminders, "interval", minutes=1)

    try:
        logger.info("Scheduler running — checking for reminders every 60 seconds.")
        scheduler.start()
    except (KeyboardInterrupt, SystemExit):
        logger.info("Scheduler stopped.")
