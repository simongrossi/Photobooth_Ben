#!/usr/bin/env python3
"""profile_mem.py — profile mémoire du photobooth via tracemalloc.

Usage :
    python3 profile_mem.py [secondes]   # défaut 60s

Prend un snapshot initial, lance le photobooth N secondes, prend un snapshot
final, affiche le top 30 des allocations par taille + le top 30 des
DIFFÉRENCES (où la mémoire grandit le plus — révèle les fuites).

Le script termine le photobooth après `secondes` via SIGALRM. Prévois
d'interagir manuellement pour couvrir les états (accueil, décompte, FIN,
impression) — les fuites en boucle 30 FPS n'apparaissent que si tu laisses
tourner plusieurs sessions.

À lancer sur le matériel cible. Les bottlenecks mémoire historiques
(PIL Image non fermé, pygame.Surface réallouées, etc.) ressortent
typiquement dans le diff.
"""
import signal
import sys
import tracemalloc


def _signal_handler(signum, frame):
    raise SystemExit("⏱️ Timeout profil mémoire : arrêt propre")


def main():
    duree = int(sys.argv[1]) if len(sys.argv) > 1 else 60
    print(f"🧠 Profile mémoire : lancement pour {duree}s...")
    print("   (interagis avec l'UI — pour révéler les fuites, enchaîne plusieurs sessions)\n")

    tracemalloc.start(25)  # 25 = profondeur du traceback capturé
    snapshot_debut = tracemalloc.take_snapshot()

    signal.signal(signal.SIGALRM, _signal_handler)
    signal.alarm(duree)

    try:
        import Photobooth_start  # noqa: F401
    except SystemExit:
        pass
    finally:
        signal.alarm(0)

    snapshot_fin = tracemalloc.take_snapshot()
    tracemalloc.stop()

    # --- Top des allocations totales ---
    print("\n" + "=" * 60)
    print("📊 TOP 30 des ALLOCATIONS À LA FIN (par taille cumulée)")
    print("=" * 60)
    stats_lineno = snapshot_fin.statistics("lineno")
    for i, stat in enumerate(stats_lineno[:30], 1):
        print(f"#{i:2d}  {stat.size / 1024:8.1f} KB  ({stat.count:5d} blocs)  {stat}")

    # --- Top des DIFFÉRENCES (les fuites) ---
    print("\n" + "=" * 60)
    print("📊 TOP 30 des CROISSANCES (début → fin) — révèle les fuites")
    print("=" * 60)
    diff = snapshot_fin.compare_to(snapshot_debut, "lineno")
    for i, stat in enumerate(diff[:30], 1):
        if stat.size_diff <= 0:
            continue
        print(f"#{i:2d}  +{stat.size_diff / 1024:8.1f} KB  ({stat.count_diff:+5d} blocs)  {stat}")

    # --- Total ---
    total_fin = sum(s.size for s in stats_lineno) / (1024 ** 2)
    print(f"\n💾 Mémoire totale allouée à la fin : {total_fin:.1f} Mo")


if __name__ == "__main__":
    main()
