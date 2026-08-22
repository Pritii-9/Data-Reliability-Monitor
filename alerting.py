import os
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from dotenv import load_dotenv

load_dotenv()

SMTP_EMAIL = os.getenv("SMTP_EMAIL")
SMTP_APP_PASSWORD = os.getenv("SMTP_APP_PASSWORD")
ALERT_RECIPIENT = os.getenv("ALERT_RECIPIENT")

def send_alert(ticket_title, description, severity, timestamp):
    """
    Sends an email alert for a newly created ticket.
    Falls back to console print if SMTP credentials are not configured.
    """
    if not all([SMTP_EMAIL, SMTP_APP_PASSWORD, ALERT_RECIPIENT]):
        print("\n" + "="*50)
        print("⚠️ CONSOLE ALERT (SMTP Credentials Not Configured) ⚠️")
        print(f"Severity: {severity}")
        print(f"Title: {ticket_title}")
        print(f"Time: {timestamp}")
        print(f"Description:\n{description}")
        print("="*50 + "\n")
        return False
        
    try:
        msg = MIMEMultipart()
        msg['From'] = SMTP_EMAIL
        msg['To'] = ALERT_RECIPIENT
        msg['Subject'] = f"[{severity}] Data Pipeline Incident: {ticket_title}"
        
        # Color coding based on severity
        color_map = {"HIGH": "#dc3545", "MEDIUM": "#fd7e14", "LOW": "#28a745"}
        header_color = color_map.get(severity, "#6c757d")
        
        # Convert simple Markdown to beautiful HTML for the email
        import re
        html_description = description
        html_description = re.sub(r'\*\*(.*?)\*\*', r'<strong style="color:#1e293b;">\1</strong>', html_description)
        html_description = re.sub(r'(?<!\*)(\*[^\*]+\*)(?!\*)', lambda m: f'<em style="color:#64748b;">{m.group(1)[1:-1]}</em>', html_description)
        html_description = re.sub(r'`(.*?)`', r'<code style="background-color:#f1f5f9;padding:2px 6px;border-radius:4px;color:#ef4444;font-size:13px;font-family:monospace;">\1</code>', html_description)
        html_description = re.sub(r'### (.*?)\n', r'<h4 style="margin:15px 0 10px 0;color:#334155;border-bottom:1px solid #cbd5e1;padding-bottom:5px;">\1</h4>', html_description)
        html_description = html_description.replace('\n', '<br>')
        
        html_body = f"""
        <html>
        <body style="margin: 0; padding: 0; background-color: #f4f7f6; font-family: 'Helvetica Neue', Helvetica, Arial, sans-serif;">
            <table width="100%" border="0" cellspacing="0" cellpadding="0" style="padding: 20px;">
                <tr>
                    <td align="center">
                        <table width="600" border="0" cellspacing="0" cellpadding="0" style="background-color: #ffffff; border-radius: 8px; overflow: hidden; box-shadow: 0 4px 6px rgba(0,0,0,0.1);">
                            <!-- Header -->
                            <tr>
                                <td style="background-color: {header_color}; padding: 20px; text-align: center; color: #ffffff;">
                                    <h2 style="margin: 0; font-size: 24px;">🚨 Pipeline Incident Alert</h2>
                                </td>
                            </tr>
                            
                            <!-- Body Content -->
                            <tr>
                                <td style="padding: 30px;">
                                    <p style="font-size: 16px; color: #333333; margin-top: 0;">An anomaly has been detected in the data pipeline. A new incident ticket has been automatically generated.</p>
                                    
                                    <table width="100%" border="0" cellspacing="0" cellpadding="12" style="margin-top: 20px; border-collapse: collapse;">
                                        <tr>
                                            <td width="30%" style="border: 1px solid #eeeeee; background-color: #f9f9f9; font-weight: bold; color: #555555;">Ticket Title</td>
                                            <td width="70%" style="border: 1px solid #eeeeee; color: #333333;">{ticket_title}</td>
                                        </tr>
                                        <tr>
                                            <td style="border: 1px solid #eeeeee; background-color: #f9f9f9; font-weight: bold; color: #555555;">Severity</td>
                                            <td style="border: 1px solid #eeeeee; font-weight: bold; color: {header_color};">{severity}</td>
                                        </tr>
                                        <tr>
                                            <td style="border: 1px solid #eeeeee; background-color: #f9f9f9; font-weight: bold; color: #555555;">Timestamp</td>
                                            <td style="border: 1px solid #eeeeee; color: #333333;">{timestamp}</td>
                                        </tr>
                                    </table>
                                    
                                    <div style="margin-top: 25px; padding: 20px; background-color: #f8f9fa; border-left: 4px solid {header_color}; border-radius: 0 4px 4px 0;">
                                        <h4 style="margin: 0 0 10px 0; color: #444444; font-size: 14px; text-transform: uppercase;">Issue Details:</h4>
                                        <p style="margin: 0; color: #333333; font-size: 14px; line-height: 1.6;">
                                            {html_description}
                                        </p>
                                    </div>
                                    
                                    <!-- Call to Action -->
                                    <div style="margin-top: 35px; text-align: center;">
                                        <a href="http://localhost:8501" style="background-color: #2b3a42; color: #ffffff; padding: 14px 28px; text-decoration: none; border-radius: 6px; font-weight: bold; font-size: 16px; display: inline-block;">View Dashboard</a>
                                    </div>
                                </td>
                            </tr>
                            
                            <!-- Footer -->
                            <tr>
                                <td style="background-color: #f1f1f1; padding: 15px; text-align: center; color: #888888; font-size: 12px;">
                                    This is an automated message from the Data Reliability Monitor.<br>
                                    Please do not reply directly to this email.
                                </td>
                            </tr>
                        </table>
                    </td>
                </tr>
            </table>
        </body>
        </html>
        """
        
        msg.attach(MIMEText(html_body, 'html'))
        
        # Connect to Gmail SMTP
        server = smtplib.SMTP('smtp.gmail.com', 587)
        server.starttls()
        server.login(SMTP_EMAIL, SMTP_APP_PASSWORD)
        server.send_message(msg)
        server.quit()
        
        print(f"Email alert sent successfully for incident: {ticket_title}")
        return True
    except Exception as e:
        print(f"Failed to send email alert: {e}")
        return False

if __name__ == "__main__":
    # Test function
    send_alert("Test Ticket", "This is a test alert from the Data Reliability Monitor.", "LOW", "2023-01-01 12:00:00")
