import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

# Email details
sender = "your_email@example.com"
receiver = "karthiks233@gmail.com"

# SMTP setup (example for Gmail)
smtp_server = "smtp.gmail.com"
smtp_port = 587
password = "YOUR_APP_PASSWORD"  # use an app-specific password, not your real login

def send_notification(subject, body, receiver_email=None):
    """Send email notification."""
    receiver_email = receiver_email or receiver
    
    msg = MIMEMultipart()
    msg["From"] = sender
    msg["To"] = receiver_email
    msg["Subject"] = subject
    msg.attach(MIMEText(body, "plain"))
    
    try:
        with smtplib.SMTP(smtp_server, smtp_port) as server:
            server.starttls()
            server.login(sender, password)
            server.send_message(msg)
        print(f"✅ Email notification sent to {receiver_email}!")
        return True
    except Exception as e:
        print(f"⚠️ Failed to send email notification: {e}")
        return False
