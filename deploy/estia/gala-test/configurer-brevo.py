"""Prepare only the gala-test private environment; never reads the SMTP key."""
from pathlib import Path
import hashlib
import json
import os
import re
import shutil
import subprocess
import tempfile


def main():
    config = Path("/home/tibillet/gala-test-config")
    repo = Path("/home/tibillet/actions-runner/_work/Tibillet/Tibillet")
    source = config / ".env"
    original = source.read_text()
    def value(key):
        values = re.findall(r"^" + re.escape(key) + r"\s*=\s*(.*)$", original, re.M)
        if len(values) != 1:
            raise SystemExit("ARRET : variable absente ou dupliquee : " + key)
        return values[0].strip().strip("\"'")
    if value("DOMAIN") != "gala-test.rezal.fr" or value("CAWL_TEST") != "1" or value("PAYMENT_PROVIDER") != "cawl":
        raise SystemExit("ARRET : cette configuration ne correspond pas a la VM CAWL de test.")
    if value("EMAIL_HOST") != "mailpit":
        raise SystemExit("ARRET : le SMTP a deja change ; examiner avant toute modification.")
    key = config / "brevo-local/smtp-key"
    if key.is_symlink() or not key.is_file() or key.stat().st_mode & 0o077 or not key.stat().st_size:
        raise SystemExit("ARRET : fichier SMTP prive absent ou permissions inattendues.")
    changes = {
        "EMAIL_HOST": "smtp-relay.brevo.com", "EMAIL_PORT": "587",
        "EMAIL_HOST_USER": "a7a396001@smtp-brevo.com",
        "EMAIL_HOST_PASSWORD": "", "DEFAULT_FROM_EMAIL": "contact@galas-am-aix.rezal.fr",
        "EMAIL_USE_TLS": "True", "EMAIL_USE_SSL": "False", "EMAIL_TIMEOUT": "30",
        "TEST": "0", "DEBUG": "0", "DEMO": "0",
    }
    prepared = original
    for name, val in changes.items():
        pattern = r"^" + re.escape(name) + r"\s*=.*$"
        replacement = name + '="' + val + '"'
        count = len(re.findall(pattern, prepared, re.M))
        if count > 1:
            raise SystemExit("ARRET : variable dupliquee : " + name)
        prepared = re.sub(pattern, replacement, prepared, flags=re.M) if count else prepared.rstrip("\n") + "\n" + replacement + "\n"
    def protected(text):
        return [line for line in text.splitlines() if re.match(r"\s*(CAWL_|PAYMENT_PROVIDER\s*=)", line)]
    if protected(prepared) != protected(original):
        raise SystemExit("ARRET : parametres CAWL modifies.")
    # Preserve every unrelated line, not merely the CAWL settings.
    def unrelated(text):
        return [line for line in text.splitlines()
                if not any(re.match(r"^" + re.escape(k) + r"\s*=", line) for k in changes)]
    if unrelated(prepared) != unrelated(original):
        raise SystemExit("ARRET : modification hors du perimetre SMTP/runtime.")
    backup = Path(tempfile.mkdtemp(prefix="brevo-prodlike-", dir=str(config)))
    backup.chmod(0o700)
    for name, path in (("external.env", source), ("checkout.env", repo / ".env")):
        shutil.copyfile(str(path), str(backup / name))
        (backup / name).chmod(0o600)
    containers = json.loads(subprocess.check_output(["docker", "inspect", "lespass_postgres", "lespass_redis", "lespass_memcached", "fedow_memcached", "lespass_mailpit"]))
    manifest = {
        "commit": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=str(repo)).decode().strip(),
        "source_sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
        "candidate_sha256": hashlib.sha256(prepared.encode()).hexdigest(),
        "protected_containers": {c["Name"].lstrip("/"): c["Id"] for c in containers},
    }
    (backup / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    with tempfile.NamedTemporaryFile(dir=str(config), prefix=".brevo-env-", delete=False) as output:
        temporary = Path(output.name)
        output.write(prepared.encode())
    temporary.chmod(0o600)
    if hashlib.sha256(source.read_bytes()).hexdigest() != manifest["source_sha256"]:
        temporary.unlink()
        raise SystemExit("ARRET : configuration modifiee ailleurs ; aucune bascule.")
    os.replace(str(temporary), str(source))
    print("Configuration privee preparee ; aucun conteneur recree.")
    print("Sauvegarde :", backup)
    print("CAWL et toutes les autres lignes inchanges ; seuls SMTP, TEST, DEBUG et DEMO evoluent.")


if __name__ == "__main__":
    main()
