"""
Email notification service for PCCM Faculty Hub
Handles confirmation emails for IRPA shifts and unavailability requests
Uses Gmail SMTP (replacing Resend)
"""

import os
import smtplib
from datetime import datetime
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from typing import List, Dict
import logging

logger = logging.getLogger(__name__)

# Email configuration
SENDER_EMAIL = os.getenv("GMAIL_USER", "uvapccmfacultyhub@gmail.com")
SENDER_NAME = "PCCM Faculty Hub"

# Gmail SMTP configuration
GMAIL_PASSWORD = os.getenv("GMAIL_APP_PASSWORD")
SMTP_SERVER = "smtp.gmail.com"
SMTP_PORT = 465


def format_date_with_day(date_str: str) -> str:
    """
    Format date string to include day of week
    Input: '2025-12-25' or datetime object
    Output: 'Thursday, December 25, 2025'
    """
    if isinstance(date_str, str):
        date_obj = datetime.strptime(date_str, "%Y-%m-%d")
    else:
        date_obj = date_str
    
    return date_obj.strftime("%A, %B %d, %Y")


def format_date_list(dates: List[str]) -> str:
    """
    Format a list of dates into a nice bulleted list with day of week
    """
    formatted_dates = [f"  • {format_date_with_day(date)}" for date in sorted(dates)]
    return "\n".join(formatted_dates)


def create_irpa_confirmation_email(
    faculty_name: str,
    faculty_email: str,
    selected_dates: List[str],
    academic_year: str
) -> str:
    """
    Create HTML email body for IRPA shift confirmation
    """
    date_count = len(selected_dates)
    date_list = format_date_list(selected_dates)
    
    html_content = f"""
    <html>
    <head>
        <style>
            body {{
                font-family: Arial, sans-serif;
                line-height: 1.6;
                color: #333;
                max-width: 600px;
                margin: 0 auto;
                padding: 20px;
            }}
            .header {{
                background-color: #232D4B;
                color: #E57200;
                padding: 20px;
                text-align: center;
                border-radius: 5px 5px 0 0;
            }}
            .content {{
                background-color: #f9f9f9;
                padding: 20px;
                border: 1px solid #ddd;
                border-radius: 0 0 5px 5px;
            }}
            .dates {{
                background-color: white;
                padding: 15px;
                margin: 15px 0;
                border-left: 4px solid #E57200;
                font-family: monospace;
            }}
            .summary {{
                background-color: #E8F4F8;
                padding: 15px;
                margin: 15px 0;
                border-radius: 5px;
            }}
            .footer {{
                margin-top: 20px;
                padding-top: 20px;
                border-top: 1px solid #ddd;
                font-size: 12px;
                color: #666;
                text-align: center;
            }}
        </style>
    </head>
    <body>
        <div class="header">
            <h2>IRPA Shift Selection Confirmed</h2>
        </div>
        <div class="content">
            <p>Dear Dr. {faculty_name},</p>
            
            <p>This email confirms your IRPA (moonlighting) shift selections for Academic Year {academic_year}.</p>
            
            <div class="summary">
                <strong>Total Nights Selected: {date_count}</strong>
            </div>
            
            <p><strong>Your Selected Dates:</strong></p>
            <div class="dates">
{date_list}
            </div>
            
            <p>These selections have been recorded in the PCCM Faculty Hub system. You can review or modify your selections by logging into the Faculty Hub.</p>
            
            <p>If you have any questions or need to make changes, please contact the scheduling team or access the Faculty Hub at your convenience.</p>
            
            <p>Thank you,<br>
            <strong>PCCM Division Scheduling</strong></p>
        </div>
        <div class="footer">
            <p>This is an automated message from the PCCM Faculty Hub. Please do not reply to this email.</p>
            <p>University of Virginia Health | Division of Pulmonary and Critical Care Medicine</p>
        </div>
    </body>
    </html>
    """
    
    return html_content


def create_unavailability_confirmation_email(
    faculty_name: str,
    faculty_email: str,
    selected_weeks: List[Dict],
    academic_year: str
) -> str:
    """
    Create HTML email body for unavailability request confirmation
    """
    week_count = len(selected_weeks)
    
    # Format weeks with date ranges
    week_list_items = []
    for week in sorted(selected_weeks, key=lambda x: x['week_number']):
        week_num = week['week_number']
        start = format_date_with_day(week['start_date'])
        end = format_date_with_day(week['end_date'])
        week_list_items.append(f"  • Week {week_num}: {start} → {end}")
    
    week_list = "\n".join(week_list_items)
    
    html_content = f"""
    <html>
    <head>
        <style>
            body {{
                font-family: Arial, sans-serif;
                line-height: 1.6;
                color: #333;
                max-width: 600px;
                margin: 0 auto;
                padding: 20px;
            }}
            .header {{
                background-color: #232D4B;
                color: #E57200;
                padding: 20px;
                text-align: center;
                border-radius: 5px 5px 0 0;
            }}
            .content {{
                background-color: #f9f9f9;
                padding: 20px;
                border: 1px solid #ddd;
                border-radius: 0 0 5px 5px;
            }}
            .weeks {{
                background-color: white;
                padding: 15px;
                margin: 15px 0;
                border-left: 4px solid #232D4B;
                font-family: monospace;
                font-size: 14px;
            }}
            .summary {{
                background-color: #E8F4F8;
                padding: 15px;
                margin: 15px 0;
                border-radius: 5px;
            }}
            .warning {{
                background-color: #FFF3CD;
                border-left: 4px solid #FFC107;
                padding: 15px;
                margin: 15px 0;
            }}
            .footer {{
                margin-top: 20px;
                padding-top: 20px;
                border-top: 1px solid #ddd;
                font-size: 12px;
                color: #666;
                text-align: center;
            }}
        </style>
    </head>
    <body>
        <div class="header">
            <h2>Unavailability Request Confirmed</h2>
        </div>
        <div class="content">
            <p>Dear Dr. {faculty_name},</p>
            
            <p>This email confirms your unavailability requests for inpatient service during Academic Year {academic_year}.</p>
            
            <div class="summary">
                <strong>Total Weeks Requested: {week_count}</strong>
            </div>
            
            <p><strong>Your Requested Unavailable Weeks:</strong></p>
            <div class="weeks">
{week_list}
            </div>
            
            <div class="warning">
                <strong>Important Notes:</strong>
                <ul>
                    <li>These are <em>requests</em> for unavailability and are subject to the point-based bidding system</li>
                    <li>Final approval depends on your bid order and available capacity for each week</li>
                    <li>You will receive notification when the final schedule is published</li>
                </ul>
            </div>
            
            <p>You can review or modify your unavailability requests by logging into the PCCM Faculty Hub. Changes can be made until the bidding window closes.</p>
            
            <p>If you have questions about the bidding process or point system, please contact the scheduling team.</p>
            
            <p>Thank you,<br>
            <strong>PCCM Division Scheduling</strong></p>
        </div>
        <div class="footer">
            <p>This is an automated message from the PCCM Faculty Hub. Please do not reply to this email.</p>
            <p>University of Virginia Health | Division of Pulmonary and Critical Care Medicine</p>
        </div>
    </body>
    </html>
    """
    
    return html_content


def create_wave_draft_confirmation_email(
    faculty_name: str,
    faculty_email: str,
    unavailable_weeks: List[Dict],
    volunteer_weeks: List[Dict],
    rejected: List[Dict],
    academic_year: str
) -> str:
    """
    Create HTML email body for wave draft submission confirmation.
    Covers both unavailable and volunteer selections plus any rejections.
    """
    # Format unavailable weeks
    unavail_items = []
    for week in sorted(unavailable_weeks, key=lambda x: x['week_number']):
        start = format_date_with_day(week['start_date'])
        end = format_date_with_day(week['end_date'])
        unavail_items.append(f"  • Week {week['week_number']}: {start} → {end}")
    unavail_list = "\n".join(unavail_items) if unavail_items else "  (none)"

    # Format volunteer weeks
    vol_items = []
    for week in sorted(volunteer_weeks, key=lambda x: x['week_number']):
        start = format_date_with_day(week['start_date'])
        end = format_date_with_day(week['end_date'])
        vol_items.append(f"  • Week {week['week_number']}: {start} → {end}")
    vol_list = "\n".join(vol_items) if vol_items else "  (none)"

    # Format rejected weeks
    rejected_section = ""
    if rejected:
        rej_items = [f"  • {r.get('label', r.get('week_id', 'Unknown'))} — {r.get('reason', 'capacity reached')}" for r in rejected]
        rej_list = "\n".join(rej_items)
        rejected_section = f"""
            <div style="background-color: #FEE2E2; border-left: 4px solid #DC2626; padding: 15px; margin: 15px 0;">
                <strong>⚠ Rejected ({len(rejected)}):</strong>
                <div style="font-family: monospace; font-size: 14px; margin-top: 8px; white-space: pre-line;">{rej_list}</div>
            </div>
        """

    html_content = f"""
    <html>
    <head>
        <style>
            body {{
                font-family: Arial, sans-serif;
                line-height: 1.6;
                color: #333;
                max-width: 600px;
                margin: 0 auto;
                padding: 20px;
            }}
            .header {{
                background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                color: white;
                padding: 20px;
                text-align: center;
                border-radius: 5px 5px 0 0;
            }}
            .content {{
                background-color: #f9f9f9;
                padding: 20px;
                border: 1px solid #ddd;
                border-radius: 0 0 5px 5px;
            }}
            .weeks {{
                background-color: white;
                padding: 15px;
                margin: 15px 0;
                border-left: 4px solid #232D4B;
                font-family: monospace;
                font-size: 14px;
                white-space: pre-line;
            }}
            .volunteer-weeks {{
                background-color: white;
                padding: 15px;
                margin: 15px 0;
                border-left: 4px solid #10b981;
                font-family: monospace;
                font-size: 14px;
                white-space: pre-line;
            }}
            .summary {{
                background-color: #E8F4F8;
                padding: 15px;
                margin: 15px 0;
                border-radius: 5px;
            }}
            .footer {{
                margin-top: 20px;
                padding-top: 20px;
                border-top: 1px solid #ddd;
                font-size: 12px;
                color: #666;
                text-align: center;
            }}
        </style>
    </head>
    <body>
        <div class="header">
            <h2>Service Availability Selections Confirmed</h2>
        </div>
        <div class="content">
            <p>Dear Dr. {faculty_name},</p>

            <p>This email confirms your service availability selections for Academic Year {academic_year}.</p>

            <div class="summary">
                <strong>Unavailable: {len(unavailable_weeks)} week(s)</strong> &nbsp;|&nbsp;
                <strong>Volunteer: {len(volunteer_weeks)} week(s)</strong>
            </div>

            <p><strong>Weeks Marked Unavailable:</strong></p>
            <div class="weeks">{unavail_list}</div>

            <p><strong>Weeks Volunteered:</strong></p>
            <div class="volunteer-weeks">{vol_list}</div>

            {rejected_section}

            <p>You can review or modify your selections by logging into the <a href="https://facultyhub.pccm.uva.edu/service-availability.html">PCCM Faculty Hub</a> until the draft submission window closes.</p>

            <p>Thank you,<br>
            <strong>PCCM Division Scheduling</strong></p>
        </div>
        <div class="footer">
            <p>This is an automated message from the PCCM Faculty Hub. Please do not reply to this email.</p>
            <p>University of Virginia Health | Division of Pulmonary and Critical Care Medicine</p>
        </div>
    </body>
    </html>
    """

    return html_content


def send_wave_draft_confirmation(
    faculty_name: str,
    faculty_email: str,
    unavailable_weeks: List[Dict],
    volunteer_weeks: List[Dict],
    rejected: List[Dict],
    academic_year: str
) -> bool:
    """
    Send wave draft submission confirmation email.

    Args:
        faculty_name: Faculty member's full name
        faculty_email: Faculty member's email address
        unavailable_weeks: List of dicts with 'week_number', 'start_date', 'end_date'
        volunteer_weeks: List of dicts with 'week_number', 'start_date', 'end_date'
        rejected: List of dicts with 'week_id', 'type', 'reason'
        academic_year: e.g., "2026-2027"

    Returns:
        bool: True if email sent successfully
    """
    subject = f"Service Availability Selections Confirmed - AY {academic_year}"
    html_content = create_wave_draft_confirmation_email(
        faculty_name, faculty_email, unavailable_weeks, volunteer_weeks, rejected, academic_year
    )

    return send_email(faculty_email, faculty_name, subject, html_content)


def send_email(to_email: str, to_name: str, subject: str, html_content: str, reply_to: str = None) -> bool:
    """
    Send email via Gmail SMTP
    
    Args:
        to_email: Recipient email address
        to_name: Recipient name
        subject: Email subject line
        html_content: HTML body of email
        reply_to: Optional reply-to email address
    
    Returns:
        bool: True if successful, False otherwise
    """
    if not GMAIL_PASSWORD:
        logger.error("GMAIL_APP_PASSWORD environment variable not set")
        return False
    
    try:
        # Create message
        msg = MIMEMultipart('alternative')
        msg['From'] = f"{SENDER_NAME} <{SENDER_EMAIL}>"
        msg['To'] = to_email
        msg['Subject'] = subject
        
        if reply_to:
            msg['Reply-To'] = reply_to
        
        # Attach HTML content
        html_part = MIMEText(html_content, 'html')
        msg.attach(html_part)
        
        # Send via Gmail SMTP
        with smtplib.SMTP_SSL(SMTP_SERVER, SMTP_PORT) as server:
            server.login(SENDER_EMAIL, GMAIL_PASSWORD)
            server.send_message(msg)
        
        logger.info(f"Email sent successfully to {to_email}: {subject}")
        return True
            
    except Exception as e:
        logger.error(f"Error sending email to {to_email}: {str(e)}")
        return False


def send_irpa_confirmation(
    faculty_name: str,
    faculty_email: str,
    selected_dates: List[str],
    academic_year: str
) -> bool:
    """
    Send IRPA shift confirmation email
    
    Args:
        faculty_name: Faculty member's full name
        faculty_email: Faculty member's email address
        selected_dates: List of date strings in YYYY-MM-DD format
        academic_year: e.g., "2025-2026"
    
    Returns:
        bool: True if email sent successfully
    """
    subject = f"IRPA Shift Selection Confirmed - AY {academic_year}"
    html_content = create_irpa_confirmation_email(
        faculty_name, faculty_email, selected_dates, academic_year
    )
    
    return send_email(faculty_email, faculty_name, subject, html_content)


def send_unavailability_confirmation(
    faculty_name: str,
    faculty_email: str,
    selected_weeks: List[Dict],
    academic_year: str
) -> bool:
    """
    Send unavailability request confirmation email
    
    Args:
        faculty_name: Faculty member's full name
        faculty_email: Faculty member's email address
        selected_weeks: List of dicts with 'week_number', 'start_date', 'end_date'
        academic_year: e.g., "2025-2026"
    
    Returns:
        bool: True if email sent successfully
    """
    subject = f"Unavailability Request Confirmed - AY {academic_year}"
    html_content = create_unavailability_confirmation_email(
        faculty_name, faculty_email, selected_weeks, academic_year
    )
    
    return send_email(faculty_email, faculty_name, subject, html_content)


def send_feedback_email(
    user_name: str,
    user_email: str,
    feedback_type: str,
    message: str,
    page_url: str = None
) -> bool:
    """
    Send feedback submission email to admin
    
    Args:
        user_name: Name of user submitting feedback
        user_email: Email of user submitting feedback  
        feedback_type: Type of feedback (bug, feature, question, etc.)
        message: The feedback message content
        page_url: Optional URL of page where feedback was submitted
    
    Returns:
        bool: True if email sent successfully
    """
    admin_email = "ke4z@uvahealth.org"
    
    # Format timestamp
    timestamp = datetime.now().strftime("%A, %B %d, %Y at %I:%M %p")
    
    # Build page URL section if provided
    page_section = ""
    if page_url:
        page_section = f"""
                <p><strong>Page:</strong> <a href="{page_url}">{page_url}</a></p>
        """
    
    html_content = f"""
    <html>
    <head>
        <style>
            body {{
                font-family: Arial, sans-serif;
                line-height: 1.6;
                color: #333;
                max-width: 600px;
                margin: 0 auto;
                padding: 20px;
            }}
            .header {{
                background-color: #232D4B;
                color: #E57200;
                padding: 20px;
                text-align: center;
                border-radius: 5px 5px 0 0;
            }}
            .content {{
                background-color: #f9f9f9;
                padding: 20px;
                border: 1px solid #ddd;
                border-radius: 0 0 5px 5px;
            }}
            .feedback {{
                background-color: white;
                padding: 15px;
                margin: 15px 0;
                border-left: 4px solid #E57200;
                white-space: pre-wrap;
            }}
            .meta {{
                background-color: #E8F4F8;
                padding: 15px;
                margin: 15px 0;
                border-radius: 5px;
            }}
            .type-badge {{
                display: inline-block;
                background-color: #E57200;
                color: white;
                padding: 4px 12px;
                border-radius: 12px;
                font-size: 12px;
                font-weight: bold;
                text-transform: uppercase;
            }}
        </style>
    </head>
    <body>
        <div class="header">
            <h2>Faculty Hub Feedback Received</h2>
        </div>
        <div class="content">
            <div class="meta">
                <p><strong>From:</strong> {user_name} ({user_email})</p>
                <p><strong>Type:</strong> <span class="type-badge">{feedback_type}</span></p>
                <p><strong>Submitted:</strong> {timestamp}</p>
{page_section}
            </div>
            
            <p><strong>Message:</strong></p>
            <div class="feedback">
{message}
            </div>
        </div>
    </body>
    </html>
    """
    
    subject = f"Faculty Hub Feedback [{feedback_type.upper()}] from {user_name}"
    
    # Include reply-to so you can reply directly to the user
    return send_email(admin_email, "Admin", subject, html_content, reply_to=user_email)

def send_draft_notification(faculty_id: str, priority: int, deadline: datetime, round_year: int):
    """
    Send email notification when faculty's draft window opens
    """
    from .models import SessionLocal, Faculty
    
    db = SessionLocal()
    try:
        faculty = db.query(Faculty).filter(Faculty.id == faculty_id).first()
        
        if not faculty or not faculty.email:
            print(f"No email found for faculty {faculty_id}")
            return
        
        # Format deadline
        deadline_str = deadline.strftime("%A, %B %d at %I:%M %p")
        
        subject = f"Your Service Availability Window is Now Open - Priority #{priority}"
        
        html_body = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <style>
                body {{ font-family: Arial, sans-serif; line-height: 1.6; color: #333; }}
                .container {{ max-width: 600px; margin: 0 auto; padding: 20px; }}
                .header {{ background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); color: white; padding: 30px; text-align: center; border-radius: 8px 8px 0 0; }}
                .content {{ background: #f9fafb; padding: 30px; border-radius: 0 0 8px 8px; }}
                .priority-badge {{ background: #667eea; color: white; padding: 8px 16px; border-radius: 20px; display: inline-block; font-weight: bold; margin: 20px 0; }}
                .deadline {{ background: #fff; border-left: 4px solid #ef4444; padding: 15px; margin: 20px 0; }}
                .button {{ background: #667eea; color: white; padding: 15px 30px; text-decoration: none; border-radius: 8px; display: inline-block; font-weight: bold; margin: 20px 0; }}
                .footer {{ text-align: center; color: #6b7280; font-size: 12px; margin-top: 30px; }}
                .tips {{ background: #dbeafe; border-left: 4px solid #3b82f6; padding: 15px; margin: 20px 0; }}
            </style>
        </head>
        <body>
            <div class="container">
                <div class="header">
                    <h1>🎯 Your Turn to Select!</h1>
                    <p>Service Availability Draft - AY {round_year}-{round_year + 1}</p>
                </div>
                <div class="content">
                    <p>Dear Dr. {faculty.name.split()[-1]},</p>
                    
                    <p>Your service availability selection window is now open!</p>
                    
                    <div class="priority-badge">Priority #{priority}</div>
                    
                    <div class="deadline">
                        <strong>⏰ Deadline:</strong> {deadline_str}<br>
                        <strong>Time Remaining:</strong> 72 hours
                    </div>
                    
                    <div class="tips">
                        <strong>💡 Quick Tips:</strong>
                        <ul>
                            <li>Week costs increase as more faculty request them</li>
                            <li>Up to 5 faculty can select simultaneously</li>
                            <li>Submit early to see more availability</li>
                            <li>You can volunteer for weeks to earn points</li>
                        </ul>
                    </div>
                    
                    <div style="text-align: center;">
                        <a href="https://facultyhub.pccm.uva.edu/service-availability.html" class="button">
                            Submit Your Selections Now →
                        </a>
                    </div>
                    
                    <p style="margin-top: 30px; color: #6b7280; font-size: 14px;">
                        Available Points: <strong>{faculty.base_points + faculty.bonus_points}</strong><br>
                        Current Status: <strong>ACTIVE - Window Open</strong>
                    </p>
                </div>
                <div class="footer">
                    <p>This is an automated notification from the PCCM Faculty Hub</p>
                    <p>University of Virginia - Division of Pulmonary and Critical Care Medicine</p>
                </div>
            </div>
        </body>
        </html>
        """
        
        text_body = f"""
        Your Service Availability Window is Now Open
        
        Dear Dr. {faculty.name.split()[-1]},
        
        Your service availability selection window is now open for AY {round_year}-{round_year + 1}.
        
        Priority: #{priority}
        Deadline: {deadline_str}
        Time Remaining: 72 hours
        
        Submit your selections at: https://facultyhub.pccm.uva.edu/service-availability.html
        
        Available Points: {faculty.base_points + faculty.bonus_points}
        
        Tips:
        - Week costs increase as more faculty request them
        - Up to 5 faculty can select simultaneously
        - Submit early to see more availability
        - You can volunteer for weeks to earn points
        
        ---
        PCCM Faculty Hub - University of Virginia
        """
        
        send_email(
            to_email=faculty.email,
            to_name=faculty.name,
            subject=subject,
            html_content=html_body
        )
        
        print(f"Draft notification sent to {faculty.name} ({faculty.email})")
        
    finally:
        db.close()

# Password Rest
def send_password_reset_email(
    faculty_name: str,
    faculty_email: str,
    reset_token: str
) -> bool:
    """
    Send password reset email with token
    
    Args:
        faculty_name: Faculty member's full name
        faculty_email: Faculty member's email address
        reset_token: Unique password reset token
    
    Returns:
        bool: True if email sent successfully
    """
    # Construct reset URL (update with your actual domain)
    reset_url = f"https://yourdomain.com/reset-password?token={reset_token}"
    # For local testing:
    # reset_url = f"http://localhost:8000/reset-password?token={reset_token}"
    
    subject = "Password Reset Request - PCCM Faculty Hub"
    
    html_content = f"""
    <html>
    <head>
        <style>
            body {{
                font-family: Arial, sans-serif;
                line-height: 1.6;
                color: #333;
                max-width: 600px;
                margin: 0 auto;
                padding: 20px;
            }}
            .header {{
                background-color: #232D4B;
                color: #E57200;
                padding: 20px;
                text-align: center;
                border-radius: 5px 5px 0 0;
            }}
            .content {{
                background-color: #f9f9f9;
                padding: 20px;
                border: 1px solid #ddd;
                border-radius: 0 0 5px 5px;
            }}
            .button {{
                display: inline-block;
                background-color: #E57200;
                color: white;
                padding: 12px 24px;
                text-decoration: none;
                border-radius: 5px;
                margin: 20px 0;
            }}
            .warning {{
                background-color: #FFF3CD;
                border-left: 4px solid #FFC107;
                padding: 15px;
                margin: 15px 0;
            }}
            .footer {{
                margin-top: 20px;
                padding-top: 20px;
                border-top: 1px solid #ddd;
                font-size: 12px;
                color: #666;
                text-align: center;
            }}
        </style>
    </head>
    <body>
        <div class="header">
            <h2>Password Reset Request</h2>
        </div>
        <div class="content">
            <p>Dear Dr. {faculty_name},</p>
            
            <p>You recently requested to reset your password for your PCCM Faculty Hub account.</p>
            
            <p>Click the button below to reset your password:</p>
            
            <p style="text-align: center;">
                <a href="{reset_url}" class="button">Reset Password</a>
            </p>
            
            <p>Or copy and paste this link into your browser:</p>
            <p style="font-family: monospace; background-color: #f0f0f0; padding: 10px; word-break: break-all;">
                {reset_url}
            </p>
            
            <div class="warning">
                <strong>⚠️ Important:</strong>
                <ul>
                    <li>This link will expire in 24 hours</li>
                    <li>The link can only be used once</li>
                    <li>If you didn't request this, you can safely ignore this email</li>
                </ul>
            </div>
            
            <p>If you did not request a password reset, please contact support if you have concerns about account security.</p>
            
            <p>Thank you,<br>
            <strong>PCCM Division IT</strong></p>
        </div>
        <div class="footer">
            <p>This is an automated message from the PCCM Faculty Hub. Please do not reply to this email.</p>
            <p>University of Virginia Health | Division of Pulmonary and Critical Care Medicine</p>
        </div>
    </body>
    </html>
    """
    
    return send_email(faculty_email, faculty_name, subject, html_content)
