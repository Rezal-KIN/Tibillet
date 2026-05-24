import logging
import os
from decimal import Decimal
from django.conf import settings
from django.core.mail import send_mail, EmailMessage
from django.http import JsonResponse, HttpResponse
from django.shortcuts import render, redirect
from django.contrib import messages
from fedow_connect.fedow_api import FedowAPI
from BaseBillet.refund_models import LocalRefundRequest
from BaseBillet.models import Configuration
from BaseBillet.views import get_skin_template

logger = logging.getLogger(__name__)

EXCLUDE_CATS = ('SUB', 'BDG')
FEDERATED_CAT = 'FED'
REFUND_ADMIN_EMAIL = 'galaamaix@rezal.fr'


def _cents_to_eur(val):
    if isinstance(val, int):
        return Decimal(val) / 100
    return Decimal(str(val))


def _get_tokens(request):
    fedowAPI = FedowAPI()
    wallet = fedowAPI.wallet.cached_retrieve_by_signature(request.user).validated_data
    return [t for t in wallet.get('tokens', [])
            if (t.get('asset_category') or t.get('asset', {}).get('category', '')) not in EXCLUDE_CATS]


def _get_local_balance(request):
    """Retourne le solde local (non fédéré) depuis Fedow — côté serveur, inviolable."""
    tokens = _get_tokens(request)
    local = Decimal('0')
    for t in tokens:
        cat = t.get('asset_category') or t.get('asset', {}).get('category', '')
        if cat != FEDERATED_CAT:
            local += _cents_to_eur(t.get('value', 0))
    return local


def balance_total(request):
    if not request.user.is_authenticated:
        return JsonResponse({'total': 0, 'federated': 0, 'local': 0}, status=401)
    try:
        tokens = _get_tokens(request)
        federated = Decimal('0')
        local = Decimal('0')
        for t in tokens:
            cat = t.get('asset_category') or t.get('asset', {}).get('category', '')
            val = _cents_to_eur(t.get('value', 0))
            if cat == FEDERATED_CAT:
                federated += val
            else:
                local += val
        total = federated + local
        return JsonResponse({
            'total': float(round(total, 2)),
            'federated': float(round(federated, 2)),
            'local': float(round(local, 2)),
        })
    except Exception as e:
        logger.error(f"balance_total error: {e}")
        return JsonResponse({'total': 0, 'federated': 0, 'local': 0, 'error': str(e)}, status=500)


def balance_tokens_rows(request):
    """Retourne les lignes HTML de solde par monnaie pour injection dans le tableau tirelire."""
    if not request.user.is_authenticated:
        return HttpResponse('')
    try:
        tokens = _get_tokens(request)
        rows = []
        for token in tokens:
            val = _cents_to_eur(token.get('value', 0))
            if val <= 0:
                continue
            asset = token.get('asset', {})
            cat = token.get('asset_category') or asset.get('category', '')
            is_fed = (cat == FEDERATED_CAT)
            name = 'Monnaie intergala' if is_fed else token.get('name', asset.get('name', '?'))
            badge = 'bg-success' if is_fed else 'bg-secondary'
            rows.append(
                f'<tr>'
                f'<td><span class="badge {badge}">Solde actuel</span></td>'
                f'<td>{name}</td>'
                f'<td><strong>{val:.2f} €</strong></td>'
                f'<td>—</td>'
                f'</tr>'
            )
        return HttpResponse(''.join(rows))
    except Exception as e:
        logger.error(f"balance_tokens_rows error: {e}")
        return HttpResponse('')


def refund_local_form(request):
    """Formulaire de remboursement du solde local (caisses physiques)."""
    if not request.user.is_authenticated:
        return redirect('/connexion/')

    if request.method == 'POST':
        # Lecture du solde côté serveur (inviolable)
        try:
            local_balance = _get_local_balance(request)
        except Exception as e:
            logger.error(f"refund_local_form balance error: {e}")
            messages.error(request, "Impossible de récupérer votre solde. Veuillez réessayer.")
            return redirect('/my_account/refund_local_form/')

        nom = request.POST.get('nom', '').strip()
        prenom = request.POST.get('prenom', '').strip()
        iban = request.POST.get('iban', '').strip().replace(' ', '').upper()
        bic = request.POST.get('bic', '').strip().upper()
        ticket_number = request.POST.get('ticket_number', '').strip()
        id_doc = request.FILES.get('id_document')

        errors = []
        if not nom:
            errors.append("Le nom est requis.")
        if not prenom:
            errors.append("Le prénom est requis.")
        if not iban or len(iban) < 14:
            errors.append("IBAN invalide.")
        if not bic or len(bic) not in (8, 11):
            errors.append("BIC invalide (8 ou 11 caractères).")
        if not id_doc:
            errors.append("La pièce d'identité est requise.")
        elif id_doc.size > 10 * 1024 * 1024:
            errors.append("Le fichier est trop volumineux (max 10 Mo).")
        if local_balance <= 0:
            errors.append("Votre solde local est nul, aucun remboursement possible.")

        if errors:
            config = Configuration.get_solo()
            base_template = get_skin_template(config, "headless.html" if request.htmx else "base.html")
            return render(request, 'reunion/views/account/refund_local_form.html', {
                'errors': errors,
                'local_balance': local_balance,
                'nom': nom,
                'prenom': prenom,
                'iban': iban,
                'bic': bic,
                'ticket_number': ticket_number,
                'base_template': base_template,
                'user': request.user,
                'config': config,
            })

        # Sauvegarde en base
        refund = LocalRefundRequest(
            user_email=request.user.email,
            user_uuid=str(getattr(request.user, 'uuid', '') or ''),
            nom=nom,
            prenom=prenom,
            iban=iban,
            bic=bic,
            ticket_number=ticket_number,
            id_document=id_doc,
            local_balance=local_balance,
        )
        refund.save()

        # Email à l'admin
        try:
            email_admin = EmailMessage(
                subject=f"[Gala AM Aix] Demande de remboursement solde local — {prenom} {nom}",
                body=(
                    f"Nouvelle demande de remboursement du solde local.\n\n"
                    f"Utilisateur : {prenom} {nom} ({request.user.email})\n"
                    f"Solde local vérifié : {local_balance:.2f} €\n"
                    f"IBAN : {iban}\n"
                    f"BIC : {bic}\n"
                    f"Numéro de billet : {ticket_number or '(non renseigné)'}\n\n"
                    f"Pièce d'identité jointe.\n"
                    f"Référence demande : #{refund.id}\n"
                ),
                from_email=settings.DEFAULT_FROM_EMAIL,
                to=[REFUND_ADMIN_EMAIL],
            )
            email_admin.attach(id_doc.name, refund.id_document.read(), id_doc.content_type)
            email_admin.send(fail_silently=True)
        except Exception as e:
            logger.error(f"refund admin email error: {e}")

        # Email de confirmation à l'utilisateur
        try:
            send_mail(
                subject="[Gala AM Aix] Confirmation de votre demande de remboursement",
                message=(
                    f"Bonjour {prenom},\n\n"
                    f"Votre demande de remboursement a bien été reçue.\n\n"
                    f"Montant à rembourser : {local_balance:.2f} €\n"
                    f"Référence : #{refund.id}\n\n"
                    f"Le traitement peut prendre jusqu'à 2 semaines.\n\n"
                    f"L'équipe du Gala AM Aix"
                ),
                from_email=settings.DEFAULT_FROM_EMAIL,
                recipient_list=[request.user.email],
                fail_silently=True,
            )
        except Exception as e:
            logger.error(f"refund confirm email error: {e}")

        return redirect('/my_account/refund_local_success/')

    # GET : afficher le formulaire
    try:
        local_balance = _get_local_balance(request)
    except Exception as e:
        logger.error(f"refund_local_form GET balance error: {e}")
        local_balance = None

    config = Configuration.get_solo()
    base_template = get_skin_template(config, "headless.html" if request.htmx else "base.html")

    return render(request, 'reunion/views/account/refund_local_form.html', {
        'local_balance': local_balance,
        'base_template': base_template,
        'user': request.user,
        'config': config,
    })


def refund_local_success(request):
    """Page de confirmation après soumission du formulaire."""
    if not request.user.is_authenticated:
        return redirect('/connexion/')
    config = Configuration.get_solo()
    base_template = get_skin_template(config, "headless.html" if request.htmx else "base.html")
    return render(request, 'reunion/views/account/refund_local_success.html', {
        'base_template': base_template,
        'user': request.user,
        'config': config,
    })
