# app/services/scheduler.py
import logging
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy.orm import Session

from app.core.database import SessionLocal
from app.models.booking import Booking
from app.services.notifications import notify_reminder

logger = logging.getLogger(__name__)

EST = ZoneInfo("America/New_York")


def _parse_booking_datetime(date, time_slot: str) -> datetime | None:
    """
    Combine a booking's date + time_slot string into a timezone-aware datetime in EST.
    time_slot format: '9:00 AM', '4:20 AM', '12:30 PM', etc.
    """
    try:
        dt_naive = datetime.strptime(f"{date} {time_slot}", "%Y-%m-%d %I:%M %p")
        return dt_naive.replace(tzinfo=EST)
    except Exception as e:
        logger.warning(
            f"Could not parse booking datetime — date={date}, time_slot={time_slot}: {e}"
        )
        return None


def send_upcoming_reminders() -> None:
    """
    Runs every minute via APScheduler.
    Finds confirmed bookings starting in 13–17 minutes (EST) with no reminder sent yet,
    fires email + SMS reminder, and stamps reminded_at to prevent duplicates.
    """
    db: Session = SessionLocal()
    try:
        now_est = datetime.now(tz=EST)
        window_start = now_est + timedelta(minutes=13)
        window_end = now_est + timedelta(minutes=17)

        logger.info(
            f"Scheduler tick — checking for reminders between "
            f"{window_start.strftime('%I:%M %p')} and {window_end.strftime('%I:%M %p')} EST"
        )

        # Pull all confirmed bookings with no reminder sent yet.
        # Filter by date first in SQL to keep the query efficient,
        # then do precise time matching in Python.
        today = now_est.date()
        tomorrow = today + timedelta(days=1)

        candidates = (
            db.query(Booking)
            .filter(
                Booking.status == "confirmed",
                Booking.reminded_at.is_(None),
                Booking.date.in_([today, tomorrow]),
            )
            .all()
        )

        fired = 0
        for booking in candidates:
            call_dt = _parse_booking_datetime(booking.date, booking.time_slot)
            if call_dt is None:
                continue

            if window_start <= call_dt <= window_end:
                logger.info(
                    f"Firing reminder for booking #{booking.id} — "
                    f"{booking.employer_name} at {booking.time_slot} EST"
                )
                try:
                    notify_reminder(
                        employer_name=booking.employer_name,
                        email=booking.employer_email,
                        phone=booking.phone or "",
                        date=str(booking.date),
                        time_slot=booking.time_slot,
                        meeting_url=booking.meeting_url or "",
                    )
                    booking.reminded_at = datetime.utcnow()
                    db.commit()
                    fired += 1
                except Exception as e:
                    logger.error(f"Reminder failed for booking #{booking.id}: {e}")
                    db.rollback()

        if fired:
            logger.info(f"Scheduler — {fired} reminder(s) sent.")
        else:
            logger.debug("Scheduler — no reminders due this tick.")

    except Exception as e:
        logger.error(f"Scheduler error: {e}")
    finally:
        db.close()
