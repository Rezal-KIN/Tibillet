"""Verify the real SMTP envelope, without sending mail to an external server."""
import copy
import os
import sys
from pathlib import Path
from unittest.mock import Mock, patch

from django.conf import settings
from django.core.exceptions import ImproperlyConfigured
from django.core.mail import EmailMultiAlternatives
from django.test import SimpleTestCase, override_settings

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from gala_mail import TestRecipientEmailBackend

if not settings.configured:
    settings.configure()


@override_settings(EMAIL_HOST="smtp.example.org", EMAIL_PORT=587,
                   EMAIL_HOST_USER="test-user", EMAIL_HOST_PASSWORD="test-password",
                   EMAIL_USE_TLS=True, EMAIL_USE_SSL=False, DEFAULT_CHARSET="utf-8")
class SmokeMailTests(SimpleTestCase):
    def test_to_cc_bcc_and_headers_cannot_escape_the_test_mailbox(self):
        message = EmailMultiAlternatives(
            "Confirm your email", "https://galas-am-aix.rezal.fr/emailconfirmation/token/",
            "sender@example.org", ["participant@example.org"],
            cc=["cc@example.org"], bcc=["bcc@example.org"],
            headers={"To": "header@example.org", "Cc": "header-cc@example.org"},
        )
        message.attach_alternative("<p>Confirm your email</p>", "text/html")
        original = copy.deepcopy(message)
        smtp = Mock()
        with patch.dict(os.environ, {"GALA_TEST_MAIL_RECIPIENT": "smoke@example.org"}), \
                patch("smtplib.SMTP", return_value=smtp):
            self.assertEqual(TestRecipientEmailBackend().send_messages([message]), 1)
        smtp.starttls.assert_called_once()
        smtp.login.assert_called_once_with("test-user", "test-password")
        sender, recipients, mime = smtp.sendmail.call_args.args
        self.assertEqual(sender, "sender@example.org")
        self.assertEqual(recipients, ["smoke@example.org"])
        for address in ("participant@", "cc@", "bcc@", "header@", "header-cc@"):
            self.assertNotIn(address.encode(), mime)
        self.assertIn(b"https://galas-am-aix.rezal.fr/emailconfirmation/token/", mime)
        self.assertIn(b"text/html", mime)
        self.assertEqual(message.to, original.to)
        self.assertEqual(message.cc, original.cc)
        self.assertEqual(message.bcc, original.bcc)
        self.assertEqual(message.extra_headers, original.extra_headers)
        self.assertEqual(message.alternatives, original.alternatives)

    def test_missing_or_invalid_recipient_fails_closed_even_when_silent(self):
        for recipient in ("", "not-an-email", "safe@example.org\r\nBcc: other@example.org"):
            with self.subTest(recipient=recipient), \
                    patch.dict(os.environ, {"GALA_TEST_MAIL_RECIPIENT": recipient}), \
                    patch("smtplib.SMTP") as smtp:
                with self.assertRaises(ImproperlyConfigured):
                    TestRecipientEmailBackend(fail_silently=True)
                smtp.assert_not_called()

    def test_empty_native_recipient_list_does_not_create_a_message(self):
        smtp = Mock()
        with patch.dict(os.environ, {"GALA_TEST_MAIL_RECIPIENT": "smoke@example.org"}), \
                patch("smtplib.SMTP", return_value=smtp):
            self.assertEqual(TestRecipientEmailBackend().send_messages([
                EmailMultiAlternatives("Empty", "Body", "sender@example.org", [])
            ]), 0)
        smtp.sendmail.assert_not_called()
