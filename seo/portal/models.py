"""Réglages partagés ; les soldes et ventes restent dans les modèles natifs.
/ Shared settings; balances and sales stay in the native models.
"""
import uuid

from django.conf import settings
from django.core.exceptions import ValidationError
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
    currency_isolated = models.BooleanField(default=False)
    currency = models.OneToOneField('fedow_core.Asset', on_delete=models.PROTECT,
                                   null=True, blank=True, related_name='gala_edition')

    def prepare_currency(self):
        from django.db import transaction
        from django_tenants.utils import tenant_context
        from BaseBillet.models import Configuration
        from fedow_connect.models import FedowConfig
        from fedow_core.models import Asset
        from fedow_core.services import AssetService

        with transaction.atomic(), tenant_context(self.venue):
            edition = type(self).objects.select_for_update().get(pk=self.pk)
            if not edition.currency_isolated:
                raise ValidationError('Cette édition n’utilise pas l’initialisation monétaire automatique.')
            if edition.currency_id:
                return edition.currency
            wallet = FedowConfig.get_solo().wallet
            if wallet is None:
                raise ValidationError('Le portefeuille natif du lieu n’est pas encore prêt.')
            monnaies = AssetService.obtenir_assets_du_tenant(self.venue).filter(category=Asset.TLF)
            if monnaies.count() > 1:
                raise ValidationError('Plusieurs monnaies locales existent : vérification nécessaire avant activation.')
            monnaie = monnaies.first()
            if monnaie is None:
                config = Configuration.get_solo()
                # Le service et son signal natifs fabriquent déjà les recharges.
                # / Native services and signals already generate top-up products.
                monnaie = AssetService.creer_asset(
                    tenant=self.venue, name=f'Monnaie {self.venue.name}', category=Asset.TLF,
                    currency_code=config.currency_code, wallet_origin=wallet,
                )
            edition.currency = monnaie
            edition.save(update_fields=['currency'])
            self.currency = monnaie
            return monnaie

    def save(self, *args, **kwargs):
        if self.pk:
            previous = type(self).objects.filter(pk=self.pk).values('currency_id', 'currency_isolated').first()
            if previous:
                if previous['currency_id'] and previous['currency_id'] != self.currency_id:
                    raise ValidationError('La monnaie d’une édition ne peut pas être remplacée.')
                if previous['currency_isolated'] and not self.currency_isolated:
                    raise ValidationError('Le cloisonnement monétaire de cette édition doit être conservé.')
        if self.currency_id:
            if self.currency.tenant_origin_id != self.venue_id or self.currency.category != 'TLF':
                raise ValidationError('La monnaie du gala doit être sa monnaie locale fiduciaire.')
        super().save(*args, **kwargs)

    class Meta:
        app_label = 'seo'
        ordering = ['-gala_date', 'pk']


def currency_policy_for_venue(venue):
    """Seules les nouvelles éditions explicitement cloisonnées sont concernées.
    / Only explicitly isolated new editions use this policy; existing venues stay native.
    """
    if not getattr(settings, 'GALA_CASHLESS_PORTAL', False) or not getattr(venue, 'pk', None):
        return None
    return GalaEdition.objects.filter(venue=venue, currency_isolated=True).only('currency_id').first()


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
