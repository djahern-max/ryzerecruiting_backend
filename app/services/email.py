import resend
import logging
from app.core.config import settings

logger = logging.getLogger(__name__)

resend.api_key = settings.RESEND_API_KEY


def send_employer_confirmation(
    employer_name: str,
    employer_email: str,
    company_name: str,
    date: str,
    time_slot: str,
) -> None:
    """Send a booking confirmation email to the employer."""

    resend.Emails.send(
        {
            "from": f"RYZE Recruiting <{settings.FROM_EMAIL}>",
            "to": [employer_email],
            "subject": "Your call with RYZE Recruiting is confirmed!",
            "html": f"""
        <div style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto; padding: 32px; background: #f9fafb; border-radius: 8px;">
            <h1 style="color: #0a66c2; margin-bottom: 8px;">RYZE Recruiting</h1>
            <hr style="border: none; border-top: 1px solid #e2e8f0; margin-bottom: 24px;" />

            <h2 style="color: #111827; margin-bottom: 16px;">Your call is confirmed!</h2>

            <p style="color: #334155; font-size: 15px;">Hi {employer_name},</p>

            <p style="color: #334155; font-size: 15px;">
                We're looking forward to speaking with you. Here are your booking details:
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
                Dane will reach out if anything changes. If you have any questions in the meantime,
                simply reply to this email.
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

    logger.info(f"Confirmation email sent to {employer_email}")


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
    """Send a new booking notification email to Dane."""

    admin_dashboard_url = f"{settings.FRONTEND_URL}/admin"

    resend.Emails.send(
        {
            "from": f"RYZE Recruiting <{settings.FROM_EMAIL}>",
            "to": [settings.ADMIN_EMAIL],
            "subject": f"New call booked — {employer_name} on {date} at {time_slot}",
            "html": f"""
        <div style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto; padding: 32px; background: #f9fafb; border-radius: 8px;">
            <h1 style="color: #0a66c2; margin-bottom: 8px;">RYZE Recruiting</h1>
            <hr style="border: none; border-top: 1px solid #e2e8f0; margin-bottom: 24px;" />

            <h2 style="color: #111827; margin-bottom: 4px;">New Call Booked 🎉</h2>
            <p style="color: #64748b; font-size: 14px; margin-top: 0;">A new employer has scheduled a discovery call.</p>

            <div style="background: #ffffff; border: 1px solid #e2e8f0; border-radius: 8px; padding: 20px; margin: 24px 0;">
                <table style="width: 100%; border-collapse: collapse;">
                    <tr>
                        <td style="padding: 8px 0; color: #64748b; font-size: 14px; width: 40%;">Name</td>
                        <td style="padding: 8px 0; color: #111827; font-size: 14px; font-weight: 600;">{employer_name}</td>
                    </tr>
                    <tr>
                        <td style="padding: 8px 0; color: #64748b; font-size: 14px;">Email</td>
                        <td style="padding: 8px 0; color: #111827; font-size: 14px;">{employer_email}</td>
                    </tr>
                    <tr>
                        <td style="padding: 8px 0; color: #64748b; font-size: 14px;">Company</td>
                        <td style="padding: 8px 0; color: #111827; font-size: 14px;">{company_name or "—"}</td>
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
                View in Admin Dashboard →
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
