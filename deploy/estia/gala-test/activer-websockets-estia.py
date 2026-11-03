"""Run as root on Estia; only our site and its own guard reference change."""
from pathlib import Path
import argparse
import base64
from concurrent.futures import ThreadPoolExecutor
import hashlib
import http.client
import json
import os
import re
import socket
import ssl
import subprocess
import tempfile
import time
from urllib.parse import urlsplit

FOLDER = Path("/root/tibillet-estia-kt3_bfym")
TARGET = Path("/etc/nginx/sites-available/zz-tibillet-gala-test.conf")
LINK = Path("/etc/nginx/sites-enabled/zz-tibillet-gala-test.conf")


def probe(host, tls):
    """Only request / locally, without following redirects or logging cookies."""
    result = {}
    try:
        with socket.create_connection(("127.0.0.1", 443 if tls else 80), timeout=4) as raw:
            conn = ssl.create_default_context().wrap_socket(raw, server_hostname=host) if tls else raw
            with conn:
                if tls:
                    result["certificate"] = hashlib.sha256(conn.getpeercert(binary_form=True)).hexdigest()
                method = "GET" if host == "hello.rezal.fr" and tls else "HEAD"
                conn.sendall((method + " / HTTP/1.1\r\nHost: " + host +
                              "\r\nConnection: close\r\n\r\n").encode("ascii"))
                response = http.client.HTTPResponse(conn, method=method)
                response.begin()
                result["status"] = response.status
                # Login redirects may contain changing secrets/nonces: never record them.
                location = urlsplit(response.getheader("Location", ""))
                result["redirect"] = (location.scheme, location.netloc, location.path)
                if method == "GET":
                    body = response.read(1024 * 1024 + 1)
                    if len(body) > 1024 * 1024:
                        raise RuntimeError("Corps hello trop volumineux")
                    result["body_sha256"] = hashlib.sha256(body).hexdigest()
    except Exception as error:
        result["error"] = type(error).__name__
    return result


def sites_snapshot(hosts):
    jobs = [(host, tls) for host in hosts for tls in (False, True)]
    with ThreadPoolExecutor(max_workers=6) as pool:
        values = list(pool.map(lambda job: probe(*job), jobs))
    return {("https://" if tls else "http://") + host: value
            for (host, tls), value in zip(jobs, values)}


def compare_sites(before, after):
    changes = [url for url in before if before[url] != after.get(url)]
    if changes:
        raise RuntimeError("Reponses differentes avant/apres : " + ", ".join(changes))


def nginx_state():
    output = subprocess.check_output(
        ["systemctl", "show", "nginx", "-p", "ActiveState", "-p", "MainPID"],
        universal_newlines=True)
    state = dict(line.split("=", 1) for line in output.splitlines() if "=" in line)
    master = int(state.get("MainPID", "0"))
    workers = set()
    processes = subprocess.check_output(["ps", "-eo", "pid,ppid,args"], universal_newlines=True)
    for line in processes.splitlines()[1:]:
        parts = line.strip().split(None, 2)
        if (len(parts) == 3 and int(parts[1]) == master and
                parts[2].startswith("nginx: worker process") and "shutting down" not in parts[2]):
            workers.add(int(parts[0]))
    if state.get("ActiveState") != "active" or not master or not workers:
        raise RuntimeError("nginx n'est pas actif avec des workers operationnels")
    return master, workers


def wait_for_reload(previous):
    deadline = time.monotonic() + 10
    while True:
        current = nginx_state()
        if current[0] != previous[0]:
            raise RuntimeError("Le processus principal nginx a change")
        if current[1] - previous[1]:
            return
        if time.monotonic() >= deadline:
            raise RuntimeError("Nouveaux workers nginx non observes apres reload")
        time.sleep(0.25)


def websocket_check():
    host = "cashless.gala-test.rezal.fr"
    key = base64.b64encode(os.urandom(16)).decode("ascii")
    with socket.create_connection(("127.0.0.1", 443), timeout=5) as raw:
        with ssl.create_default_context().wrap_socket(raw, server_hostname=host) as conn:
            conn.sendall(("GET /ws/laboutik/00000000-0000-0000-0000-000000000000/ HTTP/1.1\r\n"
                          "Host: " + host + "\r\nOrigin: https://" + host + "\r\n"
                          "Connection: Upgrade\r\nUpgrade: websocket\r\nSec-WebSocket-Key: " + key +
                          "\r\nSec-WebSocket-Version: 13\r\n\r\n").encode("ascii"))
            response = http.client.HTTPResponse(conn)
            response.begin()
            expected = base64.b64encode(hashlib.sha1(
                (key + "258EAFA5-E914-47DA-95CA-C5AB0DC85B11").encode("ascii")).digest()).decode("ascii")
            if (response.status != 101 or response.getheader("Sec-WebSocket-Accept") != expected or
                    response.getheader("Upgrade", "").lower() != "websocket"):
                raise RuntimeError("Handshake WebSocket non valide : HTTP " + str(response.status))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--verifier", action="store_true",
                        help="Controles seuls, sans modifier la configuration ni recharger nginx")
    args = parser.parse_args()
    if socket.gethostname() != "estia" or os.geteuid() != 0:
        raise SystemExit("ARRET : executer avec sudo sur estia.")
    folder = FOLDER
    before = json.loads((folder / "avant.json").read_text())
    target = TARGET
    link = LINK
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
                  for p in link.parent.iterdir()}
        if actual != expected:
            raise RuntimeError("ARRET : changement inattendu dans sites-enabled.")

    verify(original)
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
    print("OK : fichiers proteges, liens, includes et test nginx conformes.", flush=True)
    state_before = nginx_state()
    print("OK : nginx actif, master PID %s, %s workers." %
          (state_before[0], len(state_before[1])), flush=True)
    hosts = {"hello.rezal.fr", "rezal.fr", "gala-test.rezal.fr",
             "cashless.gala-test.rezal.fr", "fedow.gala-test.rezal.fr"}
    for name in before["files"]:
        text = re.sub(r"#.*", "", Path(name).read_text())
        for names in re.findall(r"\bserver_name\s+([^;]+);", text):
            hosts.update(host for host in names.split()
                         if re.fullmatch(r"[a-zA-Z0-9-]+(?:\.[a-zA-Z0-9-]+)+", host))
    if len(hosts) > 128:
        raise RuntimeError("Inventaire de sites inhabituellement grand")
    print("Controle HTTP/HTTPS local de %s noms, sans suivre les redirections..." % len(hosts), flush=True)
    sites_before = sites_snapshot(sorted(hosts))
    for url, result in sorted(sites_before.items()):
        print(url, ":", result.get("error", "HTTP " + str(result.get("status"))), flush=True)
    hello = sites_before["https://hello.rezal.fr"]
    if hello.get("status") != 200 or "error" in hello:
        raise RuntimeError("hello ne repond pas normalement AVANT activation ; aucun changement")
    print("Hello : contenu SHA256", hello["body_sha256"], flush=True)
    print("Hello : certificat SHA256", hello["certificate"], flush=True)
    for host in ("gala-test.rezal.fr", "cashless.gala-test.rezal.fr", "fedow.gala-test.rezal.fr"):
        result = sites_before["https://" + host]
        if "error" in result or not 200 <= result.get("status", 0) < 400:
            raise RuntimeError("Notre site ne repond pas normalement AVANT activation : " + host)
    if args.verifier:
        print("VERIFICATION SEULE TERMINEE : aucune configuration modifiee, aucun reload.")
        print("Les erreurs eventuelles ci-dessus sont preexistantes et restent a examiner.")
        return
    if b"$tibillet_connection_upgrade" in original:
        websocket_check()
        print("WebSockets deja configures et handshake valide ; aucun changement ni reload.")
        return
    backup = folder / "https-caisse-avant-websockets.conf"
    if backup.exists():
        if backup.is_symlink() or backup.read_bytes() != original:
            raise RuntimeError("Sauvegarde precedente inattendue ; aucun changement")
    else:
        with backup.open("xb") as output:
            output.write(original)
        backup.chmod(0o600)
    test_and_verify(original)
    if nginx_state() != state_before:
        raise RuntimeError("Etat nginx modifie pendant les controles ; aucun changement")
    reload_requested = False
    try:
        replace(target, final, 0o644)
        test_and_verify(final)
        if reference.read_bytes() != original:
            raise RuntimeError("ARRET : reference modifiee ailleurs.")
        replace(reference, final, 0o600)
        print("OK : fichiers proteges inchanges ; seul notre proxy evolue.", flush=True)
        reload_requested = True
        subprocess.run(["systemctl", "reload", "nginx"], check=True)
    except Exception:
        if reload_requested:
            print("ALERTE : reload demande mais resultat incertain ; configuration conservee pour diagnostic.")
            raise
        if not target.is_symlink() and target.read_bytes() == final:
            replace(target, original, 0o644)
        if reference.read_bytes() == final:
            replace(reference, original, 0o600)
        print("Notre configuration precedente est restauree si elle etait inchangee.")
        raise
    print("Reload demande. La commande de rechargement du certificat reste compatible.")
    # Functional failures after a reload require diagnosis, never a blind global reload.
    try:
        wait_for_reload(state_before)
        test_and_verify(final)
        sites_after = sites_snapshot(sorted(hosts))
        compare_sites(sites_before, sites_after)
        websocket_check()
        test_and_verify(final)
        nginx_state()
    except Exception:
        print("ALERTE APRES RELOAD : validation incomplete. Ne pas relancer/recharger a l'aveugle.")
        print("Notre ajout est conserve pour diagnostic ; sauvegarde :", backup)
        raise
    print("OK APRES : nginx actif avec nouveaux workers ; fichiers proteges inchanges.")
    print("OK APRES : reponses HTTP/HTTPS comparees, contenu et certificat hello identiques.")
    print("OK APRES : WebSocket 101 et signature du handshake valides.")
    print("Limite : ces sondes locales ne valident pas tous les usages ni l'acces Internet.")


if __name__ == "__main__":
    main()
