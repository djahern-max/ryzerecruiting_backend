# app/services/email.py
import resend
from app.core.config import settings

resend.api_key = settings.RESEND_API_KEY


def send_employer_confirmation(
    employer_name: str,
    employer_email: str,
    company_name: str,
    date: str,
    time_slot: str,
):
    """Send a booking confirmation email to the employer."""
    resend.Emails.send({
        "from": f"RYZE Recruiting <{settings.FROM_EMAIL}>",
        "to": employer_email,
        "subject": "Your call with RYZE Recruiting is confirmed!",
        "html": f"""
        <div style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto; padding: 40px 20px;">
            <div style="text-align: center; margin-bottom: 32px;">
                <h1 style="color: #004182; font-size: 28px; margin: 0;">RYZE Recruiting</h1>
            </div>

            <h2 style="color: #1a2e44; font-size: 22px;">You're booked, {employer_name.split()[0]}!</h2>

            <p style="color: #3d5a73; font-size: 16px; line-height: 1.6;">
                Your intro call has been scheduled. Here are your details:
            </p>

            <div style="background: #f0f5fb; border-radius: 12px; padding: 24px; margin: 24px 0;">
                <table style="width: 100%; border-collapse: collapse;">
                    <tr>
                        <td style="color: #5a7290; font-size: 14px; padding: 8px 0; width: 40%;">Date</td>
                        <td style="color: #1a2e44; font-size: 14px; font-weight: 600; padding: 8px 0;">{date}</td>
                    </tr>
                    <tr>
                        <td style="color: #5a7290; font-size: 14px; padding: 8px 0;">Time</td>
                        <td style="color: #1a2e44; font-size: 14px; font-weight: 600; padding: 8px 0;">{time_slot}</td>
                    </tr>
                    {"" if not company_name else f'''
                    <tr>
                        <td style="color: #5a7290; font-size: 14px; padding: 8px 0;">Company</td>
                        <td style="color: #1a2e44; font-size: 14px; font-weight: 600; padding: 8px 0;">{company_name}</td>
                    </tr>
                    '''}
                </table>
            </div>

            <p style="color: #3d5a73; font-size: 15px; line-height: 1.6;">
                We'll be in touch shortly. If anything comes up and you need to reschedule,
                just reply to this email.
            </p>

            <p style="color: #3d5a73; font-size: 15px; line-height: 1.6;">
                Looking forward to speaking with you!
            </p>

            <p style="color: #1a2e44; font-size: 15px; font-weight: 600; margin-top: 32px;">
                Dane Ahern<br>
                <span style="color: #5a7290; font-weight: 400;">RYZE Recruiting</span>
            </p>

            <hr style="border: none; border-top: 1px solid #e0e7ef; margin: 32px 0;" />
            <p style="color: #8fa3b8; font-size: 12px; text-align: center;">
                RYZE Recruiting · ryzerecruiting.com
            </p>
        </div>
        """,
    })


def send_admin_notification(
    employer_name: str,
    employer_email: str,
    company_name: str,
    website_url: str,
    date: str,
    time_slot: str,
    phone: str,
    notes: str,
):
    """Send a new booking notification email to Dane."""
    resend.Emails.send({
        "from": f"RYZE Recruiting <{settings.FROM_EMAIL}>",
        "to": settings.ADMIN_EMAIL,
        "subject": f"New call booked — {employer_name} on {date} at {time_slot}",
        "html": f"""
        <div style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto; padding: 40px 20px;">
            <div style="text-align: center; margin-bottom: 32px;">
                <h1 style="color: #004182; font-size: 28px; margin: 0;">RYZE Recruiting</h1>
            </div>

            <h2 style="color: #1a2e44; font-size: 22px;">New Call Booked 🎉</h2>

            <div style="background: #f0f5fb; border-radius: 12px; padding: 24px; margin: 24px 0;">
                <table style="width: 100%; border-collapse: collapse;">
                    <tr>
                        <td style="color: #5a7290; font-size: 14px; padding: 8px 0; width: 40%;">Name</td>
                        <td style="color: #1a2e44; font-size: 14px; font-weight: 600; padding: 8px 0;">{employer_name}</td>
                    </tr>
                    <tr>
                        <td style="color: #5a7290; font-size: 14px; padding: 8px 0;">Email</td>
                        <td style="color: #1a2e44; font-size: 14px; font-weight: 600; padding: 8px 0;">{employer_email}</td>
                    </tr>
                    <tr>
                        <td style="color: #5a7290; font-size: 14px; padding: 8px 0;">Date</td>
                        <td style="color: #1a2e44; font-size: 14px; font-weight: 600; padding: 8px 0;">{date}</td>
                    </tr>
                    <tr>
                        <td style="color: #5a7290; font-size: 14px; padding: 8px 0;">Time</td>
                        <td style="color: #1a2e44; font-size: 14px; font-weight: 600; padding: 8px 0;">{time_slot}</td>
                    </tr>
                    {"" if not company_name else f'''
                    <tr>
                        <td style="color: #5a7290; font-size: 14px; padding: 8px 0;">Company</td>
                        <td style="color: #1a2e44; font-size: 14px; font-weight: 600; padding: 8px 0;">{company_name}</td>
                    </tr>
                    '''}
                    {"" if not website_url else f'''
                    <tr>
                        <td style="color: #5a7290; font-size: 14px; padding: 8px 0;">Website</td>
                        <td style="font-size: 14px; font-weight: 600; padding: 8px 0;">
                            <a href="{website_url}" style="color: #004182;">{website_url}</a>
                        </td>
                    </tr>
                    '''}
                    {"" if not phone else f'''
                    <tr>
                        <td style="color: #5a7290; font-size: 14px; padding: 8px 0;">Phone</td>
                        <td style="color: #1a2e44; font-size: 14px; font-weight: 600; padding: 8px 0;">{phone}</td>
                    </tr>
                    '''}
                    {"" if not notes else f'''
                    <tr>
                        <td style="color: #5a7290; font-size: 14px; padding: 8px 0; vertical-align: top;">Notes</td>
                        <td style="color: #1a2e44; font-size: 14px; padding: 8px 0;">{notes}</td>
                    </tr>
                    '''}
                </table>
            </div>

            <a href="{settings.FRONTEND_URL}/admin"
               style="display: inline-block; background: #004182; color: #ffffff;
                      text-decoration: none; padding: 12px 24px; border-radius: 8px;
                      font-size: 15px; font-weight: 600; margin-top: 8px;">
                View in Admin Dashboard
            </a>

            <hr style="border: none; border-top: 1px solid #e0e7ef; margin: 32px 0;" />
            <p style="color: #8fa3b8; font-size: 12px; text-align: center;">
                RYZE Recruiting · ryzerecruiting.com
            </p>
        </div>
        """,
    })
