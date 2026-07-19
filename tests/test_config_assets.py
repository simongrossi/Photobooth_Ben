"""test_config_assets.py — résolution actif/défaut des assets kiosque (volet 2)."""
import os
import re

import config

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


class TestResoudreActif:
    def test_prefere_actif_si_present(self, tmp_path):
        actif = tmp_path / "actif.jpg"
        actif.write_bytes(b"x")
        assert config.resoudre_actif(str(actif), "/defaut.jpg") == str(actif)

    def test_fallback_si_actif_absent(self, tmp_path):
        absent = str(tmp_path / "absent.jpg")
        assert config.resoudre_actif(absent, "/defaut.jpg") == "/defaut.jpg"


class TestConstantesVolet2:
    def test_constantes_presentes(self):
        for nom in ("FILE_BG_ACCUEIL_ACTIF", "POLICE_FICHIER_ACTIF", "PATH_SLIDESHOW_PERSO",
                    "PATH_CORBEILLE", "PATH_ACCUEIL_BIBLIO", "PATH_FONTS_BIBLIO",
                    "BG_ACCUEIL_EFFECTIF", "POLICE_EFFECTIVE",
                    "FILE_BG_TRANSITION_ACTIF", "PATH_TRANSITION_BIBLIO",
                    "BG_TRANSITION_EFFECTIF"):
            assert hasattr(config, nom), nom


class TestFallbackFondTransition:
    """Chaîne : fond de transition activé → fond d'accueil activé → fond versionné.

    Le fond de transition est celui que voit l'invité quand il annule une photo.
    Sans fond dédié, il doit hériter de l'accueil — jamais retomber sur une image
    versionnée que l'admin croyait avoir remplacée.
    """

    def _resoudre(self, tmp_path, transition_presente, accueil_present):
        """Rejoue la chaîne de résolution de config.py avec des fichiers témoins."""
        defaut = tmp_path / "background.jpg"
        defaut.write_bytes(b"defaut")
        accueil_actif = tmp_path / "accueil_actif.jpg"
        transition_actif = tmp_path / "transition_actif.jpg"
        if accueil_present:
            accueil_actif.write_bytes(b"accueil")
        if transition_presente:
            transition_actif.write_bytes(b"transition")

        bg_accueil = config.resoudre_actif(str(accueil_actif), str(defaut))
        bg_transition = config.resoudre_actif(str(transition_actif), bg_accueil)
        return bg_transition, str(defaut), str(accueil_actif), str(transition_actif)

    def test_transition_dediee_prioritaire(self, tmp_path):
        resolu, _, _, transition = self._resoudre(tmp_path, True, True)
        assert resolu == transition

    def test_herite_du_fond_accueil_actif(self, tmp_path):
        resolu, _, accueil, _ = self._resoudre(tmp_path, False, True)
        assert resolu == accueil

    def test_retombe_sur_le_defaut_versionne(self, tmp_path):
        resolu, defaut, _, _ = self._resoudre(tmp_path, False, False)
        assert resolu == defaut

    def test_transition_seule_sans_accueil_actif(self, tmp_path):
        resolu, _, _, transition = self._resoudre(tmp_path, True, False)
        assert resolu == transition


class TestCheminsAbsolus:
    """Un chemin relatif dépend du cwd : le kiosque lancé par systemd depuis un
    autre répertoire ne trouve plus l'asset et tombe en mode dégradé sans le dire.
    """

    SUFFIXES = ("_FILE", "_ACTIF", "_EFFECTIF", "_EFFECTIVE", "_BIBLIO")
    PREFIXES = ("PATH_", "POLICE_", "FILE_", "OVERLAY_", "BG_")

    def test_constantes_de_chemin_absolues(self):
        for nom in dir(config):
            if nom.startswith("_"):
                continue
            valeur = getattr(config, nom)
            if not isinstance(valeur, str) or not valeur:
                continue
            interessant = nom.startswith(self.PREFIXES) or nom.endswith(self.SUFFIXES)
            if not interessant:
                continue
            assert os.path.isabs(valeur), f"{nom} n'est pas un chemin absolu : {valeur!r}"


class TestPasDeCouleurCodeeEnDur:
    """Garde-fou anti-récidive sur les couleurs des écrans.

    `Photobooth_start.py` et `ui/helpers.py` ne sont pas couverts par les tests
    (pas de pygame en CI) : sans ce contrôle, une couleur réintroduite en dur
    échapperait à l'éditeur d'écrans sans que rien ne le signale, et l'admin
    modifierait un réglage qui ne s'applique pas.

    La liste d'exemptions ci-dessous couvre les cas où une couleur littérale est
    légitime : elle doit rester courte et justifiée.
    """

    MOTIF = re.compile(r"\(\s*\d{1,3}\s*,\s*\d{1,3}\s*,\s*\d{1,3}\s*\)")

    # (fichier, fragment de ligne) → pourquoi cette couleur reste en dur.
    EXEMPTIONS = {
        # Ombre portée du texte : noir pur, purement technique.
        ("ui/helpers.py", "shadow_surf = font.render"),
        # Fond de secours quand aucun asset ne charge : ne doit dépendre
        # d'aucun réglage, sinon un réglage cassé rendrait l'écran illisible.
        ("ui/helpers.py", "screen.fill((155, 211, 242))"),
        # Aplats noirs structurels (voiles, surfaces de composition).
        ("Photobooth_start.py", "bandeau_bas.fill"),
        ("Photobooth_start.py", "surf.fill((0, 0, 0))"),
        ("Photobooth_start.py", "screen.fill((0, 0, 0))"),
        ("Photobooth_start.py", "screen.fill((10, 10, 10))"),
        ("Photobooth_start.py", "pygame.draw.rect(screen, (255, 255, 255)"),
        # Alertes d'exploitation (disque plein, CPU chaud) : destinées à
        # l'exploitant, pas à l'invité, et ne doivent jamais être masquables.
        ("Photobooth_start.py", "alerte.fill("),
        ("Photobooth_start.py", "True, (255, 255, 255),"),
        # Message ponctuel hors parcours nominal.
        ("Photobooth_start.py", "Impression desactivee"),
        ("Photobooth_start.py", "couleur=(100, 255, 100),"),
        ("Photobooth_start.py", "couleur=(255, 150, 150),"),
    }

    def _exempte(self, rel: str, ligne: str) -> bool:
        return any(f == rel and frag in ligne for f, frag in self.EXEMPTIONS)

    def test_aucune_couleur_litterale_non_exemptee(self):
        fautifs = []
        for rel in ("Photobooth_start.py", "ui/helpers.py"):
            chemin = os.path.join(BASE_DIR, rel)
            with open(chemin, encoding="utf-8") as f:
                for num, ligne in enumerate(f, 1):
                    sans_commentaire = ligne.split("#", 1)[0]
                    if not self.MOTIF.search(sans_commentaire):
                        continue
                    if self._exempte(rel, ligne):
                        continue
                    fautifs.append(f"{rel}:{num} → {ligne.strip()[:90]}")
        assert not fautifs, (
            "Couleur(s) codée(s) en dur dans le rendu — les rendre éditables via "
            "config + core/ecrans.py, ou les exempter explicitement dans ce test :\n  "
            + "\n  ".join(fautifs)
        )

    def test_les_exemptions_sont_toutes_utilisees(self):
        """Une exemption obsolète masquerait une vraie régression plus tard."""
        contenus = {
            rel: open(os.path.join(BASE_DIR, rel), encoding="utf-8").read()
            for rel in ("Photobooth_start.py", "ui/helpers.py")
        }
        mortes = [f"{f} → {frag}" for f, frag in self.EXEMPTIONS if frag not in contenus[f]]
        assert not mortes, f"exemptions qui ne correspondent plus à rien : {mortes}"


class TestPasDeCheminRelatifCodeEnDur:
    """Garde-fou anti-récidive : les assets doivent passer par `config.PATH_*`.

    Motivation : `ui/helpers.py` chargeait le fond de l'écran de transition via
    le littéral "assets/interface/background.jpg", ce qui (a) ignorait le fond
    activé par l'admin web et (b) dépendait du cwd.
    """

    MOTIF = re.compile(r'["\']assets/[^"\']*["\']')

    def _fichiers_source(self):
        for racine in ("ui", "core"):
            dossier = os.path.join(BASE_DIR, racine)
            for nom in sorted(os.listdir(dossier)):
                if nom.endswith(".py"):
                    yield os.path.join(dossier, nom)
        yield os.path.join(BASE_DIR, "Photobooth_start.py")

    def test_aucun_litteral_assets_relatif(self):
        fautifs = []
        for chemin in self._fichiers_source():
            with open(chemin, encoding="utf-8") as f:
                for num, ligne in enumerate(f, 1):
                    for trouve in self.MOTIF.findall(ligne):
                        rel = os.path.relpath(chemin, BASE_DIR)
                        fautifs.append(f"{rel}:{num} → {trouve}")
        assert not fautifs, (
            "Chemin(s) d'asset relatif(s) codé(s) en dur — utiliser config.PATH_* :\n  "
            + "\n  ".join(fautifs)
        )
