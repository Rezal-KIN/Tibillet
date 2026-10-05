# LaBoutik : retrait des écarts hérités des copies complètes

Le 5 octobre 2026, l’utilisateur demande de retirer les écarts hérités recensés
dans l’inventaire après le rollback du dashboard. Le parcours QR, la présentation
web et l’enregistrement automatique des cartes restent ses choix conservés.
Ce retrait reprend les sources exactes de TiBillet ; il ne réécrit pas leurs
comportements à partir d’une description.

## Référence et archive

Référence native : `TiBillet/LaBoutik@3fdba313c2dea172bfaa6a06ebab05e1caf62490`.
Image : `tibillet/laboutik@sha256:012f3f1a14b532766f6faa9b6dc55ce53b0f2e65de7035066b96e86b30c006e9`.
Archive upstream SHA-256 :
`9cb955f13e545b883ca86c65baf73d8ff53b82d1c563d8fe7e8aab0274763dfd`.

L’[archive avant retrait](reference-6c373f10.tar.gz) conserve les anciennes
copies de `views.py`, `validators.py`, `fedow_api.py` et le Compose à l’identique
depuis `Rezal-KIN/Tibillet@6c373f10ca07718fea590328c9112ea58e042e2b`.
Le [manifeste](archive-manifest.json) indique les blobs Git, tailles et empreintes.
Aucun secret, contenu de base ou fichier runtime n’est ajouté à cette archive.

Archive SHA-256 :
`987c2a1f1d770309d3dcedb9fb6f5f77733ff4156be784ed17490b632da2dd7a`.

## Ce qui est rétabli

| Écart supprimé | Source native sélectionnée ou recopiée |
| --- | --- |
| Vente de billets absente | `Commande.methode_BI` et ses imports reviennent à l’identique |
| Vérification de validité des adhésions absente | Code natif de `check_carte` et `Commande.methode_VT`, avec l’option native et la clé Lespass |
| Première carte du responsable sélectionnée | Code natif de `Commande.methode_AD` et `NFCCard.badge`, utilisant la carte primaire |
| Retours inattendus pour les erreurs d’adhésion | Exceptions natives de `Subscription.create_sub` et traitement natif de `Commande.methode_AD` |
| Tolérance incomplète des cartes déjà connues | `NFCCard.create` natif, y compris le cas 400 d’unicité `first_tag_id` |
| Logs de carte inconnue et types de codes d’erreur | `NFCCard.retrieve`, `Transaction.refill_wallet` et `Transaction.to_place` natifs |

Le fichier `deploy/Laboutik/fedow_api.py` et ses deux déclarations de volume
(une doublonnée) sont retirés. Le fichier de l’image reprend directement la
main, y compris les délais réseau et la synchronisation native de monnaie cadeau.

`views.py` et `validators.py` sont reconstruits depuis les fichiers complets
de l’archive native vérifiée. Seuls deux spans de code E déjà présents avant
le retrait sont recopiés tels quels : la branche d’enregistrement d’une carte
absente dans `check_carte`, et `validate_tag_id`. Les notices de modification
existantes sont conservées. Les [exceptions déclarées](retained-E-source.json)
contiennent le texte exact avant/après et les empreintes ; aucun `ast.unparse`
ni réécriture des unités natives n’est utilisé.

Les deux déclarations de volume doublonnées de `views.py` et `validators.py`
sont également supprimées. Chaque fichier restant n’est monté qu’une fois.

## Ce qui reste personnalisé

L’enregistrement automatique sur absence confirmée reste actif. Une erreur
réseau, de signature, d’authentification ou de payload ne déclenche pas une
création. Après création ou réponse native de doublon, une relecture réussie
de Fedow reste nécessaire.

Les montages de `views.py` et `validators.py` demeurent pour cette fonction E.
Ils remplacent toujours un fichier complet, mais leur contenu n’a plus les
écarts hérités de billets/adhésions : tout le reste est exactement natif.
Le retrait de ces deux montages supprimerait aussi E. Aucune nouvelle image
personnalisée, injection au démarrage ou infrastructure de patches n’est ajoutée.

Les autres réglages, installateur reprenable et templates de sources restent
hors de ce retrait. Il reste donc **4 fichiers Python montés dans LaBoutik**
(`settings.py`, `install.py`, `views.py`, `validators.py`) et **1 dans Fedow**.
Le total passe de **40 montages distincts / 43 déclarations** à
**39 montages distincts / 39 déclarations** dans les quatre stacks retenues.
Les cibles de sources personnalisées passent de 11 à 10 (9 fichiers locaux,
car le template d’administration est partagé entre deux applications).

L’[inventaire précédent](../../audits/2026-10-05-differences-apres-dashboard.md)
reste conservé comme état historique avant ce retrait. Son tableau d’écarts
hérités LaBoutik décrit maintenant des différences retirées par ce lot.

## Vérification et limites

Le [reçu de restauration](restoration-receipt.json) vérifie le checksum
upstream, l’absence de remplacement du client Fedow et l’identité complète
des fichiers reconstruits hors des deux exceptions E déclarées. Il contrôle
aussi que les retraits C/D/F/G/H/I restent présents.

La [reconstruction des sources](source-reconstruction-receipt.json) utilise
le générateur existant et un dépôt temporaire contenant exactement les sources
montées actuelles. L’archive LaBoutik produite contient le client Fedow natif
octet par octet, ainsi que les deux fichiers E vérifiés. Les 54 fichiers du
dashboard Fedow restent identiques aux sources natives. Cette vérification
ne construit pas une image et ne déploie pas de service.

Validation locale : **23 tests LaBoutik et 9 tests de publication des sources**.
Les tests supplémentaires vérifient la création de réservation avant la vente
locale, le refus de vente si Lespass échoue ou si le paiement n’est pas accepté,
les exceptions d’adhésion, la sélection de carte primaire, le contrôle de
validité activé et la relecture d’une carte après réponse native de doublon.
HTTP et ORM sont instrumentés ; aucun billet, paiement ou solde réel n’est créé.
La syntaxe des deux sources applicatives est compatible Python 3.8.

Depuis la racine :

```sh
python3 TECH_DOC/features-enlevees/verify-restored-code.py
python3 -m unittest discover -s deploy/tests -p 'test_laboutik*.py' -v
python3 -m unittest discover -s deploy/tests -p test_source_offer.py -v
```

Le retrait est local, sans push, déploiement ni modification de base. La
vérification complète QR/email/recharge/caisse/remboursement sur la future
instance reste nécessaire avant le gala. Les montages restants de réglages,
d’installation et de E sont à examiner séparément si l’objectif devient de
supprimer tout remplacement de source par volume.

## Éventuelle réintroduction

Ne pas réintroduire les anciennes copies complètes. Une nouvelle divergence
de TiBillet doit répondre à un besoin explicite, être limitée et documenter
les comportements natifs qu’elle remplace. L’archive sert à retrouver l’état
antérieur, sans être montée ni chargée par les applications.
