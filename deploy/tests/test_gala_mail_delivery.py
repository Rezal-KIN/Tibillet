"""SMTP isolation without a database, network access or real credentials."""
import importlib.util
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from celery import Celery
from django.conf import settings
from django.core.mail import EmailMessage
from django.test import override_settings

if not settings.configured:
    settings.configure(SECRET_KEY="smtp-isolation-tests", INSTALLED_APPS=[])

spec = importlib.util.spec_from_file_location(
    "gala_mail_delivery", Path(__file__).resolve().parents[2] / "TiBillet/mail_delivery.py"
)
delivery = importlib.util.module_from_spec(spec)
spec.loader.exec_module(delivery)


class MailDeliveryTests(unittest.TestCase):
    def setUp(self):
        self.config = override_settings(
            TEST=False, EMAIL_DELIVERY_GUARD=True, EMAIL_DELIVERY_MODE="live",
            EMAIL_CAPTURE_HOST="mailpit", EMAIL_CAPTURE_PORT=1025,
        )
        self.config.enable()
        self.addCleanup(self.config.disable)
        self.current = patch.object(delivery, "current_task", None)
        self.current.start()
        self.addCleanup(self.current.stop)

    def task(self, marker=None, called_directly=False):
        return SimpleNamespace(request=SimpleNamespace(
            called_directly=called_directly,
            headers={} if marker is None else {delivery.MODE_HEADER: marker},
        ))

    def test_normal_web_request_is_live(self):
        self.assertEqual(delivery.delivery_mode(), "live")

    def test_tests_and_capture_profile_override_live_task(self):
        with patch.object(delivery, "current_task", self.task("live")):
            with override_settings(TEST=True):
                self.assertEqual(delivery.delivery_mode(), "capture")
            with override_settings(EMAIL_DELIVERY_MODE="capture"):
                self.assertEqual(delivery.delivery_mode(), "capture")

    def test_unmarked_and_invalid_tasks_are_captured(self):
        for marker in (None, "capture", "invalid"):
            with self.subTest(marker=marker), patch.object(delivery, "current_task", self.task(marker)):
                self.assertEqual(delivery.delivery_mode(), "capture")

    def test_marked_normal_task_is_live(self):
        with patch.object(delivery, "current_task", self.task("live")):
            self.assertEqual(delivery.delivery_mode(), "live")

    def test_synchronous_task_call_uses_runtime_mode(self):
        with patch.object(delivery, "current_task", self.task(called_directly=True)):
            self.assertEqual(delivery.delivery_mode(), "live")

    def test_publisher_marks_normal_tasks_and_preserves_other_headers(self):
        headers = {"tenant": "lespass"}
        delivery.mark_task_mail_mode(headers=headers)
        self.assertEqual(headers, {"tenant": "lespass", delivery.MODE_HEADER: "live"})

    def test_descendants_of_legacy_or_test_tasks_stay_captured(self):
        for marker in (None, "capture", "invalid"):
            with patch.object(delivery, "current_task", self.task(marker)):
                headers = {delivery.MODE_HEADER: "live"}
                delivery.mark_task_mail_mode(headers=headers)
                self.assertEqual(headers[delivery.MODE_HEADER], "capture")

    def test_explicit_capture_cannot_be_promoted_after_profile_restoration(self):
        headers = {delivery.MODE_HEADER: "capture"}
        delivery.mark_task_mail_mode(headers=headers)
        self.assertEqual(headers[delivery.MODE_HEADER], "capture")

    def test_test_process_cannot_request_live_mail(self):
        with override_settings(TEST=True):
            headers = {delivery.MODE_HEADER: "live"}
            delivery.mark_task_mail_mode(headers=headers)
            self.assertEqual(headers[delivery.MODE_HEADER], "capture")

    def test_other_deployments_keep_existing_metadata(self):
        with override_settings(EMAIL_DELIVERY_GUARD=False):
            headers = {"tenant": "lespass"}
            delivery.mark_task_mail_mode(headers=headers)
            self.assertEqual(headers, {"tenant": "lespass"})

    def test_celery_retry_keeps_capture_header(self):
        app = Celery("isolation-test", broker="memory://", fixups=[])
        def noop():
            pass
        task = app.task(noop, name="smtp-test")
        task.push_request(
            id="retry-test", args=(), kwargs={}, called_directly=False,
            headers={delivery.MODE_HEADER: "capture"},
        )
        try:
            signature = task.signature_from_request()
            self.assertEqual(signature.options["headers"][delivery.MODE_HEADER], "capture")
            headers = dict(signature.options["headers"])
            delivery.mark_task_mail_mode(headers=headers)
            self.assertEqual(headers[delivery.MODE_HEADER], "capture")
        finally:
            task.pop_request()
            app.close()

    def test_capture_clears_all_supplied_smtp_credentials_and_tls(self):
        mail = EmailMessage("test", "body", "sender@example.invalid", ["recipient@example.invalid"])
        with override_settings(TEST=True), patch.object(delivery, "SMTPBackend") as smtp:
            smtp.return_value.__enter__.return_value.send_messages.return_value = 1
            backend = delivery.EmailBackend(
                host="smtp.example.invalid", username="private", password="private",
                use_tls=True, use_ssl=True, ssl_keyfile="private.pem",
            )
            self.assertEqual(backend.send_messages([mail]), 1)
            options = smtp.call_args.kwargs
            self.assertEqual((options["host"], options["port"]), ("mailpit", 1025))
            self.assertEqual((options["username"], options["password"]), ("", ""))
            self.assertFalse(options["use_tls"])
            self.assertFalse(options["use_ssl"])
            self.assertIsNone(options["ssl_keyfile"])

    def test_live_uses_django_smtp_configuration(self):
        with patch.object(delivery, "SMTPBackend") as smtp:
            delivery.EmailBackend().send_messages([object()])
            smtp.assert_called_once_with(fail_silently=False)

    def test_reused_backend_rechecks_mode(self):
        backend = delivery.EmailBackend()
        with patch.object(delivery, "SMTPBackend") as smtp:
            backend.send_messages([object()])
            self.assertNotIn("host", smtp.call_args.kwargs)
            with override_settings(EMAIL_DELIVERY_MODE="capture"):
                backend.send_messages([object()])
            self.assertEqual(smtp.call_args.kwargs["host"], "mailpit")


if __name__ == "__main__":
    unittest.main()
