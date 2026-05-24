from django.db import models


class LocalRefundRequest(models.Model):
    class Meta:
        app_label = 'BaseBillet'
        db_table = 'BaseBillet_localrefundrequest'

    STATUS_PENDING = 'pending'
    STATUS_APPROVED = 'approved'
    STATUS_REJECTED = 'rejected'
    STATUS_CHOICES = [
        (STATUS_PENDING, 'En attente'),
        (STATUS_APPROVED, 'Approuvé'),
        (STATUS_REJECTED, 'Rejeté'),
    ]

    user_email = models.EmailField()
    user_uuid = models.CharField(max_length=100, blank=True)
    nom = models.CharField(max_length=100)
    prenom = models.CharField(max_length=100)
    iban = models.CharField(max_length=34)
    bic = models.CharField(max_length=11)
    ticket_number = models.CharField(max_length=100, blank=True)
    id_document = models.FileField(upload_to='refund_uploads/')
    local_balance = models.DecimalField(max_digits=10, decimal_places=2)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_PENDING)
    created_at = models.DateTimeField(auto_now_add=True)
    notes = models.TextField(blank=True)

    def __str__(self):
        return f"Remboursement {self.prenom} {self.nom} ({self.user_email}) — {self.local_balance} €"
