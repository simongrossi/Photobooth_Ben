#!/usr/bin/env python3
"""profile.py — lance Photobooth_start sous cProfile pendant N secondes.

Usage :
    python3 profile.py [secondes]  # défaut 60s

Produit `profile.stats` (format Python) + affiche le top 30 des fonctions
les plus coûteuses à la fin. Ouvrable ensuite avec :
    python3 -m pstats profile.stats
    > sort cumulative
    > stats 30

À lancer sur le matériel cible (Raspberry) pour identifier les bottlenecks
réels (get_canon_frame ? génération montage ? slideshow render ? etc).

Le script termine le photobooth après `secondes` via SIGALRM — prévoir
d'interagir manuellement pendant ce temps pour couvrir les états (accueil,
décompte, validation, fin).
"""
import cProfile
import pstats
import signal
import sys


def _signal_handler(signum, frame):
    raise SystemExit("⏱️ Timeout profil : arrêt propre")


def main():
    duree = int(sys.argv[1]) if len(sys.argv) > 1 else 60
    print(f"🔬 Profile : lancement du photobooth pour {duree}s...")
    print("   (interagis avec l'UI pour couvrir les états — le script s'arrête auto)\n")

    # SIGALRM envoyé après `duree` secondes → SystemExit propre
    signal.signal(signal.SIGALRM, _signal_handler)
    signal.alarm(duree)

    profiler = cProfile.Profile()
    profiler.enable()
    try:
        # On importe Photobooth_start qui démarre immédiatement (boucle while running)
        import Photobooth_start  # noqa: F401
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
