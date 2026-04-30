#!/usr/bin/env python3
"""status.py — diagnostic pré-événement.

Vérifie en 2 secondes que le photobooth est prêt :
  - espace disque > 1 Go
  - caméra gphoto2 détectée
  - files d'impression CUPS (10x15 + strip) enabled
  - assets d'interface et d'impression présents
  - sons (optionnels) présents

Usage : python3 status.py
Exit code : 0 si tout OK, 1 si un critique manque.

À lancer 1 min avant le début de l'événement, sur le matériel cible.
"""
import os
import shutil
import subprocess
import sys

from config import (
    BG_10X15_FILE, BG_STRIPS_FILE, FILE_BG_ACCUEIL,
    NOM_IMPRIMANTE_10X15, NOM_IMPRIMANTE_STRIP,
    OVERLAY_10X15, OVERLAY_STRIPS,
    PATH_DATA, PATH_IMG_10X15, PATH_IMG_STRIP,
    POLICE_FICHIER, SEUIL_TEMP_CRITIQUE_C, SON_BEEP, SON_BEEP_FINAL,
    SON_SHUTTER, SON_SUCCESS, TEMP_PATH,
)

# --- Sortie ANSI (pas de dépendance externe) ---
_tty = sys.stdout.isatty()
GREEN = "\033[92m" if _tty else ""
RED = "\033[91m" if _tty else ""
YELLOW = "\033[93m" if _tty else ""
BLUE = "\033[94m" if _tty else ""
RESET = "\033[0m" if _tty else ""


def _marker(ok):
    return f"{GREEN}✓{RESET}" if ok else f"{RED}✗{RESET}"


def print_check(label, ok, detail=""):
    suffix = f"  — {detail}" if detail else ""
    print(f"  {_marker(ok)} {label}{suffix}")
    return ok


def print_section(title):
    print(f"\n{BLUE}{title}{RESET}")


def check_file(path, label):
    ok = os.path.exists(path)
    return print_check(label, ok, "" if ok else f"manquant : {path}")


def check_optional_file(path, label):
    """Affiche mais ne bloque pas."""
    if os.path.exists(path):
        print(f"  {GREEN}✓{RESET} {label}")
    else:
        print(f"  {YELLOW}·{RESET} {label}  — (optionnel, absent)")


def check_disk():
    try:
        usage = shutil.disk_usage(PATH_DATA)
        libre_go = usage.free / (1024 ** 3)
    except FileNotFoundError:
        return print_check("Espace disque", False, f"PATH_DATA introuvable : {PATH_DATA}")
    ok = libre_go >= 1.0
    detail = f"{libre_go:.1f} Go libres" + (" — PURGER AVANT !" if not ok else "")
    return print_check("Espace disque", ok, detail)


def check_temperature():
    """Lit la température CPU (Pi). Ne bloque pas : info purement indicative.

    Sur macOS/Windows ou si TEMP_PATH n'existe pas, on affiche un marqueur
    optionnel. Sur Pi chaud (>= seuil critique), on alerte."""
    try:
        with open(TEMP_PATH) as f:
            temp_c = int(f.read().strip()) / 1000.0
    except FileNotFoundError:
        print(f"  {YELLOW}·{RESET} Température CPU  — (non disponible sur cet OS)")
        return True  # pas un échec critique
    except Exception as e:
        print_check("Température CPU", False, str(e))
        return True

    ok = temp_c < SEUIL_TEMP_CRITIQUE_C
    detail = f"{temp_c:.1f} °C" + (f" — AU-DESSUS DE {SEUIL_TEMP_CRITIQUE_C:.0f} °C" if not ok else "")
    return print_check("Température CPU", ok, detail)


def check_camera():
    try:
        r = subprocess.run(
            ["gphoto2", "--auto-detect"],
            capture_output=True, text=True, timeout=5,
        )
    except FileNotFoundError:
        return print_check("Caméra gphoto2", False, "commande gphoto2 absente (apt install gphoto2)")
    except subprocess.TimeoutExpired:
        return print_check("Caméra gphoto2", False, "timeout 5s — USB bloqué ?")
    except Exception as e:
        return print_check("Caméra gphoto2", False, str(e))

    # Output gphoto2 : lignes "Model    Port" avec séparateur ----, on garde celles qui ne sont ni header ni sep
    lines = [ligne.strip() for ligne in r.stdout.splitlines() if ligne.strip()]
    modeles = [ligne for ligne in lines if not ligne.startswith("Model") and not ligne.startswith("----")]
    ok = bool(modeles)
    return print_check("Caméra gphoto2 détectée", ok, modeles[0] if ok else "aucun appareil détecté")


def check_printer(nom):
    try:
        r = subprocess.run(
            ["lpstat", "-p", nom],
            capture_output=True, text=True, timeout=3,
        )
    except FileNotFoundError:
        return print_check(f"Imprimante {nom}", False, "commande lpstat absente (cups-client)")
    except Exception as e:
        return print_check(f"Imprimante {nom}", False, str(e))

    out = (r.stdout or "").strip()
    if not out:
        return print_check(f"Imprimante {nom}", False, "introuvable dans CUPS")
    if "disabled" in out.lower():
        return print_check(f"Imprimante {nom}", False, f"disabled — `cupsenable {nom}`")
    ok = any(tag in out.lower() for tag in ("idle", "enabled", "printing"))
    return print_check(f"Imprimante {nom}", ok, out.splitlines()[0])


def check_python_deps():
    """Vérifie que les modules Python nécessaires sont installés."""
    deps = ["pygame", "cv2", "gphoto2", "PIL", "numpy"]
    tous_ok = True
    for mod in deps:
        try:
            __import__(mod)
            print_check(f"Module Python : {mod}", True)
        except ImportError as e:
            print_check(f"Module Python : {mod}", False, str(e))
            tous_ok = False
    return tous_ok


def main():
    print(f"{BLUE}════════════════════════════════════════{RESET}")
    print(f"{BLUE}  Photobooth — diagnostic pré-événement{RESET}")
    print(f"{BLUE}════════════════════════════════════════{RESET}")

    all_ok = True

    print_section("Stockage")
    all_ok &= check_disk()

    print_section("Système")
    check_temperature()

    print_section("Dépendances Python")
    all_ok &= check_python_deps()

    print_section("Caméra")
    all_ok &= check_camera()

    print_section("Imprimantes CUPS")
    all_ok &= check_printer(NOM_IMPRIMANTE_10X15)
    all_ok &= check_printer(NOM_IMPRIMANTE_STRIP)

    print_section("Assets interface (critiques)")
    all_ok &= check_file(FILE_BG_ACCUEIL, "Fond d'accueil")
    all_ok &= check_file(PATH_IMG_10X15, "Icône 10x15")
    all_ok &= check_file(PATH_IMG_STRIP, "Icône strip")
    all_ok &= check_file(POLICE_FICHIER, "Police")

    print_section("Assets impression (critiques)")
    all_ok &= check_file(BG_10X15_FILE, "Fond 10x15")
    all_ok &= check_file(BG_STRIPS_FILE, "Fond strip")
    all_ok &= check_file(OVERLAY_10X15, "Overlay 10x15")
    all_ok &= check_file(OVERLAY_STRIPS, "Overlay strip")

    print_section("Sons (optionnels — silencieux si absents)")
    check_optional_file(SON_BEEP, "Beep décompte")
    check_optional_file(SON_BEEP_FINAL, "Beep dernière seconde (fallback SON_BEEP)")
    check_optional_file(SON_SHUTTER, "Shutter")
    check_optional_file(SON_SUCCESS, "Success impression")

    print()
    if all_ok:
        print(f"{GREEN}✓ Tout est prêt — tu peux démarrer le photobooth.{RESET}")
    else:
        print(f"{RED}✗ Des éléments critiques manquent — corriger avant l'événement.{RESET}")
    return 0 if all_ok else 1


if __name__ == "__main__":
    sys.exit(main())
