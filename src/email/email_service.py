"""
Email service for sending flight risk alerts to users.
"""
import os
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime, timedelta
import logging

logger = logging.getLogger(__name__)


class EmailService:
    """Service for sending email notifications."""
    
    def __init__(self):
        """Initialize email service with SMTP configuration."""
        self.smtp_host = os.environ.get('SMTP_HOST', 'smtp.gmail.com')
        self.smtp_port = int(os.environ.get('SMTP_PORT', '587'))
        self.smtp_user = os.environ.get('SMTP_USER', '')
        self.smtp_password = os.environ.get('SMTP_PASSWORD', '')
        self.from_email = os.environ.get('SMTP_FROM_EMAIL', self.smtp_user)
        self.from_name = os.environ.get('SMTP_FROM_NAME', 'SkyGuard AI')
        
        # Check if email is configured
        self.is_configured = bool(self.smtp_user and self.smtp_password)
        
        if not self.is_configured:
            logger.warning("Email service not configured. Set SMTP_USER and SMTP_PASSWORD in .env file")
    
    def send_email(self, to_email, subject, html_body, text_body=None):
        """
        Send an email.
        
        Args:
            to_email: Recipient email address
            subject: Email subject
            html_body: HTML content of the email
            text_body: Plain text fallback (optional)
        
        Returns:
            bool: True if sent successfully, False otherwise
        """
        if not self.is_configured:
            logger.error("Cannot send email - service not configured")
            return False
        
        try:
            # Create message
            msg = MIMEMultipart('alternative')
            msg['Subject'] = subject
            msg['From'] = f"{self.from_name} <{self.from_email}>"
            msg['To'] = to_email
            
            # Add plain text version if provided
            if text_body:
                msg.attach(MIMEText(text_body, 'plain'))
            
            # Add HTML version
            msg.attach(MIMEText(html_body, 'html'))
            
            # Send email
            with smtplib.SMTP(self.smtp_host, self.smtp_port) as server:
                server.starttls()
                server.login(self.smtp_user, self.smtp_password)
                server.send_message(msg)
            
            logger.info(f"Email sent successfully to {to_email}: {subject}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to send email to {to_email}: {e}")
            return False
    
    def send_flight_alert(self, user_email, user_name, alert_data):
        """
        Send a flight risk alert email.
        
        Args:
            user_email: User's email address
            user_name: User's name
            alert_data: Dictionary containing alert information
        
        Returns:
            bool: True if sent successfully
        """
        subject = f"⚠️ SkyGuard AI Alert: {alert_data.get('title', 'Flight Risk Detected')}"
        
        html_body = self._create_alert_html(user_name, alert_data)
        text_body = self._create_alert_text(user_name, alert_data)
        
        return self.send_email(user_email, subject, html_body, text_body)
    
    def send_batch_flight_alert(self, user_email, user_name, watchlist_name, flights):
        """
        Send a batch alert email with multiple flights from one watchlist check.
        
        Args:
            user_email: User's email address
            user_name: User's name
            watchlist_name: Name of the watchlist
            flights: List of flight dictionaries
        
        Returns:
            bool: True if sent successfully
        """
        flight_count = len(flights)
        subject = f"⚠️ SkyGuard AI: {flight_count} High-Risk Flight{'s' if flight_count > 1 else ''} in {watchlist_name}"
        
        html_body = self._create_batch_alert_html(user_name, watchlist_name, flights)
        text_body = self._create_batch_alert_text(user_name, watchlist_name, flights)
        
        return self.send_email(user_email, subject, html_body, text_body)
    
    def send_otp(self, user_email, otp_code, purpose='signup'):
        """
        Send OTP verification email.
        
        Args:
            user_email: User's email address
            otp_code: 6-digit OTP code
            purpose: Purpose of OTP (signup, password_reset, etc.)
        
        Returns:
            bool: True if sent successfully
        """
        purpose_titles = {
            'signup': 'Email Verification',
            'password_reset': 'Password Reset',
            'email_change': 'Email Change Verification'
        }
        
        title = purpose_titles.get(purpose, 'Verification')
        subject = f"🔐 SkyGuard AI - {title} Code"
        
        html_body = self._create_otp_html(user_email, otp_code, purpose, title)
        text_body = self._create_otp_text(otp_code, purpose, title)
        
        return self.send_email(user_email, subject, html_body, text_body)
    
    def _create_otp_html(self, user_email, otp_code, purpose, title):
        """Create HTML email body for OTP."""
        html = f"""
<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
</head>
<body style="margin: 0; padding: 0; font-family: Arial, sans-serif; background-color: #0f172a; color: #e2e8f0;">
    <div style="max-width: 600px; margin: 0 auto; padding: 20px;">
        <!-- Header -->
        <div style="background: linear-gradient(135deg, #3b82f6, #8b5cf6); padding: 30px; border-radius: 12px 12px 0 0; text-align: center;">
            <h1 style="margin: 0; color: white; font-size: 24px;">🛡️ SkyGuard AI</h1>
            <p style="margin: 10px 0 0 0; color: rgba(255,255,255,0.9);">Flight Risk Alert System</p>
        </div>
        
        <!-- Content -->
        <div style="background-color: #1e293b; padding: 40px 30px; border-radius: 0 0 12px 12px;">
            <h2 style="margin: 0 0 20px 0; color: #f59e0b; font-size: 22px;">{title}</h2>
            
            <p style="margin: 0 0 30px 0; font-size: 16px; line-height: 1.6;">
                Thank you for using SkyGuard AI! Please use the following verification code to complete your {purpose}:
            </p>
            
            <!-- OTP Code -->
            <div style="background: linear-gradient(135deg, #3b82f6, #8b5cf6); padding: 30px; border-radius: 12px; text-align: center; margin: 30px 0;">
                <div style="font-size: 42px; font-weight: bold; color: white; letter-spacing: 8px; font-family: 'Courier New', monospace;">
                    {otp_code}
                </div>
            </div>
            
            <div style="background-color: #334155; padding: 20px; border-radius: 8px; margin: 30px 0;">
                <p style="margin: 0 0 10px 0; font-size: 14px; color: #fbbf24;">⚠️ Important Security Information:</p>
                <ul style="margin: 0; padding-left: 20px; font-size: 14px; line-height: 1.8; color: #cbd5e1;">
                    <li>This code expires in <strong>10 minutes</strong></li>
                    <li>Do not share this code with anyone</li>
                    <li>SkyGuard AI will never ask for this code via phone or email</li>
                    <li>If you didn't request this code, please ignore this email</li>
                </ul>
            </div>
            
            <p style="margin: 30px 0 0 0; font-size: 14px; color: #94a3b8;">
                If you have any questions, please contact our support team.
            </p>
        </div>
        
        <!-- Footer -->
        <div style="text-align: center; padding: 20px; font-size: 12px; color: #64748b;">
            <p style="margin: 0;">© 2026 SkyGuard AI. All rights reserved.</p>
            <p style="margin: 10px 0 0 0;">Intelligent Flight Risk Assessment Platform</p>
        </div>
    </div>
</body>
</html>
"""
        return html
    
    def _create_otp_text(self, otp_code, purpose, title):
        """Create plain text email body for OTP."""
        text = f"""
SkyGuard AI - {title}

Your verification code is: {otp_code}

Please use this code to complete your {purpose}.

IMPORTANT:
- This code expires in 10 minutes
- Do not share this code with anyone
- SkyGuard AI will never ask for this code via phone or email
- If you didn't request this code, please ignore this email

If you have any questions, please contact our support team.

© 2026 SkyGuard AI. All rights reserved.
Intelligent Flight Risk Assessment Platform
"""
        return text
    
    def _create_alert_html(self, user_name, alert_data):
        """Create HTML email body for flight alert."""
        severity = alert_data.get('severity', 'MEDIUM')
        title = alert_data.get('title', 'Flight Alert')
        message = alert_data.get('message', '')
        flight_data = alert_data.get('flight_data', {})
        
        # Severity colors
        severity_colors = {
            'LOW': '#22c55e',
            'MEDIUM': '#f59e0b',
            'HIGH': '#ef4444'
        }
        color = severity_colors.get(severity, '#f59e0b')
        
        html = f"""
<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
</head>
<body style="margin: 0; padding: 0; font-family: Arial, sans-serif; background-color: #0f172a; color: #e2e8f0;">
    <div style="max-width: 600px; margin: 0 auto; padding: 20px;">
        <!-- Header -->
        <div style="background: linear-gradient(135deg, #3b82f6, #8b5cf6); padding: 30px; border-radius: 12px 12px 0 0; text-align: center;">
            <h1 style="margin: 0; color: white; font-size: 24px;">🛡️ SkyGuard AI</h1>
            <p style="margin: 10px 0 0 0; color: rgba(255,255,255,0.9);">Flight Risk Alert System</p>
        </div>
        
        <!-- Content -->
        <div style="background-color: #1e293b; padding: 30px; border-radius: 0 0 12px 12px;">
            <p style="margin: 0 0 20px 0; font-size: 16px;">Hi {user_name},</p>
            
            <!-- Alert Badge -->
            <div style="background-color: {color}; color: white; padding: 12px 20px; border-radius: 8px; margin-bottom: 20px; text-align: center;">
                <strong style="font-size: 18px;">{severity} SEVERITY ALERT</strong>
            </div>
            
            <!-- Alert Details -->
            <div style="background-color: rgba(59, 130, 246, 0.1); padding: 20px; border-radius: 8px; border-left: 4px solid #3b82f6; margin-bottom: 20px;">
                <h2 style="margin: 0 0 15px 0; color: #60a5fa; font-size: 18px;">{title}</h2>
                <p style="margin: 0; line-height: 1.6; color: #cbd5e1;">{message}</p>
            </div>
            
            <!-- Flight Information -->
"""
        
        if flight_data:
            html += """
            <div style="background-color: rgba(255, 255, 255, 0.05); padding: 20px; border-radius: 8px; margin-bottom: 20px;">
                <h3 style="margin: 0 0 15px 0; color: #60a5fa; font-size: 16px;">📋 Flight Details</h3>
                <table style="width: 100%; border-collapse: collapse;">
"""
            
            if 'callsign' in flight_data:
                html += f"""
                    <tr>
                        <td style="padding: 8px 0; color: #94a3b8;">Callsign:</td>
                        <td style="padding: 8px 0; color: #e2e8f0; font-weight: 600;">{flight_data['callsign']}</td>
                    </tr>
"""
            
            if 'icao24' in flight_data:
                html += f"""
                    <tr>
                        <td style="padding: 8px 0; color: #94a3b8;">ICAO24:</td>
                        <td style="padding: 8px 0; color: #e2e8f0;">{flight_data['icao24']}</td>
                    </tr>
"""
            
            if 'origin_country' in flight_data:
                html += f"""
                    <tr>
                        <td style="padding: 8px 0; color: #94a3b8;">Origin:</td>
                        <td style="padding: 8px 0; color: #e2e8f0;">{flight_data['origin_country']}</td>
                    </tr>
"""
            
            if 'risk_score' in flight_data:
                html += f"""
                    <tr>
                        <td style="padding: 8px 0; color: #94a3b8;">Risk Score:</td>
                        <td style="padding: 8px 0; color: #ef4444; font-weight: 600;">{flight_data['risk_score']:.2f}</td>
                    </tr>
"""
            
            html += """
                </table>
            </div>
"""
        
        html += f"""
            <!-- Action Button -->
            <div style="text-align: center; margin: 30px 0;">
                <a href="http://127.0.0.1:5500/dashboard.html" 
                   style="display: inline-block; background: linear-gradient(135deg, #3b82f6, #8b5cf6); color: white; 
                          padding: 14px 32px; border-radius: 8px; text-decoration: none; font-weight: 600; font-size: 16px;">
                    View Dashboard
                </a>
            </div>
            
            <!-- Timestamp -->
            <div style="text-align: center; margin-top: 30px; padding-top: 20px; border-top: 1px solid rgba(255,255,255,0.1);">
                <p style="margin: 0; color: #64748b; font-size: 14px;">
                    Alert sent on {(datetime.now() + timedelta(hours=5, minutes=30)).strftime('%B %d, %Y at %I:%M %p IST')}
                </p>
            </div>
            
            <!-- Footer -->
            <div style="margin-top: 20px; text-align: center;">
                <p style="margin: 0; color: #64748b; font-size: 12px;">
                    This is an automated alert from SkyGuard AI. To manage your alert preferences, 
                    <a href="http://127.0.0.1:5500/dashboard.html" style="color: #60a5fa; text-decoration: none;">visit your dashboard</a>.
                </p>
            </div>
        </div>
    </div>
</body>
</html>
"""
        return html
    
    def _create_alert_text(self, user_name, alert_data):
        """Create plain text email body for flight alert."""
        severity = alert_data.get('severity', 'MEDIUM')
        title = alert_data.get('title', 'Flight Alert')
        message = alert_data.get('message', '')
        flight_data = alert_data.get('flight_data', {})
        
        text = f"""
SkyGuard AI - Flight Risk Alert
{'=' * 50}

Hi {user_name},

{severity} SEVERITY ALERT

{title}

{message}

"""
        
        if flight_data:
            text += "Flight Details:\n"
            text += "-" * 50 + "\n"
            
            if 'callsign' in flight_data:
                text += f"Callsign: {flight_data['callsign']}\n"
            if 'icao24' in flight_data:
                text += f"ICAO24: {flight_data['icao24']}\n"
            if 'origin_country' in flight_data:
                text += f"Origin: {flight_data['origin_country']}\n"
            if 'risk_score' in flight_data:
                text += f"Risk Score: {flight_data['risk_score']:.2f}\n"
            
            text += "\n"
        
        text += f"""
View your dashboard: http://127.0.0.1:5500/dashboard.html

---
This is an automated message from SkyGuard AI.
"""
        
        return text
    
    def _create_batch_alert_html(self, user_name, watchlist_name, flights):
        """Create HTML email body for batch flight alerts."""
        flight_count = len(flights)
        
        # Determine overall severity
        high_count = sum(1 for f in flights if f.get('risk_level') == 'HIGH')
        medium_count = sum(1 for f in flights if f.get('risk_level') == 'MEDIUM')
        low_count = sum(1 for f in flights if f.get('risk_level') == 'LOW')
        
        if high_count > 0:
            overall_severity = 'HIGH'
            severity_color = '#dc3545'
        elif medium_count > 0:
            overall_severity = 'MEDIUM'
            severity_color = '#ffc107'
        else:
            overall_severity = 'LOW'
            severity_color = '#28a745'
        
        # Build flights table rows
        flight_rows = ""
        for flight in flights:
            risk_level = flight.get('risk_level', 'UNKNOWN')
            risk_colors = {
                'HIGH': '#dc3545',
                'MEDIUM': '#ffc107',
                'LOW': '#28a745'
            }
            risk_color = risk_colors.get(risk_level, '#6c757d')
            
            flight_rows += f"""
                <tr>
                    <td style="padding: 12px; border-bottom: 1px solid #dee2e6;">{flight.get('callsign', 'N/A')}</td>
                    <td style="padding: 12px; border-bottom: 1px solid #dee2e6;">{flight.get('icao24', 'N/A')}</td>
                    <td style="padding: 12px; border-bottom: 1px solid #dee2e6;">{flight.get('origin_country', 'N/A')}</td>
                    <td style="padding: 12px; border-bottom: 1px solid #dee2e6;">{flight.get('risk_score', 0):.2f}</td>
                    <td style="padding: 12px; border-bottom: 1px solid #dee2e6;">
                        <span style="background-color: {risk_color}; color: white; padding: 4px 12px; border-radius: 12px; font-size: 12px; font-weight: bold;">
                            {risk_level}
                        </span>
                    </td>
                </tr>
            """
        
        html = f"""
<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
</head>
<body style="margin: 0; padding: 0; font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; background-color: #f8f9fa;">
    <div style="max-width: 650px; margin: 40px auto; background: white; border-radius: 12px; overflow: hidden; box-shadow: 0 4px 12px rgba(0,0,0,0.1);">
        <div style="background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); padding: 30px; text-align: center;">
            <h1 style="color: white; margin: 0; font-size: 28px; font-weight: 600;">⚠️ SkyGuard AI Alert</h1>
        </div>
        
        <div style="padding: 30px;">
            <p style="color: #333; font-size: 16px; margin-bottom: 20px;">
                Hello <strong>{user_name}</strong>,
            </p>
            
            <div style="background: linear-gradient(135deg, {severity_color}15 0%, {severity_color}05 100%); border-left: 4px solid {severity_color}; padding: 20px; margin: 20px 0; border-radius: 6px;">
                <div style="display: flex; align-items: center; margin-bottom: 15px;">
                    <span style="background-color: {severity_color}; color: white; padding: 6px 16px; border-radius: 16px; font-size: 14px; font-weight: bold; margin-right: 12px;">
                        {overall_severity} SEVERITY
                    </span>
                    <span style="color: #333; font-size: 18px; font-weight: 600;">
                        {flight_count} High-Risk Flight{'s' if flight_count > 1 else ''} Detected
                    </span>
                </div>
                
                <p style="color: #555; font-size: 15px; margin: 10px 0 0 0; line-height: 1.6;">
                    Multiple high-risk flights have been detected in your watchlist <strong>"{watchlist_name}"</strong>.
                </p>
            </div>
            
            <h3 style="color: #333; margin-top: 30px; margin-bottom: 15px; font-size: 18px;">Flight Summary</h3>
            <div style="background: #f8f9fa; padding: 15px; border-radius: 8px; margin-bottom: 20px;">
                <div style="display: flex; justify-content: space-around; text-align: center;">
                    <div>
                        <div style="color: #dc3545; font-size: 24px; font-weight: bold;">{high_count}</div>
                        <div style="color: #666; font-size: 12px;">HIGH</div>
                    </div>
                    <div>
                        <div style="color: #ffc107; font-size: 24px; font-weight: bold;">{medium_count}</div>
                        <div style="color: #666; font-size: 12px;">MEDIUM</div>
                    </div>
                    <div>
                        <div style="color: #28a745; font-size: 24px; font-weight: bold;">{low_count}</div>
                        <div style="color: #666; font-size: 12px;">LOW</div>
                    </div>
                    <div>
                        <div style="color: #667eea; font-size: 24px; font-weight: bold;">{flight_count}</div>
                        <div style="color: #666; font-size: 12px;">TOTAL</div>
                    </div>
                </div>
            </div>
            
            <h3 style="color: #333; margin-top: 30px; margin-bottom: 15px; font-size: 18px;">Flight Details</h3>
            <div style="overflow-x: auto;">
                <table style="width: 100%; border-collapse: collapse; background: white; border-radius: 8px; overflow: hidden;">
                    <thead>
                        <tr style="background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);">
                            <th style="padding: 12px; text-align: left; color: white; font-weight: 600; font-size: 13px;">Callsign</th>
                            <th style="padding: 12px; text-align: left; color: white; font-weight: 600; font-size: 13px;">ICAO24</th>
                            <th style="padding: 12px; text-align: left; color: white; font-weight: 600; font-size: 13px;">Origin</th>
                            <th style="padding: 12px; text-align: left; color: white; font-weight: 600; font-size: 13px;">Risk Score</th>
                            <th style="padding: 12px; text-align: left; color: white; font-weight: 600; font-size: 13px;">Level</th>
                        </tr>
                    </thead>
                    <tbody>
                        {flight_rows}
                    </tbody>
                </table>
            </div>
            
            <div style="text-align: center; margin-top: 30px;">
                <a href="http://127.0.0.1:5500/dashboard.html" style="background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); color: white; padding: 14px 32px; text-decoration: none; border-radius: 6px; font-weight: 600; display: inline-block; font-size: 15px;">
                    View Dashboard
                </a>
            </div>
            
            <div style="margin-top: 30px; padding-top: 20px; border-top: 1px solid #dee2e6; color: #666; font-size: 13px; text-align: center;">
                <p style="margin: 5px 0;">This is an automated message from SkyGuard AI</p>
                <p style="margin: 5px 0;">Sent at {(datetime.now() + timedelta(hours=5, minutes=30)).strftime('%Y-%m-%d %I:%M:%S %p IST')}</p>
            </div>
        </div>
    </div>
</body>
</html>
"""
        return html
    
    def _create_batch_alert_text(self, user_name, watchlist_name, flights):
        """Create plain text email body for batch flight alerts."""
        flight_count = len(flights)
        
        # Count by severity
        high_count = sum(1 for f in flights if f.get('risk_level') == 'HIGH')
        medium_count = sum(1 for f in flights if f.get('risk_level') == 'MEDIUM')
        low_count = sum(1 for f in flights if f.get('risk_level') == 'LOW')
        
        text = f"""
SkyGuard AI - Flight Risk Alert
{'=' * 60}

Hi {user_name},

MULTIPLE HIGH-RISK FLIGHTS DETECTED

{flight_count} high-risk flight{'s' if flight_count > 1 else ''} detected in watchlist: {watchlist_name}

SUMMARY
{'-' * 60}
HIGH severity:    {high_count}
MEDIUM severity:  {medium_count}
LOW severity:     {low_count}
TOTAL flights:    {flight_count}

FLIGHT DETAILS
{'-' * 60}
"""
        
        for i, flight in enumerate(flights, 1):
            text += f"""
Flight #{i}:
  Callsign:     {flight.get('callsign', 'N/A')}
  ICAO24:       {flight.get('icao24', 'N/A')}
  Origin:       {flight.get('origin_country', 'N/A')}
  Risk Score:   {flight.get('risk_score', 0):.2f}
  Risk Level:   {flight.get('risk_level', 'UNKNOWN')}
"""
        
        text += f"""
{'-' * 60}

View your dashboard: http://127.0.0.1:5500/dashboard.html

Alert sent on {datetime.now().strftime('%B %d, %Y at %I:%M %p')}

---
This is an automated alert from SkyGuard AI.
To manage your alert preferences, visit your dashboard.
"""
        
        return text


# Global email service instance
_email_service = None


def get_email_service():
    """Get the global email service instance."""
    global _email_service
    if _email_service is None:
        _email_service = EmailService()
    return _email_service
