import logging

from cryptography.fernet import Fernet
from django.contrib.auth import get_user_model
from django.db import connection
from rest_framework import status, permissions
from rest_framework.decorators import permission_classes
from rest_framework.generics import get_object_or_404
from rest_framework.response import Response
from rest_framework.views import APIView

from ApiBillet.permissions import TibilletUser
from BaseBillet.models import Configuration
from fedow_connect.fedow_api import FedowAPI
from fedow_connect.utils import rsa_decrypt_string, rsa_encrypt_string, get_public_key, data_to_b64

logger = logging.getLogger(__name__)


@permission_classes([permissions.AllowAny])
class GetUserPubPemMultiCashless(APIView):
    """
    Version multi-cashless :
    - ne bloque plus si un cashless est déjà configuré pour le tenant
    - vérifie toujours que l'email appartient à un admin du tenant courant
    """

    def post(self, request):
        email = (request.data.get("email") or "").strip().lower()
        if not email:
            return Response({"error": "email_required"}, status=status.HTTP_400_BAD_REQUEST)

        User = get_user_model()
        user: TibilletUser = get_object_or_404(User, email=email)
        if not user.is_tenant_admin(connection.tenant):
            return Response(status=status.HTTP_401_UNAUTHORIZED)

        return Response({"public_pem": f"{user.get_public_pem()}"}, status=status.HTTP_200_OK)


@permission_classes([permissions.AllowAny])
class OnboardLaboutikMultiCashless(APIView):
    """
    Version multi-cashless :
    - autorise plusieurs onboardings LaBoutik pour un même tenant Lesspass
    - conserve le comportement historique de réponse (clé Fedow chiffrée)
    """

    def post(self, request):
        config = Configuration.get_solo()

        required_fields = ("email", "server_cashless", "pum_pem_cashless", "key_cashless")
        missing = [f for f in required_fields if not request.data.get(f)]
        if missing:
            return Response({"error": "missing_fields", "fields": missing}, status=status.HTTP_400_BAD_REQUEST)

        email_admin = f"{request.data['email']}".strip().lower()
        user_admin: TibilletUser = connection.tenant.user_admin.get(email=email_admin)
        logger.info(f"[multi-cashless] Onboard demandé par admin={user_admin}")

        fedow_api = FedowAPI(admin=user_admin)
        fedow_api.wallet.get_or_create_wallet(user_admin)
        temp_key = fedow_api.place.link_cashless_to_place(admin=user_admin)
        fconfig = fedow_api.fedow_config
        json_key_to_cashless = {
            "domain": fconfig.fedow_domain(),
            "uuid": f"{fconfig.fedow_place_uuid}",
            "temp_key": temp_key,
        }

        # On conserve les champs historiques pour compat admin/diagnostic :
        # la "dernière" instance onboardée devient la référence affichée.
        config.server_cashless = f"{request.data['server_cashless']}"
        config.laboutik_public_pem = f"{request.data['pum_pem_cashless']}"
        cypher_key_cashless = f"{request.data['key_cashless']}"
        config.key_cashless = rsa_decrypt_string(
            utf8_enc_string=cypher_key_cashless,
            private_key=user_admin.get_private_key(),
        )

        rand_key = Fernet.generate_key()
        cypher_rand_key = rsa_encrypt_string(
            utf8_string=rand_key.decode("utf8"),
            public_key=get_public_key(config.laboutik_public_pem),
        )
        encryptor = Fernet(rand_key)
        cypher_json_key_to_cashless = encryptor.encrypt(data_to_b64(json_key_to_cashless)).decode("utf8")

        address = f"{config.postal_address.street_address}" if config.postal_address else ""
        city = f"{config.postal_address.address_locality}" if config.postal_address else ""
        country = f"{config.postal_address.address_country}" if config.postal_address else ""
        postal_code = f"{config.postal_address.postal_code}" if config.postal_address else ""

        data = {
            "cypher_rand_key": cypher_rand_key,
            "cypher_json_key_to_cashless": cypher_json_key_to_cashless,
            "organisation_name": config.organisation,
            "adress": address,
            "city": city,
            "country": country,
            "postal_code": postal_code,
            "tva_number": config.tva_number,
            "siren": config.siren,
            "phone": config.phone,
            "site_web": config.site_web,
        }
        config.save()
        logger.info(f"[multi-cashless] Onboard OK pour {config.server_cashless} tenant={connection.tenant}")
        return Response(data=data, status=status.HTTP_200_OK)
