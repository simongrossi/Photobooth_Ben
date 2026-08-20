"""test_web_apercu.py — aperçu du rendu final depuis l'admin web.

Vérifie que /templates/apercu/rendu produit bien le montage du kiosque, avec
les calques choisis, sans rien activer ni écrire sur le disque de production.
"""
from __future__ import annotations

import base64
import io
import json
import os
import time

import pytest
from PIL import Image

from web.app import create_app
from web.db import connexion

HEADERS = {"Authorization": "Basic " + base64.b64encode(b"admin:test").decode()}

SESSION_A = "2026-08-20_14h32_07"
SESSION_B = "2026-08-20_09h10_00"


def _simuler_session_kiosque(monkeypatch):
    from web import session_guard

    monkeypatch.setattr(session_guard.ecrans, "lire_etat_kiosque", lambda: {
        "online": True,
        "heartbeat_ts": time.time(),
        "session_active": True,
        "etat": "DECOMPTE",
        "session_id": "session-test",
    })


@pytest.fixture
def env(tmp_path, monkeypatch):
    data = tmp_path / "data"
    temp = data / "temp"
    overlays = tmp_path / "overlays"
    fonds = tmp_path / "fonds"
    raw = tmp_path / "raw"
    for dossier in (data, temp, overlays, fonds, raw):
        dossier.mkdir(parents=True)
    monkeypatch.setenv("PHOTOBOOTH_ADMIN_PASS", "test")

    import config
    from core import montage
    from web import photos_raw
    import web.db
    import web.routes.templates_route as tr

    monkeypatch.setattr(config, "PATH_DATA", str(data))
    monkeypatch.setattr(config, "PATH_TEMP", str(temp))
    monkeypatch.setattr(montage, "PATH_TEMP", str(temp))
    monkeypatch.setattr(config, "PATH_RAW", str(raw))
    monkeypatch.setattr(photos_raw, "PATH_RAW", str(raw))
    monkeypatch.setattr(config, "PATH_OVERLAYS", str(overlays))
    monkeypatch.setattr(config, "PATH_FONDS", str(fonds))
    monkeypatch.setattr(web.db, "DB_PATH", str(data / "admin.db"))
    monkeypatch.setattr(tr, "_RACINE_PAR_COUCHE", {
        "overlay": str(overlays), "fond": str(fonds),
    })
    for nom in ("OVERLAY_10X15", "OVERLAY_STRIPS", "BG_10X15_FILE", "BG_STRIPS_FILE"):
        monkeypatch.setattr(montage, nom, "/inexistant/" + nom)
    monkeypatch.setattr(montage, "PATH_MISE_EN_PAGE_10X15", str(data / "mep.json"))
    monkeypatch.setattr(montage, "PATH_MISE_EN_PAGE_STRIP", str(data / "mep_strip.json"))

    app = create_app()
    app.config["TESTING"] = True
    return {
        "client": app.test_client(),
        "overlays": overlays,
        "fonds": fonds,
        "raw": raw,
        "temp": temp,
    }


def _photo_raw(env, id_session, index, couleur=(0, 120, 255)):
    chemin = env["raw"] / f"photo_{id_session}_{index}.jpg"
    Image.new("RGB", (800, 600), couleur).save(chemin, "JPEG", quality=90)
    return chemin


def _template(env, *, nom, type_t, couche, couleur=(0, 200, 0), alpha=255):
    """Crée le fichier de template et sa ligne en base. Retourne son id.

    `alpha=0` donne un overlay transparent : indispensable pour observer la
    photo en dessous quand on teste la géométrie.
    """
    extension = ".png" if couche == "overlay" else ".jpg"
    fichier = f"{nom}{extension}"
    dossier = env["overlays"] if couche == "overlay" else env["fonds"]
    taille = (600, 1800) if type_t == "strip" else (1800, 1200)
    if couche == "overlay":
        Image.new("RGBA", taille, (*couleur, alpha)).save(dossier / fichier, "PNG")
    else:
        Image.new("RGB", taille, couleur).save(dossier / fichier, "JPEG", quality=90)
    with connexion() as conn:
        curseur = conn.execute(
            "INSERT INTO template (nom, type, couche, fichier, actif, taille_octets) "
            "VALUES (?, ?, ?, ?, 0, 0)",
            (nom, type_t, couche, fichier),
        )
        return curseur.lastrowid


def _image(reponse) -> Image.Image:
    return Image.open(io.BytesIO(reponse.data))


class TestAcces:
    def test_page_accessible_a_l_admin(self, env):
        r = env["client"].get("/templates/apercu", headers=HEADERS)
        assert r.status_code == 200

    def test_page_refusee_sans_authentification(self, env):
        assert env["client"].get("/templates/apercu").status_code == 401

    def test_rendu_refuse_sans_authentification(self, env):
        assert env["client"].get("/templates/apercu/rendu").status_code == 401


class TestRendu:
    def test_10x15_aux_dimensions_du_montage(self, env):
        _photo_raw(env, SESSION_A, 1)
        r = env["client"].get("/templates/apercu/rendu?format=10x15", headers=HEADERS)
        assert r.status_code == 200
        assert r.mimetype == "image/jpeg"
        assert _image(r).size == (1800, 1200)

    def test_strip_aux_dimensions_de_la_bandelette(self, env):
        for i in (1, 2, 3):
            _photo_raw(env, SESSION_A, i)
        r = env["client"].get("/templates/apercu/rendu?format=strip", headers=HEADERS)
        assert r.status_code == 200
        assert _image(r).size == (600, 1800)

    def test_utilise_le_fond_choisi_sans_l_activer(self, env):
        _photo_raw(env, SESSION_A, 1)
        id_fond = _template(env, nom="fondrouge", type_t="10x15",
                            couche="fond", couleur=(255, 0, 0))
        r = env["client"].get(
            f"/templates/apercu/rendu?format=10x15&fond={id_fond}", headers=HEADERS)
        assert r.status_code == 200
        rouge, vert, _ = _image(r).getpixel((10, 10))[:3]
        assert rouge > 200 and vert < 80
        with connexion() as conn:
            actif = conn.execute(
                "SELECT actif FROM template WHERE id = ?", (id_fond,)).fetchone()
        assert actif["actif"] == 0

    def test_fond_et_overlay_a_aucun(self, env):
        _photo_raw(env, SESSION_A, 1)
        r = env["client"].get(
            "/templates/apercu/rendu?format=10x15&fond=aucun&overlay=aucun",
            headers=HEADERS)
        assert r.status_code == 200
        assert _image(r).getpixel((10, 10))[:3] == (255, 255, 255)

    def test_session_choisie_explicitement(self, env):
        _photo_raw(env, SESSION_A, 1, couleur=(255, 0, 0))
        _photo_raw(env, SESSION_B, 1, couleur=(0, 0, 255))
        r = env["client"].get(
            f"/templates/apercu/rendu?format=10x15&session={SESSION_B}&fond=aucun",
            headers=HEADERS)
        bleu = _image(r).getpixel((900, 600))[2]
        assert bleu > 200

    def test_pas_de_mise_en_cache(self, env):
        _photo_raw(env, SESSION_A, 1)
        r = env["client"].get("/templates/apercu/rendu?format=10x15", headers=HEADERS)
        assert "no-store" in r.headers.get("Cache-Control", "")

    def test_n_ecrit_rien_dans_data_temp(self, env):
        _photo_raw(env, SESSION_A, 1)
        env["client"].get("/templates/apercu/rendu?format=10x15", headers=HEADERS)
        assert os.listdir(env["temp"]) == []


class TestErreurs:
    def test_format_inconnu(self, env):
        _photo_raw(env, SESSION_A, 1)
        r = env["client"].get("/templates/apercu/rendu?format=a4", headers=HEADERS)
        assert r.status_code == 400

    def test_template_inexistant(self, env):
        _photo_raw(env, SESSION_A, 1)
        r = env["client"].get(
            "/templates/apercu/rendu?format=10x15&fond=9999", headers=HEADERS)
        assert r.status_code == 404

    def test_strip_refuse_une_session_incomplete(self, env):
        _photo_raw(env, SESSION_A, 1)
        r = env["client"].get(
            f"/templates/apercu/rendu?format=strip&session={SESSION_A}",
            headers=HEADERS)
        assert r.status_code == 400

    def test_refus_pendant_une_session_kiosque(self, env, monkeypatch):
        _photo_raw(env, SESSION_A, 1)
        _simuler_session_kiosque(monkeypatch)
        r = env["client"].get("/templates/apercu/rendu?format=10x15", headers=HEADERS)
        assert r.status_code == 409


class TestSansPhoto:
    def test_rendu_avec_image_de_substitution(self, env):
        r = env["client"].get("/templates/apercu/rendu?format=10x15", headers=HEADERS)
        assert r.status_code == 200
        assert _image(r).size == (1800, 1200)

    def test_la_page_signale_la_substitution(self, env):
        r = env["client"].get("/templates/apercu", headers=HEADERS)
        assert r.status_code == 200
        assert "substitution".encode() in r.data


def _poser_mise_en_page(template_id, *, x, y, largeur, hauteur):
    with connexion() as conn:
        conn.execute(
            "UPDATE template SET photo_x = ?, photo_y = ?, photo_largeur = ?, "
            "photo_hauteur = ? WHERE id = ?",
            (x, y, largeur, hauteur, template_id),
        )


def _poser_zones_strip(template_id, zones):
    with connexion() as conn:
        conn.execute(
            "UPDATE template SET zones_strip = ? WHERE id = ?",
            (json.dumps(zones), template_id),
        )


class TestMiseEnPage:
    def test_10x15_suit_la_geometrie_du_template_choisi(self, env):
        _photo_raw(env, SESSION_A, 1, couleur=(255, 0, 0))
        id_overlay = _template(env, nom="ovgeo", type_t="10x15",
                               couche="overlay", alpha=0)
        _poser_mise_en_page(id_overlay, x=0, y=0, largeur=200, hauteur=200)
        r = env["client"].get(
            f"/templates/apercu/rendu?format=10x15&fond=aucun&overlay={id_overlay}",
            headers=HEADERS)
        image = _image(r)
        # Zone photo réduite au coin haut-gauche : rouge dedans, blanc dehors.
        assert image.getpixel((100, 100))[0] > 200
        assert image.getpixel((900, 600))[:3] == (255, 255, 255)

    def test_overlay_prioritaire_sur_le_fond(self, env):
        _photo_raw(env, SESSION_A, 1, couleur=(255, 0, 0))
        id_fond = _template(env, nom="fondgeo", type_t="10x15", couche="fond")
        id_overlay = _template(env, nom="ovgeo2", type_t="10x15",
                               couche="overlay", alpha=0)
        _poser_mise_en_page(id_fond, x=0, y=0, largeur=1800, hauteur=1200)
        _poser_mise_en_page(id_overlay, x=0, y=0, largeur=200, hauteur=200)
        r = env["client"].get(
            f"/templates/apercu/rendu?format=10x15&fond={id_fond}&overlay={id_overlay}",
            headers=HEADERS)
        # Si le fond l'emportait, la photo couvrirait tout le canevas.
        assert _image(r).getpixel((900, 600))[1] > 150

    def test_strip_suit_les_zones_du_template_choisi(self, env):
        for i in (1, 2, 3):
            _photo_raw(env, SESSION_A, i, couleur=(255, 0, 0))
        id_overlay = _template(env, nom="stripgeo", type_t="strip",
                               couche="overlay", alpha=0)
        _poser_zones_strip(id_overlay, [
            {"x": 0, "y": 0, "largeur": 100, "hauteur": 100},
            {"x": 0, "y": 200, "largeur": 100, "hauteur": 100},
            {"x": 0, "y": 400, "largeur": 100, "hauteur": 100},
        ])
        r = env["client"].get(
            f"/templates/apercu/rendu?format=strip&fond=aucun&overlay={id_overlay}",
            headers=HEADERS)
        image = _image(r)
        assert image.getpixel((50, 50))[0] > 200
        assert image.getpixel((300, 900))[:3] == (255, 255, 255)

    def test_zones_strip_corrompues_retombent_sur_le_defaut(self, env):
        for i in (1, 2, 3):
            _photo_raw(env, SESSION_A, i)
        id_overlay = _template(env, nom="stripko", type_t="strip", couche="overlay")
        with connexion() as conn:
            conn.execute("UPDATE template SET zones_strip = ? WHERE id = ?",
                         ("pas du json", id_overlay))
        r = env["client"].get(
            f"/templates/apercu/rendu?format=strip&overlay={id_overlay}",
            headers=HEADERS)
        assert r.status_code == 200
        assert _image(r).size == (600, 1800)


class TestParametresInvalides:
    def test_identifiant_de_template_non_numerique(self, env):
        _photo_raw(env, SESSION_A, 1)
        r = env["client"].get(
            "/templates/apercu/rendu?format=10x15&fond=abc", headers=HEADERS)
        assert r.status_code == 400

    def test_template_du_mauvais_format(self, env):
        _photo_raw(env, SESSION_A, 1)
        id_strip = _template(env, nom="strip1", type_t="strip", couche="fond")
        r = env["client"].get(
            f"/templates/apercu/rendu?format=10x15&fond={id_strip}", headers=HEADERS)
        assert r.status_code == 404
