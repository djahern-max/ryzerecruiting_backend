# app/services/email.py
import resend
import logging
from app.core.config import settings

logger = logging.getLogger(__name__)

resend.api_key = settings.RESEND_API_KEY


# ---------------------------------------------------------------------------
# AI Brief formatter
# ---------------------------------------------------------------------------


def _format_brief_for_email(brief: dict) -> str:
    """
    Convert a structured AI brief dict into readable HTML for the recruiter email.
    Handles both the structured case and the raw fallback case gracefully.
    Returns an empty string if brief is empty or falsy.
    """
    if not brief:
        return ""

    # Fallback path: JSON parse failed, raw text was stored under 'ai_brief_raw'
    if "ai_brief_raw" in brief:
        return brief["ai_brief_raw"]

    sections = []

    if brief.get("company_overview"):
        sections.append(
            f"<strong>COMPANY OVERVIEW</strong><br>{brief['company_overview']}"
        )

    if brief.get("industry"):
        sections.append(f"<strong>INDUSTRY</strong><br>{brief['industry']}")

    if brief.get("estimated_size"):
        sections.append(f"<strong>ESTIMATED SIZE</strong><br>{brief['estimated_size']}")

    if brief.get("hiring_needs"):
        needs = brief["hiring_needs"]
        if isinstance(needs, list):
            needs_html = ", ".join(needs)
        else:
            needs_html = str(needs)
        sections.append(f"<strong>LIKELY HIRING NEEDS</strong><br>{needs_html}")

    if brief.get("talking_points"):
        pts = brief["talking_points"]
        if isinstance(pts, list):
            pts_html = "<br>".join(f"• {p}" for p in pts)
        else:
            pts_html = str(pts)
        sections.append(f"<strong>KEY TALKING POINTS</strong><br>{pts_html}")

    if brief.get("red_flags"):
        sections.append(
            f"<strong>RED FLAGS / CONSIDERATIONS</strong><br>{brief['red_flags']}"
        )

    return "<br><br>".join(sections)


# ---------------------------------------------------------------------------
# Email functions
# ---------------------------------------------------------------------------


def send_employer_confirmation(
    employer_name: str,
    employer_email: str,
    company_name: str,
    date: str,
    time_slot: str,
) -> None:
    """Send a booking request confirmation email to the employer.
    Zoom link is NOT included yet — sent separately when admin confirms."""

    resend.Emails.send(
        {
            "from": f"RYZE.ai <{settings.FROM_EMAIL}>",
            "to": [employer_email],
            "subject": "Your call request with RYZE.ai has been received!",
            "html": f"""
        <div style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto; padding: 32px; background: #f9fafb; border-radius: 8px;">
            <h1 style="color: #0a66c2; margin-bottom: 8px;">RYZE.ai</h1>
            <hr style="border: none; border-top: 1px solid #e2e8f0; margin-bottom: 24px;" />

            <h2 style="color: #111827; margin-bottom: 4px;">We received your call request</h2>
            <p style="color: #64748b; font-size: 14px; margin-top: 0;">We'll review it shortly and confirm your Zoom link.</p>

            <p style="color: #334155; font-size: 15px;">Hi {employer_name},</p>

            <p style="color: #334155; font-size: 15px;">
                Thanks for reaching out! We've received your request for a discovery call and
                will confirm your booking shortly. Once confirmed, you'll receive a separate
                email with your Zoom meeting link.
            </p>

            <div style="background: #ffffff; border: 1px solid #e2e8f0; border-radius: 8px; padding: 20px; margin: 24px 0;">
                <table style="width: 100%; border-collapse: collapse;">
                    <tr>
                        <td style="padding: 8px 0; color: #64748b; font-size: 14px; width: 40%;">Company</td>
                        <td style="padding: 8px 0; color: #111827; font-size: 14px; font-weight: 600;">{company_name or "—"}</td>
                    </tr>
                    <tr>
                        <td style="padding: 8px 0; color: #64748b; font-size: 14px;">Date</td>
                        <td style="padding: 8px 0; color: #111827; font-size: 14px; font-weight: 600;">{date}</td>
                    </tr>
                    <tr>
                        <td style="padding: 8px 0; color: #64748b; font-size: 14px;">Time</td>
                        <td style="padding: 8px 0; color: #111827; font-size: 14px; font-weight: 600;">{time_slot} EST</td>
                    </tr>
                </table>
            </div>

            <p style="color: #334155; font-size: 15px;">
                If you have any questions in the meantime, simply reply to this email.
            </p>

            <p style="color: #334155; font-size: 15px;">Talk soon,<br/><strong>Dane</strong><br/>RYZE.ai</p>

            <hr style="border: none; border-top: 1px solid #e2e8f0; margin-top: 32px;" />
            <p style="color: #94a3b8; font-size: 12px; text-align: center;">
                © 2026 RYZE.ai. All rights reserved.
            </p>
        </div>
        """,
        }
    )

    logger.info(f"Booking request confirmation sent to {employer_email}")


def send_admin_notification(
    employer_name: str,
    employer_email: str,
    company_name: str,
    website_url: str,
    date: str,
    time_slot: str,
    phone: str,
    notes: str,
) -> None:
    """Send a new booking request notification email to Dane — action required."""

    admin_dashboard_url = f"{settings.FRONTEND_URL}/admin"

    resend.Emails.send(
        {
            "from": f"RYZE.ai <{settings.FROM_EMAIL}>",
            "to": [settings.ADMIN_EMAIL],
            "subject": f"New Call Request — {employer_name} on {date} at {time_slot} — Confirmation Required",
            "html": f"""
        <div style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto; padding: 32px; background: #f9fafb; border-radius: 8px;">
            <h1 style="color: #0a66c2; margin-bottom: 8px;">RYZE.ai</h1>
            <hr style="border: none; border-top: 1px solid #e2e8f0; margin-bottom: 24px;" />

            <h2 style="color: #111827; margin-bottom: 4px;">New Call Request 📋</h2>
            <p style="color: #64748b; font-size: 14px; margin-top: 0;">
                A new employer has requested a discovery call. Please confirm in the Admin Dashboard
                to create their Zoom meeting and send them their link.
            </p>

            <div style="background: #ffffff; border: 1px solid #e2e8f0; border-radius: 8px; padding: 20px; margin: 24px 0;">
                <table style="width: 100%; border-collapse: collapse;">
                    <tr>
                        <td style="padding: 8px 0; color: #64748b; font-size: 14px; width: 40%;">Name</td>
                        <td style="padding: 8px 0; color: #111827; font-size: 14px; font-weight: 600;">{employer_name}</td>
                    </tr>
                    <tr>
                        <td style="padding: 8px 0; color: #64748b; font-size: 14px;">Email</td>
                        <td style="padding: 8px 0; color: #111827; font-size: 14px;">
                            <a href="mailto:{employer_email}" style="color: #0a66c2;">{employer_email}</a>
                        </td>
                    </tr>
                    <tr>
                        <td style="padding: 8px 0; color: #64748b; font-size: 14px;">Company</td>
                        <td style="padding: 8px 0; color: #111827; font-size: 14px; font-weight: 600;">{company_name or "—"}</td>
                    </tr>
                    <tr>
                        <td style="padding: 8px 0; color: #64748b; font-size: 14px;">Website</td>
                        <td style="padding: 8px 0; color: #111827; font-size: 14px;">
                            {"<a href='" + website_url + "' style='color: #0a66c2;'>" + website_url + "</a>" if website_url else "—"}
                        </td>
                    </tr>
                    <tr>
                        <td style="padding: 8px 0; color: #64748b; font-size: 14px;">Phone</td>
                        <td style="padding: 8px 0; color: #111827; font-size: 14px;">{phone or "—"}</td>
                    </tr>
                    <tr>
                        <td style="padding: 8px 0; color: #64748b; font-size: 14px;">Date</td>
                        <td style="padding: 8px 0; color: #111827; font-size: 14px; font-weight: 600;">{date}</td>
                    </tr>
                    <tr>
                        <td style="padding: 8px 0; color: #64748b; font-size: 14px;">Time</td>
                        <td style="padding: 8px 0; color: #111827; font-size: 14px; font-weight: 600;">{time_slot} EST</td>
                    </tr>
                    <tr>
                        <td style="padding: 8px 0; color: #64748b; font-size: 14px; vertical-align: top;">Notes</td>
                        <td style="padding: 8px 0; color: #111827; font-size: 14px;">{notes or "—"}</td>
                    </tr>
                </table>
            </div>

            <a href="{admin_dashboard_url}"
               style="display: inline-block; background: #0a66c2; color: white; text-decoration: none;
                      font-weight: 700; padding: 12px 24px; border-radius: 8px; font-size: 14px;">
                Confirm in Admin Dashboard →
            </a>

            <hr style="border: none; border-top: 1px solid #e2e8f0; margin-top: 32px;" />
            <p style="color: #94a3b8; font-size: 12px; text-align: center;">
                © 2026 RYZE.ai. All rights reserved.
            </p>
        </div>
        """,
        }
    )

    logger.info(f"Admin notification sent for booking by {employer_email}")


def send_meeting_confirmed(
    employer_name: str,
    employer_email: str,
    company_name: str,
    date: str,
    time_slot: str,
    meeting_url: str,
    phone: str = "",
    notes: str = "",
    ai_brief: dict = None,
) -> None:
    """Send confirmed call email with Zoom link to both the employer and the recruiter (Dane)."""

    if ai_brief is None:
        ai_brief = {}

    # --- Employer email ---
    resend.Emails.send(
        {
            "from": f"RYZE.ai <{settings.FROM_EMAIL}>",
            "to": [employer_email],
            "subject": "Your call with RYZE.ai is confirmed — here's your Zoom link!",
            "html": f"""
        <div style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto; padding: 32px; background: #f9fafb; border-radius: 8px;">
            <h1 style="color: #0a66c2; margin-bottom: 8px;">RYZE.ai</h1>
            <hr style="border: none; border-top: 1px solid #e2e8f0; margin-bottom: 24px;" />

            <h2 style="color: #111827; margin-bottom: 4px;">Your call is confirmed! ✅</h2>
            <p style="color: #64748b; font-size: 14px; margin-top: 0;">
                We're looking forward to speaking with you. Here are your call details.
            </p>

            <div style="background: #ffffff; border: 1px solid #e2e8f0; border-radius: 8px; padding: 20px; margin: 24px 0;">
                <table style="width: 100%; border-collapse: collapse;">
                    <tr>
                        <td style="padding: 8px 0; color: #64748b; font-size: 14px; width: 40%;">Company</td>
                        <td style="padding: 8px 0; color: #111827; font-size: 14px; font-weight: 600;">{company_name or "—"}</td>
                    </tr>
                    <tr>
                        <td style="padding: 8px 0; color: #64748b; font-size: 14px;">Date</td>
                        <td style="padding: 8px 0; color: #111827; font-size: 14px; font-weight: 600;">{date}</td>
                    </tr>
                    <tr>
                        <td style="padding: 8px 0; color: #64748b; font-size: 14px;">Time</td>
                        <td style="padding: 8px 0; color: #111827; font-size: 14px; font-weight: 600;">{time_slot} EST</td>
                    </tr>
                    <tr>
                        <td style="padding: 8px 0; color: #64748b; font-size: 14px;">Your Zoom Link</td>
                        <td style="padding: 8px 0; font-size: 14px;">
                            <a href="{meeting_url}" style="color: #0a66c2; font-weight: 600; text-decoration: none;">
                                Join Zoom Call →
                            </a>
                        </td>
                    </tr>
                </table>
            </div>

            <a href="{meeting_url}"
               style="display: inline-block; background: #0a66c2; color: white; text-decoration: none;
                      font-weight: 700; padding: 12px 24px; border-radius: 8px; font-size: 14px; margin-bottom: 24px;">
                Join Zoom Call →
            </a>

            <p style="color: #334155; font-size: 15px;">
                If you have any questions beforehand, simply reply to this email.
            </p>

            <p style="color: #334155; font-size: 15px;">See you soon,<br/><strong>Dane</strong><br/>RYZE.ai</p>

            <hr style="border: none; border-top: 1px solid #e2e8f0; margin-top: 32px;" />
            <p style="color: #94a3b8; font-size: 12px; text-align: center;">
                © 2026 RYZE.ai. All rights reserved.
            </p>
        </div>
        """,
        }
    )

    logger.info(f"Meeting confirmed email with Zoom link sent to {employer_email}")

    # --- Recruiter (admin) email with AI brief ---
    brief_html_content = _format_brief_for_email(ai_brief)
    ai_brief_html = (
        f"""
        <div style="margin: 24px 0;">
            <h3 style="color: #111827; font-size: 15px; margin-bottom: 8px;">
                ⚡ Pre-Call Intelligence Brief
            </h3>
            <div style="background: #f0f9ff; border-left: 4px solid #0a66c2;
                        border-radius: 0 6px 6px 0; padding: 16px;">
                <div style="font-family: Arial, sans-serif; font-size: 13px;
                            color: #1e3a5f; line-height: 1.8;">{brief_html_content}</div>
            </div>
        </div>
        """
        if brief_html_content
        else ""
    )

    resend.Emails.send(
        {
            "from": f"RYZE.ai <{settings.FROM_EMAIL}>",
            "to": [settings.ADMIN_EMAIL],
            "subject": f"Call Confirmed — {employer_name} ({company_name}) on {date} at {time_slot}",
            "html": f"""
        <div style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto; padding: 32px; background: #f9fafb; border-radius: 8px;">
            <h1 style="color: #0a66c2; margin-bottom: 8px;">RYZE.ai</h1>
            <hr style="border: none; border-top: 1px solid #e2e8f0; margin-bottom: 24px;" />

            <h2 style="color: #111827; margin-bottom: 4px;">Call Confirmed ✅</h2>
            <p style="color: #64748b; font-size: 14px; margin-top: 0;">
                You've confirmed this call. A Zoom link has been sent to the employer.
                Here's everything you need to prepare.
            </p>

            <div style="background: #ffffff; border: 1px solid #e2e8f0; border-radius: 8px; padding: 20px; margin: 24px 0;">
                <table style="width: 100%; border-collapse: collapse;">
                    <tr>
                        <td style="padding: 8px 0; color: #64748b; font-size: 14px; width: 40%;">Name</td>
                        <td style="padding: 8px 0; color: #111827; font-size: 14px; font-weight: 600;">{employer_name}</td>
                    </tr>
                    <tr>
                        <td style="padding: 8px 0; color: #64748b; font-size: 14px;">Email</td>
                        <td style="padding: 8px 0; color: #111827; font-size: 14px;">
                            <a href="mailto:{employer_email}" style="color: #0a66c2;">{employer_email}</a>
                        </td>
                    </tr>
                    <tr>
                        <td style="padding: 8px 0; color: #64748b; font-size: 14px;">Company</td>
                        <td style="padding: 8px 0; color: #111827; font-size: 14px; font-weight: 600;">{company_name or "—"}</td>
                    </tr>
                    <tr>
                        <td style="padding: 8px 0; color: #64748b; font-size: 14px;">Phone</td>
                        <td style="padding: 8px 0; color: #111827; font-size: 14px;">{phone or "—"}</td>
                    </tr>
                    <tr>
                        <td style="padding: 8px 0; color: #64748b; font-size: 14px;">Date</td>
                        <td style="padding: 8px 0; color: #111827; font-size: 14px; font-weight: 600;">{date}</td>
                    </tr>
                    <tr>
                        <td style="padding: 8px 0; color: #64748b; font-size: 14px;">Time</td>
                        <td style="padding: 8px 0; color: #111827; font-size: 14px; font-weight: 600;">{time_slot} EST</td>
                    </tr>
                    <tr>
                        <td style="padding: 8px 0; color: #64748b; font-size: 14px; vertical-align: top;">Notes</td>
                        <td style="padding: 8px 0; color: #111827; font-size: 14px;">{notes or "—"}</td>
                    </tr>
                    <tr>
                        <td style="padding: 8px 0; color: #64748b; font-size: 14px;">Zoom Link</td>
                        <td style="padding: 8px 0; font-size: 14px;">
                            <a href="{meeting_url}" style="color: #0a66c2; font-weight: 600; text-decoration: none;">
                                Join Zoom Call →
                            </a>
                        </td>
                    </tr>
                </table>
            </div>

            {ai_brief_html}

            <a href="{meeting_url}"
               style="display: inline-block; background: #0a66c2; color: white; text-decoration: none;
                      font-weight: 700; padding: 12px 24px; border-radius: 8px; font-size: 14px; margin-bottom: 24px;">
                Join Zoom Call →
            </a>

            <hr style="border: none; border-top: 1px solid #e2e8f0; margin-top: 32px;" />
            <p style="color: #94a3b8; font-size: 12px; text-align: center;">
                © 2026 RYZE.ai. All rights reserved.
            </p>
        </div>
        """,
        }
    )

    logger.info(
        f"Admin confirmation email with Zoom link sent to {settings.ADMIN_EMAIL}"
    )


def send_cancellation_email(
    employer_name: str,
    employer_email: str,
    company_name: str,
    date: str,
    time_slot: str,
) -> None:
    """Notify both the employer and the recruiter (Dane) that a booking has been cancelled."""

    # --- Employer email ---
    resend.Emails.send(
        {
            "from": f"RYZE.ai <{settings.FROM_EMAIL}>",
            "to": [employer_email],
            "subject": "Your call with RYZE.ai has been cancelled",
            "html": f"""
        <div style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto; padding: 32px; background: #f9fafb; border-radius: 8px;">
            <h1 style="color: #0a66c2; margin-bottom: 8px;">RYZE.ai</h1>
            <hr style="border: none; border-top: 1px solid #e2e8f0; margin-bottom: 24px;" />

            <h2 style="color: #111827; margin-bottom: 16px;">Your call has been cancelled</h2>

            <p style="color: #334155; font-size: 15px;">Hi {employer_name},</p>

            <p style="color: #334155; font-size: 15px;">
                We're sorry to let you know that the following discovery call has been cancelled.
                Please reach out if you'd like to reschedule — we'd love to connect.
            </p>

            <div style="background: #ffffff; border: 1px solid #e2e8f0; border-radius: 8px; padding: 20px; margin: 24px 0;">
                <table style="width: 100%; border-collapse: collapse;">
                    <tr>
                        <td style="padding: 8px 0; color: #64748b; font-size: 14px; width: 40%;">Company</td>
                        <td style="padding: 8px 0; color: #111827; font-size: 14px; font-weight: 600;">{company_name or "—"}</td>
                    </tr>
                    <tr>
                        <td style="padding: 8px 0; color: #64748b; font-size: 14px;">Date</td>
                        <td style="padding: 8px 0; color: #111827; font-size: 14px; font-weight: 600;">{date}</td>
                    </tr>
                    <tr>
                        <td style="padding: 8px 0; color: #64748b; font-size: 14px;">Time</td>
                        <td style="padding: 8px 0; color: #111827; font-size: 14px; font-weight: 600;">{time_slot} EST</td>
                    </tr>
                </table>
            </div>

            <p style="color: #334155; font-size: 15px;">
                Visit <a href="{settings.FRONTEND_URL}" style="color: #0a66c2;">ryze.ai</a>
                to schedule a new time.
            </p>

            <p style="color: #334155; font-size: 15px;">Best,<br/><strong>Dane</strong><br/>RYZE.ai</p>

            <hr style="border: none; border-top: 1px solid #e2e8f0; margin-top: 32px;" />
            <p style="color: #94a3b8; font-size: 12px; text-align: center;">
                © 2026 RYZE.ai. All rights reserved.
            </p>
        </div>
        """,
        }
    )

    logger.info(f"Cancellation email sent to {employer_email}")

    # --- Admin (recruiter) cancellation email ---
    resend.Emails.send(
        {
            "from": f"RYZE.ai <{settings.FROM_EMAIL}>",
            "to": [settings.ADMIN_EMAIL],
            "subject": f"Call Cancelled — {employer_name} ({company_name}) on {date} at {time_slot}",
            "html": f"""
        <div style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto; padding: 32px; background: #f9fafb; border-radius: 8px;">
            <h1 style="color: #0a66c2; margin-bottom: 8px;">RYZE.ai</h1>
            <hr style="border: none; border-top: 1px solid #e2e8f0; margin-bottom: 24px;" />

            <h2 style="color: #111827; margin-bottom: 4px;">Call Cancelled ❌</h2>
            <p style="color: #64748b; font-size: 14px; margin-top: 0;">
                The following booking has been cancelled. The employer has been notified.
            </p>

            <div style="background: #ffffff; border: 1px solid #e2e8f0; border-radius: 8px; padding: 20px; margin: 24px 0;">
                <table style="width: 100%; border-collapse: collapse;">
                    <tr>
                        <td style="padding: 8px 0; color: #64748b; font-size: 14px; width: 40%;">Name</td>
                        <td style="padding: 8px 0; color: #111827; font-size: 14px; font-weight: 600;">{employer_name}</td>
                    </tr>
                    <tr>
                        <td style="padding: 8px 0; color: #64748b; font-size: 14px;">Email</td>
                        <td style="padding: 8px 0; color: #111827; font-size: 14px;">
                            <a href="mailto:{employer_email}" style="color: #0a66c2;">{employer_email}</a>
                        </td>
                    </tr>
                    <tr>
                        <td style="padding: 8px 0; color: #64748b; font-size: 14px;">Company</td>
                        <td style="padding: 8px 0; color: #111827; font-size: 14px; font-weight: 600;">{company_name or "—"}</td>
                    </tr>
                    <tr>
                        <td style="padding: 8px 0; color: #64748b; font-size: 14px;">Date</td>
                        <td style="padding: 8px 0; color: #111827; font-size: 14px; font-weight: 600;">{date}</td>
                    </tr>
                    <tr>
                        <td style="padding: 8px 0; color: #64748b; font-size: 14px;">Time</td>
                        <td style="padding: 8px 0; color: #111827; font-size: 14px; font-weight: 600;">{time_slot} EST</td>
                    </tr>
                </table>
            </div>

            <hr style="border: none; border-top: 1px solid #e2e8f0; margin-top: 32px;" />
            <p style="color: #94a3b8; font-size: 12px; text-align: center;">
                © 2026 RYZE.ai. All rights reserved.
            </p>
        </div>
        """,
        }
    )

    logger.info(f"Cancellation admin email sent to {settings.ADMIN_EMAIL}")


# ---------------------------------------------------------------------------
# Task 4: 15-minute reminder email
# ---------------------------------------------------------------------------


def send_reminder_email(
    employer_name: str,
    employer_email: str,
    date: str,
    time_slot: str,
    meeting_url: str,
) -> None:
    """Send a 15-minute reminder email with Zoom link directly to the employer."""

    resend.Emails.send(
        {
            "from": f"RYZE.ai <{settings.FROM_EMAIL}>",
            "to": [employer_email],
            "subject": "⏰ Your call starts in 15 minutes — Zoom link inside",
            "html": f"""
        <div style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto; padding: 32px; background: #f9fafb; border-radius: 8px;">
            <h1 style="color: #0a66c2; margin-bottom: 8px;">RYZE.ai</h1>
            <hr style="border: none; border-top: 1px solid #e2e8f0; margin-bottom: 24px;" />

            <h2 style="color: #111827; margin-bottom: 4px;">Your call starts in 15 minutes</h2>
            <p style="color: #64748b; font-size: 14px; margin-top: 0;">Get ready — your discovery call with RYZE.ai is coming up.</p>

            <p style="color: #334155; font-size: 15px;">Hi {employer_name},</p>

            <p style="color: #334155; font-size: 15px;">
                Just a quick heads-up that your intro call is starting soon.
                Click the button below to join the Zoom meeting.
            </p>

            <div style="background: #ffffff; border: 1px solid #e2e8f0; border-radius: 8px; padding: 20px; margin: 24px 0;">
                <table style="width: 100%; border-collapse: collapse;">
                    <tr>
                        <td style="padding: 8px 0; color: #64748b; font-size: 14px; width: 40%;">Date</td>
                        <td style="padding: 8px 0; color: #111827; font-size: 14px; font-weight: 600;">{date}</td>
                    </tr>
                    <tr>
                        <td style="padding: 8px 0; color: #64748b; font-size: 14px;">Time</td>
                        <td style="padding: 8px 0; color: #111827; font-size: 14px; font-weight: 600;">{time_slot} EST</td>
                    </tr>
                    <tr>
                        <td style="padding: 8px 0; color: #64748b; font-size: 14px;">Zoom Link</td>
                        <td style="padding: 8px 0; font-size: 14px;">
                            <a href="{meeting_url}" style="color: #0a66c2; font-weight: 600; text-decoration: none;">
                                Join Zoom Call →
                            </a>
                        </td>
                    </tr>
                </table>
            </div>

            <a href="{meeting_url}"
               style="display: inline-block; background: #0a66c2; color: white; text-decoration: none;
                      font-weight: 700; padding: 14px 28px; border-radius: 8px; font-size: 15px; margin-bottom: 24px;">
                Join Zoom Call →
            </a>

            <p style="color: #334155; font-size: 15px;">See you in a few minutes!<br/><strong>Dane</strong><br/>RYZE.ai</p>

            <hr style="border: none; border-top: 1px solid #e2e8f0; margin-top: 32px;" />
            <p style="color: #94a3b8; font-size: 12px; text-align: center;">
                © 2026 RYZE.ai. All rights reserved.
            </p>
        </div>
        """,
        }
    )

    logger.info(f"Reminder email sent to {employer_email} for {date} at {time_slot}")


# ---------------------------------------------------------------------------
# Recruiter-initiated outbound invite email
# ---------------------------------------------------------------------------


def send_recruiter_invite(
    contact_name: str,
    contact_email: str,
    contact_type: str,
    company_name: str,
    date: str,
    time_slot: str,
    meeting_url: str,
    notes: str = "",
    is_admin_copy: bool = False,
) -> None:
    type_label = "Employer" if contact_type == "employer" else "Candidate"
    company_line = f" ({company_name})" if company_name else ""

    if is_admin_copy:
        subject = f"Outbound Invite Sent — {contact_name}{company_line} on {date} at {time_slot}"
        intro_heading = f"Invite Sent — {type_label} ✉️"
        intro_sub = f"You've sent a meeting invite to {contact_name}{company_line}. Here's a copy for your records."
        greeting = f"<p style='color:#334155;font-size:15px;'>Contact: <strong>{contact_name}</strong></p>"
        sign_off = ""
    else:
        subject = (
            f"You're invited — Discovery call with RYZE.ai on {date} at {time_slot}"
        )
        intro_heading = "You're invited to a call with RYZE.ai 📅"
        intro_sub = "Dane Ahern from RYZE.ai has scheduled time to connect with you."
        greeting = f"<p style='color:#334155;font-size:15px;'>Hi {contact_name},</p>"
        sign_off = f"""
            <p style="color:#334155;font-size:15px;">
                Looking forward to connecting.<br/>
                <strong>Dane Ahern</strong><br/>
                RYZE.ai
            </p>
        """

    notes_row = (
        f"""
        <tr>
            <td style="padding:8px 0;color:#64748b;font-size:14px;vertical-align:top;">Notes</td>
            <td style="padding:8px 0;color:#111827;font-size:14px;">{notes}</td>
        </tr>
    """
        if notes
        else ""
    )

    company_row = (
        f"""
        <tr>
            <td style="padding:8px 0;color:#64748b;font-size:14px;">Company</td>
            <td style="padding:8px 0;color:#111827;font-size:14px;font-weight:600;">{company_name}</td>
        </tr>
    """
        if company_name
        else ""
    )

    resend.Emails.send(
        {
            "from": f"RYZE.ai <{settings.FROM_EMAIL}>",
            "to": [contact_email],
            "subject": subject,
            "html": f"""
        <div style="font-family:Arial,sans-serif;max-width:600px;margin:0 auto;padding:32px;background:#f9fafb;border-radius:8px;">
            <h1 style="color:#0a66c2;margin-bottom:8px;">RYZE.ai</h1>
            <hr style="border:none;border-top:1px solid #e2e8f0;margin-bottom:24px;" />
            <h2 style="color:#111827;margin-bottom:4px;">{intro_heading}</h2>
            <p style="color:#64748b;font-size:14px;margin-top:0;">{intro_sub}</p>
            {greeting}
            <div style="background:#ffffff;border:1px solid #e2e8f0;border-radius:8px;padding:20px;margin:24px 0;">
                <table style="width:100%;border-collapse:collapse;">
                    {company_row}
                    <tr>
                        <td style="padding:8px 0;color:#64748b;font-size:14px;width:40%;">Date</td>
                        <td style="padding:8px 0;color:#111827;font-size:14px;font-weight:600;">{date}</td>
                    </tr>
                    <tr>
                        <td style="padding:8px 0;color:#64748b;font-size:14px;">Time</td>
                        <td style="padding:8px 0;color:#111827;font-size:14px;font-weight:600;">{time_slot} EST</td>
                    </tr>
                    <tr>
                        <td style="padding:8px 0;color:#64748b;font-size:14px;">Zoom Link</td>
                        <td style="padding:8px 0;font-size:14px;">
                            <a href="{meeting_url}" style="color:#0a66c2;font-weight:600;text-decoration:none;">Join Zoom Call →</a>
                        </td>
                    </tr>
                    {notes_row}
                </table>
            </div>
            <a href="{meeting_url}"
               style="display:inline-block;background:#0a66c2;color:white;text-decoration:none;
                      font-weight:700;padding:12px 24px;border-radius:8px;font-size:14px;margin-bottom:24px;">
                Join Zoom Call →
            </a>
            {sign_off}
            <hr style="border:none;border-top:1px solid #e2e8f0;margin-top:32px;" />
            <p style="color:#94a3b8;font-size:12px;text-align:center;">© 2026 RYZE.ai. All rights reserved.</p>
        </div>
        """,
        }
    )

    logger.info(
        f"Recruiter invite email sent to {contact_email} "
        f"({'admin copy' if is_admin_copy else contact_type})"
    )


def send_candidate_booking_received_admin(
    candidate_name: str,
    candidate_email: str,
    date: str,
    time_slot: str,
    phone: str = "",
    notes: str = "",
) -> None:
    """Notify Dane that a candidate has requested a call."""

    admin_dashboard_url = f"{settings.FRONTEND_URL}/admin"

    resend.Emails.send(
        {
            "from": f"RYZE.ai <{settings.FROM_EMAIL}>",
            "to": [settings.ADMIN_EMAIL],
            "subject": f"New Candidate Call Request — {candidate_name} on {date} at {time_slot} — Confirmation Required",
            "html": f"""
        <div style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto; padding: 32px; background: #f9fafb; border-radius: 8px;">
            <h1 style="color: #0a66c2; margin-bottom: 8px;">RYZE.ai</h1>
            <hr style="border: none; border-top: 1px solid #e2e8f0; margin-bottom: 24px;" />

            <h2 style="color: #111827; margin-bottom: 4px;">New Candidate Call Request 🧑‍💼</h2>
            <p style="color: #64748b; font-size: 14px; margin-top: 0;">
                A candidate has requested a call. Please confirm in the Admin Dashboard
                to create their Zoom meeting and send them their link.
            </p>

            <div style="background: #ffffff; border: 1px solid #e2e8f0; border-radius: 8px; padding: 20px; margin: 24px 0;">
                <table style="width: 100%; border-collapse: collapse;">
                    <tr>
                        <td style="padding: 8px 0; color: #64748b; font-size: 14px; width: 40%;">Name</td>
                        <td style="padding: 8px 0; color: #111827; font-size: 14px; font-weight: 600;">{candidate_name}</td>
                    </tr>
                    <tr>
                        <td style="padding: 8px 0; color: #64748b; font-size: 14px;">Email</td>
                        <td style="padding: 8px 0; color: #111827; font-size: 14px;">
                            <a href="mailto:{candidate_email}" style="color: #0a66c2;">{candidate_email}</a>
                        </td>
                    </tr>
                    <tr>
                        <td style="padding: 8px 0; color: #64748b; font-size: 14px;">Phone</td>
                        <td style="padding: 8px 0; color: #111827; font-size: 14px;">{phone or "—"}</td>
                    </tr>
                    <tr>
                        <td style="padding: 8px 0; color: #64748b; font-size: 14px;">Date</td>
                        <td style="padding: 8px 0; color: #111827; font-size: 14px; font-weight: 600;">{date}</td>
                    </tr>
                    <tr>
                        <td style="padding: 8px 0; color: #64748b; font-size: 14px;">Time</td>
                        <td style="padding: 8px 0; color: #111827; font-size: 14px; font-weight: 600;">{time_slot} EST</td>
                    </tr>
                    <tr>
                        <td style="padding: 8px 0; color: #64748b; font-size: 14px; vertical-align: top;">Notes</td>
                        <td style="padding: 8px 0; color: #111827; font-size: 14px;">{notes or "—"}</td>
                    </tr>
                </table>
            </div>

            <a href="{admin_dashboard_url}"
               style="display: inline-block; background: #0a66c2; color: white; text-decoration: none;
                      font-weight: 700; padding: 12px 24px; border-radius: 8px; font-size: 14px;">
                Confirm in Admin Dashboard →
            </a>

            <hr style="border: none; border-top: 1px solid #e2e8f0; margin-top: 32px;" />
            <p style="color: #94a3b8; font-size: 12px; text-align: center;">
                © 2026 RYZE.ai. All rights reserved.
            </p>
        </div>
        """,
        }
    )

    logger.info(f"Candidate booking admin notification sent for {candidate_email}")


def send_candidate_booking_confirmation(
    candidate_name: str,
    candidate_email: str,
    date: str,
    time_slot: str,
) -> None:
    """Send a booking request confirmation to the candidate.
    Zoom link is NOT included yet — sent separately when admin confirms."""

    resend.Emails.send(
        {
            "from": f"RYZE.ai <{settings.FROM_EMAIL}>",
            "to": [candidate_email],
            "subject": "Your call request with RYZE.ai has been received!",
            "html": f"""
        <div style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto; padding: 32px; background: #f9fafb; border-radius: 8px;">
            <h1 style="color: #0a66c2; margin-bottom: 8px;">RYZE.ai</h1>
            <hr style="border: none; border-top: 1px solid #e2e8f0; margin-bottom: 24px;" />

            <h2 style="color: #111827; margin-bottom: 4px;">We received your call request</h2>
            <p style="color: #64748b; font-size: 14px; margin-top: 0;">We'll review it shortly and confirm your Zoom link.</p>

            <p style="color: #334155; font-size: 15px;">Hi {candidate_name},</p>

            <p style="color: #334155; font-size: 15px;">
                Thanks for reaching out! We've received your request for a call and
                will confirm your booking shortly. Once confirmed, you'll receive a
                separate email with your Zoom meeting link.
            </p>

            <div style="background: #ffffff; border: 1px solid #e2e8f0; border-radius: 8px; padding: 20px; margin: 24px 0;">
                <table style="width: 100%; border-collapse: collapse;">
                    <tr>
                        <td style="padding: 8px 0; color: #64748b; font-size: 14px; width: 40%;">Date</td>
                        <td style="padding: 8px 0; color: #111827; font-size: 14px; font-weight: 600;">{date}</td>
                    </tr>
                    <tr>
                        <td style="padding: 8px 0; color: #64748b; font-size: 14px;">Time</td>
                        <td style="padding: 8px 0; color: #111827; font-size: 14px; font-weight: 600;">{time_slot} EST</td>
                    </tr>
                </table>
            </div>

            <p style="color: #334155; font-size: 15px;">
                If you have any questions in the meantime, simply reply to this email.
            </p>

            <p style="color: #334155; font-size: 15px;">Talk soon,<br/><strong>Dane</strong><br/>RYZE.ai</p>

            <hr style="border: none; border-top: 1px solid #e2e8f0; margin-top: 32px;" />
            <p style="color: #94a3b8; font-size: 12px; text-align: center;">
                © 2026 RYZE.ai. All rights reserved.
            </p>
        </div>
        """,
        }
    )

    logger.info(f"Candidate booking confirmation sent to {candidate_email}")


# ADD THESE FUNCTIONS to app/services/email.py
# ---------------------------------------------------------------------------
# Outbound invite email — Accept / Decline buttons (replaces Zoom link)
# ---------------------------------------------------------------------------


def send_recruiter_invite_with_response(
    contact_name: str,
    contact_email: str,
    contact_type: str,  # "employer" | "candidate"
    company_name: str,
    date: str,
    time_slot: str,
    booking_id: int,
    response_token: str,
    notes: str = "",
) -> None:
    """
    Outbound invite email sent to the contact.
    Contains Accept and Decline buttons — NO Zoom link yet.
    Zoom link is only sent after they accept.
    """
    import resend
    from app.core.config import settings

    accept_url = f"{settings.BACKEND_URL}/api/bookings/respond?token={response_token}&action=accept"
    decline_url = f"{settings.BACKEND_URL}/api/bookings/respond?token={response_token}&action=decline"

    company_line = f" ({company_name})" if company_name else ""
    notes_row = (
        f"""
        <tr>
            <td style="padding:8px 0;color:#64748b;font-size:14px;vertical-align:top;">Notes</td>
            <td style="padding:8px 0;color:#111827;font-size:14px;">{notes}</td>
        </tr>"""
        if notes
        else ""
    )

    company_row = (
        f"""
        <tr>
            <td style="padding:8px 0;color:#64748b;font-size:14px;">Company</td>
            <td style="padding:8px 0;color:#111827;font-size:14px;font-weight:600;">{company_name}</td>
        </tr>"""
        if company_name
        else ""
    )

    resend.Emails.send(
        {
            "from": f"RYZE.ai <{settings.FROM_EMAIL}>",
            "to": [contact_email],
            "subject": f"Dane Ahern from RYZE.ai wants to connect — {date} at {time_slot}",
            "html": f"""
        <div style="font-family:Arial,sans-serif;max-width:600px;margin:0 auto;padding:32px;background:#f9fafb;border-radius:8px;">
            <h1 style="color:#0a66c2;margin-bottom:8px;">RYZE.ai</h1>
            <hr style="border:none;border-top:1px solid #e2e8f0;margin-bottom:24px;"/>

            <h2 style="color:#111827;margin-bottom:4px;">You're invited to a call 📅</h2>
            <p style="color:#64748b;font-size:14px;margin-top:0;">
                Dane Ahern from RYZE.ai would like to connect with you.
            </p>

            <p style="color:#334155;font-size:15px;">Hi {contact_name},</p>
            <p style="color:#334155;font-size:15px;">
                I'd love to set up a quick intro call to learn more about you
                {"and your hiring needs" if contact_type == "employer" else "and your career goals"}.
                I've proposed the time below — does this work for you?
            </p>

            <div style="background:#ffffff;border:1px solid #e2e8f0;border-radius:8px;padding:20px;margin:24px 0;">
                <table style="width:100%;border-collapse:collapse;">
                    {company_row}
                    <tr>
                        <td style="padding:8px 0;color:#64748b;font-size:14px;width:40%;">Date</td>
                        <td style="padding:8px 0;color:#111827;font-size:14px;font-weight:600;">{date}</td>
                    </tr>
                    <tr>
                        <td style="padding:8px 0;color:#64748b;font-size:14px;">Time</td>
                        <td style="padding:8px 0;color:#111827;font-size:14px;font-weight:600;">{time_slot} EST</td>
                    </tr>
                    <tr>
                        <td style="padding:8px 0;color:#64748b;font-size:14px;">Duration</td>
                        <td style="padding:8px 0;color:#111827;font-size:14px;">30 minutes via Zoom</td>
                    </tr>
                    {notes_row}
                </table>
            </div>

            <p style="color:#334155;font-size:14px;margin-bottom:20px;">
                Please let me know if this works — just click one of the buttons below:
            </p>

            <div style="display:flex;gap:12px;margin-bottom:28px;">
                <a href="{accept_url}"
                   style="display:inline-block;background:#16a34a;color:#fff;text-decoration:none;
                          font-weight:700;padding:14px 32px;border-radius:8px;font-size:15px;margin-right:12px;">
                    ✓ Accept
                </a>
                <a href="{decline_url}"
                   style="display:inline-block;background:#f1f5f9;color:#475569;text-decoration:none;
                          font-weight:700;padding:14px 32px;border-radius:8px;font-size:15px;
                          border:1px solid #e2e8f0;">
                    Decline
                </a>
            </div>

            <p style="color:#334155;font-size:15px;">
                Looking forward to connecting.<br/>
                <strong>Dane Ahern</strong><br/>
                RYZE.ai
            </p>

            <hr style="border:none;border-top:1px solid #e2e8f0;margin-top:32px;"/>
            <p style="color:#94a3b8;font-size:12px;text-align:center;">
                © 2026 RYZE.ai. You received this because someone requested a meeting with you.
            </p>
        </div>
        """,
        }
    )

    logger.info(f"Outbound invite with Accept/Decline sent to {contact_email}")


def send_invite_accepted_admin_notify(
    contact_name: str,
    contact_type: str,  # "employer" | "candidate"
    company_name: str,
    date: str,
    time_slot: str,
    meeting_url: str,
) -> None:
    """
    Notifies the recruiter (ADMIN_EMAIL) that their outbound invite was accepted.
    Fires immediately when the contact clicks Accept — before AI brief is ready.
    """
    import resend
    from app.core.config import settings

    company_line = f" ({company_name})" if company_name else ""
    type_label = "Employer" if contact_type == "employer" else "Candidate"

    resend.Emails.send(
        {
            "from": f"RYZE.ai <{settings.FROM_EMAIL}>",
            "to": [settings.ADMIN_EMAIL],
            "subject": f"✅ Accepted — {contact_name}{company_line} confirmed the call",
            "html": f"""
        <div style="font-family:Arial,sans-serif;max-width:600px;margin:0 auto;padding:32px;background:#f9fafb;border-radius:8px;">
            <h1 style="color:#0a66c2;margin-bottom:8px;">RYZE.ai</h1>
            <hr style="border:none;border-top:1px solid #e2e8f0;margin-bottom:24px;"/>
 
            <h2 style="color:#111827;margin-bottom:4px;">Invite Accepted ✅</h2>
            <p style="color:#64748b;font-size:14px;margin-top:0;">
                <strong>{contact_name}</strong> accepted your meeting invite.
                Zoom and Calendar have been created automatically.
            </p>
 
            <div style="background:#ffffff;border:1px solid #e2e8f0;border-radius:8px;padding:20px;margin:24px 0;">
                <table style="width:100%;border-collapse:collapse;">
                    <tr>
                        <td style="padding:8px 0;color:#64748b;font-size:14px;width:40%;">Contact</td>
                        <td style="padding:8px 0;color:#111827;font-size:14px;font-weight:600;">{contact_name}{company_line}</td>
                    </tr>
                    <tr>
                        <td style="padding:8px 0;color:#64748b;font-size:14px;">Type</td>
                        <td style="padding:8px 0;color:#111827;font-size:14px;">{type_label}</td>
                    </tr>
                    <tr>
                        <td style="padding:8px 0;color:#64748b;font-size:14px;">Date</td>
                        <td style="padding:8px 0;color:#111827;font-size:14px;font-weight:600;">{date}</td>
                    </tr>
                    <tr>
                        <td style="padding:8px 0;color:#64748b;font-size:14px;">Time</td>
                        <td style="padding:8px 0;color:#111827;font-size:14px;font-weight:600;">{time_slot} EST</td>
                    </tr>
                    <tr>
                        <td style="padding:8px 0;color:#64748b;font-size:14px;">Zoom</td>
                        <td style="padding:8px 0;color:#111827;font-size:14px;">
                            <a href="{meeting_url}" style="color:#0a66c2;">{meeting_url}</a>
                        </td>
                    </tr>
                </table>
            </div>
 
            <p style="color:#64748b;font-size:13px;font-style:italic;">
                The AI brief is generating in the background and will appear in the admin dashboard shortly.
            </p>
 
            <a href="{settings.FRONTEND_URL}/admin"
               style="display:inline-block;background:#0a66c2;color:white;text-decoration:none;
                      font-weight:700;padding:12px 24px;border-radius:8px;font-size:14px;margin-top:16px;">
                View in Admin Dashboard →
            </a>
 
            <hr style="border:none;border-top:1px solid #e2e8f0;margin-top:32px;" />
            <p style="color:#94a3b8;font-size:12px;text-align:center;">
                © 2026 RYZE.ai. All rights reserved.
            </p>
        </div>
        """,
        }
    )

    logger.info(f"Invite accepted admin notification sent for {contact_name}")


def send_invite_admin_copy(
    contact_name: str,
    contact_type: str,
    company_name: str,
    date: str,
    time_slot: str,
) -> None:
    """Admin copy confirming the outbound invite was sent — awaiting response."""
    import resend
    from app.core.config import settings

    company_line = f" ({company_name})" if company_name else ""
    type_label = "Employer" if contact_type == "employer" else "Candidate"

    resend.Emails.send(
        {
            "from": f"RYZE.ai <{settings.FROM_EMAIL}>",
            "to": [settings.ADMIN_EMAIL],
            "subject": f"Outbound Invite Sent — {contact_name}{company_line} · Awaiting Response",
            "html": f"""
        <div style="font-family:Arial,sans-serif;max-width:600px;margin:0 auto;padding:32px;background:#f9fafb;border-radius:8px;">
            <h1 style="color:#0a66c2;margin-bottom:8px;">RYZE.ai</h1>
            <hr style="border:none;border-top:1px solid #e2e8f0;margin-bottom:24px;"/>
            <h2 style="color:#111827;margin-bottom:4px;">Invite Sent — Awaiting Response ⏳</h2>
            <p style="color:#64748b;font-size:14px;margin-top:0;">
                Your outbound invite has been sent to <strong>{contact_name}</strong>.
                The booking is <strong>pending</strong> until they accept.
                Zoom and Calendar will be created automatically when they do.
            </p>
            <div style="background:#fffbeb;border:1px solid #fde68a;border-radius:8px;padding:16px;margin:20px 0;">
                <p style="margin:0;color:#92400e;font-size:14px;">
                    <strong>Status:</strong> Pending — no Zoom link or Calendar event yet
                </p>
            </div>
            <div style="background:#fff;border:1px solid #e2e8f0;border-radius:8px;padding:20px;margin:20px 0;">
                <table style="width:100%;border-collapse:collapse;">
                    <tr>
                        <td style="padding:6px 0;color:#64748b;font-size:14px;width:40%;">Contact</td>
                        <td style="padding:6px 0;color:#111827;font-size:14px;font-weight:600;">{contact_name}{company_line}</td>
                    </tr>
                    <tr>
                        <td style="padding:6px 0;color:#64748b;font-size:14px;">Type</td>
                        <td style="padding:6px 0;color:#111827;font-size:14px;">{type_label}</td>
                    </tr>
                    <tr>
                        <td style="padding:6px 0;color:#64748b;font-size:14px;">Date</td>
                        <td style="padding:6px 0;color:#111827;font-size:14px;font-weight:600;">{date}</td>
                    </tr>
                    <tr>
                        <td style="padding:6px 0;color:#64748b;font-size:14px;">Time</td>
                        <td style="padding:6px 0;color:#111827;font-size:14px;font-weight:600;">{time_slot} EST</td>
                    </tr>
                </table>
            </div>
            <hr style="border:none;border-top:1px solid #e2e8f0;margin-top:32px;"/>
            <p style="color:#94a3b8;font-size:12px;text-align:center;">© 2026 RYZE.ai</p>
        </div>
        """,
        }
    )
    logger.info(f"Admin copy (invite sent, awaiting response) sent for {contact_name}")


def send_invite_accepted_confirmation(
    contact_name: str,
    contact_email: str,
    contact_type: str,
    company_name: str,
    date: str,
    time_slot: str,
    meeting_url: str,
) -> None:
    """Confirmation email to contact after they accept — includes Zoom link."""
    import resend
    from app.core.config import settings

    company_line = f" ({company_name})" if company_name else ""

    resend.Emails.send(
        {
            "from": f"RYZE.ai <{settings.FROM_EMAIL}>",
            "to": [contact_email],
            "subject": f"You're confirmed — Call with RYZE.ai on {date} at {time_slot}",
            "html": f"""
        <div style="font-family:Arial,sans-serif;max-width:600px;margin:0 auto;padding:32px;background:#f9fafb;border-radius:8px;">
            <h1 style="color:#0a66c2;margin-bottom:8px;">RYZE.ai</h1>
            <hr style="border:none;border-top:1px solid #e2e8f0;margin-bottom:24px;"/>
            <h2 style="color:#111827;margin-bottom:4px;">You're confirmed! ✅</h2>
            <p style="color:#64748b;font-size:14px;margin-top:0;">Your call with Dane at RYZE.ai is all set.</p>
            <p style="color:#334155;font-size:15px;">Hi {contact_name},</p>
            <p style="color:#334155;font-size:15px;">Great — looking forward to our conversation. Here are your call details:</p>

            <div style="background:#fff;border:1px solid #e2e8f0;border-radius:8px;padding:20px;margin:24px 0;">
                <table style="width:100%;border-collapse:collapse;">
                    <tr>
                        <td style="padding:8px 0;color:#64748b;font-size:14px;width:40%;">Date</td>
                        <td style="padding:8px 0;color:#111827;font-size:14px;font-weight:600;">{date}</td>
                    </tr>
                    <tr>
                        <td style="padding:8px 0;color:#64748b;font-size:14px;">Time</td>
                        <td style="padding:8px 0;color:#111827;font-size:14px;font-weight:600;">{time_slot} EST</td>
                    </tr>
                    <tr>
                        <td style="padding:8px 0;color:#64748b;font-size:14px;">Zoom Link</td>
                        <td style="padding:8px 0;font-size:14px;">
                            <a href="{meeting_url}" style="color:#0a66c2;font-weight:600;text-decoration:none;">
                                Join Zoom Call →
                            </a>
                        </td>
                    </tr>
                </table>
            </div>

            <a href="{meeting_url}"
               style="display:inline-block;background:#0a66c2;color:#fff;text-decoration:none;
                      font-weight:700;padding:14px 28px;border-radius:8px;font-size:15px;margin-bottom:24px;">
                Join Zoom Call →
            </a>

            <p style="color:#334155;font-size:15px;">
                See you then!<br/><strong>Dane Ahern</strong><br/>RYZE.ai
            </p>
            <hr style="border:none;border-top:1px solid #e2e8f0;margin-top:32px;"/>
            <p style="color:#94a3b8;font-size:12px;text-align:center;">© 2026 RYZE.ai</p>
        </div>
        """,
        }
    )
    logger.info(f"Acceptance confirmation with Zoom link sent to {contact_email}")


def send_invite_declined_admin(
    contact_name: str,
    contact_type: str,
    company_name: str,
    date: str,
    time_slot: str,
) -> None:
    """Notify admin that the contact declined the invite."""
    import resend
    from app.core.config import settings

    company_line = f" ({company_name})" if company_name else ""

    resend.Emails.send(
        {
            "from": f"RYZE.ai <{settings.FROM_EMAIL}>",
            "to": [settings.ADMIN_EMAIL],
            "subject": f"Invite Declined — {contact_name}{company_line}",
            "html": f"""
        <div style="font-family:Arial,sans-serif;max-width:600px;margin:0 auto;padding:32px;background:#f9fafb;border-radius:8px;">
            <h1 style="color:#0a66c2;margin-bottom:8px;">RYZE.ai</h1>
            <hr style="border:none;border-top:1px solid #e2e8f0;margin-bottom:24px;"/>
            <h2 style="color:#111827;margin-bottom:4px;">Invite Declined ❌</h2>
            <p style="color:#64748b;font-size:14px;margin-top:0;">
                <strong>{contact_name}</strong>{company_line} has declined your meeting request
                for {date} at {time_slot} EST.
                The booking has been marked as cancelled.
            </p>
            <hr style="border:none;border-top:1px solid #e2e8f0;margin-top:32px;"/>
            <p style="color:#94a3b8;font-size:12px;text-align:center;">© 2026 RYZE.ai</p>
        </div>
        """,
        }
    )
    logger.info(f"Admin notified of declined invite from {contact_name}")


# ---------------------------------------------------------------------------
# Aliases — bridge notifications.py import names to actual function names
# ---------------------------------------------------------------------------


def send_booking_received_email(
    employer_name: str,
    employer_email: str,
    company_name: str,
    website_url: str,
    date: str,
    time_slot: str,
    phone: str = "",
    notes: str = "",
) -> None:
    send_employer_confirmation(
        employer_name=employer_name,
        employer_email=employer_email,
        company_name=company_name,
        date=date,
        time_slot=time_slot,
    )
    send_admin_notification(
        employer_name=employer_name,
        employer_email=employer_email,
        company_name=company_name,
        website_url=website_url,
        date=date,
        time_slot=time_slot,
        phone=phone,
        notes=notes,
    )


send_invite_declined_admin_notify = send_invite_declined_admin
send_candidate_booking_admin_notify = send_candidate_booking_received_admin


def send_candidate_confirmed_email(
    candidate_name: str,
    candidate_email: str,
    date: str,
    time_slot: str,
    meeting_url: str,
) -> None:
    """Confirmation email sent to candidate when admin confirms their booking."""
    zoom_button = (
        f'<a href="{meeting_url}" style="display:inline-block;background:#0a66c2;'
        f"color:white;text-decoration:none;font-weight:700;padding:12px 24px;"
        f'border-radius:8px;font-size:14px;">Join Zoom Call →</a>'
        if meeting_url
        else ""
    )

    resend.Emails.send(
        {
            "from": f"RYZE.ai <{settings.FROM_EMAIL}>",
            "to": [candidate_email],
            "subject": f"You're confirmed — Call with RYZE.ai on {date} at {time_slot}",
            "html": f"""
        <div style="font-family:Arial,sans-serif;max-width:600px;margin:0 auto;padding:32px;background:#f9fafb;border-radius:8px;">
            <h1 style="color:#0a66c2;margin-bottom:8px;">RYZE.ai</h1>
            <hr style="border:none;border-top:1px solid #e2e8f0;margin-bottom:24px;"/>
            <h2 style="color:#111827;margin-bottom:4px;">You're confirmed! ✅</h2>
            <p style="color:#64748b;font-size:14px;margin-top:0;">Your screening call with Dane at RYZE.ai is all set.</p>
            <p style="color:#334155;font-size:15px;">Hi {candidate_name},</p>
            <p style="color:#334155;font-size:15px;">Looking forward to connecting and learning more about your background.</p>
            <div style="background:#ffffff;border:1px solid #e2e8f0;border-radius:8px;padding:20px;margin:24px 0;">
                <table style="width:100%;border-collapse:collapse;">
                    <tr>
                        <td style="padding:8px 0;color:#64748b;font-size:14px;width:40%;">Date</td>
                        <td style="padding:8px 0;color:#111827;font-size:14px;font-weight:600;">{date}</td>
                    </tr>
                    <tr>
                        <td style="padding:8px 0;color:#64748b;font-size:14px;">Time</td>
                        <td style="padding:8px 0;color:#111827;font-size:14px;font-weight:600;">{time_slot} EST</td>
                    </tr>
                </table>
            </div>
            {zoom_button}
            <p style="color:#334155;font-size:15px;margin-top:24px;">Talk soon,<br/><strong>Dane</strong><br/>RYZE.ai</p>
            <hr style="border:none;border-top:1px solid #e2e8f0;margin-top:32px;"/>
            <p style="color:#94a3b8;font-size:12px;text-align:center;">© 2026 RYZE.ai. All rights reserved.</p>
        </div>
        """,
        }
    )
    logger.info(f"Candidate confirmed email sent to {candidate_email}")


# ── Paste this function into app/services/email.py ──────────────────────────


def send_welcome_invite_email(
    full_name: str,
    email: str,
    temp_password: str,
    company_name: str,
    trial_ends_at,  # datetime
) -> None:
    """
    Send a branded welcome email to a newly invited recruiting firm.
    Fired immediately after the tenant and user records are created.
    """
    trial_end_str = trial_ends_at.strftime("%B %d, %Y")

    resend.Emails.send(
        {
            "from": f"RYZE.ai <{settings.FROM_EMAIL}>",
            "to": [email],
            "subject": "You're invited to RYZE.ai — your 30-day trial starts today",
            "html": f"""
        <div style="font-family:Arial,sans-serif;max-width:600px;margin:0 auto;padding:32px;background:#f9fafb;border-radius:8px;">
            <h1 style="color:#0a66c2;margin-bottom:8px;">RYZE.ai</h1>
            <hr style="border:none;border-top:1px solid #e2e8f0;margin-bottom:24px;" />

            <h2 style="color:#111827;margin-bottom:4px;">Welcome to RYZE.ai, {full_name}! 🎉</h2>
            <p style="color:#64748b;font-size:14px;margin-top:0;">
                Your 30-day free trial for <strong>{company_name}</strong> starts now.
            </p>

            <p style="color:#334155;font-size:15px;">
                Your account is ready. Use the credentials below to log in and get started.
            </p>

            <div style="background:#ffffff;border:1px solid #e2e8f0;border-radius:8px;padding:20px;margin:24px 0;">
                <table style="width:100%;border-collapse:collapse;">
                    <tr>
                        <td style="padding:8px 0;color:#64748b;font-size:14px;width:40%;">Login URL</td>
                        <td style="padding:8px 0;font-size:14px;">
                            <a href="https://ryze.ai/auth" style="color:#0a66c2;font-weight:600;">https://ryze.ai/auth</a>
                        </td>
                    </tr>
                    <tr>
                        <td style="padding:8px 0;color:#64748b;font-size:14px;">Email</td>
                        <td style="padding:8px 0;color:#111827;font-size:14px;font-weight:600;">{email}</td>
                    </tr>
                    <tr>
                        <td style="padding:8px 0;color:#64748b;font-size:14px;">Temporary Password</td>
                        <td style="padding:8px 0;color:#111827;font-size:14px;font-weight:600;font-family:monospace;">{temp_password}</td>
                    </tr>
                    <tr>
                        <td style="padding:8px 0;color:#64748b;font-size:14px;">Trial Ends</td>
                        <td style="padding:8px 0;color:#111827;font-size:14px;font-weight:600;">{trial_end_str}</td>
                    </tr>
                </table>
            </div>

            <div style="text-align:center;margin:32px 0;">
                <a href="https://ryze.ai/auth"
                   style="background:#0a66c2;color:#ffffff;padding:14px 32px;border-radius:6px;
                          text-decoration:none;font-size:15px;font-weight:600;display:inline-block;">
                    Log In to RYZE.ai →
                </a>
            </div>

            <p style="color:#64748b;font-size:13px;">
                We recommend changing your password after your first login.
                Your trial gives you full access to all platform features through {trial_end_str}.
            </p>

            <hr style="border:none;border-top:1px solid #e2e8f0;margin-top:32px;" />
            <p style="color:#94a3b8;font-size:12px;text-align:center;">
                © 2026 RYZE GROUP, Inc. · Manchester, NH<br />
                You received this email because you were invited to RYZE.ai.
            </p>
        </div>
        """,
        }
    )
    logger.info(f"Welcome email sent to {email} ({company_name})")
