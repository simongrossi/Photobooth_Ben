# Design — Fiabiliser la gestion d'impression DNP DS620

**Date** : 2026-08-24 · **Statut** : à valider (Simon) · **Déclencheur** : incident en événement.

## Objectif

Qu'un manque de papier en pleine soirée redevienne un incident de 30 secondes
(recharger, appuyer sur un bouton) au lieu d'une panne nécessitant clavier,
sortie du kiosque, interface CUPS et plusieurs redémarrages.

## L'incident

Séquence réellement vécue :

1. Le papier s'épuise. CUPS applique sa politique par défaut
   `ErrorPolicy=stop-printer` : il **désactive la file** et y laisse le job.
2. Le rouleau et le ribbon sont changés.
3. « Démarrer l'imprimante » dans CUPS ne débloque rien. Le message « plus de
   papier » persiste. Un redémarrage du PC n'y change rien non plus. Il a fallu
   s'y reprendre plusieurs fois.

### Pourquoi le redémarrage n'a servi à rien

Deux états survivent au reboot : `State Stopped` dans
`/etc/cups/printers.conf`, et le job en attente dans `/var/spool/cups`. Au
redémarrage, CUPS revient exactement dans l'état où il s'était arrêté.

### Pourquoi « Démarrer l'imprimante » ne suffisait pas

`cupsenable` réactive la file, ce qui fait **immédiatement redispatcher le job
empoisonné** — celui créé quand il n'y avait plus de papier. La DS620 vient
d'être rallumée et met une vingtaine de secondes à relire le ribbon : le job
repart trop tôt, échoue, et CUPS redésactive la file. Boucle.

La séquence correcte est `cancel -a` **puis** `cupsenable`, dans cet ordre. Le
job n'a jamais été purgé, donc chaque « Démarrer » le relançait.

### Pourquoi il a fallu recommencer plusieurs fois

Constat décisif du diagnostic terrain :

```
DNP_10x15  → gutenprint53+usb://dnp-ds620/DS6X54003557
DNP_STRIP  → gutenprint53+usb://dnp-ds620/DS6X54003557
```

**Deux files CUPS, une seule imprimante physique.** Le manque de papier
désactive les deux et coince un job dans chacune. Réarmer une file laissait
l'autre avec son job empoisonné, qui repartait et remettait l'imprimante en
erreur. Chaque intervention ne réparait qu'une moitié du problème.

### Ce que le code ne savait pas faire

- `is_ready()` ne lit jamais la cause réelle. `lpstat -p` sur une file
  désactivée ne contient ni `idle`, ni `paused` : on tombe sur le générique
  « IMPRIMANTE HORS LIGNE » (`core/printer.py:66`), qui ne dit pas quoi faire.
- Le job coincé fait retourner « FILE D'ATTENTE PLEINE » à toutes les sessions
  suivantes (`core/printer.py:60`).
- Le comptage des jobs est **par file**, pas par imprimante. Un strip coincé
  n'empêche pas d'envoyer un 10×15 sur la même DS620.
- Aucun moyen de réarmer une file : d'où le passage obligé par CUPS.
- `session.message_erreur_impression` est calculé, stocké et loggé — puis
  **jamais affiché**. L'écran ne montre que « IMPRESSION NON ENVOYÉE »
  (`Photobooth_start.py:1540`). La cause précise existait déjà en mémoire ;
  personne ne la voyait.

## Diagnostic terrain — ce qui est disponible

Vérifié sur le mini-PC (utilisateur `photobooth`) :

- **`pycups` est installé et fonctionnel.** `getPrinters()` renvoie
  `printer-state`, `printer-state-message` et `printer-state-reasons` sous
  forme de mots-clés IPP non localisés. Pas de parsing de texte français.
- **`photobooth` est dans `lpadmin`** (et `sudo`). `cupsenable` et `cancel -a`
  fonctionneront sans privilège supplémentaire.
- **Le niveau de média est lisible** via `marker-levels` (57), avec
  `marker-message` = « 228 native prints remaining on 6x4 (PC) media » et
  `marker-low-levels` = 10.
- `lpstat -l -p` n'expose **pas** `printer-state-reasons` (seulement
  « Alerts: none »). Cette source est écartée.
- La machine héberge une dizaine d'autres files (imprimantes de bureau). Toute
  opération destructive doit rester strictement limitée aux files DNP
  configurées — ce que `purger_file_attente()` fait déjà correctement.

## Décisions validées

- **Source de vérité** : `pycups`, avec repli `lpstat` quand le module est
  absent (CI, Mac de dev), selon le pattern `try/except ImportError` déjà
  utilisé pour `gphoto2` et `pyserial`.
- **Périmètre périphérique** : les files partageant un `device-uri` sont
  vérifiées et réarmées **ensemble**.
- **Papier vraiment épuisé** : le job attend et sort tout seul au rechargement
  (`printer-error-policy=retry-job`). La file n'est plus jamais désactivée.
- **Réarmement** : déclenché par la touche RÉESSAYER existante, jamais
  automatiquement. L'appui humain vaut confirmation que le papier est rechargé.
- **Pas de nouveau bouton** : le boîtier n'a que 3 boutons physiques, et
  l'écran d'erreur les utilise déjà tous les trois.
- **Alerte préventive** : bandeau sur l'accueil sous un seuil configurable de
  tirages restants.

## Approches écartées

**Réarmement automatique au démarrage et avant chaque impression.** Répare dans
le dos de l'animateur. Si le papier est réellement vide, une réparation
silencieuse masque le problème au lieu de le signaler. Le choix retenu — un
appui volontaire sur RÉESSAYER — donne le même résultat avec une intention
explicite.

**Bouton « Réarmer » dans l'admin web.** C'est précisément ce qu'il a fallu
faire pendant l'incident : prendre un clavier, quitter le kiosque, ouvrir un
navigateur. L'objectif est de supprimer ce détour, pas de le rendre plus
confortable.

**Parsing du message d'état localisé de `lpstat`.** Fragile (dépend de la
locale) et moins riche que les mots-clés IPP. Écarté dès lors que `pycups`
répond.

**Thread de surveillance de l'imprimante.** Un `tick()` rate-limité dans la
boucle de rendu suffit et suit le pattern `DiskMonitor` / `TempMonitor` déjà en
place. Un thread supplémentaire n'apporterait rien et compliquerait l'arrêt.

## Architecture

### `core/printer.py` — diagnostic

Nouveau dataclass exposé par une méthode `diagnostic(mode)` :

```python
@dataclass
class EtatImprimante:
    pret: bool
    raison: str          # mot-clé IPP brut, "" si aucun
    message: str         # texte FR affichable
    file_desactivee: bool
    jobs: int            # cumulé sur toutes les files du même device
    tirages_restants: Optional[int]   # marker-levels, None si inconnu
```

Les mots-clés IPP portent des suffixes `-error`, `-warning`, `-report` :
**le suffixe est retiré avant correspondance**. Table :

| Mot-clé IPP | Message écran |
|---|---|
| `media-empty`, `media-needed` | PAPIER ÉPUISÉ — recharger le bac |
| `media-jam` | BOURRAGE PAPIER |
| `marker-supply-empty` | RIBBON ÉPUISÉ |
| `marker-supply-low` | RIBBON BIENTÔT ÉPUISÉ |
| `cover-open`, `door-open` | CAPOT OUVERT |
| `connecting-to-device`, `timed-out` | IMPRIMANTE ÉTEINTE OU DÉBRANCHÉE |
| `paused` / `printer-state` = 5 | FILE D'IMPRESSION ARRÊTÉE |
| inconnu | mot-clé brut, préfixé « Imprimante : » |

`is_ready()` devient un mince wrapper au-dessus de `diagnostic()` et conserve
son contrat actuel (`True` ou chaîne), pour ne casser ni les appelants
(`Photobooth_start.py`, `web/routes/dashboard.py`) ni les tests existants.

Changement de sémantique : avec `retry-job`, un job en file n'est plus
« FILE D'ATTENTE PLEINE » mais « TIRAGE EN ATTENTE — {cause} ».

### `core/printer.py` — groupement par périphérique

`_files_du_meme_device(mode)` lit `device-uri` via `pycups` et retourne toutes
les files configurées qui partagent le périphérique du mode demandé. Sans
`pycups`, le repli retourne les deux files configurées : conservateur, et sans
effet de bord puisque la conséquence est seulement de vérifier ou réarmer une
file de plus.

`jobs_en_attente()` et `diagnostic()` agrègent sur ce groupe.

### `core/printer.py` — `reamorcer(mode)`

```
1. cancel -a <file>       pour chaque file du groupe   ← l'étape manquante
2. attendre que la DS620 réponde
      polling de diagnostic() toutes les 1 s
      sortie dès qu'aucune file ne rapporte connecting-to-device / timed-out
      plafond DELAI_REAMORCAGE_S (30 s)
3. cupsenable + cupsaccept  pour chaque file du groupe
4. re-diagnostiquer et retourner l'EtatImprimante final
```

Borné, sans boucle infinie, journalisé via `log_info` / `log_critical`. Aucune
file hors groupe DNP n'est touchée.

### `Photobooth_start.py` — RÉESSAYER répare

Dans `_handle_erreur_impression`, touche `TOUCHE_MILIEU` : si le diagnostic
indique une file désactivée, `reamorcer()` est exécuté **avant** de relancer
l'impression. L'appel passe par `executer_avec_spinner()` (`ui/helpers.py:403`)
pour que l'UI reste vivante pendant l'attente bornée.

L'écran d'erreur affiche `session.message_erreur_impression` sous le titre
« IMPRESSION NON ENVOYÉE », dans les deux fonctions de rendu concernées
(`Photobooth_start.py:1540` et `:1635`). C'est le changement d'une ligne qui
aurait évité l'essentiel de l'incident.

### `core/monitoring.py` — `MediaMonitor`

Même forme que `DiskMonitor` et `TempMonitor` : `tick()` rate-limité, flag
`critique`, warning loggé à la seule transition OK→critique.

```python
MediaMonitor(printer_mgr, mode, seuil_tirages, intervalle_s)
    .tick()               # lit marker-levels via diagnostic()
    .critique             # tirages_restants <= seuil
    .tirages_restants
```

`tick()` est ignoré tant que `session.impression_en_cours` est vrai, pour ne
pas interroger CUPS pendant un envoi.

### `Photobooth_start.py` — bandeau d'alerte papier

Troisième bandeau dans la pile d'alertes de `_render_accueil_normal`
(`Photobooth_start.py:1139`), qui empile déjà disque puis température via
l'accumulateur `y_alerte`. Couleur ambre, texte
« ⚠ PAPIER BIENTÔT ÉPUISÉ — {n} tirages restants ».

### `config.py` — nouveaux réglages

| Clé | Défaut | Bornes |
|---|---|---|
| `SEUIL_TIRAGES_RESTANTS` | `20` | (0, 10000) |
| `INTERVALLE_CHECK_MEDIA_S` | `120.0` | (10.0, 3600.0) |
| `DELAI_REAMORCAGE_S` | `30.0` | (5.0, 120.0) |

Ajoutées à `_CONFIG_OVERRIDES_WHITELIST` et `_CONFIG_OVERRIDES_BOURNES`, plus
les textes d'écran associés dans le bloc `TXT_*`. `docs/CONFIG.md` est mis à
jour en conséquence.

### `deploy/install.sh` — politique CUPS

Étape nouvelle, idempotente :

```bash
for f in "$NOM_IMPRIMANTE_10X15" "$NOM_IMPRIMANTE_STRIP"; do
  lpadmin -p "$f" -o printer-error-policy=retry-job
done
```

Et dans `cupsd.conf` : `JobRetryInterval 30` avec `JobRetryLimit 240`, soit
2 heures d'attente au lieu des 2 min 30 par défaut (5 tentatives × 30 s) — sans
quoi un tirage serait abandonné avant même que le rouleau soit changé.

Le script vérifie aussi l'appartenance de l'utilisateur du kiosque à `lpadmin`
et échoue explicitement sinon : sans ce droit, `reamorcer()` ne peut rien faire.

`docs/DEPLOYMENT.md` et `docs/RUNBOOK.md` sont mis à jour — notamment la ligne
« File CUPS bloquée » du tableau de dépannage (`docs/RUNBOOK.md:129`), qui
décrit aujourd'hui la manipulation manuelle que ce travail supprime.

## Tests

`core/printer.py` et `core/monitoring.py` restent des modules purs, testables
en CI. `pycups` n'y étant pas installé, les tests injectent une fausse
connexion, sur le modèle de `FakeSerial` / `FakePygame` de `core/arduino.py`.

Dans `tests/test_printer.py` :

- correspondance de chaque mot-clé IPP, suffixes `-error` / `-warning` /
  `-report` compris, et comportement sur mot-clé inconnu ;
- `printer-state` = 5 → `file_desactivee` vrai ;
- groupement par `device-uri` : deux files sur le même périphérique cumulent
  leurs jobs ; deux files sur des périphériques distincts non ;
- **`reamorcer()` appelle `cancel` avant `cupsenable`** — assertion sur l'ordre
  des appels, c'est le cœur du correctif ;
- `reamorcer()` traite **toutes** les files du groupe, pas seulement celle du
  mode courant ;
- plafond de l'attente de warm-up respecté ;
- aucune file hors groupe DNP n'est touchée ;
- repli sans `pycups` : le comportement actuel est conservé.

Dans `tests/test_monitoring.py` : seuil, transition OK→critique loggée une
seule fois, `tick()` ignoré pendant une impression.

Dans `tests/test_impression_flow.py` : RÉESSAYER sur file désactivée déclenche
bien `reamorcer()` puis la relance ; RÉESSAYER sur une file saine ne le
déclenche pas.

## Hors périmètre

Pas de réarmement automatique au démarrage ou avant chaque impression, pas de
bouton dans l'admin web, pas de quatrième bouton physique, pas de thread de
surveillance de l'imprimante.

## Risques et points à vérifier sur le terrain

- **`marker-levels` après changement de rouleau.** Le design suppose que le
  compteur remonte sans qu'il faille imprimer d'abord. C'est le comportement
  attendu du backend Gutenprint, mais ce n'est pas vérifié. Le niveau de média
  est donc utilisé comme **indice** (alerte préventive, journalisation), jamais
  comme condition bloquante du réarmement.
- **Durée réelle du warm-up DS620** après un changement de média. Les 30 s de
  `DELAI_REAMORCAGE_S` sont une estimation, à ajuster après un test réel.
- **`retry-job` et accumulation de jobs.** Le garde-fou « file non vide »
  existant limite l'accumulation à un ou deux jobs, puisqu'une nouvelle session
  ne peut pas imprimer tant qu'un tirage est en attente. À confirmer en
  conditions réelles.
