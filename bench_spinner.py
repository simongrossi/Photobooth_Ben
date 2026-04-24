#!/usr/bin/env python3
"""bench_spinner.py — microbench autonome du LoaderAnimation.

Mesure le FPS réel et la latence par frame de la roue de chargement, sans
démarrer caméra / gphoto2 / machine d'état. Utile pour :

- Valider un gain CPU après tuning `ANIM_NB_POINTS` ou pré-rendu des sprites.
- Comparer deux configurations (ex. 300 vs 120 points) sur Raspberry Pi.

Usage :
    python3 bench_spinner.py                    # défaut : 10s, points config
    python3 bench_spinner.py --duree 5
    python3 bench_spinner.py --points 300       # override ANIM_NB_POINTS
    python3 bench_spinner.py --fps 60           # override cap pygame.clock.tick

En l'absence de display (CI, ssh sans X), passe en SDL dummy driver.
Noter qu'en SDL dummy le blit est quasi gratuit → pour un chiffre réaliste,
lancer avec un affichage réel (framebuffer Pi ou xserver X11).
"""
from __future__ import annotations

import argparse
import os
import statistics
import sys
import time


def _run(duree: float, fps_cap: int, points_override: int | None) -> None:
    if "DISPLAY" not in os.environ and "WAYLAND_DISPLAY" not in os.environ:
        os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
        print("ℹ️  Pas de DISPLAY détecté → SDL_VIDEODRIVER=dummy (blit sans GPU)")

    if points_override is not None:
        import config
        config.ANIM_NB_POINTS = points_override
        print(f"🔧 Override ANIM_NB_POINTS = {points_override}")

    import pygame
    from config import WIDTH, HEIGHT, ANIM_NB_POINTS, COULEUR_FOND_LOADER
    from ui.helpers import LoaderAnimation

    pygame.init()
    try:
        screen = pygame.display.set_mode((WIDTH, HEIGHT))
    except pygame.error as exc:
        print(f"⚠️  set_mode a échoué ({exc}) — tentative via dummy driver")
        os.environ["SDL_VIDEODRIVER"] = "dummy"
        pygame.display.quit()
        pygame.display.init()
        screen = pygame.display.set_mode((WIDTH, HEIGHT))

    clock = pygame.time.Clock()
    loader = LoaderAnimation()

    frame_durations_ms: list[float] = []
    t0 = time.perf_counter()
    t_end = t0 + duree
    frames = 0
    while time.perf_counter() < t_end:
        t_frame = time.perf_counter()
        screen.fill(COULEUR_FOND_LOADER)
        loader.update_and_draw(screen)
        pygame.display.flip()
        frame_durations_ms.append((time.perf_counter() - t_frame) * 1000.0)
        frames += 1
        clock.tick(fps_cap)

    elapsed = time.perf_counter() - t0
    fps_moyen = frames / elapsed if elapsed > 0 else 0.0

    # Percentiles ms/frame
    frame_durations_ms.sort()
    p50 = frame_durations_ms[len(frame_durations_ms) // 2]
    p95 = frame_durations_ms[int(len(frame_durations_ms) * 0.95)]
    p99 = frame_durations_ms[min(int(len(frame_durations_ms) * 0.99), len(frame_durations_ms) - 1)]
    moy = statistics.mean(frame_durations_ms)

    print("\n" + "=" * 60)
    print(f"📊 bench_spinner — {ANIM_NB_POINTS} points · cap {fps_cap} FPS · {duree:.1f}s")
    print("=" * 60)
    print(f"  Frames rendues     : {frames}")
    print(f"  Durée réelle       : {elapsed:.2f} s")
    print(f"  FPS moyen          : {fps_moyen:.1f}")
    print(f"  ms/frame moyenne   : {moy:.2f}")
    print(f"  ms/frame p50       : {p50:.2f}")
    print(f"  ms/frame p95       : {p95:.2f}")
    print(f"  ms/frame p99       : {p99:.2f}")
    print("=" * 60)

    pygame.quit()


def main() -> None:
    parser = argparse.ArgumentParser(description="Microbench LoaderAnimation")
    parser.add_argument("--duree", type=float, default=10.0, help="Durée du bench en secondes (défaut : 10)")
    parser.add_argument("--fps", type=int, default=60, help="Cap pygame.clock.tick (défaut : 60)")
    parser.add_argument("--points", type=int, default=None,
                        help="Override ANIM_NB_POINTS (ex. 300 pour comparer à l'ancien défaut)")
    args = parser.parse_args()

    if args.duree <= 0 or args.fps <= 0:
        print("❌ --duree et --fps doivent être > 0", file=sys.stderr)
        sys.exit(1)

    _run(args.duree, args.fps, args.points)


if __name__ == "__main__":
    main()
