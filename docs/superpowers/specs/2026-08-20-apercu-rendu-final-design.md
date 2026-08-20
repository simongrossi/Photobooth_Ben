# Design — Aperçu du rendu final depuis l'admin web

**Date** : 2026-08-20 · **Statut** : validé (Simon) · **Approche retenue** : A (paramétrer `core/montage.py`).

## Objectif

Voir à l'écran, depuis l'admin web, le rendu **réel** d'une photo avec un
template donné — sans activer ce template et sans lancer d'impression. Le but
opérationnel est de ne plus brûler de papier pour vérifier un calage.

L'aperçu doit être produit par le moteur du kiosque, pas par une simulation.
L'aperçu CSS actuel de l'éditeur de mise en page (`template_editeur.html`, des
`<img>` empilés) est une approximation : il ignore le filigrane, le grain, le
recadrage `ImageOps.fit` et la rotation à 180° des calques strip.

## Décisions validées

- **Source des photos** : les photos brutes déjà présentes dans `data/raw/`.
  Pas de déclenchement du Canon, pas d'upload, pas de webcam du navigateur.
- **Rendu affiché** : le visuel final lisible à l'écran — 10×15 complet
  (1800×1200) pour le format photo, bandelette « CLEAN » (600×1800) pour le
  strip. Filigrane et grain inclus, donc conformes à ce que verra l'invité.
  **Pas** la planche `READY_TO_PRINT` (deux bandes + offsets de calibration
  DNP) : elle ne sert qu'à l'imprimante et rend l'aperçu illisible.
- **Emplacement** : page dédiée `/templates/apercu`, avec choix explicite du
  format, du fond, de l'overlay et de la ou des photos. Permet de tester une
  combinaison fond + overlay qui n'est activée nulle part, donc sans aucun
  risque pendant un événement.
- **Approche technique** : paramétrer `core/montage.py` (approche A). Les
  approches écartées sont documentées plus bas.

## Approches écartées

**B — activer le template, rendre, restaurer.** Ne touche pas à `core/`, mais
mute un état global partagé avec le kiosque. Si une session démarre pendant
l'aperçu, ou si Flask meurt entre les deux étapes, le mauvais template reste
actif pour de vrai. Rédhibitoire pour un usage en événement.

**C — moteur de rendu séparé dans `web/`.** Isolation totale, mais duplication
d'une logique qui divergera du vrai rendu au premier changement de `config.py`.
C'est exactement le défaut de l'aperçu CSS qu'on cherche à corriger. La
rotation à 180° des calques strip en est l'illustration : une réimplémentation
naïve l'aurait manquée.

## Architecture

### `core/montage.py` — trois changements à défaut inchangé

Les helpers `_canvas_depuis_bg_ou_blanc` et `_coller_overlay` acceptent déjà un
chemin en paramètre. Seul `_composer` fige les chemins actifs et la mise en
page publiée sur disque.

```python
@classmethod
def _composer(
    cls,
    chemin_photo,                    # ou `photos: list` côté strip
    taille_sortie=None,
    resampling=Image.Resampling.LANCZOS,
    bg_path=None,                    # NOUVEAU — défaut : BG_10X15_FILE / BG_STRIPS_FILE
    overlay_path=None,               # NOUVEAU — défaut : OVERLAY_10X15 / OVERLAY_STRIPS
    mise_en_page=None,               # NOUVEAU — défaut : cls._mise_en_page_active()
) -> Image.Image: ...

@classmethod
def composer_apercu(
    cls, photos, *, bg_path, overlay_path, mise_en_page,
) -> Image.Image:
    """Rendu final en mémoire : compose + filigrane + grain, sans écriture disque."""
```

`composer_apercu` applique `_appliquer_watermark` puis `_appliquer_grain` comme
`final()`, et **retourne l'image** au lieu de l'écrire. Ces deux traitements
sont déjà pilotés par `WATERMARK_ENABLED` / `GRAIN_ENABLED` : l'aperçu hérite
donc automatiquement des réglages en vigueur.

Troisième changement : `_charger_asset_transforme` gagne `utiliser_cache=True`,
et l'aperçu passe `False`. Le cache de classe `_transformed_asset_cache` n'a
pas d'éviction ; il est borné côté kiosque parce que seuls quatre chemins fixes
y entrent, mais l'aperçu y ajouterait une entrée par template essayé, à ~8 Mo
l'asset 1800×1200 RGBA, dans un service plafonné à `MemoryMax=256M`.

Chemins de sortie attendus, pour mémoire : `MONTAGE_10X15_SIZE = (1800, 1200)`,
`MONTAGE_STRIP_SIZE = (600, 1800)`.

### `web/routes/apercu_route.py` — nouveau module

Un module séparé plutôt qu'un ajout à `templates_route.py`, qui fait déjà
~900 lignes et porte sept responsabilités (liste, upload, activation,
affectation événement, vignettes, édition de mise en page, photo d'exemple).

Blueprint `apercu`, `url_prefix="/templates/apercu"`. Pas de collision avec le
blueprint `templates` : `apercu` est un segment statique, les règles existantes
sont `/templates/activer/<int:id>`, `/templates/editer/<int:id>`, etc.

| Route | Méthode | Rôle |
|---|---|---|
| `/templates/apercu` | GET | Formulaire + zone d'aperçu |
| `/templates/apercu/rendu` | GET | Renvoie l'image JPEG rendue |

`rendu` prend quatre paramètres de requête :

- `format` : `10x15` ou `strip` (autre valeur → 400) ;
- `fond` et `overlay` : un `id` de template, ou `aucun` (absent → le template
  actuellement actif pour cette couche et ce format) ;
- `session` : un `id_session` présent dans `data/raw/`.

Il répond un `image/jpeg` servi depuis un `BytesIO`, en `Cache-Control: no-store`.
La page pointe simplement son `<img>` dessus. Un peu de JS rafraîchit le `src`
quand un sélecteur change ; le formulaire en GET reste fonctionnel sans JS.

### Sélection des photos

Les photos brutes sont nommées `photo_<id_session>_<index>.jpg` avec
`id_session` au format `2026-08-20_14h32_07`. Le regroupement par session
réutilise `_SESSION_ID_RE` / `_extraire_session_id`, aujourd'hui privés de
`web/routes/gallery.py`. Ils sont déplacés dans un nouveau module
`web/photos_raw.py` (lecture et regroupement des photos brutes), que `gallery`
et `apercu` importent tous les deux — plutôt qu'un import entre blueprints ou
une recopie de la regex.

- Format 10×15 → une photo.
- Format strip → une session comptant trois photos.
- Défaut : la session valide la plus récente pour le format choisi.

### Mise en page

L'aperçu applique la règle déjà en vigueur dans
`_synchroniser_mise_en_page_active()` : la mise en page du template **overlay**
choisi, sinon celle du **fond** choisi, sinon le défaut de `config.py`. Les
valeurs viennent de la DB (`photo_x/y/largeur/hauteur` en 10×15, `zones_strip`
en JSON pour le strip), pas des fichiers publiés sur disque — c'est ce qui
permet de prévisualiser un template non activé.

## Garde-fous

- `@require_auth`, pas `require_lecture` : un rendu coûte du CPU, ce n'est pas
  ouvert aux viewers anonymes du wifi.
- Refus si une session kiosque est active (`etat_verrou_session()`), avec le
  message existant invitant à attendre le retour à l'accueil. Le service admin
  est déjà `Nice=10 / CPUWeight=20`, mais un rendu 1800×1200 pendant une
  capture n'a rien à y faire.
- **Aucune écriture disque** : ni dans `data/temp/`, ni dans `data/print/`.
  Écarte tout risque qu'un fichier d'aperçu soit ramassé par le pipeline
  d'impression.
- Aucune photo brute disponible : le rendu est produit quand même, à partir du
  visuel neutre déjà généré par `/templates/photo-exemple` (répété trois fois
  pour le strip), et la page affiche un message disant que l'aperçu utilise une
  image de substitution.
- Fond ou overlay à « Aucun » : rendu quand même — le moteur gère nativement
  l'absence (fond → toile blanche, overlay → photo nue).

## Tests

`tests/test_web_apercu.py` (nouveau) :

- rendu 10×15 → 200, `image/jpeg`, dimensions `MONTAGE_10X15_SIZE` ;
- rendu strip → dimensions `MONTAGE_STRIP_SIZE` ;
- template inexistant → 404 ; `format` inconnu → 400 ;
- fond et/ou overlay à « Aucun » → rendu valide ;
- session strip ne comptant pas trois photos → refus explicite ;
- session kiosque active → redirection avec message d'erreur ;
- non authentifié → 401 ;
- aucune photo dans `data/raw/` → message, pas d'erreur 500.

`tests/test_montage.py` (complété) :

- **non-régression** : `_composer` appelé sans les nouveaux paramètres produit
  le même résultat qu'avant sur les deux formats ;
- `composer_apercu` avec un `bg_path` / `overlay_path` explicites n'ouvre
  jamais les chemins actifs ;
- `utiliser_cache=False` n'ajoute pas d'entrée à `_transformed_asset_cache`.

`tests/test_web_gallery.py` (inchangé) : doit continuer à passer tel quel après
l'extraction de `web/photos_raw.py`. Toute modification nécessaire de ce fichier
signale que l'extraction a changé un comportement, ce qu'elle ne doit pas faire.

Isolation habituelle : `tmp_path` + `monkeypatch.setattr` sur les chemins, rien
n'est écrit dans le vrai `data/`.

## Documentation à mettre à jour

- `docs/ADMIN.md` : nouvelle section « Aperçu du rendu final ».
- `docs/CHANGELOG.md` : entrée de sprint.
- `docs/ROADMAP.md` : l'entrée P2 « impression de test depuis l'éditeur avec un
  rendu strictement identique à celui du kiosque » (ligne ~387) devient
  partiellement couverte — l'aperçu écran est fait, l'impression de test reste
  ouverte.
- `config.py` n'est pas touché, donc `docs/CONFIG.md` reste inchangé.
- `docs/ARCHITECTURE.md` : inchangé, aucune règle d'import n'est modifiée
  (`web/` importe `core/`, ce qui est déjà autorisé).

## Hors périmètre

Explicitement exclus de ce lot, ajoutables ensuite sans rien casser :

- déclenchement du Canon depuis l'admin (le kiosque garde la caméra ouverte via
  gphoto2 ; il faudrait arrêter le kiosque ou ajouter un échange par fichier) ;
- upload d'une photo de test, ou capture par la webcam du navigateur ;
- aperçu de la planche `READY_TO_PRINT` ;
- bouton « imprimer ce test » depuis l'aperçu ;
- remplacement de l'aperçu CSS de l'éditeur de mise en page, qui reste en place
  pour le calage interactif.
