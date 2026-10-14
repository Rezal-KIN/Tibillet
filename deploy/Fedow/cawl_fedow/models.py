from uuid import uuid4
from django.db import models


class Checkout(models.Model):
    uuid = models.UUIDField(primary_key=True, default=uuid4, editable=False)
    wallet = models.ForeignKey("fedow_core.Wallet", on_delete=models.PROTECT)
    place = models.ForeignKey("fedow_core.Place", on_delete=models.PROTECT)
    asset = models.ForeignKey("fedow_core.Asset", on_delete=models.PROTECT)
    merchant_id = models.CharField(max_length=128)
    test_mode = models.BooleanField(default=True)
    amount = models.PositiveIntegerField()
    hosted_checkout_id = models.CharField(max_length=128, unique=True, null=True)
    checkout_url = models.URLField(max_length=1000, blank=True)
    provider_payment_id = models.CharField(max_length=128, unique=True, null=True)
    provider_status = models.CharField(max_length=64, blank=True)
    refill = models.OneToOneField("fedow_core.Transaction", on_delete=models.PROTECT, null=True)
    lock_version = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)


class Webhook(models.Model):
    event_id = models.CharField(max_length=128, primary_key=True)
    received_at = models.DateTimeField(auto_now_add=True)
