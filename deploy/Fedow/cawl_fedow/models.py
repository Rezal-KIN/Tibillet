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


class WalletRefundRequest(models.Model):
    """One signed user confirmation, possibly allocated to several recharges."""

    uuid = models.UUIDField(primary_key=True, editable=False)
    wallet = models.ForeignKey("fedow_core.Wallet", on_delete=models.PROTECT)
    place = models.ForeignKey("fedow_core.Place", on_delete=models.PROTECT)
    amount = models.PositiveIntegerField(default=0)
    ip = models.GenericIPAddressField(default="0.0.0.0")
    created_at = models.DateTimeField(auto_now_add=True)


class WalletRefund(models.Model):
    uuid = models.UUIDField(primary_key=True, default=uuid4, editable=False)
    request = models.ForeignKey(WalletRefundRequest, on_delete=models.PROTECT, related_name="refunds")
    checkout = models.ForeignKey(Checkout, on_delete=models.PROTECT, related_name="refunds")
    amount = models.PositiveIntegerField()
    # Native append-only ledger: reserve with RFD, release with COR only on rejection.
    debit = models.OneToOneField("fedow_core.Transaction", on_delete=models.PROTECT, related_name="+")
    release = models.OneToOneField("fedow_core.Transaction", on_delete=models.PROTECT, related_name="+", null=True)
    provider_refund_id = models.CharField(max_length=128, unique=True, null=True)
    status = models.CharField(max_length=64, default="CREATED", db_index=True)
    first_attempt_at = models.DateTimeField(null=True)
    last_attempt_at = models.DateTimeField(null=True)
    error_code = models.CharField(max_length=64, blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["request", "checkout"], name="cawl_wallet_refund_allocation_unique"),
            models.CheckConstraint(check=models.Q(amount__gt=0), name="cawl_wallet_refund_amount_positive"),
        ]
