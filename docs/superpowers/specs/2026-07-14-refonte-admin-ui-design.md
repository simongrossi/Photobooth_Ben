# Design — Refonte UI de l'admin web (volet 1/3)

**Date** : 2026-07-14 · **Statut** : validé (Simon, maquette navigateur validée) ·
**Maquettes** : `.superpowers/brainstorm/95415-1784020528/content/` (direction C + dashboard 4 étages).

## Contexte et découpage

Demande : « lisibilité des stats, interface moderne, gestion des images de fonds,
des polices ». Découpé en 3 volets validés :

1. **Refonte UI de l'admin** ← ce document
2. Assets kiosque dans l'admin (fond d'accueil, police .ttf, slideshow) — spec séparée
3. Contrôle kiosque à distance (migration systemd + bouton redémarrage) — spec séparée

## Décisions validées

- **Thème automatique jour/nuit** (option C de la maquette) : suit
  `prefers-color-scheme`, sans toggle manuel (YAGNI).
- **Dashboard 4 étages** (maquette validée) :
  1. bandeau santé matériel (pastilles imprimantes 10×15/strip, disque, CPU),
  2. « Aujourd'hui » : gros compteur de sessions du jour + répartition
     imprimées/abandons/échecs + histogramme horaire **du jour**,
  3. grille KPI des totaux (sessions, taux imprimées %, photos, durée moyenne,
     compteurs par mode),
  4. historique par journée (tableau : date, sessions, imprimées, barre
     proportionnelle) — prépare la future feature « Événements ».
- **Restyle global** : Galerie, Templates, Réglages héritent du nouveau thème
  (mêmes classes, feuille refondue) sans refonte structurelle de ces pages.
- **Contrainte hors-ligne** : le booth tourne souvent sans Internet en événement →
  **zéro CDN, zéro framework, zéro webfont externe**. CSS maison à base de
  custom properties. Police système (`-apple-system, system-ui, sans-serif`).

## Architecture

```
web/static/admin.css        ← refonte complète : variables :root + @media (prefers-color-scheme: dark)
web/templates/base.html     ← nav restylée (inchangée structurellement)
web/templates/dashboard.html← restructuré en 4 étages
web/routes/dashboard.py     ← collecte : stats jour + historique + état imprimantes
stats.py                    ← nouvelles fonctions pures : stats_du_jour(), stats_par_jour()
core/printer.py             ← réutilisé tel quel (is_ready par mode)
```

- `stats.py` reste le module **pur et testé** de calcul : on y ajoute
  `stats_du_jour(sessions, date_str)` (compteurs + histogramme horaire du jour)
  et `stats_par_jour(sessions)` (liste ordonnée desc. : date, total, printed).
  Le champ source est `ts` des lignes `sessions.jsonl` (format `YYYY-MM-DD HH:MM:SS`).
- `dashboard.py` appelle `PrinterManager(NOM_IMPRIMANTE_10X15, NOM_IMPRIMANTE_STRIP).is_ready(mode)`
  pour les deux modes. `is_ready` renvoie `True` ou une chaîne d'erreur (contrat
  existant) → la pastille affiche « prête » (vert) ou la chaîne (rouge).
  Timeout lpstat déjà à 2 s ; sur machine de dev sans CUPS → chaîne d'erreur
  affichée, pas de crash.
- Thème : toutes les couleurs passent par des custom properties définies dans
  `:root` (clair) et surchargées dans `@media (prefers-color-scheme: dark)`.
  Palette = celle de la maquette validée (clair `#f4f6fa`/cartes blanches/accent
  `#6366f1` ; sombre `#0f1218`/cartes `#181d26`/accent `#818cf8` ;
  ok/warn/err adaptés par thème).

## Données du dashboard (contrat de rendu)

| Étage | Variable gabarit | Source |
|---|---|---|
| Santé | `sante` : liste de `(libellé, ok: bool, détail: str)` | is_ready ×2, DiskMonitor, TempMonitor |
| Aujourd'hui | `jour` : `{date_affichee, total, printed, abandoned, capture_failed, heures}` | `stats_du_jour()` |
| KPI totaux | `stats` (existant) + `taux_imprimees` (calculé, % arrondi, `—` si 0 session) | `calculer_stats()` |
| Historique | `historique` : liste `{date, total, printed, pct_barre}` (14 derniers jours actifs max) | `stats_par_jour()` |

## Gestion d'erreurs

- `sessions.jsonl` absent/vide : dashboard s'affiche avec zéros et « Aucune
  session » (comportement actuel conservé).
- Lignes `ts` malformées : ignorées par les fonctions de stats (pas d'exception).
- CUPS absent (dev) : pastilles imprimantes rouges avec le message d'`is_ready`.
- `TempMonitor` sans sonde (dev/mac) : pastille « N/A » neutre (ni vert ni rouge).

## Tests (CI pure)

- `test_stats.py` : `stats_du_jour` (jour vide, jour actif, ts malformé,
  histogramme du jour uniquement), `stats_par_jour` (tri desc, agrégats, limite).
- `test_web_app.py` : le dashboard rend les 4 étages (présence des sections
  santé/aujourd'hui/historique), pastilles imprimante avec is_ready mocké
  (monkeypatch `PrinterManager.is_ready`), zéro session → pas d'exception.
- Pas de test CSS (visuel, hors CI).

## Docs à mettre à jour

- `docs/ADMIN.md` : description du dashboard (4 étages, thème auto).

## Hors périmètre (volets suivants ou plus tard)

- Fond d'accueil, polices kiosque, gestion slideshow (volet 2).
- Bouton redémarrage kiosque / systemd (volet 3).
- Notion d'« événement » nommé (feature Événements, cadrage séparé) — le tableau
  par journée n'introduit aucune table ni concept nouveau.
- Toggle manuel de thème, graphiques JS, auto-refresh du dashboard.
