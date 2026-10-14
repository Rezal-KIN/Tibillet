from django.db import models


class CawlPayment(models.Model):
    # FR : La FK garde les ventes et l'historique existants sans renommer de table.
    # EN: Keep existing sales and history without renaming the legacy table.
    payment = models.OneToOneField(
        "BaseBillet.Paiement_stripe", primary_key=True,
        on_delete=models.PROTECT, related_name="cawl_payment",
    )
    merchant_id = models.CharField(max_length=128)
    test_mode = models.BooleanField(default=True)
    amount = models.PositiveIntegerField()
    hosted_checkout_id = models.CharField(max_length=128, unique=True, null=True)
    checkout_url = models.URLField(max_length=1000, blank=True)
    provider_payment_id = models.CharField(max_length=128, unique=True, null=True)
    provider_status = models.CharField(max_length=64, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)


class CawlWebhook(models.Model):
    event_id = models.CharField(max_length=128, primary_key=True)
    event_type = models.CharField(max_length=128)
    received_at = models.DateTimeField(auto_now_add=True)


class CawlRefund(models.Model):
    operation_id = models.UUIDField(primary_key=True, editable=False)
    payment = models.ForeignKey(CawlPayment, on_delete=models.PROTECT, related_name="refunds")
    amount = models.PositiveIntegerField()
    allocations = models.JSONField(default=list)
    provider_refund_id = models.CharField(max_length=128, unique=True, null=True)
    status = models.CharField(max_length=64, default="CREATED")
    accounted = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
