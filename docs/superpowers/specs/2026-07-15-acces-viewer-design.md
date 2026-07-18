# Design — Mode consultation sans mot de passe (viewer) + admin

**Date** : 2026-07-15 · **Statut** : validé (Simon) · **Approche retenue** : A (deux rôles, une seule app).

## Objectif

Deux niveaux d'accès à l'admin web :
- **admin** (Basic Auth, inchangé) : tout, y compris chaque action.
- **viewer** (aucun mot de passe) : consultation seule — dashboard et galerie —
  pour suivre l'événement depuis n'importe quel appareil du LAN (Benjamin,
  invités sur le wifi : **choix assumé**, les photos sont visibles).

## Décisions validées

- Le viewer voit : **dashboard en lecture seule** (stats du jour, événement en
  cours, santé matériel — sans les chemins système) et **galerie** (photos +
  miniatures — sans bouton « Retirer » ni section Corbeille).
- Le viewer ne voit pas : Templates, Kiosque, Réglages, corbeille, et ne peut
  déclencher **aucun POST**.
- **Interrupteur** `PHOTOBOOTH_ACCES_LIBRE` (env, défaut `1`) : à `0`, le mode
  viewer est coupé (tout exige l'admin — comportement historique) pour les
  événements privés.
- **Fail-closed conservé** : sans `PHOTOBOOTH_ADMIN_PASS`, 503 partout, viewer
  compris.
- Basic Auth conservé pour l'admin (pas de système de sessions) ; la
  « déconnexion » admin = fermer l'onglet/navigateur (limite documentée).

## Architecture (`web/auth.py` étendu, pattern décorateur conservé)

```python
def role_courant() -> str | None:
    """'admin' si Basic Auth valide, 'viewer' si anonyme autorisé, None sinon."""

def require_auth(f):      # inchangé : admin uniquement (toutes les actions)

def require_lecture(f):   # NOUVEAU : admin OU viewer (si PHOTOBOOTH_ACCES_LIBRE != "0")
```

- `require_lecture` : si Basic Auth valide → passe (role admin) ; sinon si
  accès libre activé → passe (role viewer) ; sinon → 401 (challenge Basic).
  Toujours 503 si `PHOTOBOOTH_ADMIN_PASS` absent.
- Un **context processor** Flask injecte `role` dans tous les gabarits
  (`create_app`), pour le masquage conditionnel.

## Application par route

| Routes | Décorateur |
|---|---|
| `GET /dashboard/`, `GET /dashboard/heure-serveur` (si présente) | `require_lecture` |
| `GET /galerie/`, `GET /galerie/image/...`, `GET /galerie/thumb/...` | `require_lecture` |
| `POST /galerie/retirer|restaurer`, pages Templates / Kiosque / Réglages / éditeurs, tous les POST | `require_auth` (inchangé) |

## Gabarits

- `base.html` : nav filtrée — viewer ne voit que Dashboard et Galerie + bouton
  « Connexion admin » (lien vers une route `GET /connexion` sous `require_auth`
  qui redirige vers le dashboard : déclenche le challenge du navigateur).
- `dashboard.html` : bloc chemins système (`Journal : …`) sous `{% if role == 'admin' %}`.
- `gallery.html` : bouton « Retirer » et section Corbeille sous `{% if role == 'admin' %}`.

## Gestion d'erreurs

- Mauvais mot de passe sur une route `require_lecture` : on **repasse en
  viewer** silencieusement ? Non — 401 explicite (l'utilisateur voulait se
  connecter ; l'anonyme total reste viewer).
- `PHOTOBOOTH_ACCES_LIBRE` non défini → traité comme `1` (activé).

## Tests (CI pure, `tests/test_web_app.py` + nouveaux cas)

- Sans auth : `GET /dashboard/` et `GET /galerie/` → 200 ; le HTML ne contient
  ni « Retirer », ni « Corbeille », ni « Réglages », ni chemins système.
- Sans auth : `POST /galerie/retirer/...`, `GET /templates/`, `GET /kiosque/`,
  `GET /settings/` (préfixe réel à vérifier) → 401.
- Avec `PHOTOBOOTH_ACCES_LIBRE=0` : `GET /dashboard/` sans auth → 401.
- Sans `PHOTOBOOTH_ADMIN_PASS` : 503 partout (inchangé).
- Admin : comportements existants inchangés (non-régression suite complète).
- Mauvais mot de passe sur route lecture → 401.

## Docs

- `docs/ADMIN.md` : les deux niveaux d'accès, l'interrupteur, la mise en garde
  vie privée (galerie visible par le wifi), la limite de déconnexion Basic Auth.
- `deploy/install-admin.sh` : ajouter `PHOTOBOOTH_ACCES_LIBRE=1` commenté dans
  le fichier env généré (documentation à l'endroit où on le règle).

## Hors périmètre

- Vrai système de sessions/comptes multiples, HTTPS, logout propre.
- Page publique dédiée type « mur de photos » (pourra venir plus tard).
