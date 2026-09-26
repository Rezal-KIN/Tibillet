#!/usr/bin/env python3
"""Build Gala dotenv files from stable generated keys and shared integrations."""
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
    "fedow_secret_key", "fedow_fernet_key", "fedow_postgres_password",
    "laboutik_django_secret", "laboutik_fernet_key", "laboutik_postgres_password",
    "lespass_django_secret", "lespass_fernet_key", "lespass_postgres_password",
    "active_gala_api_token",
}
DOMAIN = re.compile(r"^[a-z0-9](?:[a-z0-9-]*[a-z0-9])?(?:\.[a-z0-9](?:[a-z0-9-]*[a-z0-9])?)+$")


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


def assemble(
    generated: dict[str, object], stripe_secret: dict[str, object],
    mail_secret: dict[str, object], fedow_domain: str,
    laboutik_domain: str, lespass_domain: str, smoke: bool,
) -> dict[str, str]:
    if set(generated) != GENERATED_FIELDS or generated.get("schema_version") != 1:
        raise ValueError("generated secret schema is invalid")
    if set(stripe_secret) != {"schema_version", "stripe"} or stripe_secret.get("schema_version") != 1:
        raise ValueError("shared Stripe schema is invalid")
    if set(mail_secret) != {"schema_version", "mail", "site", "test_recipient"} or mail_secret.get("schema_version") != 1:
        raise ValueError("shared mail schema is invalid")
    for domain in (fedow_domain, laboutik_domain, lespass_domain):
        if not DOMAIN.fullmatch(domain):
            raise ValueError("invalid configured Gala domain")

    stripe = stripe_secret["stripe"]
    mail = mail_secret["mail"]
    site = mail_secret["site"]
    if not isinstance(stripe, dict) or set(stripe) != {"mode", "secret_key", "publishable_key", "fedow_webhook_secret"}:
        raise ValueError("shared Stripe fields are invalid")
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
    mode = stripe.get("mode")
    if mode not in {"test", "live"}:
        raise ValueError("shared Stripe mode must be test or live")
    if mode != ("test" if smoke else "live"):
        raise ValueError("Stripe mode does not match Gala environment")
    stripe_key = text_field(stripe, "secret_key")
    public_key = text_field(stripe, "publishable_key")
    webhook_key = text_field(stripe, "fedow_webhook_secret")
    if not stripe_key.startswith(f"sk_{mode}_") or not public_key.startswith(f"pk_{mode}_"):
        raise ValueError("Stripe key prefixes do not match the selected mode")
    if not webhook_key.startswith("whsec_"):
        raise ValueError("invalid Stripe webhook secret prefix")
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
    for name in ("fedow_postgres_password", "laboutik_postgres_password", "lespass_postgres_password", "active_gala_api_token"):
        text_field(generated, name)

    stripe_lines = {
        "STRIPE_TEST": "1" if mode == "test" else "0",
        "STRIPE_KEY_TEST" if mode == "test" else "STRIPE_KEY": stripe_key,
        "STRIPE_KEY_PUBLIC": public_key,
        "STRIPE_ENDPOINT_SECRET_TEST" if mode == "test" else "STRIPE_ENDPOINT_SECRET": webhook_key,
    }
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
        # Until a dedicated recipient-rewriting SMTP relay is part of the
        # stack, no email from Smoke may leave the host. Admin notices are
        # addressed to the configured test mailbox, but Django is a sink.
        mail_lines["ADMIN_EMAIL"] = test_recipient
        mail_lines["EMAIL_BACKEND"] = "django.core.mail.backends.dummy.EmailBackend"
    common = {"TIME_ZONE": "Europe/Paris", "TZ": "Europe/Paris"}
    fedow = {
        "SECRET_KEY": text_field(generated, "fedow_secret_key"),
        "FERNET_KEY": fernet_field(generated, "fedow_fernet_key"),
        "POSTGRES_DB": "fedow", "POSTGRES_USER": "fedow_user",
        "POSTGRES_PASSWORD": text_field(generated, "fedow_postgres_password"),
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
        "FEDOW_URL": f"https://{fedow_domain}",
        "LESPASS_TENANT_URL": f"https://{lespass_domain}/",
        "LANGUAGE_CODE": "fr", **common, **mail_lines,
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
    return {
        "fedow.env": "".join(dotenv_line(key, value) for key, value in fedow.items()),
        "laboutik.env": "".join(dotenv_line(key, value) for key, value in laboutik.items()),
        "lespass.env": "".join(dotenv_line(key, value) for key, value in lespass.items()),
    }


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
    parser.add_argument("--generated", required=True, type=Path)
    parser.add_argument("--stripe", required=True, type=Path)
    parser.add_argument("--mail", required=True, type=Path)
    parser.add_argument("--smoke", required=True, choices=["true", "false"])
    parser.add_argument("--fedow-domain", required=True)
    parser.add_argument("--laboutik-domain", required=True)
    parser.add_argument("--lespass-domain", required=True)
    parser.add_argument("--output-dir", required=True, type=Path)
    args = parser.parse_args()
    files = assemble(
        read_json(args.generated, "generated secret"),
        read_json(args.stripe, "shared Stripe secret"),
        read_json(args.mail, "shared mail secret"),
        args.fedow_domain, args.laboutik_domain, args.lespass_domain,
        args.smoke == "true",
    )
    write_files(args.output_dir, files)


if __name__ == "__main__":
    try:
        main()
    except ValueError as error:
        print(f"ERROR: {error}", file=sys.stderr)
        raise SystemExit(1) from error
