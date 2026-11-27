"""Historique d'une carte pour le mode gérant de LaBoutik (lecture seule).

FR : Fedow tient le registre complet d'une carte : recharges (caisse et en ligne),
ventes, remboursements, association à un compte (fusion de portefeuilles), etc.
Cette vue ne fait que lire. Elle est réservée au lieu qui a émis la carte, authentifié
par sa clé d'API et sa signature (comme les autres appels LaBoutik → Fedow).
EN: Read-only card ledger for LaBoutik's manager mode, limited to the issuing place.
"""
import re

from django.db.models import Q
from django.shortcuts import get_object_or_404
from rest_framework import status, viewsets
from rest_framework.response import Response

from fedow_core.models import Card, Configuration, Place, Token, Transaction
from fedow_core.permissions import HasKeyAndPlaceSignature

LIMIT = 200
LABELS = {
    Transaction.FIRST: "Premier bloc",
    Transaction.SALE: "Achat",
    Transaction.QRCODE_SALE: "Achat (QR code)",
    Transaction.CREATION: "Création monétaire",
    Transaction.REFILL: "Recharge",
    Transaction.TRANSFER: "Transfert",
    Transaction.SUBSCRIBE: "Adhésion",
    Transaction.BADGE: "Badge",
    Transaction.FUSION: "Association à un compte",
    Transaction.REFUND: "Remboursement",
    Transaction.VOID: "Carte dissociée / vidée",
    Transaction.DEPOSIT: "Remise en banque",
    Transaction.CORRECTION: "Correction",
}


def mask_email(email):
    if not email or '@' not in email:
        return None
    name, domain = email.split('@', 1)
    return (name[:1] + '***@' + domain) if name else '***@' + domain


def card_history(card, place):
    """Construit l'historique sérialisable d'une carte, du plus récent au plus ancien."""
    primary_wallet_id = Configuration.get_solo().primary_wallet_id
    wallets = {w.pk for w in (card.wallet_ephemere, card.user.wallet if card.user_id else None) if w is not None}
    places = {p.wallet_id: p.name for p in Place.objects.all()}

    def label_wallet(wallet_id):
        if wallet_id in wallets:
            return "Carte"
        if wallet_id == primary_wallet_id:
            return "Banque"
        return places.get(wallet_id, "Autre portefeuille")

    condition = Q(card=card)
    if wallets:
        condition |= Q(sender_id__in=wallets) | Q(receiver_id__in=wallets)
    queryset = (Transaction.objects.filter(condition)
                .exclude(action__in=[Transaction.FIRST, Transaction.CREATION])
                .select_related('asset').order_by('-datetime'))
    total = queryset.count()
    operations = []
    for tx in queryset[:LIMIT]:
        incoming = tx.receiver_id in wallets
        outgoing = tx.sender_id in wallets
        sign = 0 if incoming == outgoing else (1 if incoming else -1)
        metadata = tx.metadata if isinstance(tx.metadata, dict) else {}
        operations.append({
            'datetime': tx.datetime.isoformat(),
            'action': tx.action,
            'label': LABELS.get(tx.action, tx.get_action_display()),
            'amount': tx.amount,
            'sign': sign,
            'asset': tx.asset.name,
            'asset_category': tx.asset.category,
            'from': label_wallet(tx.sender_id),
            'to': label_wallet(tx.receiver_id),
            'online': metadata.get('payment_provider') == 'cawl',
            'comment': (tx.comment or '')[:120],
        })

    from cawl_fedow.models import Checkout, WalletRefund
    checkouts = [{
        'created_at': c.created_at.isoformat(), 'amount': c.amount, 'fee': c.fee,
        'status': c.provider_status or 'CREATED', 'credited': bool(c.refill_id),
    } for c in Checkout.objects.filter(wallet_id__in=wallets).order_by('-created_at')[:50]] if wallets else []
    refunds = [{
        'updated_at': r.updated_at.isoformat(), 'amount': r.amount, 'status': r.status,
    } for r in WalletRefund.objects.filter(checkout__wallet_id__in=wallets).order_by('-updated_at')[:50]] if wallets else []

    balances = []
    for token in Token.objects.filter(wallet_id__in=wallets).select_related('asset').order_by('asset__name'):
        if token.value:
            balances.append({'asset': token.asset.name, 'category': token.asset.category, 'value': token.value})

    return {
        'card': {
            'tag_id': card.first_tag_id,
            'number': card.number_printed,
            'generation': card.origin.generation,
            'linked_to_account': bool(card.user_id),
            'email': mask_email(card.user.email) if card.user_id else None,
            'anonymous_wallet': card.is_wallet_ephemere(),
        },
        'balances': balances,
        'operations': operations,
        'operations_total': total,
        'truncated': total > len(operations),
        'online_refills': checkouts,
        'online_refunds': refunds,
    }


class CardHistoryAPI(viewsets.ViewSet):
    permission_classes = [HasKeyAndPlaceSignature]

    def retrieve(self, request, pk=None):
        if not pk or not re.fullmatch(r'[0-9A-Fa-f]{8}', pk):
            return Response("Identifiant de carte invalide.", status=status.HTTP_400_BAD_REQUEST)
        card = get_object_or_404(Card.objects.select_related('origin', 'user', 'wallet_ephemere'),
                                 first_tag_id=pk.upper())
        # FR : Un lieu ne lit que l'historique des cartes qu'il a émises.
        # EN: A place may only read the history of the cards it issued.
        if card.origin.place_id != request.place.pk:
            return Response("Carte d'un autre lieu.", status=status.HTTP_403_FORBIDDEN)
        return Response(card_history(card, request.place), status=status.HTTP_200_OK)

    def by_number(self, request, number=None):
        """Même lecture, à partir du numéro imprimé (saisie sur ordinateur)."""
        if not number or not re.fullmatch(r'[0-9A-Za-z]{8}', number):
            return Response("Numéro de carte invalide.", status=status.HTTP_400_BAD_REQUEST)
        card = get_object_or_404(Card.objects.select_related('origin', 'user', 'wallet_ephemere'),
                                 number_printed=number.upper())
        if card.origin.place_id != request.place.pk:
            return Response("Carte d'un autre lieu.", status=status.HTTP_403_FORBIDDEN)
        return Response(card_history(card, request.place), status=status.HTTP_200_OK)
