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
            "from": f"RYZE Recruiting <{settings.FROM_EMAIL}>",
            "to": [employer_email],
            "subject": "Your call request with RYZE Recruiting has been received!",
            "html": f"""
        <div style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto; padding: 32px; background: #f9fafb; border-radius: 8px;">
            <h1 style="color: #0a66c2; margin-bottom: 8px;">RYZE Recruiting</h1>
            <hr style="border: none; border-top: 1px solid #e2e8f0; margin-bottom: 24px;" />

            <h2 style="color: #111827; margin-bottom: 16px;">We've received your request!</h2>

            <p style="color: #334155; font-size: 15px;">Hi {employer_name},</p>

            <p style="color: #334155; font-size: 15px;">
                Thanks for reaching out! We've received your request and will confirm your call shortly.
                Here's what you requested:
            </p>

            <div style="background: #ffffff; border: 1px solid #e2e8f0; border-radius: 8px; padding: 20px; margin: 24px 0;">
                <table style="width: 100%; border-collapse: collapse;">
                    <tr>
                        <td style="padding: 8px 0; color: #64748b; font-size: 14px; width: 40%;">Company</td>
                        <td style="padding: 8px 0; color: #111827; font-size: 14px; font-weight: 600;">{company_name or "—"}</td>
                    </tr>
                    <tr>
                        <td style="padding: 8px 0; color: #64748b; font-size: 14px;">Requested Date</td>
                        <td style="padding: 8px 0; color: #111827; font-size: 14px; font-weight: 600;">{date}</td>
                    </tr>
                    <tr>
                        <td style="padding: 8px 0; color: #64748b; font-size: 14px;">Requested Time</td>
                        <td style="padding: 8px 0; color: #111827; font-size: 14px; font-weight: 600;">{time_slot} EST</td>
                    </tr>
                    <tr>
                        <td style="padding: 8px 0; color: #64748b; font-size: 14px;">Status</td>
                        <td style="padding: 8px 0; font-size: 14px;">
                            <span style="background: #fef3c7; color: #92400e; padding: 2px 10px; border-radius: 12px; font-size: 13px; font-weight: 600;">
                                Pending Confirmation
                            </span>
                        </td>
                    </tr>
                </table>
            </div>

            <p style="color: #334155; font-size: 15px;">
                You'll receive a follow-up email with your Zoom link once your call is confirmed.
                If you have any questions in the meantime, simply reply to this email.
            </p>

            <p style="color: #334155; font-size: 15px;">Talk soon,<br/><strong>Dane</strong><br/>RYZE Recruiting</p>

            <hr style="border: none; border-top: 1px solid #e2e8f0; margin-top: 32px;" />
            <p style="color: #94a3b8; font-size: 12px; text-align: center;">
                © 2026 RYZE Recruiting. All rights reserved.
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
            "from": f"RYZE Recruiting <{settings.FROM_EMAIL}>",
            "to": [settings.ADMIN_EMAIL],
            "subject": f"New Call Request — {employer_name} on {date} at {time_slot} — Confirmation Required",
            "html": f"""
        <div style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto; padding: 32px; background: #f9fafb; border-radius: 8px;">
            <h1 style="color: #0a66c2; margin-bottom: 8px;">RYZE Recruiting</h1>
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
                © 2026 RYZE Recruiting. All rights reserved.
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
    ai_brief: dict = None,  # Now accepts a dict (was str)
) -> None:
    """Send confirmed call email with Zoom link to both the employer and the recruiter (Dane)."""

    if ai_brief is None:
        ai_brief = {}

    # --- Employer email ---
    resend.Emails.send(
        {
            "from": f"RYZE Recruiting <{settings.FROM_EMAIL}>",
            "to": [employer_email],
            "subject": "Your call with RYZE Recruiting is confirmed — here's your Zoom link!",
            "html": f"""
        <div style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto; padding: 32px; background: #f9fafb; border-radius: 8px;">
            <h1 style="color: #0a66c2; margin-bottom: 8px;">RYZE Recruiting</h1>
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

            <p style="color: #334155; font-size: 15px;">See you soon,<br/><strong>Dane</strong><br/>RYZE Recruiting</p>

            <hr style="border: none; border-top: 1px solid #e2e8f0; margin-top: 32px;" />
            <p style="color: #94a3b8; font-size: 12px; text-align: center;">
                © 2026 RYZE Recruiting. All rights reserved.
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
            "from": f"RYZE Recruiting <{settings.FROM_EMAIL}>",
            "to": [settings.ADMIN_EMAIL],
            "subject": f"Call Confirmed — {employer_name} ({company_name}) on {date} at {time_slot}",
            "html": f"""
        <div style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto; padding: 32px; background: #f9fafb; border-radius: 8px;">
            <h1 style="color: #0a66c2; margin-bottom: 8px;">RYZE Recruiting</h1>
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
                © 2026 RYZE Recruiting. All rights reserved.
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
            "from": f"RYZE Recruiting <{settings.FROM_EMAIL}>",
            "to": [employer_email],
            "subject": "Your call with RYZE Recruiting has been cancelled",
            "html": f"""
        <div style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto; padding: 32px; background: #f9fafb; border-radius: 8px;">
            <h1 style="color: #0a66c2; margin-bottom: 8px;">RYZE Recruiting</h1>
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
                Visit <a href="{settings.FRONTEND_URL}" style="color: #0a66c2;">ryzerecruiting.com</a>
                to schedule a new time.
            </p>

            <p style="color: #334155; font-size: 15px;">Best,<br/><strong>Dane</strong><br/>RYZE Recruiting</p>

            <hr style="border: none; border-top: 1px solid #e2e8f0; margin-top: 32px;" />
            <p style="color: #94a3b8; font-size: 12px; text-align: center;">
                © 2026 RYZE Recruiting. All rights reserved.
            </p>
        </div>
        """,
        }
    )

    logger.info(f"Cancellation email sent to {employer_email}")

    # --- Admin (recruiter) cancellation email ---
    resend.Emails.send(
        {
            "from": f"RYZE Recruiting <{settings.FROM_EMAIL}>",
            "to": [settings.ADMIN_EMAIL],
            "subject": f"Call Cancelled — {employer_name} ({company_name}) on {date} at {time_slot}",
            "html": f"""
        <div style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto; padding: 32px; background: #f9fafb; border-radius: 8px;">
            <h1 style="color: #0a66c2; margin-bottom: 8px;">RYZE Recruiting</h1>
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
                © 2026 RYZE Recruiting. All rights reserved.
            </p>
        </div>
        """,
        }
    )

    logger.info(f"Cancellation admin email sent to {settings.ADMIN_EMAIL}")
