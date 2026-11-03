"""Réglages partagés ; les soldes et ventes restent dans les modèles natifs.
/ Shared settings; balances and sales stay in the native models.
"""
import uuid

from django.conf import settings
from django.db import models


class CollectiveConfiguration(models.Model):
    id = models.PositiveSmallIntegerField(primary_key=True, default=1, editable=False)
    login_venue = models.ForeignKey('Customers.Client', on_delete=models.PROTECT,
                                    related_name='+')
    live_venue = models.ForeignKey('Customers.Client', on_delete=models.PROTECT,
                                   related_name='+', null=True, blank=True)

    class Meta:
        app_label = 'seo'
        permissions = [('manage_collective', 'Gérer le collectif des Galas')]


class GalaEdition(models.Model):
    venue = models.OneToOneField('Customers.Client', on_delete=models.PROTECT,
                                 related_name='gala_edition')
    gala_date = models.DateField(null=True, blank=True)
    enabled = models.BooleanField(default=True)
    disabled_assets = models.JSONField(default=list, blank=True)

    class Meta:
        app_label = 'seo'
        ordering = ['-gala_date', 'pk']


class PrimaryCard(models.Model):
    card = models.OneToOneField('QrcodeCashless.CarteCashless', on_delete=models.PROTECT,
                                related_name='collective_primary')

    class Meta:
        app_label = 'seo'


class PrimaryCardAccess(models.Model):
    primary = models.ForeignKey(PrimaryCard, on_delete=models.CASCADE, related_name='accesses')
    edition = models.ForeignKey(GalaEdition, on_delete=models.PROTECT, related_name='card_accesses')
    enabled = models.BooleanField(default=False)
    edit_mode = models.BooleanField(default=False)
    point_ids = models.JSONField(default=list, blank=True)
    sync_error = models.BooleanField(default=False)

    class Meta:
        app_label = 'seo'
        constraints = [models.UniqueConstraint(fields=['primary', 'edition'],
                                               name='collective_card_edition_unique')]


class PortalTransfer(models.Model):
    # Un ticket aléatoire à usage unique, lié à un hôte et une destination fixe.
    # / A random single-use ticket bound to one host and a fixed destination.
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE,
                             null=True, blank=True)
    domain = models.CharField(max_length=253)
    destination = models.CharField(max_length=24)
    expires_at = models.DateTimeField()
    used_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        app_label = 'seo'


class CollectiveAudit(models.Model):
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True)
    action = models.CharField(max_length=40)
    subject = models.CharField(max_length=100)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        app_label = 'seo'
