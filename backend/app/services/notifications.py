import asyncio
import json
import logging
from typing import Optional

import aiosmtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import httpx

from app.models import Client, Run

logger = logging.getLogger(__name__)


class NotificationService:
    def __init__(self, smtp_server: str, smtp_port: int, smtp_username: str, smtp_password: str):
        self.smtp_server = smtp_server
        self.smtp_port = smtp_port
        self.smtp_username = smtp_username
        self.smtp_password = smtp_password

    async def send_email_notification(self, client: Client, run: Run) -> None:
        """Send email notification for run completion."""
        if not client.email:
            return

        try:
            msg = MIMEMultipart()
            msg['From'] = self.smtp_username
            msg['To'] = client.email
            msg['Subject'] = f"Test Run {run.status.title()} - {client.name}"

            body = f"""
Test run #{run.id} has {run.status}.

Client: {client.name}
Tests: {', '.join(run.selected_tests)}
Started: {run.started_at}
Finished: {run.finished_at}

View details: http://localhost:8000/runs/{run.id}
"""
            msg.attach(MIMEText(body, 'plain'))

            async with aiosmtplib.SMTP(hostname=self.smtp_server, port=self.smtp_port, use_tls=True) as smtp:
                await smtp.login(self.smtp_username, self.smtp_password)
                await smtp.send_message(msg)

            logger.info(f"Email notification sent to {client.email} for run {run.id}")
        except Exception as e:
            logger.error(f"Failed to send email notification: {e}")

    async def send_webhook_notification(self, client: Client, run: Run) -> None:
        """Send webhook notification for run completion."""
        if not client.webhook_url:
            return

        try:
            payload = {
                "run_id": run.id,
                "client_name": client.name,
                "status": run.status,
                "selected_tests": run.selected_tests,
                "started_at": run.started_at.isoformat() if run.started_at else None,
                "finished_at": run.finished_at.isoformat() if run.finished_at else None,
                "note": run.note
            }

            async with httpx.AsyncClient() as client_http:
                response = await client_http.post(
                    client.webhook_url,
                    json=payload,
                    headers={"Content-Type": "application/json"},
                    timeout=10.0
                )
                response.raise_for_status()

            logger.info(f"Webhook notification sent to {client.webhook_url} for run {run.id}")
        except Exception as e:
            logger.error(f"Failed to send webhook notification: {e}")

    async def notify_run_completion(self, client: Client, run: Run) -> None:
        """Send notifications for run completion."""
        await asyncio.gather(
            self.send_email_notification(client, run),
            self.send_webhook_notification(client, run)
        )