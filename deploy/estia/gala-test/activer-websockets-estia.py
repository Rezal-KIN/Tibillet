"""Run as root on Estia; only our site and its own guard reference change."""
from pathlib import Path
import hashlib
import json
import os
import re
import socket
import subprocess
import tempfile


def main():
    if socket.gethostname() != "estia" or os.geteuid() != 0:
        raise SystemExit("ARRET : executer avec sudo sur estia.")
    folder = Path("/root/tibillet-estia-kt3_bfym")
    before = json.loads((folder / "avant.json").read_text())
    target = Path("/etc/nginx/sites-available/zz-tibillet-gala-test.conf")
    link = Path("/etc/nginx/sites-enabled/zz-tibillet-gala-test.conf")
    reference = folder / "https-caisse.conf"
    original = reference.read_bytes()

    def verify(content):
        for name, expected in before["files"].items():
            p = Path(name)
            actual = {"target": str(p.resolve()),
                      "sha256": hashlib.sha256(p.read_bytes()).hexdigest()}
            if actual != expected:
                raise RuntimeError("ARRET : fichier protege modifie : " + name)
        if target.is_symlink() or target.read_bytes() != content:
            raise RuntimeError("ARRET : notre site a change.")
        if not link.is_symlink() or link.resolve() != target:
            raise RuntimeError("ARRET : notre lien a change.")
        expected = dict(before["enabled"])
        expected[str(link)] = str(target)
        actual = {str(p): str(p.resolve())
                  for p in Path("/etc/nginx/sites-enabled").iterdir()}
        if actual != expected:
            raise RuntimeError("ARRET : changement inattendu dans sites-enabled.")

    verify(original)
    if b"$tibillet_connection_upgrade" in original:
        print("WebSockets deja configures ; aucun changement ni reload.")
        return
    marker = b"        proxy_http_version 1.1;\n"
    if original.count(marker) != 2:
        raise SystemExit("ARRET : structure de notre site inattendue.")
    final = b"""map $http_upgrade $tibillet_connection_upgrade {
    default upgrade;
    '' close;
}

""" + original.replace(marker, marker + b"""        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection $tibillet_connection_upgrade;
        proxy_read_timeout 86400;
""")
    backup = folder / "https-caisse-avant-websockets.conf"
    with backup.open("xb") as output:
        output.write(original)
    backup.chmod(0o600)

    def replace(path, content, mode):
        with tempfile.NamedTemporaryFile(dir=str(path.parent),
                                         prefix=".tibillet-", delete=False) as output:
            temporary = Path(output.name)
            output.write(content)
        temporary.chmod(mode)
        os.replace(str(temporary), str(path))

    # Reject unexpected includes before any write, and recheck after staging.
    def test_and_verify(content):
        verify(content)
        result = subprocess.run(["/usr/sbin/nginx", "-T"],
                                stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                universal_newlines=True)
        if result.returncode:
            print(result.stderr)
            raise RuntimeError("ARRET : test nginx echoue.")
        loaded = set(re.findall(r"^# configuration file (.+):$",
                                result.stdout, re.MULTILINE))
        if loaded != (set(before["files"]) | {str(link)}):
            raise RuntimeError("ARRET : liste inattendue de fichiers charges.")
        verify(content)

    test_and_verify(original)
    try:
        replace(target, final, 0o644)
        test_and_verify(final)
        if reference.read_bytes() != original:
            raise RuntimeError("ARRET : reference modifiee ailleurs.")
        replace(reference, final, 0o600)
        print("OK : fichiers proteges inchanges ; seul notre proxy evolue.", flush=True)
        subprocess.run(["systemctl", "reload", "nginx"], check=True)
    except Exception:
        if not target.is_symlink() and target.read_bytes() == final:
            replace(target, original, 0o644)
        if reference.read_bytes() == final:
            replace(reference, original, 0o600)
        print("Notre configuration precedente est restauree si elle etait inchangee.")
        raise
    print("Reload demande. La commande de rechargement du certificat reste compatible.")


if __name__ == "__main__":
    main()
