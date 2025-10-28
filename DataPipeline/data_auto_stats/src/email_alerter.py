"""
Email Alert System for SEC Filings Validation Pipeline
Integrated with existing MONITORING_CONFIG
"""

import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.base import MIMEBase
from email import encoders
import json
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, List, Optional
import logging
import os
from dotenv import load_dotenv

# Import existing config
from config import MONITORING_CONFIG

load_dotenv('.env.email')

logger = logging.getLogger(__name__)

class EmailAlerter:
    """
    Email notification system for validation pipeline
    Uses MONITORING_CONFIG from config.py
    """
    
    def __init__(self, 
                 smtp_server: str = None,
                 smtp_port: int = None,
                 sender_email: str = None,
                 sender_password: str = None,
                 recipient_emails: List[str] = None):
        """
        Initialize email alerter - integrates with MONITORING_CONFIG
        """
        # Check if monitoring is enabled
        self.enabled = MONITORING_CONFIG.get('enable_metrics', True)
        
        if not self.enabled:
            logger.info("Monitoring disabled in config")
            self.configured = False
            return
        
        # Get SMTP configuration from env or parameters
        self.smtp_server = smtp_server or os.getenv('SMTP_SERVER', 'smtp.gmail.com')
        self.smtp_port = smtp_port or int(os.getenv('SMTP_PORT', '587'))
        self.sender_email = sender_email or os.getenv('SENDER_EMAIL')
        self.sender_password = sender_password or os.getenv('SENDER_PASSWORD')
        
        # Get recipients - prioritize MONITORING_CONFIG, then env, then parameters
        if recipient_emails:
            self.recipient_emails = recipient_emails
        else:
            # First check MONITORING_CONFIG
            config_email = MONITORING_CONFIG.get('alert_email')
            if config_email and config_email != 'data-team@company.com':  # Not default
                self.recipient_emails = [email.strip() for email in config_email.split(',')]
            else:
                # Fall back to env variable
                recipients_env = os.getenv('RECIPIENT_EMAILS', '')
                self.recipient_emails = [email.strip() for email in recipients_env.split(',') if email.strip()]
        
        # Set log level from config
        log_level = MONITORING_CONFIG.get('log_level', 'INFO')
        logging.getLogger().setLevel(getattr(logging, log_level))
        
        # Validate configuration
        if not all([self.smtp_server, self.smtp_port, self.sender_email, 
                   self.sender_password, self.recipient_emails]):
            logger.warning("Email configuration incomplete. Alerts will be logged but not sent.")
            self.configured = False
        else:
            self.configured = True
            logger.info(f"Email alerter configured for {len(self.recipient_emails)} recipients")
            logger.debug(f"Recipients: {self.recipient_emails}")
    
    def send_validation_alert(self, 
                              validation_results: Dict[str, Any],
                              attach_report: bool = True) -> bool:
        """
        Send email alert for validation results
        
        Args:
            validation_results: Dictionary containing validation results
            attach_report: Whether to attach the full JSON report
        
        Returns:
            bool: True if email sent successfully
        """
        if not self.enabled:
            logger.debug("Monitoring disabled - skipping email")
            return False
            
        if not self.configured:
            logger.warning("Email not configured. Logging alert instead.")
            self._log_alert(validation_results)
            return False
        
        try:
            # Determine status
            quality_score = validation_results.get('quality_report', {}).get('quality_score', 0)
            status = 'PASSED' if quality_score >= 80 else 'FAILED'
            
            # Create email
            msg = MIMEMultipart('alternative')
            
            # Email subject with status indicator
            subject_emoji = '✅' if status == 'PASSED' else '❌'
            msg['Subject'] = f"{subject_emoji} SEC Validation {status} - Score: {quality_score:.1f}%"
            msg['From'] = self.sender_email
            msg['To'] = ', '.join(self.recipient_emails)
            
            # Create both plain text and HTML versions
            text_body = self._create_text_body(validation_results, status)
            html_body = self._create_html_body(validation_results, status)
            
            # Attach parts
            msg.attach(MIMEText(text_body, 'plain'))
            msg.attach(MIMEText(html_body, 'html'))
            
            # Attach JSON report if requested
            if attach_report:
                attachment = self._create_json_attachment(validation_results)
                if attachment:
                    msg.attach(attachment)
            
            # Send email
            return self._send_email(msg)
            
        except Exception as e:
            logger.error(f"Failed to send email alert: {e}")
            return False
    
    def _create_text_body(self, results: Dict[str, Any], status: str) -> str:
        """Create plain text email body"""
        
        quality_score = results.get('quality_report', {}).get('quality_score', 0)
        checks_passed = results.get('quality_report', {}).get('checks_passed', 0)
        total_checks = results.get('quality_report', {}).get('total_checks', 0)
        
        body = f"""
SEC FILINGS VALIDATION REPORT
{'='*60}

VALIDATION STATUS: {status}
Timestamp: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
Monitoring Port: {MONITORING_CONFIG.get('metrics_port', 8000)}

SUMMARY
-------
• Quality Score: {quality_score:.1f}%
• Checks Passed: {checks_passed}/{total_checks}
• Data Shape: {results.get('data_loaded', {}).get('rows', 0):,} rows × {results.get('data_loaded', {}).get('columns', 0)} columns
• Schema Valid: {results.get('schema_validation', {}).get('is_valid', False)}

DATA QUALITY DETAILS
-------------------
"""
        
        # Add validation results
        validation_results = results.get('quality_report', {}).get('validation_results', {})
        
        failed_checks = []
        passed_checks = []
        
        for check_name, check_result in validation_results.items():
            if check_result.get('passed', False):
                passed_checks.append(check_name)
            else:
                failed_checks.append(check_name)
        
        if failed_checks:
            body += f"\nFAILED CHECKS ({len(failed_checks)}):\n"
            for check in failed_checks[:10]:  # Show first 10
                body += f"  ❌ {check}\n"
            if len(failed_checks) > 10:
                body += f"  ... and {len(failed_checks) - 10} more\n"
        
        if passed_checks:
            body += f"\nPASSED CHECKS ({len(passed_checks)}):\n"
            for check in passed_checks[:5]:  # Show first 5
                body += f"  ✓ {check}\n"
            if len(passed_checks) > 5:
                body += f"  ... and {len(passed_checks) - 5} more\n"
        
        # Add statistics summary
        stats = results.get('statistics', {})
        if stats:
            body += f"""

STATISTICS SUMMARY
-----------------
• Total Null Values: {stats.get('data_quality_metrics', {}).get('total_null_values', 0):,}
• Duplicate Rows: {stats.get('data_quality_metrics', {}).get('duplicate_rows', 0):,}
"""
        
        body += f"""

{'='*60}
Full report attached as JSON.
Log Level: {MONITORING_CONFIG.get('log_level', 'INFO')}
"""
        
        return body
    
    def _create_html_body(self, results: Dict[str, Any], status: str) -> str:
        """Create HTML email body"""
        
        quality_score = results.get('quality_report', {}).get('quality_score', 0)
        checks_passed = results.get('quality_report', {}).get('checks_passed', 0)
        total_checks = results.get('quality_report', {}).get('total_checks', 0)
        
        status_color = '#28a745' if status == 'PASSED' else '#dc3545'
        score_color = '#28a745' if quality_score >= 80 else '#ffc107' if quality_score >= 50 else '#dc3545'
        
        html = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <style>
                body {{ font-family: Arial, sans-serif; line-height: 1.6; color: #333; }}
                .container {{ max-width: 600px; margin: 0 auto; padding: 20px; }}
                .header {{ background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); color: white; padding: 20px; border-radius: 10px 10px 0 0; }}
                .status-badge {{ display: inline-block; padding: 5px 15px; border-radius: 20px; font-weight: bold; background: {status_color}; color: white; }}
                .content {{ background: #f8f9fa; padding: 20px; border: 1px solid #dee2e6; }}
                .metric-card {{ background: white; padding: 15px; margin: 10px 0; border-radius: 8px; box-shadow: 0 2px 4px rgba(0,0,0,0.1); }}
                .metric-title {{ color: #6c757d; font-size: 12px; text-transform: uppercase; }}
                .metric-value {{ font-size: 24px; font-weight: bold; color: #212529; }}
                .progress-bar {{ width: 100%; height: 20px; background: #e9ecef; border-radius: 10px; overflow: hidden; }}
                .progress-fill {{ height: 100%; background: {score_color}; width: {quality_score}%; }}
                .check-item {{ padding: 5px; margin: 3px 0; }}
                .failed {{ color: #dc3545; }}
                .passed {{ color: #28a745; }}
                .footer {{ margin-top: 20px; padding: 10px; background: #e9ecef; border-radius: 5px; font-size: 11px; color: #6c757d; }}
                table {{ width: 100%; border-collapse: collapse; }}
                th, td {{ padding: 8px; text-align: left; border-bottom: 1px solid #dee2e6; }}
                th {{ background: #f8f9fa; font-weight: bold; }}
            </style>
        </head>
        <body>
            <div class="container">
                <div class="header">
                    <h2 style="margin: 0;">SEC Filings Validation Report</h2>
                    <p style="margin: 10px 0;">
                        <span class="status-badge">{status}</span>
                    </p>
                    <p style="margin: 5px 0; font-size: 14px;">
                        {datetime.now().strftime('%B %d, %Y at %I:%M %p')}
                    </p>
                </div>
                
                <div class="content">
                    <div class="metric-card">
                        <div class="metric-title">Quality Score</div>
                        <div class="metric-value" style="color: {score_color};">{quality_score:.1f}%</div>
                        <div class="progress-bar">
                            <div class="progress-fill"></div>
                        </div>
                    </div>
                    
                    <div style="display: flex; gap: 10px;">
                        <div class="metric-card" style="flex: 1;">
                            <div class="metric-title">Checks Passed</div>
                            <div class="metric-value">{checks_passed}/{total_checks}</div>
                        </div>
                        <div class="metric-card" style="flex: 1;">
                            <div class="metric-title">Data Shape</div>
                            <div class="metric-value" style="font-size: 18px;">
                                {results.get('data_loaded', {}).get('rows', 0):,} × {results.get('data_loaded', {}).get('columns', 0)}
                            </div>
                        </div>
                    </div>
        """
        
        # Add failed checks summary
        validation_results = results.get('quality_report', {}).get('validation_results', {})
        failed_checks = [k for k, v in validation_results.items() if not v.get('passed', False)]
        
        if failed_checks:
            html += f"""
                    <div class="metric-card">
                        <h3 style="color: #dc3545; margin-top: 0;">Failed Checks ({len(failed_checks)})</h3>
                        <ul style="margin: 0; padding-left: 20px;">
            """
            for check in failed_checks[:5]:
                html += f'<li class="check-item failed">{check}</li>'
            if len(failed_checks) > 5:
                html += f'<li class="check-item" style="color: #6c757d;">... and {len(failed_checks) - 5} more</li>'
            html += """
                        </ul>
                    </div>
            """
        
        # Add key metrics table
        stats = results.get('statistics', {}).get('data_quality_metrics', {})
        if stats:
            html += f"""
                    <div class="metric-card">
                        <h3 style="margin-top: 0;">Key Metrics</h3>
                        <table>
                            <tr>
                                <th>Metric</th>
                                <th>Value</th>
                            </tr>
                            <tr>
                                <td>Total Null Values</td>
                                <td>{stats.get('total_null_values', 0):,}</td>
                            </tr>
                            <tr>
                                <td>Duplicate Rows</td>
                                <td>{stats.get('duplicate_rows', 0):,}</td>
                            </tr>
                            <tr>
                                <td>Schema Valid</td>
                                <td>{'✅ Yes' if results.get('schema_validation', {}).get('is_valid', False) else '❌ No'}</td>
                            </tr>
                        </table>
                    </div>
            """
        
        html += f"""
                    <div class="footer">
                        <strong>Monitoring Configuration:</strong><br>
                        Metrics Port: {MONITORING_CONFIG.get('metrics_port', 8000)} | 
                        Log Level: {MONITORING_CONFIG.get('log_level', 'INFO')}<br>
                        Full validation report attached as JSON file.
                    </div>
                </div>
            </div>
        </body>
        </html>
        """
        
        return html
    
    def _create_json_attachment(self, results: Dict[str, Any]) -> Optional[MIMEBase]:
        """Create JSON attachment with full results"""
        try:
            # Create attachment
            attachment = MIMEBase('application', 'json')
            
            # Convert results to JSON
            json_content = json.dumps(results, indent=2, default=str)
            attachment.set_payload(json_content.encode('utf-8'))
            
            # Encode
            encoders.encode_base64(attachment)
            
            # Add header
            filename = f"validation_report_{datetime.now():%Y%m%d_%H%M%S}.json"
            attachment.add_header(
                'Content-Disposition',
                f'attachment; filename={filename}'
            )
            
            return attachment
            
        except Exception as e:
            logger.error(f"Failed to create attachment: {e}")
            return None
    
    def _send_email(self, msg: MIMEMultipart) -> bool:
        """Send the email message"""
        try:
            # Create SMTP session
            if self.smtp_port == 465:  # SSL
                server = smtplib.SMTP_SSL(self.smtp_server, self.smtp_port)
            else:  # TLS
                server = smtplib.SMTP(self.smtp_server, self.smtp_port)
                server.starttls()
            
            # Login
            server.login(self.sender_email, self.sender_password)
            
            # Send email
            text = msg.as_string()
            server.sendmail(self.sender_email, self.recipient_emails, text)
            
            # Quit
            server.quit()
            
            logger.info(f"Email alert sent successfully to {len(self.recipient_emails)} recipients")
            return True
            
        except Exception as e:
            logger.error(f"Failed to send email: {e}")
            return False
    
    def _log_alert(self, results: Dict[str, Any]):
        """Log alert when email is not configured"""
        quality_score = results.get('quality_report', {}).get('quality_score', 0)
        status = 'PASSED' if quality_score >= 80 else 'FAILED'
        
        logger.info("="*60)
        logger.info(f"VALIDATION ALERT: {status}")
        logger.info(f"Quality Score: {quality_score:.1f}%")
        logger.info(f"Checks: {results.get('quality_report', {}).get('checks_passed', 0)}/{results.get('quality_report', {}).get('total_checks', 0)}")
        logger.info(f"Monitoring Port: {MONITORING_CONFIG.get('metrics_port', 8000)}")
        logger.info("="*60)