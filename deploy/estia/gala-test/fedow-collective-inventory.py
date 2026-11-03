"""Inventaire agrégé du lieu authentifié, sans identifiants ni données des cartes.
/ Aggregate inventory of the authenticated place, without card identifiers or data.
"""
from django.db.models import Count, Q
from rest_framework import viewsets
from rest_framework.response import Response
from fedow_core.models import Card
from fedow_core.permissions import HasKeyAndPlaceSignature


class CollectiveInventory(viewsets.ViewSet):
    permission_classes = [HasKeyAndPlaceSignature]
    http_method_names = ['get', 'head', 'options']

    def list(self, request):
        rows = Card.objects.filter(origin__place=request.place).values('origin__generation').annotate(
            count=Count('uuid'), linked_count=Count('uuid', filter=Q(user__isnull=False)))
        response = Response([{'generation': row['origin__generation'], 'count': row['count'],
                              'linked_count': row['linked_count']} for row in rows])
        response['Cache-Control'] = 'no-store'
        return response
