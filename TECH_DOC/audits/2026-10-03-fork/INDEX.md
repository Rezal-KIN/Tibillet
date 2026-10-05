# Audit conservé — fork TiBillet, reprises 100J et volumes

Dossier créé le 3 octobre 2026 à la demande de conserver l'audit et d'investiguer les surcharges. Il contient uniquement documentation, diffs de code et reproductions sur données de test. Aucun correctif applicatif ni déploiement dans ce lot.

- [Inventaire 100J/volumes et choix de rollback A–L](INVENTAIRE-100J-VOLUMES.md) : éléments à conserver/retirer, commits d'origine, effets et dépendances.
- [Tous les montages des quatre Compose actifs](VOLUMES.md) : 47 montages distincts par service, 50 déclarations brutes.
- [Investigation et défauts reproduits](INVESTIGATION.md) : atomicité des recharges, concurrence, cartes, réseau, billets et adhésions.
- [Audit initial des différences depuis le fork](README.md) : snapshot original préservé sans réécriture. Les chemins `.context/fork-audit/` qu'il mentionne sont les emplacements de création ; les mêmes preuves se trouvent maintenant dans ce dossier.
- Les fichiers `.diff` sont des preuves brutes : leurs lignes de contexte conservent les espaces originaux. Les alertes de whitespace de Git sur ces artefacts ne doivent pas conduire à réécrire le snapshot. Le contrôle de whitespace du nouveau texte et des sondes se fait en excluant ces `.diff`.
- `SHA256SUMS` : empreintes du snapshot initial, inchangé. `ALL_SHA256SUMS` couvre ensuite tout le dossier conservé.
- `comparison.json`, `overlays.json`, `all-files.tsv`, fichiers `.diff` : références et preuves initiales.
- `volumes.json`, `file-history.json`, `original-import-history.txt` : inventaire et histoire Git.
- `fedow-results.json`, `laboutik-results.json`, [sondes reproductibles](probes/README.md) : résultats sur données locales synthétiques.

Ce dossier décrit un état précis du code. Une nouvelle release ou un nouveau choix de rollback exige une comparaison avec cet état et une vérification des parcours concernés. Aucun incident financier de production n'est déduit automatiquement d'une reproduction locale.
