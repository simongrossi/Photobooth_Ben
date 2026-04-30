# Profiling sur Raspberry Pi

Protocole à suivre pour mesurer les perfs de l'app sur la cible réelle avant
toute nouvelle optim. Les gains supposés sur un desktop x86 ne sont pas
représentatifs du Pi (CPU ARM, GPU VideoCore, framebuffer, thermique).

## But

- Identifier les vrais bottlenecks CPU / mémoire en conditions d'événement.
- Valider qu'une optim livrée réduit bien le coût cible (pas juste sur macOS).
- Détecter les fuites mémoire qui ne se voient qu'en enchaînant plusieurs
  sessions (≥ 3).

## Baselines attendues

| Métrique | Seuil OK | Rouge |
|---|---|---|
| FPS boucle principale (ACCUEIL repos) | ≥ 55 | < 40 |
| FPS boucle principale (DECOMPTE + liveview) | ≥ 25 | < 15 |
| ms/frame p95 spinner (`ecran_attente_impression`) | ≤ 35 | > 60 |
| RAM résidente après 5 sessions | stable ±20 Mo | croissance linéaire |
| Température CPU soutenue | < 75 °C | ≥ 80 °C (throttle) |

## Outils

Trois scripts, exécutables directement sur le Pi :

- `profile.py` — cProfile sur toute la boucle (fonctions chaudes).
- `profile_mem.py` — tracemalloc (top allocs + top croissances).
- `bench_spinner.py` — microbench isolé du `LoaderAnimation`.

Optionnel sur le poste de dev : `pip install snakeviz` pour visualiser
`profile.stats` en graphe.

## 1. cProfile — fonctions chaudes

Sur le Pi, arrêter le service kiosque s'il tourne, puis :

```bash
cd ~/Photobooth_Ben
python3 profile.py 120
```

Scénario d'interaction pendant les 120 s (chronométrer grossièrement) :

1. 0–10 s : laisser ACCUEIL (slideshow possible)
2. 10–40 s : session **strips** complète (3 photos + FIN + impression)
3. 40–70 s : session **10×15** complète
4. 70–120 s : rester sur ACCUEIL

Le fichier `profile.stats` est produit à la racine. Rapatrier :

```bash
scp pi@photobooth:~/Photobooth_Ben/profile.stats .
python3 -m pstats profile.stats
> sort cumulative
> stats 30
> sort tottime
> stats 30
```

Zones à surveiller :

- `LoaderAnimation.update_and_draw` — doit avoir quitté le top 10 cumulatif
  depuis le pré-rendu des sprites.
- `render_decompte` — doit être proportionnel au temps passé dans cet état,
  pas à un multiplicateur caché (le cache masque limite les allocs).
- `get_canon_frame` / `pygame.transform.scale` — dominés par l'USB + le
  rescale ; baisser la résolution liveview si nécessaire.

## 2. tracemalloc — fuites mémoire

```bash
python3 profile_mem.py 300
```

Enchaîner **au moins 3 sessions complètes** pendant les 5 min. Les fuites
en boucle 30 FPS n'apparaissent dans le diff qu'avec du volume.

Lire d'abord la section **« TOP 30 des CROISSANCES »**. Seuil de suspicion :
> 100 KB de croissance sans contre-partie identifiée, surtout si la fonction
est dans `ui/` ou `core/montage.py`.

Piège historique : `PIL.Image` non fermé ou `pygame.Surface` recréée à
chaque frame. Si ça réapparaît, chercher un `with Image.open(...)` manquant
ou un `get_pygame_surf()` hors cache.

## 3. Microbench spinner

À utiliser pour isoler un changement ciblé sur la roue sans relancer tout
le kiosque :

```bash
python3 bench_spinner.py --duree 10                  # config actuelle
python3 bench_spinner.py --duree 10 --points 300     # config avant optim
python3 bench_spinner.py --duree 10 --points 120     # config par défaut
```

Comparer **FPS moyen** et **ms/frame p95**. Exemple de tableau à consigner
dans le commit ou dans `docs/CHANGELOG.md` :

| `--points` | FPS moyen | p50 (ms) | p95 (ms) |
|---|---|---|---|
| 300 | … | … | … |
| 120 | … | … | … |

En SDL dummy (sans display) le blit est quasi gratuit → exécuter dans le
kiosk framebuffer pour un chiffre réaliste.

## 4. Checklist post-optim

Après avoir livré une optim, revalider sur Pi :

- [ ] `bench_spinner.py` : FPS moyen ≥ celui d'avant, p95 ≤ celui d'avant.
- [ ] `profile.py 120` + scénario : pas de nouvelle fonction au top 10.
- [ ] `profile_mem.py 300` + 3 sessions : pas de croissance > 500 KB sur une
      ligne inconnue.
- [ ] `stats.py` : session `issue=printed` sans erreur (pas de régression
      fonctionnelle côté imprimante).
- [ ] Thermique : `vcgencmd measure_temp` au repos et après 5 sessions —
      pas d'emballement (< 75 °C soutenu).

## Liens

- [profile.py](../profile.py) · [profile_mem.py](../profile_mem.py) · [bench_spinner.py](../bench_spinner.py)
- Contexte macro : [ARCHITECTURE.md](ARCHITECTURE.md)
- Journal des perfs : [CHANGELOG.md](CHANGELOG.md)
