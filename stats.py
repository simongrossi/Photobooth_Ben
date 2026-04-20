#!/usr/bin/env python3
"""stats.py — rapport fin de soirée.

Parse `data/sessions.jsonl` (produit par Sprint 5.4) et affiche :
  - Nombre total de sessions
  - Taux d'impression / abandon / capture échouée
  - Répartition par mode (10x15 vs strips)
  - Durée moyenne et max
  - Heure de pointe

Usage :
    python3 stats.py                  # toutes les sessions
    python3 stats.py --date 2026-04-20  # filtre par date
    python3 stats.py --json           # sortie JSON pour scripts

Exit code : 0 si le fichier existe, 1 sinon.
"""
import argparse
import json
import os
import sys
from collections import Counter

from config import PATH_DATA

_tty = sys.stdout.isatty()
BOLD = "\033[1m" if _tty else ""
GREEN = "\033[92m" if _tty else ""
YELLOW = "\033[93m" if _tty else ""
RED = "\033[91m" if _tty else ""
BLUE = "\033[94m" if _tty else ""
RESET = "\033[0m" if _tty else ""


def load_sessions(chemin):
    """Charge les sessions depuis un fichier JSONL. Lignes invalides ignorées."""
    if not os.path.exists(chemin):
        return None
    sessions = []
    with open(chemin, encoding="utf-8") as f:
        for ligne in f:
            ligne = ligne.strip()
            if not ligne:
                continue
            try:
                sessions.append(json.loads(ligne))
            except json.JSONDecodeError:
                continue  # on tolère les lignes corrompues
    return sessions


def filtrer_par_date(sessions, date_str):
    """Garde seulement les sessions dont le timestamp commence par date_str (YYYY-MM-DD)."""
    return [s for s in sessions if s.get("ts", "").startswith(date_str)]


def calculer_stats(sessions):
    """Calcule les stats agrégées. Retourne un dict prêt à afficher ou sérialiser."""
    total = len(sessions)
    if total == 0:
        return {"total": 0}

    issues = Counter(s.get("issue", "unknown") for s in sessions)
    modes = Counter(s.get("mode", "unknown") for s in sessions)

    durees = [s.get("duree_s", 0) for s in sessions if s.get("duree_s")]
    duree_moy = sum(durees) / len(durees) if durees else 0.0
    duree_max = max(durees) if durees else 0.0

    heures = Counter()
    for s in sessions:
        ts = s.get("ts", "")
        try:
            heure = ts.split(" ")[1].split(":")[0]
            heures[int(heure)] += 1
        except (IndexError, ValueError):
            continue

    nb_photos_total = sum(s.get("nb_photos", 0) for s in sessions)

    return {
        "total": total,
        "printed": issues.get("printed", 0),
        "abandoned": issues.get("abandoned", 0),
        "capture_failed": issues.get("capture_failed", 0),
        "modes": dict(modes),
        "duree_moyenne_s": round(duree_moy, 1),
        "duree_max_s": round(duree_max, 1),
        "heures": dict(heures),
        "heure_pointe": heures.most_common(1)[0] if heures else None,
        "nb_photos_total": nb_photos_total,
    }


def afficher_texte(stats, date_filter=None):
    """Affichage lisible pour lecture humaine dans un terminal."""
    total = stats["total"]
    header = "RAPPORT PHOTOBOOTH"
    if date_filter:
        header += f" — {date_filter}"

    print(f"{BLUE}{'=' * 50}{RESET}")
    print(f"{BOLD}{header}{RESET}")
    print(f"{BLUE}{'=' * 50}{RESET}")

    if total == 0:
        print(f"{YELLOW}Aucune session trouvée{RESET}")
        return

    printed = stats["printed"]
    pct = 100 * printed / total if total else 0
    print(f"\n{BOLD}Issue des sessions{RESET} (total : {total})")
    print(f"  {GREEN}Imprimées    : {printed}  ({pct:.0f}%){RESET}")
    print(f"  {YELLOW}Abandonnées  : {stats['abandoned']}{RESET}")
    print(f"  {RED}Capture KO   : {stats['capture_failed']}{RESET}")

    print(f"\n{BOLD}Modes{RESET}")
    for mode, n in stats["modes"].items():
        print(f"  {mode or 'inconnu'} : {n}")

    print(f"\n{BOLD}Durée{RESET}")
    print(f"  Moyenne : {stats['duree_moyenne_s']} s")
    print(f"  Max     : {stats['duree_max_s']} s")

    if stats["heure_pointe"]:
        h, n = stats["heure_pointe"]
        print(f"\n{BOLD}Heure de pointe{RESET} : {h:02d}h ({n} sessions)")

    # Histogramme horaire si on a des données
    if stats["heures"]:
        print(f"\n{BOLD}Répartition horaire{RESET}")
        max_n = max(stats["heures"].values())
        for h in sorted(stats["heures"].keys()):
            n = stats["heures"][h]
            barre_len = int(30 * n / max_n) if max_n else 0
            barre = "█" * barre_len
            print(f"  {h:02d}h │ {barre} {n}")

    print(f"\n{BOLD}Total photos capturées{RESET} : {stats['nb_photos_total']}")


def main():
    parser = argparse.ArgumentParser(description="Rapport stats photobooth")
    parser.add_argument("--date", help="Filtre YYYY-MM-DD (ex : 2026-04-20)")
    parser.add_argument("--json", action="store_true", help="Sortie JSON")
    parser.add_argument(
        "--file", default=os.path.join(PATH_DATA, "sessions.jsonl"),
        help="Chemin du fichier sessions.jsonl",
    )
    args = parser.parse_args()

    sessions = load_sessions(args.file)
    if sessions is None:
        print(f"{RED}Fichier introuvable : {args.file}{RESET}", file=sys.stderr)
        return 1

    if args.date:
        sessions = filtrer_par_date(sessions, args.date)

    stats = calculer_stats(sessions)

    if args.json:
        # heure_pointe est un tuple → on le sérialise en dict
        if stats.get("heure_pointe"):
            h, n = stats["heure_pointe"]
            stats["heure_pointe"] = {"heure": h, "nb_sessions": n}
        print(json.dumps(stats, ensure_ascii=False, indent=2))
    else:
        afficher_texte(stats, date_filter=args.date)

    return 0


if __name__ == "__main__":
    sys.exit(main())
