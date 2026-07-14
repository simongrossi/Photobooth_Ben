# Design — Assets kiosque dans l'admin (volet 2/3)

**Date** : 2026-07-14 · **Statut** : validé (Simon).
**Volets** : 1 = refonte UI (livré) · **2 = ce document** · 3 = contrôle kiosque (systemd).

## Objectif

Gérer depuis l'admin web, sans SSH : le **fond d'écran d'accueil** du kiosque, la
**police** unique des textes à l'écran, et le contenu du **slideshow** d'attente
(visuels perso + retrait de photos gênantes).

## Décisions validées

- Nouvelle page **« Kiosque »** (nav entre Templates et Réglages), table SQLite
  séparée `asset_kiosque` — les assets sont globaux, pas de dimension 10×15/strip.
- Mécanique **« actif + fallback »** : l'activation copie vers un fichier `*_actif`,
  le kiosque le préfère au défaut s'il existe. « Défaut » = suppression du fichier
  actif. Aucun fichier versionné n'est écrasé.
- Fond d'accueil et police : effet **au redémarrage du kiosque** (chargés au boot).
  Le bouton de redémarrage distant est le volet 3.
- Slides perso : effet **à chaud** (le slideshow rescanne toutes les 30 s).
- Retrait d'une photo (galerie) : **déplacement vers `data/corbeille/`**, jamais de
  suppression définitive ; restauration possible.

## Modèle de données

Nouvelle table (dans `web/db.py`, même `_SCHEMA` / `init_db`) :

```sql
CREATE TABLE IF NOT EXISTS asset_kiosque (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    nom TEXT NOT NULL,
    categorie TEXT NOT NULL,          -- 'accueil' | 'police' | 'slide'
    fichier TEXT NOT NULL UNIQUE,
    actif INTEGER NOT NULL DEFAULT 0, -- sans objet pour 'slide' (reste 0)
    uploaded_at TEXT NOT NULL DEFAULT (datetime('now')),
    taille_octets INTEGER NOT NULL DEFAULT 0
);
```

`CREATE TABLE IF NOT EXISTS` suffit (table neuve, pas de migration de colonnes).
Invariant : au plus un `actif=1` par catégorie (`accueil`, `police`).

## Fichiers et chemins

| Catégorie | Bibliothèque | Fichier actif | Fallback kiosque | Extensions |
|---|---|---|---|---|
| accueil | `assets/interface/accueil/` | `assets/interface/accueil_actif.jpg` | `background.jpg` actuel | .jpg/.jpeg/.png |
| police | `assets/fonts/bibliotheque/` | `assets/fonts/police_active.ttf` | WesternBangBang → Arial | .ttf/.otf |
| slide | `assets/slideshow/` | — (tous les fichiers tournent) | — | .jpg/.jpeg/.png |

Corbeille galerie : `data/corbeille/10x15/` et `data/corbeille/strip/`
(déplacement `os.replace`, nom conservé → restauration triviale).

## Config (`config.py` + `docs/CONFIG.md`)

```python
# Volet 2 — assets kiosque gérés par l'admin web
FILE_BG_ACCUEIL_ACTIF = os.path.join(PATH_INTERFACE, "accueil_actif.jpg")
POLICE_FICHIER_ACTIF  = os.path.join(BASE_DIR, "assets/fonts/police_active.ttf")
PATH_SLIDESHOW_PERSO  = os.path.join(PATH_ASSETS, "slideshow")
PATH_CORBEILLE        = os.path.join(PATH_DATA, "corbeille")

# Résolution actif > défaut (évaluée à l'import ; le kiosque charge au boot)
BG_ACCUEIL_EFFECTIF = FILE_BG_ACCUEIL_ACTIF if os.path.exists(FILE_BG_ACCUEIL_ACTIF) else FILE_BG_ACCUEIL
POLICE_EFFECTIVE    = POLICE_FICHIER_ACTIF if os.path.exists(POLICE_FICHIER_ACTIF) else POLICE_FICHIER
```

Côté kiosque : `Photobooth_start.py` remplace `FILE_BG_ACCUEIL` par
`BG_ACCUEIL_EFFECTIF` (chargement AccueilAssets) et `POLICE_FICHIER` par
`POLICE_EFFECTIVE` (`_charger_polices`, watermark via `core/montage.py` inchangé —
le watermark garde `POLICE_FICHIER`) ; `ui/helpers.py` (fonts impression) passe à
`POLICE_EFFECTIVE`. Le slideshow ajoute `PATH_SLIDESHOW_PERSO` à la liste passée à
`lister_images_slideshow` (fonction déjà multi-dossiers, testée).

## Routes (nouveau `web/routes/kiosque_route.py`, Blueprint `/kiosque`)

- `GET /kiosque/` : page 3 sections (Fond d'accueil, Police, Slides) avec état
  « Actif : X » / « Défaut » pour accueil et police.
- `POST /kiosque/upload` : champs `nom`, `categorie`, `fichier`. Validation :
  extensions par catégorie ; images → `Image.verify()` ; police →
  `PIL.ImageFont.truetype(bytes, 24)` (rejette un fichier non-fonte).
- `POST /kiosque/activer/<id>` : copie vers le fichier actif de la catégorie
  (400 pour `slide`), reset `actif` par catégorie.
- `POST /kiosque/defaut/<categorie>` : supprime le fichier actif
  (`FileNotFoundError` ignoré), `actif=0` pour la catégorie. 404 si catégorie
  inconnue ou `slide`.
- `POST /kiosque/supprimer/<id>` : refusé si actif ; les `slide` se suppriment
  librement (retirés de la rotation ≤ 30 s).
- `GET /kiosque/thumb/<id>` : miniature image ; pour une police, rendu PIL
  « Aa Bb 123 » (fond transparent) avec la fonte.

## Galerie : retirer / restaurer

- `POST /gallery/retirer/<mode>/<nom>` : `os.replace` vers
  `data/corbeille/<mode>/<nom>` (création du dossier au besoin). Sécurité chemin
  identique à `_resoudre_chemin` existant.
- Section « Corbeille » en bas de la galerie (miniatures) avec
  `POST /gallery/restaurer/<mode>/<nom>` (déplacement inverse).
- Aucune route de suppression définitive (nettoyage manuel assumé).

## Gestion d'erreurs

- Fichier actif posé à la main (hors DB) : bouton « Défaut » le supprime quand même
  (même logique « Forcer aucun » que la page Templates).
- Upload police corrompue : rejet avec flash (la validation truetype échoue).
- Retrait galerie d'un fichier disparu : flash erreur, pas de crash.
- Restauration vers un nom déjà existant : `os.replace` écrase (même nom = même
  montage, cas bénin).

## Tests (CI pure)

- `web/db.py` : table `asset_kiosque` créée (neuve + base existante).
- `kiosque_route` : upload par catégorie (+ rejets extension/catégorie/fonte
  invalide), activer accueil/police (copie vers actif, exclusivité), activer un
  slide → 400, défaut (suppression + idempotence + 404), thumb police (PNG rendu).
- `gallery` : retirer → fichier déplacé en corbeille, absent de la liste ;
  restaurer → de retour ; sécurité traversée de chemin.
- Kiosque : `test_config` (si présent) — les constantes existent ; la résolution
  actif/défaut est testée en monkeypatchant l'existence des fichiers…
  la logique étant à l'import de config, on la teste via un petit helper pur
  `resoudre_actif(chemin_actif, chemin_defaut)` défini dans config et appelé
  pour les deux constantes.

## Docs

- `docs/CONFIG.md` : nouvelles constantes.
- `docs/ADMIN.md` : page Kiosque + corbeille galerie + tableau source de vérité.

## Hors périmètre

- Redémarrage kiosque à distance (volet 3).
- Purge automatique de la corbeille.
- Plusieurs polices simultanées (titres ≠ boutons) — une seule police globale.
