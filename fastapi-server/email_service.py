import os
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

from jinja2 import Environment, FileSystemLoader


def send_email(to: str, subject: str, template_name: str, context: dict):
    """
    Send an email with a Jinja2-rendered HTML template.

    Args:
        to: Recipient email address
        subject: Email subject line
        template_name: Name of the template file in templates/emails/
        context: Dictionary of variables to pass to the template

    Returns:
        True if email was sent successfully

    Raises:
        Exception if SMTP operation fails
    """
    env = Environment(loader=FileSystemLoader("templates/emails"))
    template = env.get_template(template_name)
    html = template.render(**context)

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = os.getenv("SMTP_USER", "noreply@example.com")
    msg["To"] = to
    msg.attach(MIMEText(html, "html"))

    smtp_host = os.getenv("SMTP_HOST", "localhost")
    smtp_port = int(os.getenv("SMTP_PORT", "587"))
    smtp_user = os.getenv("SMTP_USER")
    smtp_pass = os.getenv("SMTP_PASS")

    with smtplib.SMTP(smtp_host, smtp_port) as server:
        server.starttls()
        if smtp_user and smtp_pass:
            server.login(smtp_user, smtp_pass)
        server.send_message(msg)
    return True