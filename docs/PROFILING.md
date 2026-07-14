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
| FPS boucle principale (ACCUEIL repos, cap 30) | ≥ 29 | < 25 |
| Nouvelles frames caméra (DECOMPTE) | ≥ 12 FPS | < 8 FPS |
| ms/frame p95 spinner (`ecran_attente_impression`) | ≤ 35 | > 60 |
| RAM résidente après 5 sessions | stable ±20 Mo | croissance linéaire |
| Température CPU soutenue | < 75 °C | ≥ 80 °C (throttle) |

## Télémétrie continue, sans profilage intrusif

Le kiosque écrit `logs/performance.jsonl` (rotation 2 Mo × 5). Les mesures de
chaque frame du décompte et du LiveView restent dans des buffers mémoire bornés ;
elles sont résumées en p50/p95 avant une écriture unique à la fin de la capture.
Les autres écritures ont uniquement lieu aux transitions : début/fin de session,
aperçu, montage et soumission d'impression. Il n'y a donc aucune écriture disque
à 30 FPS.

Sur la machine de développement, le résumé de 150 frames coûte environ 8 µs et
une ligne JSONL environ 0,06 ms en moyenne. Ces chiffres ne préjugent pas du coût
de la carte SD du Pi, mais les écritures étant très rares, elles ne se trouvent
pas sur le chemin critique du rendu.

Après un événement ou une série de tests :

```bash
python3 perf_report.py
python3 perf_report.py --date 2026-07-15
python3 perf_report.py --date 2026-07-15 --json > perf-2026-07-15.json
```

Le rapport regroupe p50/p95/max par mode et signale notamment : première frame
> 500 ms, preview < 12 FPS, rendu décompte > 25 ms, capture > 5 s, montage
> 3 s, température ≥ 75 °C ou croissance RSS > 20 Mo sur cinq captures.

## Outils

Trois scripts, exécutables directement sur le Pi :

- `profile_app.py` — cProfile sur toute la boucle (fonctions chaudes).
- `profile_mem.py` — tracemalloc (top allocs + top croissances) et RSS du
  processus chaque seconde, afin d'inclure les buffers natifs PIL/OpenCV.
- `bench_spinner.py` — microbench isolé du `LoaderAnimation`.

Optionnel sur le poste de dev : `pip install snakeviz` pour visualiser
`profile.stats` en graphe.

## 1. cProfile — fonctions chaudes

Sur le Pi, arrêter le service kiosque s'il tourne, puis :

```bash
cd ~/Photobooth_Ben
python3 profile_app.py 120
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
- `CameraManager._preview_loop` / `pygame.transform.scale` — le premier est
  dominé par l'USB+décodage ; le second ne doit apparaître qu'une fois par
  nouvelle génération de frame.
- lignes `[PERF] preview_validation` et `[PERF] montage_final` dans le log —
  comparer les modes 10×15/strip et les premières générations après changement
  de template.

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
- [ ] `profile_app.py 120` + scénario : pas de nouvelle fonction au top 10.
- [ ] `profile_mem.py 300` + 3 sessions : pas de croissance > 500 KB sur une
      ligne inconnue.
- [ ] `stats.py` : session `issue=printed` sans erreur (pas de régression
      fonctionnelle côté imprimante).
- [ ] `perf_report.py --date …` : archiver le JSON et comparer les p95 au
      relevé précédent, par mode.
- [ ] Thermique : `vcgencmd measure_temp` au repos et après 5 sessions —
      pas d'emballement (< 75 °C soutenu).

## Liens

- [profile_app.py](../profile_app.py) · [profile_mem.py](../profile_mem.py) · [bench_spinner.py](../bench_spinner.py) · [perf_report.py](../perf_report.py)
- Contexte macro : [ARCHITECTURE.md](ARCHITECTURE.md)
- Journal des perfs : [CHANGELOG.md](CHANGELOG.md)
