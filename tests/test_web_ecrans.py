"""test_web_ecrans.py — inventaire et éditeur des écrans du kiosque.

Le fil rouge est « jamais de surprises » : la page doit refléter ce que le
kiosque affichera vraiment, et refuser toute saisie qui l'empêcherait de
démarrer.
"""
from __future__ import annotations

import base64
import io
import json
import os
from html import unescape

import pytest
from PIL import Image

from web.app import create_app

HEADERS = {"Authorization": "Basic " + base64.b64encode(b"admin:test").decode()}


@pytest.fixture
def ctx(tmp_path, monkeypatch):
    data = tmp_path / "data"
    data.mkdir()
    monkeypatch.setenv("PHOTOBOOTH_ADMIN_PASS", "test")

    fond = tmp_path / "background.jpg"
    Image.new("RGB", (128, 80), (10, 120, 220)).save(fond, format="JPEG")

    ecrans_path = str(data / "ecrans_overrides.json")
    reglages_path = str(data / "config_overrides.json")

    import config
    monkeypatch.setattr(config, "PATH_DATA", str(data))
    monkeypatch.setattr(config, "ECRANS_OVERRIDES_PATH", ecrans_path)
    monkeypatch.setattr(config, "CONFIG_OVERRIDES_PATH", reglages_path)
    monkeypatch.setattr(config, "BG_ACCUEIL_EFFECTIF", str(fond))
    monkeypatch.setattr(config, "BG_TRANSITION_EFFECTIF", str(fond))

    from core import ecrans
    monkeypatch.setattr(ecrans, "ETAT_KIOSQUE_PATH", str(data / "kiosque_etat.json"))

    import web.db
    monkeypatch.setattr(web.db, "DB_PATH", str(data / "admin.db"))

    app = create_app()
    app.config["TESTING"] = True
    return app.test_client(), ecrans_path, reglages_path


def _ecrire(chemin, donnees):
    with open(chemin, "w", encoding="utf-8") as f:
        json.dump(donnees, f)


class TestInventaire:
    def test_page_accessible(self, ctx):
        c, _, _ = ctx
        assert c.get("/ecrans/", headers=HEADERS).status_code == 200

    def test_liste_tous_les_ecrans(self, ctx):
        c, _, _ = ctx
        from core import ecrans
        html = unescape(c.get("/ecrans/", headers=HEADERS).get_data(as_text=True))
        for e in ecrans.REGISTRE:
            assert e.libelle in html, e.id

    def test_affiche_lorigine_reelle_du_fond(self, ctx):
        """Le cœur de la fonctionnalité : dire d'où vient l'image affichée."""
        c, _, _ = ctx
        html = unescape(c.get("/ecrans/", headers=HEADERS).get_data(as_text=True))
        assert "Hérité du fond d'accueil" in html

    def test_signale_un_ecran_sans_fond(self, ctx):
        """« Aucun fond par conception » ne doit pas ressembler à une erreur."""
        c, _, _ = ctx
        html = unescape(c.get("/ecrans/", headers=HEADERS).get_data(as_text=True))
        assert "Aucun fond" in html

    def test_signale_un_fichier_introuvable(self, ctx, tmp_path, monkeypatch):
        c, _, _ = ctx
        import config
        monkeypatch.setattr(config, "BG_ACCUEIL_EFFECTIF", str(tmp_path / "disparu.jpg"))
        html = unescape(c.get("/ecrans/", headers=HEADERS).get_data(as_text=True))
        assert "introuvable" in html

    def test_compte_les_reglages_personnalises(self, ctx):
        c, ecrans_path, _ = ctx
        _ecrire(ecrans_path, {"TAILLE_DECOMPTE": 210})
        html = unescape(c.get("/ecrans/", headers=HEADERS).get_data(as_text=True))
        assert "1 réglage(s) personnalisé(s)" in html

    def test_sans_override_aucun_personnalise(self, ctx):
        c, _, _ = ctx
        html = unescape(c.get("/ecrans/", headers=HEADERS).get_data(as_text=True))
        assert "Aucun réglage personnalisé" in html


class TestApercu:
    def test_renvoie_un_png(self, ctx):
        c, _, _ = ctx
        r = c.get("/ecrans/apercu/accueil", headers=HEADERS)
        assert r.status_code == 200
        assert r.mimetype == "image/png"
        with Image.open(io.BytesIO(r.data)) as img:
            assert img.size[0] <= 420

    def test_404_sur_ecran_inconnu(self, ctx):
        c, _, _ = ctx
        assert c.get("/ecrans/apercu/nexiste-pas", headers=HEADERS).status_code == 404

    def test_404_si_ecran_sans_fond(self, ctx):
        c, _, _ = ctx
        assert c.get("/ecrans/apercu/erreur", headers=HEADERS).status_code == 404


class TestEditeur:
    def test_formulaire_accessible(self, ctx):
        c, _, _ = ctx
        r = c.get("/ecrans/accueil", headers=HEADERS)
        assert r.status_code == 200
        assert b"BANDEAU_ACCUEIL" in r.data

    def test_404_sur_ecran_inconnu(self, ctx):
        c, _, _ = ctx
        assert c.get("/ecrans/nexiste-pas", headers=HEADERS).status_code == 404

    def test_reset_nest_pas_pris_pour_un_ecran(self, ctx):
        """/ecrans/reset et /ecrans/<id> partagent la même forme d'URL."""
        c, _, _ = ctx
        assert c.get("/ecrans/reset", headers=HEADERS).status_code in (404, 405)

    def test_champs_groupes_par_nature(self, ctx):
        c, _, _ = ctx
        html = unescape(c.get("/ecrans/accueil", headers=HEADERS).get_data(as_text=True))
        assert "Textes affichés" in html
        assert "Tailles" in html


class TestEnregistrement:
    def test_enregistre_une_valeur(self, ctx):
        c, ecrans_path, _ = ctx
        c.post("/ecrans/decompte", headers=HEADERS,
               data={"TAILLE_DECOMPTE": "250"}, follow_redirects=True)
        assert json.load(open(ecrans_path))["TAILLE_DECOMPTE"] == 250

    def test_enregistre_un_texte(self, ctx):
        c, ecrans_path, _ = ctx
        c.post("/ecrans/fin", headers=HEADERS,
               data={"TXT_BOUTON_IMPRIMER": "GO !"}, follow_redirects=True)
        assert json.load(open(ecrans_path))["TXT_BOUTON_IMPRIMER"] == "GO !"

    def test_refuse_hors_bornes_sans_rien_ecrire(self, ctx):
        """Une saisie invalide ne doit pas laisser le fichier à moitié écrit."""
        c, ecrans_path, _ = ctx
        r = c.post("/ecrans/decompte", headers=HEADERS,
                   data={"TAILLE_DECOMPTE": "99999"}, follow_redirects=True)
        assert "hors bornes" in unescape(r.get_data(as_text=True))
        assert not os.path.exists(ecrans_path)

    def test_refuse_type_invalide(self, ctx):
        c, ecrans_path, _ = ctx
        r = c.post("/ecrans/decompte", headers=HEADERS,
                   data={"TAILLE_DECOMPTE": "énorme"}, follow_redirects=True)
        assert "valide" in unescape(r.get_data(as_text=True))
        assert not os.path.exists(ecrans_path)

    def test_une_erreur_annule_tout_le_formulaire(self, ctx):
        """Sinon l'admin croit avoir tout enregistré alors qu'une partie a sauté."""
        c, ecrans_path, _ = ctx
        c.post("/ecrans/decompte", headers=HEADERS, follow_redirects=True,
               data={"TAILLE_DECOMPTE": "99999", "STRIP_FILIGRANE_TAILLE": "300"})
        assert not os.path.exists(ecrans_path)

    def test_champ_vide_supprime_loverride(self, ctx):
        c, ecrans_path, _ = ctx
        _ecrire(ecrans_path, {"TAILLE_DECOMPTE": 250})
        c.post("/ecrans/decompte", headers=HEADERS,
               data={"TAILLE_DECOMPTE": ""}, follow_redirects=True)
        assert "TAILLE_DECOMPTE" not in json.load(open(ecrans_path))

    def test_cle_hors_registre_ignoree(self, ctx):
        c, ecrans_path, _ = ctx
        c.post("/ecrans/decompte", headers=HEADERS, follow_redirects=True,
               data={"TAILLE_DECOMPTE": "250", "NOM_IMPRIMANTE_10X15": "pirate"})
        assert "NOM_IMPRIMANTE_10X15" not in json.load(open(ecrans_path))

    def test_cle_dun_autre_ecran_ignoree(self, ctx):
        """Poster un champ d'un autre écran ne doit pas l'enregistrer."""
        c, ecrans_path, _ = ctx
        c.post("/ecrans/decompte", headers=HEADERS, follow_redirects=True,
               data={"TAILLE_DECOMPTE": "250", "TXT_BOUTON_IMPRIMER": "PIRATE"})
        assert "TXT_BOUTON_IMPRIMER" not in json.load(open(ecrans_path))

    def test_bascule_decochee_enregistree_false(self, ctx):
        c, ecrans_path, _ = ctx
        c.post("/ecrans/decompte", headers=HEADERS,
               data={"TAILLE_DECOMPTE": "250"}, follow_redirects=True)
        assert json.load(open(ecrans_path))["STRIP_FILIGRANE_ENABLED"] is False

    def test_valeur_ecrite_est_relisible_par_config(self, ctx, monkeypatch):
        """Boucle complète : ce que l'admin écrit, le kiosque doit le charger."""
        c, ecrans_path, _ = ctx
        c.post("/ecrans/decompte", headers=HEADERS,
               data={"TAILLE_DECOMPTE": "250"}, follow_redirects=True)
        import config
        avant = config.TAILLE_DECOMPTE
        monkeypatch.setattr(config, "TAILLE_DECOMPTE", avant)
        config._appliquer_overrides_ecrans()
        assert config.TAILLE_DECOMPTE == 250


class TestReset:
    def test_supprime_le_fichier(self, ctx):
        c, ecrans_path, _ = ctx
        _ecrire(ecrans_path, {"TAILLE_DECOMPTE": 250})
        c.post("/ecrans/reset", headers=HEADERS, follow_redirects=True)
        assert not os.path.exists(ecrans_path)

    def test_ne_touche_pas_aux_reglages(self, ctx):
        """Les deux éditeurs se réinitialisent indépendamment."""
        c, ecrans_path, reglages_path = ctx
        _ecrire(ecrans_path, {"TAILLE_DECOMPTE": 250})
        _ecrire(reglages_path, {"TEMPS_DECOMPTE": 4})
        c.post("/ecrans/reset", headers=HEADERS, follow_redirects=True)
        assert json.load(open(reglages_path)) == {"TEMPS_DECOMPTE": 4}

    def test_idempotent(self, ctx):
        c, _, _ = ctx
        r = c.post("/ecrans/reset", headers=HEADERS, follow_redirects=True)
        assert r.status_code == 200
        assert "Aucun réglage" in unescape(r.get_data(as_text=True))


class TestReglagesReset:
    def test_reset_des_reglages_ne_touche_pas_aux_ecrans(self, ctx, monkeypatch):
        """Symétrique du précédent — vérifie l'autre sens."""
        c, ecrans_path, reglages_path = ctx
        import web.routes.settings_route as sr
        monkeypatch.setattr(sr, "CONFIG_OVERRIDES_PATH", reglages_path)
        _ecrire(ecrans_path, {"TAILLE_DECOMPTE": 250})
        _ecrire(reglages_path, {"TEMPS_DECOMPTE": 4})
        c.post("/settings/reset", headers=HEADERS, follow_redirects=True)
        assert json.load(open(ecrans_path)) == {"TAILLE_DECOMPTE": 250}


class TestRedemarrageRequis:
    def test_etat_inconnu_sans_kiosque(self, ctx):
        c, _, _ = ctx
        html = unescape(c.get("/ecrans/", headers=HEADERS).get_data(as_text=True))
        assert "État du kiosque inconnu" in html

    def test_pas_dalerte_juste_apres_le_boot(self, ctx):
        c, _, _ = ctx
        from core import ecrans
        ecrans.ecrire_etat_kiosque()
        html = unescape(c.get("/ecrans/", headers=HEADERS).get_data(as_text=True))
        assert "Redémarrage requis" not in html

    def test_alerte_apres_modification(self, ctx):
        c, ecrans_path, _ = ctx
        from core import ecrans
        ecrans.ecrire_etat_kiosque()
        c.post("/ecrans/decompte", headers=HEADERS,
               data={"TAILLE_DECOMPTE": "250"}, follow_redirects=True)
        html = unescape(c.get("/ecrans/", headers=HEADERS).get_data(as_text=True))
        assert "Redémarrage requis" in html


class TestApercuPositionne:
    """Aperçu à l'échelle 1280×800 de la page d'édition."""

    def test_accueil_a_un_apercu(self, ctx):
        html = ctx[0].get("/ecrans/accueil", headers=HEADERS).get_data(as_text=True)
        assert 'id="apercu"' in html

    def test_ecran_sans_geometrie_na_pas_dapercu(self, ctx):
        """Mieux vaut aucun aperçu qu'un aperçu qui ne reproduit pas le rendu."""
        html = ctx[0].get("/ecrans/erreur", headers=HEADERS).get_data(as_text=True)
        assert 'id="apercu"' not in html

    def test_geometrie_exposee_au_gabarit(self, ctx):
        html = ctx[0].get("/ecrans/accueil", headers=HEADERS).get_data(as_text=True)
        assert '"axe_y_centre": 340' in html   # (800 // 2) - 60
        assert '"largeur": 1280' in html

    def test_police_servie(self, ctx):
        r = ctx[0].get("/ecrans/police.ttf", headers=HEADERS)
        assert r.status_code == 200
        assert r.mimetype == "font/ttf"
        assert len(r.data) > 1000

    def test_icones_servies(self, ctx):
        for cle in ("icone-10x15", "icone-strip"):
            r = ctx[0].get(f"/ecrans/image/{cle}", headers=HEADERS)
            assert r.status_code == 200, cle
            assert r.mimetype.startswith("image/"), cle

    def test_cle_dimage_inconnue_404(self, ctx):
        assert ctx[0].get("/ecrans/image/nimporte-quoi", headers=HEADERS).status_code == 404

    def test_pas_de_traversee_de_chemin(self, ctx):
        """La clé indexe un dictionnaire ; ce n'est jamais un chemin."""
        for tentative in ("../../etc/passwd", "..%2f..%2fetc%2fpasswd", "POLICE_EFFECTIVE"):
            r = ctx[0].get(f"/ecrans/image/{tentative}", headers=HEADERS)
            assert r.status_code == 404, tentative


class TestGeometrieSynchroniseAvecLeKiosque:
    """L'aperçu rejoue en JS les formules de `_render_accueil_normal`.

    C'est une duplication assumée (le web n'a pas pygame), mais une duplication
    qui diverge en silence produirait un aperçu convaincant et faux — on
    réglerait des positions en se fiant à une image qui ment. Ces tests
    échouent si le rendu du kiosque change sans que l'aperçu suive.
    """

    @staticmethod
    def _source_render_accueil() -> str:
        racine = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        with open(os.path.join(racine, "Photobooth_start.py"), encoding="utf-8") as f:
            source = f.read()
        debut = source.index("def _render_accueil_normal")
        fin = source.index("\ndef ", debut + 1)
        return source[debut:fin]

    def test_axe_vertical_toujours_decale_de_60(self):
        src = self._source_render_accueil()
        assert "axe_y_centre = (HEIGHT // 2) - 60" in src, (
            "l'axe vertical de l'accueil a changé : mettre à jour "
            "_geometrie_apercu() dans web/routes/ecrans_route.py"
        )

    def test_ecart_du_label_toujours_de_20(self):
        src = self._source_render_accueil()
        assert src.count("+ 20)") >= 2, (
            "l'écart des libellés sous les icônes a changé : mettre à jour "
            "decalage_label dans _geometrie_apercu()"
        )

    def test_formule_horizontale_inchangee(self):
        src = self._source_render_accueil()
        attendus = (
            "x_10 = (WIDTH // 2) - img_draw.get_width() - (marge_centrale // 2) + OFFSET_DROITE_10X15",
            "x_s = (WIDTH // 2) + (marge_centrale // 2) + OFFSET_DROITE_STRIP",
        )
        for formule in attendus:
            assert formule in src, (
                f"formule de position modifiée ({formule[:20]}…) : mettre à jour "
                "la fonction redessiner() de web/templates/ecran_editeur.html"
            )

    def test_valeurs_exposees_coherentes(self):
        """L'axe calculé côté web doit valoir celui du kiosque."""
        import config

        import web.routes.ecrans_route as er
        geo = er._geometrie_apercu("accueil")
        assert geo["axe_y_centre"] == (config.HEIGHT // 2) - 60
        assert geo["largeur"] == config.WIDTH
        assert geo["hauteur"] == config.HEIGHT

    def test_pas_de_geometrie_hors_liste(self):
        import web.routes.ecrans_route as er
        for e_id in ("erreur", "camera", "fin"):
            assert er._geometrie_apercu(e_id) is None, e_id


class TestAcces:
    """Le viewer consulte le dashboard mais ne doit pas pouvoir régler le kiosque."""

    def test_admin_voit_le_lien(self, ctx):
        """Repère de contrôle : sans lui, le test suivant passerait à vide."""
        html = ctx[0].get("/dashboard/", headers=HEADERS).get_data(as_text=True)
        assert "/ecrans/" in html

    def test_viewer_na_pas_le_lien(self, ctx):
        c, _, _ = ctx
        r = c.get("/dashboard/")
        assert r.status_code == 200, "le viewer doit pouvoir consulter le dashboard"
        assert "/ecrans/" not in r.get_data(as_text=True)

    def test_viewer_ne_peut_pas_lire_la_page(self, ctx):
        assert ctx[0].get("/ecrans/").status_code == 401

    def test_viewer_ne_peut_pas_enregistrer(self, ctx):
        c, ecrans_path, _ = ctx
        assert c.post("/ecrans/decompte", data={"TAILLE_DECOMPTE": "250"}).status_code == 401
        assert not os.path.exists(ecrans_path)

    def test_viewer_ne_peut_pas_reinitialiser(self, ctx):
        c, ecrans_path, _ = ctx
        _ecrire(ecrans_path, {"TAILLE_DECOMPTE": 250})
        assert c.post("/ecrans/reset").status_code == 401
        assert os.path.exists(ecrans_path)

    def test_viewer_ne_peut_pas_redemarrer(self, ctx):
        assert ctx[0].post("/ecrans/redemarrer").status_code == 401
