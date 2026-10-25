#!/usr/bin/env python3
"""Build Gala dotenv files from its own keys and shared dev/prod integrations."""
from __future__ import annotations

import argparse
import base64
import binascii
import json
import os
import re
import sys
import tempfile
from pathlib import Path


GENERATED_FIELDS = {
    "schema_version",
    "fedow_secret_key", "fedow_fernet_key",
    "laboutik_django_secret", "laboutik_fernet_key", "laboutik_postgres_password",
    "lespass_django_secret", "lespass_fernet_key", "lespass_postgres_password",
    "active_gala_api_token",
}
DOMAIN = re.compile(r"^[a-z0-9](?:[a-z0-9-]*[a-z0-9])?(?:\.[a-z0-9](?:[a-z0-9-]*[a-z0-9])?)+$")
ADMIN_HASH = re.compile(r"pbkdf2_sha256\$[1-9][0-9]{4,6}\$[a-zA-Z0-9]+\$[a-zA-Z0-9+/]{43}=")


def environment_sections(source: dict, smoke: bool) -> tuple[dict, dict, dict]:
    required = {"schema_version", "environment", "stripe", "cawl", "mail", "site",
                "test_recipient", "admin"}
    if set(source) != required or source.get("schema_version") != 2:
        raise ValueError("environment secret schema is invalid")
    if source.get("environment") != ("dev" if smoke else "prod"):
        raise ValueError("environment secret does not match Gala environment")
    for provider in ("stripe", "cawl"):
        if not isinstance(source[provider], dict) or source[provider].get("mode") != ("test" if smoke else "live"):
            raise ValueError("payment mode does not match environment secret")
    payment = {"schema_version": 1, "stripe": source["stripe"], "cawl": source["cawl"]}
    mail = {"schema_version": 1, **{key: source[key] for key in ("mail", "site", "test_recipient")}}
    return payment, mail, admin_credentials(source["admin"])


def admin_credentials(source: dict[str, object] | None) -> dict[str, str]:
    admin = source
    if not isinstance(admin, dict) or set(admin) != {"username", "password_hash"}:
        raise ValueError("shared admin credentials are missing or invalid")
    username = text_field(admin, "username")
    encoded = text_field(admin, "password_hash")
    if not re.fullmatch(r"[a-zA-Z0-9_.@+-]{1,150}", username) or not ADMIN_HASH.fullmatch(encoded):
        raise ValueError("shared admin username or password hash is invalid")
    return {"username": username, "password_hash": encoded}


def read_json(path: Path, label: str) -> dict[str, object]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:
        raise ValueError(f"{label} is not valid JSON") from error
    if not isinstance(value, dict):
        raise ValueError(f"{label} must be an object")
    return value


def text_field(source: dict[str, object], name: str) -> str:
    value = source.get(name)
    if not isinstance(value, str) or not value or any(char in value for char in "\r\n\x00"):
        raise ValueError(f"invalid field: {name}")
    return value


def fernet_field(source: dict[str, object], name: str) -> str:
    value = text_field(source, name)
    try:
        decoded = base64.urlsafe_b64decode(value.encode("ascii"))
    except (ValueError, UnicodeError, binascii.Error) as error:
        raise ValueError(f"invalid Fernet key: {name}") from error
    if len(value) != 44 or len(decoded) != 32:
        raise ValueError(f"invalid Fernet key length: {name}")
    return value


def dotenv_line(name: str, value: str) -> str:
    # Compose treats single-quoted env_file values literally, including '$'
    # and '#'. Only line breaks and NUL are impossible in this format.
    if any(char in value for char in "\r\n\x00"):
        raise ValueError(f"invalid dotenv value: {name}")
    escaped = value.replace("\\", "\\\\").replace("'", "\\'")
    return f"{name}='{escaped}'\n"


def payment_environment(source, smoke, tenant_schema, provider=None):
    if source.get('schema_version') != 1:
        raise ValueError('shared payment schema is invalid')
    providers = set(source) - {'schema_version'}
    if not providers or not providers <= {'stripe', 'cawl'}:
        raise ValueError('shared payment schema is invalid')
    # Existing standalone CAWL secrets remain readable; a combined secret
    # defaults to Stripe until versioned host configuration selects CAWL.
    provider = provider or ('cawl' if providers == {'cawl'} else 'stripe')
    if provider not in {'stripe', 'cawl'} or provider not in providers:
        raise ValueError('selected payment provider is missing or invalid')
    if provider == 'cawl':
        account = source['cawl']
        fields = {'mode', 'merchant_id', 'api_key_id', 'api_secret', 'webhook_key_id', 'webhook_secret'}
        if not isinstance(account, dict) or set(account) != fields:
            raise ValueError('shared CAWL fields are invalid')
        mode = account['mode']
        if mode != ('test' if smoke else 'live'):
            raise ValueError('CAWL mode does not match Gala environment')
        result = {'PAYMENT_PROVIDER': 'cawl', 'CAWL_TEST': '1' if mode == 'test' else '0',
                  'CAWL_TENANT_SCHEMA': tenant_schema}
        for field in sorted(fields - {'mode'}):
            value = text_field(account, field)
            if value != value.strip():
                raise ValueError('invalid CAWL field: ' + field)
            result['CAWL_' + field.upper()] = value
        return result
    stripe = source['stripe']
    if not isinstance(stripe, dict) or set(stripe) != {'mode', 'secret_key', 'publishable_key', 'fedow_webhook_secret'}:
        raise ValueError('shared Stripe fields are invalid')
    mode = stripe.get('mode')
    if mode not in {'test', 'live'}:
        raise ValueError('shared Stripe mode must be test or live')
    if mode != ('test' if smoke else 'live'):
        raise ValueError('Stripe mode does not match Gala environment')
    stripe_key = text_field(stripe, 'secret_key')
    public_key = text_field(stripe, 'publishable_key')
    webhook_key = text_field(stripe, 'fedow_webhook_secret')
    if not stripe_key.startswith(f'sk_{mode}_') or not public_key.startswith(f'pk_{mode}_'):
        raise ValueError('Stripe key prefixes do not match the selected mode')
    if not webhook_key.startswith('whsec_'):
        raise ValueError('invalid Stripe webhook secret prefix')
    return {'PAYMENT_PROVIDER': 'stripe', 'STRIPE_TEST': '1' if mode == 'test' else '0',
            'STRIPE_KEY_TEST' if mode == 'test' else 'STRIPE_KEY': stripe_key,
            'STRIPE_KEY_PUBLIC': public_key,
            'STRIPE_ENDPOINT_SECRET_TEST' if mode == 'test' else 'STRIPE_ENDPOINT_SECRET': webhook_key}


def assemble(
    generated: dict[str, object], stripe_secret: dict[str, object],
    mail_secret: dict[str, object], fedow_domain: str,
    laboutik_domain: str, lespass_domain: str, smoke: bool,
    admin_secret: dict[str, object] | None = None, require_admin: bool = False,
    payment_provider: str | None = None,
) -> dict[str, str]:
    # Older secrets may retain this unused field. Accept them without rotating
    # existing Gala keys, but never write PostgreSQL settings into Fedow's env.
    if set(generated) - {"fedow_postgres_password"} != GENERATED_FIELDS or generated.get("schema_version") != 1:
        raise ValueError("generated secret schema is invalid")
    if set(mail_secret) != {"schema_version", "mail", "site", "test_recipient"} or mail_secret.get("schema_version") != 1:
        raise ValueError("shared mail schema is invalid")
    admin = admin_credentials(admin_secret) if require_admin or admin_secret is not None else None
    for domain in (fedow_domain, laboutik_domain, lespass_domain):
        if not DOMAIN.fullmatch(domain):
            raise ValueError("invalid configured Gala domain")

    mail = mail_secret["mail"]
    site = mail_secret["site"]
    if not isinstance(mail, dict) or set(mail) != {"host", "port", "username", "password", "from", "admin_email"}:
        raise ValueError("shared mail fields are invalid")
    if not isinstance(site, dict) or set(site) != {
        "lespass_domain", "fedow_domain", "laboutik_domain",
        "public_name", "tenant_subdomain", "meta_subdomain",
    }:
        raise ValueError("shared site fields are invalid")
    if (
        site["fedow_domain"], site["laboutik_domain"], site["lespass_domain"]
    ) != (fedow_domain, laboutik_domain, lespass_domain):
        raise ValueError("shared domains do not match this Gala's approved configuration")
    for name in ("tenant_subdomain", "meta_subdomain"):
        if not re.fullmatch(r"[a-z0-9](?:[a-z0-9-]*[a-z0-9])?", text_field(site, name)):
            raise ValueError(f"invalid site subdomain: {name}")
    text_field(site, "public_name")
    stripe_lines = payment_environment(stripe_secret, smoke, text_field(site, 'tenant_subdomain'), payment_provider)
    for name in ("host", "username", "password", "from", "admin_email"):
        text_field(mail, name)
    port = mail["port"]
    if type(port) is not int or not 1 <= port <= 65535:
        raise ValueError("invalid mail port")
    test_recipient = text_field(mail_secret, "test_recipient")
    if not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", test_recipient):
        raise ValueError("invalid Smoke test recipient")

    for name in ("fedow_secret_key", "laboutik_django_secret", "lespass_django_secret"):
        if len(text_field(generated, name)) != 50:
            raise ValueError(f"invalid generated key length: {name}")
    for name in ("fedow_fernet_key", "laboutik_fernet_key", "lespass_fernet_key"):
        fernet_field(generated, name)
    for name in ("laboutik_postgres_password", "lespass_postgres_password", "active_gala_api_token"):
        text_field(generated, name)

    mail_lines = {
        "EMAIL_HOST": text_field(mail, "host"),
        "EMAIL_PORT": str(port),
        "EMAIL_HOST_USER": text_field(mail, "username"),
        "EMAIL_HOST_PASSWORD": text_field(mail, "password"),
        "DEFAULT_FROM_EMAIL": text_field(mail, "from"),
        "ADMIN_EMAIL": text_field(mail, "admin_email"),
        "EMAIL_USE_TLS": "1",
        "EMAIL_USE_SSL": "0",
    }
    if smoke:
        # Use the same native SMTP transport on both Smoke hosts, with every
        # outgoing envelope confined to the configured test mailbox.
        mail_lines["ADMIN_EMAIL"] = test_recipient
        mail_lines["EMAIL_BACKEND"] = "gala_mail.TestRecipientEmailBackend"
        mail_lines["GALA_TEST_MAIL_RECIPIENT"] = test_recipient
    common = {"TIME_ZONE": "Europe/Paris", "TZ": "Europe/Paris"}
    fedow = {
        "SECRET_KEY": text_field(generated, "fedow_secret_key"),
        "FERNET_KEY": fernet_field(generated, "fedow_fernet_key"),
        "DOMAIN": fedow_domain,
        "ACTIVE_GALA_API_TOKEN": text_field(generated, "active_gala_api_token"),
        **common, **stripe_lines,
    }
    laboutik = {
        "DJANGO_SECRET": text_field(generated, "laboutik_django_secret"),
        "FERNET_KEY": fernet_field(generated, "laboutik_fernet_key"),
        "POSTGRES_DB": "laboutik", "POSTGRES_USER": "laboutik_user",
        "POSTGRES_PASSWORD": text_field(generated, "laboutik_postgres_password"),
        "DOMAIN": laboutik_domain,
        # The upstream Laboutik installer requires this before it can create
        # payment methods, terminals and the first staff account. Use the
        # shared, stable public name rather than a per-host manual setting.
        "MAIN_ASSET_NAME": text_field(site, "public_name"),
        # Laboutik's upstream install command appends paths directly to the
        # environment value (for example FEDOW_URL + "helloworld/").
        "FEDOW_URL": f"https://{fedow_domain}/",
        "LESPASS_TENANT_URL": f"https://{lespass_domain}/",
        "LANGUAGE_CODE": "fr", "PAYMENT_PROVIDER": stripe_lines['PAYMENT_PROVIDER'], **common, **mail_lines,
    }
    lespass = {
        "DJANGO_SECRET": text_field(generated, "lespass_django_secret"),
        "FERNET_KEY": fernet_field(generated, "lespass_fernet_key"),
        "POSTGRES_DB": "lespass", "POSTGRES_USER": "lespass_user",
        "POSTGRES_PASSWORD": text_field(generated, "lespass_postgres_password"),
        "DOMAIN": lespass_domain,
        "PUBLIC": text_field(site, "public_name"),
        "SUB": text_field(site, "tenant_subdomain"),
        "GALA_APEX_TENANT": "1",
        "GALA_LOCAL_FEDOW": "1",
        "META": text_field(site, "meta_subdomain"),
        "FEDOW_DOMAIN": fedow_domain,
        "ACTIVE_GALA_API_TOKEN": text_field(generated, "active_gala_api_token"),
        "CELERY_BROKER": "redis://redis:6379/0",
        "CELERY_BACKEND": "redis://redis:6379/0",
        **common, **stripe_lines, **mail_lines,
    }
    files = {
        "fedow.env": "".join(dotenv_line(key, value) for key, value in fedow.items()),
        "laboutik.env": "".join(dotenv_line(key, value) for key, value in laboutik.items()),
        "lespass.env": "".join(dotenv_line(key, value) for key, value in lespass.items()),
    }
    if admin:
        files["admin.json"] = json.dumps(admin) + "\n"
    return files


def write_files(output_dir: Path, contents: dict[str, str]) -> None:
    output_dir.mkdir(mode=0o700, parents=True, exist_ok=True)
    for filename, content in contents.items():
        descriptor, temporary = tempfile.mkstemp(prefix=f".{filename}.", dir=output_dir, text=True)
        try:
            with os.fdopen(descriptor, "w", encoding="utf-8") as destination:
                destination.write(content)
            os.chmod(temporary, 0o600)
            os.replace(temporary, output_dir / filename)
        finally:
            if os.path.exists(temporary):
                os.unlink(temporary)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--environment", type=Path)
    parser.add_argument("--generated", required=True, type=Path)
    parser.add_argument("--stripe", "--payment", dest="stripe", type=Path)
    parser.add_argument("--provider", choices=["stripe", "cawl"], default="stripe")
    parser.add_argument("--check-combined-compatibility", action="store_true")
    parser.add_argument("--mail", type=Path)
    parser.add_argument("--smoke", required=True, choices=["true", "false"])
    parser.add_argument("--fedow-domain", required=True)
    parser.add_argument("--laboutik-domain", required=True)
    parser.add_argument("--lespass-domain", required=True)
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--admin", type=Path)
    args = parser.parse_args()
    generated = read_json(args.generated, "generated secret")
    if args.environment:
        if any((args.stripe, args.mail, args.admin)):
            raise ValueError("shared environment secret cannot be mixed with legacy integration selectors")
        payment, mail, admin = environment_sections(
            read_json(args.environment, "environment secret"), args.smoke == "true")
    else:
        if not all((args.stripe, args.mail, args.admin)):
            raise ValueError("legacy runtime requires generated, payment, mail and admin secrets")
        payment = read_json(args.stripe, "shared payment secret")
        mail = read_json(args.mail, "shared mail secret")
        admin = read_json(args.admin, "shared admin secret")
    def render(payment_secret):
        return assemble(generated, payment_secret, mail,
                        args.fedow_domain, args.laboutik_domain, args.lespass_domain,
                        args.smoke == "true", admin, require_admin=True,
                        payment_provider=args.provider)
    files = render(payment)
    if args.check_combined_compatibility:
        if args.provider != "stripe":
            raise ValueError("compatibility check requires a Stripe Gala")
        combined = dict(payment)
        combined.setdefault("cawl", {"mode": "test" if args.smoke == "true" else "live",
                                    **{field: "" for field in ("merchant_id", "api_key_id", "api_secret", "webhook_key_id", "webhook_secret")}})
        if render(combined) != files:
            raise ValueError("adding the CAWL section changes Stripe runtime credentials")
        print("Shared payment secret compatibility verified; Stripe runtime is identical")
    else:
        write_files(args.output_dir, files)



if __name__ == "__main__":
    try:
        main()
    except ValueError as error:
        print(f"ERROR: {error}", file=sys.stderr)
        raise SystemExit(1) from error
