# Design — Bibliothèque templates deux couches + état « Aucun »

**Date** : 2026-07-14 · **Statut** : validé (Simon) · **Issue liée** : besoin exprimé hors issue
(cas d'usage : lendemain de mariage, faire une photo sans l'habillage de l'événement).

## Problème

La page Templates de l'admin web ne gère que les **overlays** (PNG par-dessus la photo).
Or un habillage complet = 2 couches par format : l'**overlay** et le **fond**
(`assets/backgrounds/*.jpg`, sous les photos). Il manque :

1. La gestion des **fonds** dans la bibliothèque (upload, activation par format).
2. Un état **« Aucun »** par couche×format : retirer l'overlay (photo nue) et/ou le fond
   (toile blanche), sans SSH, à chaud.

Le moteur (`core/montage.py`) gère déjà nativement l'absence des deux couches :
fond absent → `Image.new("RGB", size, "white")` ; overlay absent → étape sautée.
Aucun changement kiosque n'est nécessaire.

## Décisions de cadrage (validées)

- Deux contrôles **séparés** (désactiver l'overlay / désactiver le fond), pas un bouton unique.
- **Bibliothèque complète** pour les fonds, symétrique aux overlays (pas un simple on/off).
- Approche retenue : **généraliser le système existant** (une table, une page), pas de
  duplication de route ni de solution sans DB.

## Modèle de données

Table `template` (SQLite `data/admin.db`) : ajout d'une colonne
`couche TEXT NOT NULL DEFAULT 'overlay'` (valeurs : `'overlay'` | `'fond'`).

- **Migration idempotente** dans `init_db()` : si `couche` absente de
  `PRAGMA table_info(template)` → `ALTER TABLE template ADD COLUMN ...`.
  Les lignes existantes deviennent des overlays (défaut). Les bases neuves
  incluent la colonne directement dans le `CREATE TABLE`.
- Invariant : **au plus un** `actif=1` par couple (couche, type).
- Nouvel index `idx_template_couche_type_actif` sur (couche, type, actif) ; l'ancien
  `idx_template_type_actif` est conservé (inoffensif, volumes minuscules).

## Stockage fichiers

| Couche | Bibliothèque | Cible active (lue par le kiosque) |
|---|---|---|
| overlay 10x15 | `assets/overlays/10x15__<nom>.png` | `assets/overlays/10x15_overlay.png` (`OVERLAY_10X15`) |
| overlay strip | `assets/overlays/strip__<nom>.png` | `assets/overlays/strips_overlay.png` (`OVERLAY_STRIPS`) |
| fond 10x15 | `assets/backgrounds/10x15__<nom>.<ext>` | `assets/backgrounds/10x15_background.jpg` (`BG_10X15_FILE`) |
| fond strip | `assets/backgrounds/strip__<nom>.<ext>` | `assets/backgrounds/strips_background.jpg` (`BG_STRIPS_FILE`) |

- L'activation reste une **copie** bibliothèque → cible fixe ; le kiosque relit le fichier
  à chaque montage → effet **à chaud**, aucun redémarrage.
- Un PNG copié vers une cible `.jpg` fonctionne : PIL identifie le format au contenu.
- La protection anti-traversée (`realpath` contraint à la racine) s'applique aux deux dossiers.

## Routes (web/routes/templates_route.py)

- `POST /templates/upload` : champ `couche` ajouté au formulaire.
  Validation : overlay → `.png` uniquement (transparence requise) ; fond → `.png/.jpg/.jpeg`.
  Toujours : validation PIL (`Image.verify`), nettoyage du nom, préfixe `<type>__`.
- `POST /templates/activer/<id>` : inchangé dans l'esprit ; la cible active est résolue
  par (couche, type) ; reset `actif` limité au couple (couche, type).
- **Nouveau** `POST /templates/desactiver/<couche>/<type>` : supprime le fichier cible actif
  (`FileNotFoundError` ignoré) + `UPDATE template SET actif=0` pour le couple.
  Couche/type validés contre les listes autorisées (sinon 400/404).
- `POST /templates/supprimer/<id>`, `GET /templates/thumb/<id>` : inchangés
  (le chemin est résolu selon la couche pour thumb/suppression).

## Interface (web/templates/templates.html)

- Deux sections : **Overlays** et **Fonds**, chacune découpée par format (10×15 / bandelette),
  avec la même carte template (miniature, nom, taille, date, bouton Activer/Supprimer).
- Par couche×format : indicateur d'état (« Actif : <nom> » ou « Aucun ») + bouton
  **« Aucun (désactiver) »** avec `confirm()` natif du navigateur.
- Formulaire d'upload : select `couche` en plus du select `type` ; textes d'aide sur
  les dimensions attendues (1800×1200 pour 10×15, 600×1800 pour strip).

## Gestion d'erreurs

- Désactivation d'une couche déjà « Aucune » : no-op silencieux + flash info.
- Fichier bibliothèque manquant à l'activation : flash erreur (comportement existant).
- Base ancienne sans colonne `couche` : migrée au premier démarrage du service admin.

## Tests (test_web_templates.py, CI pure)

- Migration : DB créée avec l'ancien schéma → `init_db()` ajoute `couche`,
  lignes existantes = `overlay`.
- Upload fond (jpg et png) → fichier dans `assets/backgrounds/` (monkeypatché `tmp_path`).
- Activation d'un fond → copie vers la cible `BG_*` ; `actif` exclusif par (couche, type).
- Désactivation → fichier cible supprimé + plus aucun `actif` ; idempotente si déjà aucun.
- Rejet : extension invalide par couche, couche/type inconnus, traversée de chemin.

## Docs à mettre à jour

- `docs/ADMIN.md` : page Templates (deux couches), tableau « source de vérité »
  (ajouter les fonds), captures/description.

## Déploiement

- Feature branch depuis `main`, PR vers `main` (convention repo, historique bisectable).
- Sur la machine de l'événement : `git pull` + `sudo systemctl restart photobooth-admin`.
  Le kiosque n'est pas concerné. Le clone y est actuellement sur `config_impression`
  (travail de Benjamin) : la récupération se fera par merge de `main`, sans toucher sa branche.
- **Prérequis d'usage** : uploader l'habillage mariage dans la bibliothèque avant la première
  désactivation (le fichier actif est aujourd'hui l'unique copie kiosque ; sauvegarde faite
  dans `~/sauvegarde_templates/` le 2026-07-13).

## Hors périmètre

- Preview du rendu final composé (fond + photos + overlay).
- Gestion des `STRIP_PROFILES` / géométrie.
- Sortir les fichiers actifs du suivi git (amélioration future notée).
