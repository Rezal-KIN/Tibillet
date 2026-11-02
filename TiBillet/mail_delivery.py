"""Opt-in SMTP isolation for the public gala-test VM.

Only trusted Celery metadata carries the mode; HTTP headers never select it.
Unmarked tasks predate the cutover and must keep using the capture server.
"""
from celery import current_task
from django.conf import settings
from django.core.mail.backends.base import BaseEmailBackend
from django.core.mail.backends.smtp import EmailBackend as SMTPBackend


MODE_HEADER = "tibillet_mail_mode"


def delivery_mode():
    if getattr(settings, "TEST", False):
        return "capture"
    if getattr(settings, "EMAIL_DELIVERY_MODE", "capture") != "live":
        return "capture"
    task = current_task
    if task and not task.request.called_directly:
        headers = task.request.headers or {}
        return "live" if headers.get(MODE_HEADER) == "live" else "capture"
    return "live"


def mark_task_mail_mode(headers=None, **kwargs):
    if not getattr(settings, "EMAIL_DELIVERY_GUARD", False) or headers is None:
        return
    # An explicit capture marker (including a retry) can never be promoted.
    existing = headers.get(MODE_HEADER)
    headers[MODE_HEADER] = (
        "live" if delivery_mode() == "live" and existing in (None, "live")
        else "capture"
    )


class EmailBackend(BaseEmailBackend):
    """Resolve the destination for every batch, even on a reused connection."""

    def __init__(self, fail_silently=False, **kwargs):
        super().__init__(fail_silently=fail_silently)
        self.smtp_options = kwargs

    def send_messages(self, email_messages):
        if not email_messages:
            return 0
        options = dict(self.smtp_options)
        if delivery_mode() == "capture":
            options.update(
                host=settings.EMAIL_CAPTURE_HOST,
                port=settings.EMAIL_CAPTURE_PORT,
                username="", password="", use_tls=False, use_ssl=False,
                ssl_keyfile=None, ssl_certfile=None, timeout=10,
            )
        with SMTPBackend(fail_silently=self.fail_silently, **options) as backend:
            return backend.send_messages(email_messages)
