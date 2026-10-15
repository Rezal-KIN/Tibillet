"""Use Django's SMTP delivery while confining Smoke mail to its test mailbox."""
import copy
import os

from django.core.exceptions import ImproperlyConfigured, ValidationError
from django.core.mail.backends.smtp import EmailBackend
from django.core.validators import validate_email


class TestRecipientEmailBackend(EmailBackend):
    def __init__(self, *args, **kwargs):
        self.test_recipient = os.environ.get("GALA_TEST_MAIL_RECIPIENT", "")
        try:
            validate_email(self.test_recipient)
        except ValidationError as error:
            raise ImproperlyConfigured("Smoke SMTP requires a valid test recipient") from error
        super().__init__(*args, **kwargs)

    def _send(self, email_message):
        if not email_message.recipients():
            return False
        # Preserve the caller's message, attachments, alternatives and login
        # links. Only the delivery recipients differ from the native backend.
        message = copy.copy(email_message)
        message.to = [self.test_recipient]
        message.cc = []
        message.bcc = []
        message.extra_headers = {
            key: value for key, value in email_message.extra_headers.items()
            if key.lower() not in {"to", "cc", "bcc", "resent-to", "resent-cc", "resent-bcc"}
        }
        return super()._send(message)
