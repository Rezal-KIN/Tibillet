#!/usr/bin/env python3
"""Lister les références des images épinglées, après contrôle de l'archive."""
import argparse
import ast
import csv
import hashlib
import json
import re
import tarfile
from collections import Counter
from pathlib import Path

from inventory import Symbols, dotted_name


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--source', type=Path, required=True)
    parser.add_argument('--archive', type=Path, required=True)
    parser.add_argument('--sha256', required=True)
    parser.add_argument('--output', type=Path, required=True)
    arguments = parser.parse_args()
    if hashlib.sha256(arguments.archive.read_bytes()).hexdigest() != arguments.sha256:
        raise SystemExit('Archive non conforme à la source épinglée')
    rows, calls, files, scopes, parse_errors = [], [], [], [], []
    # FR : Lire l'archive vérifiée évite d'inclure les caches et les changements locaux.
    # EN: Read verified archive bytes, including JS/CSS/env/lock files, without extraction.
    sources = []
    with tarfile.open(arguments.archive) as archive:
        for member in sorted(archive.getmembers(), key=lambda item: item.name):
            if not member.isfile():
                continue
            data = archive.extractfile(member).read()
            if b'\0' in data:
                continue
            try:
                source = data.decode('utf-8')
            except UnicodeError:
                continue
            relative = str(Path(member.name).relative_to(arguments.source.name))
            sources.append((relative, source))
    for relative, source in sources:
        symbols = Symbols()
        if relative.endswith('.py'):
            try:
                tree = ast.parse(source)
            except SyntaxError as error:
                parse_errors.append({'path': relative, 'line': error.lineno, 'message': error.msg})
                tree = None
            if tree:
                symbols.visit(tree)
                for node in ast.walk(tree):
                    if isinstance(node, ast.Call) and dotted_name(node.func).startswith('stripe.'):
                        calls.append((relative, node.lineno, symbols.at_line(node.lineno), dotted_name(node.func)))
        counts = Counter()
        for number, line in enumerate(source.splitlines(), 1):
            if 'stripe' in line.lower():
                names = sorted(set(re.findall(r'\b\w*stripe\w*\b', line, re.I)))
                symbol = symbols.at_line(number)
                rows.append((relative, number, symbol, ','.join(names)))
                counts[symbol] += 1
        if counts:
            files.append((relative, sum(counts.values())))
            scopes.extend((relative, symbol, count) for symbol, count in sorted(counts.items()))
    arguments.output.mkdir(parents=True, exist_ok=True)
    for name, header, content in [('references.tsv', ['path', 'line', 'symbol', 'identifiers'], rows),
                                  ('sdk-calls.tsv', ['path', 'line', 'symbol', 'call'], calls),
                                  ('files.tsv', ['path', 'matched_lines'], files),
                                  ('symbols.tsv', ['path', 'symbol', 'matched_lines'], scopes)]:
        with (arguments.output / name).open('w', encoding='utf-8', newline='') as stream:
            writer = csv.writer(stream, delimiter='\t', lineterminator='\n')
            writer.writerow(header)
            writer.writerows(content)
    summary = {'source': arguments.source.name, 'archive_sha256': arguments.sha256,
               'files_with_stripe': len({row[0] for row in rows}), 'matched_lines': len(rows),
               'sdk_call_sites': len(calls),
               'parse_errors': parse_errors,
               'scope': 'Tous les fichiers texte UTF-8 de l’archive épinglée ; les extensions de cette branche sont un périmètre supplémentaire.',
               'limits': ['Recherche de la chaîne stripe, incluant noms CSS tels que striped, documentation et historique.',
                          'Analyse syntaxique Python ; aucun graphe dynamique ni accès aux secrets du marchand.'],
               'sha256': {name: hashlib.sha256((arguments.output / name).read_bytes()).hexdigest()
                          for name in ('references.tsv', 'sdk-calls.tsv', 'files.tsv', 'symbols.tsv')}}
    (arguments.output / 'summary.json').write_text(json.dumps(summary, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps(summary, ensure_ascii=False))


if __name__ == '__main__':
    main()
