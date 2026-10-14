#!/usr/bin/env python3
"""Inventaire reproductible, sans réseau ni accès aux secrets.

FR : Les références sont lues dans une révision Git précise. Aucun extrait de
fichier n'est exporté : les tables contiennent chemins, lignes et symboles.
EN: Read a fixed Git revision. Export locations and symbols, never file contents.
"""

import argparse
import ast
import csv
import hashlib
import json
import re
import subprocess
from collections import Counter, defaultdict
from pathlib import Path


def git(repository, *arguments):
    result = subprocess.run(
        ["git", "-C", str(repository), *arguments],
        check=True, capture_output=True,
    )
    return result.stdout


def file_role(path):
    if path.startswith("deploy/Lespass/legacy-") or "features-enlevees/" in path:
        return "archive"
    if "/migrations/" in path:
        return "migration_historique"
    if path.startswith("tests/") or path.endswith("/tests.py") or "/tests/" in path:
        return "test"
    if path.startswith("deploy/"):
        if path.endswith(".py") and "/tools/" not in path:
            return "application_deployee"
        return "exploitation_deploiement"
    if path.endswith(".py"):
        return "application_lespass"
    if "/templates/" in path or "/static/" in path:
        return "interface"
    if path.startswith("locale/"):
        return "traduction"
    if path in {"pyproject.toml", "poetry.lock"}:
        return "dependance"
    if path.endswith(".md") or path.startswith(".claude/"):
        return "documentation"
    return "configuration_ou_autre"


def dotted_name(node):
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        parent = dotted_name(node.value)
        if parent:
            return parent + "." + node.attr
    return ""


class Symbols(ast.NodeVisitor):
    def __init__(self):
        self.parents = []
        self.definitions = []

    def visit_definition(self, node):
        self.parents.append(node.name)
        self.definitions.append((node.lineno, node.end_lineno, ".".join(self.parents)))
        self.generic_visit(node)
        self.parents.pop()

    visit_ClassDef = visit_definition
    visit_FunctionDef = visit_definition
    visit_AsyncFunctionDef = visit_definition

    def at_line(self, line):
        candidates = []
        for start, end, name in self.definitions:
            if start <= line <= end:
                candidates.append((end - start, name))
        if candidates:
            return min(candidates)[1]
        return "<module>"


def table(destination, name, columns, rows):
    with (destination / name).open("w", encoding="utf-8", newline="") as output:
        writer = csv.writer(output, delimiter="\t", lineterminator="\n")
        writer.writerow(columns)
        writer.writerows(rows)


def inventory(repository, revision, destination):
    commit = git(repository, "rev-parse", revision + "^{commit}").decode().strip()
    tracked = git(repository, "ls-tree", "-r", "--name-only", "-z", commit).decode().split("\0")
    tracked = [path for path in tracked if path]
    result = subprocess.run(
        ["git", "-C", str(repository), "grep", "--full-name", "-n", "-I", "-i", "stripe", commit, "--"],
        capture_output=True,
    )
    if result.returncode not in {0, 1}:
        raise RuntimeError(result.stderr.decode())
    matches = defaultdict(list)
    for line in result.stdout.decode("utf-8", errors="replace").splitlines():
        _, path, number, source = line.split(":", 3)
        identifiers = sorted(set(re.findall(r"\b\w*stripe\w*\b", source, re.IGNORECASE)))
        matches[path].append((int(number), identifiers))

    references = []
    files = []
    symbols = []
    sdk_calls = []
    calls = []
    parse_errors = []
    for path in sorted(matches):
        role = file_role(path)
        visitor = Symbols()
        if path.endswith(".py"):
            source = git(repository, "show", commit + ":" + path).decode("utf-8", errors="replace")
            try:
                tree = ast.parse(source, filename=path)
            except SyntaxError as error:
                parse_errors.append({"path": path, "line": error.lineno, "message": error.msg})
            else:
                visitor.visit(tree)
                for node in ast.walk(tree):
                    if isinstance(node, ast.Call):
                        name = dotted_name(node.func)
                        if name.startswith("stripe."):
                            sdk_calls.append((path, node.lineno, visitor.at_line(node.lineno), name, role))
                        if "stripe" in name.lower() or name.endswith("get_federated_token_refill_checkout"):
                            calls.append((path, node.lineno, visitor.at_line(node.lineno), name, role))
        function_counts = Counter()
        for number, identifiers in matches[path]:
            symbol = visitor.at_line(number)
            function_counts[symbol] += 1
            references.append((path, number, symbol, role, ",".join(identifiers)))
        for symbol, count in sorted(function_counts.items()):
            symbols.append((path, symbol, count, role))
        files.append((path, len(matches[path]), role))

    destination.mkdir(parents=True, exist_ok=True)
    table(destination, "references.tsv", ["path", "line", "symbol", "role", "identifiers"], references)
    table(destination, "files.tsv", ["path", "matched_lines", "role"], files)
    table(destination, "symbols.tsv", ["path", "symbol", "matched_lines", "role"], symbols)
    table(destination, "sdk-calls.tsv", ["path", "line", "symbol", "call", "role"], sorted(sdk_calls))
    table(destination, "call-sites.tsv", ["path", "line", "symbol", "call", "role"], sorted(calls))
    counts = Counter(role for _, _, role in files)
    summary = {
        "revision": commit,
        "tracked_files": len(tracked),
        "files_with_stripe": len(files),
        "matched_lines": len(references),
        "symbol_scopes": len(symbols),
        "python_symbol_scopes": sum(1 for row in symbols if row[0].endswith('.py')),
        "direct_sdk_call_sites": len(sdk_calls),
        "direct_sdk_operations": sorted(set(row[3] for row in sdk_calls if row[4].startswith("application"))),
        "files_by_role": dict(sorted(counts.items())),
        "parse_errors": parse_errors,
        "limits": [
            "Recherche insensible à la casse de Stripe dans les fichiers texte suivis par Git.",
            "Les symboles incluent classes, fonctions, commentaires et docstrings ; ce n'est pas une mesure de code exécuté.",
            "Les appels AST sont des emplacements syntaxiques, pas un graphe dynamique ni une preuve d'accessibilité.",
            "Les sources internes des images Fedow/LaBoutik sont un périmètre distinct du dépôt.",
            "Les fichiers ignorés, les données et les secrets de production ne sont pas lus.",
        ],
        "sha256": {},
    }
    for name in ["references.tsv", "files.tsv", "symbols.tsv", "sdk-calls.tsv", "call-sites.tsv"]:
        summary["sha256"][name] = hashlib.sha256((destination / name).read_bytes()).hexdigest()
    (destination / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({key: value for key, value in summary.items() if key not in {"sha256", "limits"}}, ensure_ascii=False, indent=2))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repository", type=Path, default=Path.cwd())
    parser.add_argument("--revision", required=True)
    parser.add_argument("--output", type=Path, required=True)
    arguments = parser.parse_args()
    inventory(arguments.repository, arguments.revision, arguments.output)


if __name__ == "__main__":
    main()
