"""Initialisation explicite, sans compte créé ni élévation superutilisateur.
/ Explicit setup without creating accounts or granting superuser rights.
"""
from django.conf import settings
from django.contrib.auth.models import Group, Permission
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django_tenants.utils import schema_context


class Command(BaseCommand):
    help = 'Initialiser le portail avec un lieu et un compte administrateur existants.'

    def add_arguments(self, parser):
        parser.add_argument('--schema', required=True)
        parser.add_argument('--admin-email', required=True)

    def handle(self, *args, **options):
        if not getattr(settings, 'GALA_CASHLESS_PORTAL', False):
            raise CommandError('Portail désactivé dans la configuration.')
        from AuthBillet.models import TibilletUser
        from Customers.models import Client
        from seo.portal.models import CollectiveConfiguration, GalaEdition
        from seo.portal.services import MANAGER_GROUP
        with schema_context('public'), transaction.atomic():
            venue = Client.objects.get(schema_name=options['schema'])
            if venue.schema_name == 'public' or not venue.get_primary_domain():
                raise CommandError('Choisissez un lieu métier avec domaine.')
            user = TibilletUser.objects.filter(espece=TibilletUser.TYPE_HUM, email__iexact=options['admin_email'], is_active=True, email_valid=True).first()
            if user is None or not user.is_tenant_admin(venue):
                raise CommandError('Le compte doit déjà être vérifié et administrateur de ce lieu.')
            group, _ = Group.objects.get_or_create(name=MANAGER_GROUP)
            group.permissions.add(Permission.objects.get(content_type__app_label='seo', codename='manage_collective'))
            user.groups.add(group)
            GalaEdition.objects.get_or_create(venue=venue)
            CollectiveConfiguration.objects.get_or_create(pk=1, defaults={'login_venue': venue, 'live_venue': venue})
        self.stdout.write('Portail initialisé ; compte existant autorisé, aucun solde modifié.')
