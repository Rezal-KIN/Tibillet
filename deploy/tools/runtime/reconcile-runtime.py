#!/usr/bin/env python3
"""Idempotently reconcile an existing Gala host from versioned configuration."""
from __future__ import annotations

import os
import re
import sys
import tempfile
from pathlib import Path


DOMAIN = "galas-am-aix.rezal.fr"
ARN = re.compile(r"^arn:aws:secretsmanager:eu-west-3:318629836660:secret:tibillet-gala-paris/shared/integrations-[a-z-]+-[A-Za-z0-9]{6}$")
SLUG = re.compile(r"^[a-z0-9][a-z0-9-]{1,62}$")
# Smoke hosts use test credentials; gala-smoke-cawl is the CAWL Smoke.
SMOKE_SLUGS = {"gala-smoke", "gala-smoke-cawl"}


def update(text: str, slug: str, generated_arn: str, stripe_arn: str, mail_arn: str, payment_provider: str = "stripe") -> str:
    if not SLUG.fullmatch(slug) or slug == "bapts":
        raise ValueError("invalid Gala slug")
    mode = "test" if slug in SMOKE_SLUGS else "live"
    if payment_provider not in {"stripe", "cawl"}:
        raise ValueError("invalid payment provider")
    if slug == "gala-smoke-cawl" and payment_provider != "cawl":
        raise ValueError("CAWL Smoke requires the CAWL provider")
    if slug == "gala-smoke" and payment_provider != "stripe":
        raise ValueError("Stripe Smoke requires the Stripe provider")
    if not ARN.fullmatch(stripe_arn) or f"integrations-stripe-{mode}-" not in stripe_arn:
        raise ValueError(f"Gala requires the shared payment {mode} secret")
    unified = generated_arn == stripe_arn == mail_arn
    if not unified:
        if not re.fullmatch(rf"arn:aws:secretsmanager:eu-west-3:318629836660:secret:tibillet-gala-paris/galas/{slug}/generated-[A-Za-z0-9]{{6}}", generated_arn):
            raise ValueError("Gala requires its own generated secret")
        if not ARN.fullmatch(mail_arn) or "integrations-mail-" not in mail_arn:
            raise ValueError("Smoke requires the shared mail secret")
    if not re.search(rf'^GALA_SLUG=["\']?{slug}["\']?$', text, re.MULTILINE):
        raise ValueError("target config targets another Gala")
    replacements = {
        "LESPASS_PUBLIC_DOMAIN": DOMAIN,
        "FEDOW_PUBLIC_DOMAIN": f"fedow.{DOMAIN}",
        "LABOUTIK_PUBLIC_DOMAIN": f"cashless.{DOMAIN}",
        "HEALTHCHECK_URLS": f"https://fedow.{DOMAIN}/,https://cashless.{DOMAIN}/,https://{DOMAIN}/",
        "GENERATED_SECRET_ARN": generated_arn,
        "SHARED_STRIPE_SECRET_ARN": stripe_arn,
        "PAYMENT_PROVIDER": payment_provider,
        "SHARED_MAIL_SECRET_ARN": mail_arn,
        "DEPLOYMENT_LOCKED": "false",
        "ALLOW_INITIAL_DEPLOY": "true",
    }
    kept = [
        line for line in text.splitlines()
        if line.split("=", 1)[0] not in replacements and
        line.split("=", 1)[0] != "SHARED_INTEGRATIONS_SECRET_ARN"
    ]
    return "\n".join(kept + [f'{key}="{value}"' for key, value in replacements.items()]) + "\n"


def main() -> None:
    if len(sys.argv) not in {6, 7}:
        raise SystemExit("usage: reconcile-runtime.py CONFIG GALA_SLUG GENERATED_ARN PAYMENT_ARN MAIL_ARN [PAYMENT_PROVIDER]")
    config = Path(sys.argv[1])
    text = config.read_text(encoding="utf-8")
    updated = update(text, sys.argv[2], sys.argv[3], sys.argv[4], sys.argv[5], sys.argv[6] if len(sys.argv) == 7 else "stripe")
    fd, path = tempfile.mkstemp(prefix=f".{sys.argv[2]}.", dir=config.parent, text=True)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as destination:
            destination.write(updated)
        os.chmod(path, 0o600)
        os.replace(path, config)
    finally:
        if os.path.exists(path):
            os.unlink(path)
    print(f"Gala runtime configuration reconciled from versioned code: {sys.argv[2]}")


if __name__ == "__main__":
    main()
