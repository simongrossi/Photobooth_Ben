#!/usr/bin/env python3
"""Profile CPU du photobooth pendant une durée déterminée.

Usage :
    python3 profile_app.py [secondes]  # défaut 60 s

Le nom évite volontairement ``profile.py`` : un fichier portant ce nom masque
le module standard utilisé par :mod:`cProfile` lorsque le script est lancé
depuis la racine du dépôt.
"""
from __future__ import annotations

import cProfile
import pstats
import signal
import sys


def _signal_handler(signum, frame):
    raise SystemExit("⏱️ Timeout profil : arrêt propre")


def _executer_application() -> None:
    """Importe le module sans effet de bord puis appelle son point d'entrée."""
    import Photobooth_start

    Photobooth_start.main()


def main() -> None:
    duree = int(sys.argv[1]) if len(sys.argv) > 1 else 60
    print(f"🔬 Profile : lancement du photobooth pour {duree}s...")
    print("   (interagis avec l'UI pour couvrir les états — le script s'arrête auto)\n")

    signal.signal(signal.SIGALRM, _signal_handler)
    signal.alarm(duree)

    profiler = cProfile.Profile()
    profiler.enable()
    try:
        _executer_application()
    except SystemExit:
        pass
    finally:
        profiler.disable()
        signal.alarm(0)

    profiler.dump_stats("profile.stats")

    print("\n" + "=" * 60)
    print("📊 TOP 30 des fonctions par temps CUMULATIF (incl. appelés)")
    print("=" * 60)
    stats = pstats.Stats(profiler).sort_stats("cumulative")
    stats.print_stats(30)

    print("\n" + "=" * 60)
    print("📊 TOP 30 par temps TOTAL (interne à la fonction)")
    print("=" * 60)
    stats.sort_stats("tottime").print_stats(30)

    print("\n💾 Fichier brut sauvegardé : profile.stats")
    print("   Ouvre avec : python3 -m pstats profile.stats")
    print("   Puis : sort cumulative  /  stats 30")


if __name__ == "__main__":
    main()
