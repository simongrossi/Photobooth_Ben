"""test_ecrans.py — registre des écrans, résolution d'assets, overrides, empreinte.

Deux familles de tests :

- **Cohérence structurelle** : le registre et la whitelist de `config` doivent
  rester synchronisés dans les deux sens. C'est ce qui empêche la page d'admin
  de planter ou d'exposer un champ sans effet.
- **Robustesse au boot** : aucune valeur écrite dans `ecrans_overrides.json`,
  même corrompue à la main, ne doit pouvoir empêcher le kiosque de démarrer.
"""
from __future__ import annotations

import json
import os

import pytest

import config
from core import ecrans


# ========================================================================================
# --- Cohérence registre ↔ whitelist ---
# ========================================================================================

class TestCoherenceRegistre:
    def test_chaque_champ_est_whiteliste(self):
        """Un champ hors whitelist s'afficherait dans l'admin sans aucun effet."""
        orphelins = [c.cle for c in ecrans.tous_les_champs()
                     if c.cle not in config._ECRANS_OVERRIDES_WHITELIST]
        assert not orphelins, f"champs sans bornes dans config : {orphelins}"

    def test_chaque_cle_whitelistee_est_dans_un_ecran(self):
        """Une clé bornée mais non exposée serait éditable par personne."""
        exposees = {c.cle for c in ecrans.tous_les_champs()}
        oubliees = sorted(set(config._ECRANS_OVERRIDES_WHITELIST) - exposees)
        assert not oubliees, f"clés whitelistées absentes du registre : {oubliees}"

    def test_aucun_champ_en_double(self):
        """Le même réglage sur deux écrans : deux formulaires qui s'écrasent."""
        cles = [c.cle for c in ecrans.tous_les_champs()]
        doublons = sorted({c for c in cles if cles.count(c) > 1})
        assert not doublons, f"champs présents sur plusieurs écrans : {doublons}"

    def test_chaque_cle_existe_dans_config(self):
        absentes = [c.cle for c in ecrans.tous_les_champs() if not hasattr(config, c.cle)]
        assert not absentes, f"clés sans constante correspondante : {absentes}"

    def test_intersection_vide_avec_les_reglages(self):
        """Une clé, un fichier, un propriétaire.

        Une clé présente dans les deux whitelists serait écrite dans deux
        fichiers, et le dernier import de `config` gagnerait — silencieusement.
        """
        collision = set(config._ECRANS_OVERRIDES_WHITELIST) & set(config._CONFIG_OVERRIDES_WHITELIST)
        assert not collision, f"clés revendiquées par les deux éditeurs : {sorted(collision)}"

    def test_identifiants_ecrans_uniques(self):
        ids = [e.id for e in ecrans.REGISTRE]
        assert len(ids) == len(set(ids))

    def test_chaque_ecran_a_un_libelle_et_une_description(self):
        for e in ecrans.REGISTRE:
            assert e.libelle and e.description, e.id

    def test_natures_de_champ_connues(self):
        connues = {ecrans.TEXTE, ecrans.DUREE, ecrans.TAILLE, ecrans.POSITION, ecrans.BASCULE}
        for champ in ecrans.tous_les_champs():
            assert champ.nature in connues, f"{champ.cle} : nature {champ.nature!r}"

    def test_attributs_de_fond_existent(self):
        for e in ecrans.REGISTRE:
            for attribut in (e.attribut_fond, e.attribut_fond_actif):
                if attribut is not None:
                    assert hasattr(config, attribut), f"{e.id} → {attribut}"


class TestBornesPlusStrictesQueLesAssertions:
    """Les bornes de l'éditeur doivent exclure toute valeur que
    `_valider_config()` refuserait : sinon un réglage sauvegardé depuis l'admin
    rendrait le kiosque non bootable, et l'erreur n'apparaîtrait qu'au
    redémarrage — typiquement en plein événement.
    """

    # (clé, valeur que _valider_config() rejette)
    VALEURS_INTERDITES = [
        ("DUREE_ECRAN_ERREUR", 0.0),
        ("DUREE_CONFIRM_ABANDON", 0.0),
        ("TIMEOUT_SPLASH_CAMERA", 0.0),
        ("DUREE_FLASH_BLANC", -1.0),
        ("BANDEAU_ALPHA", 256),
        ("BANDEAU_ALPHA", -1),
    ]

    @pytest.mark.parametrize("cle,valeur", VALEURS_INTERDITES)
    def test_valeur_refusee_par_les_bornes(self, cle, valeur):
        assert config.valeur_ecran_valide(cle, valeur) is None, (
            f"{cle}={valeur} passerait l'éditeur mais casserait _valider_config()"
        )

    def test_bornes_numeriques_coherentes(self):
        for cle, (type_attendu, mini, maxi) in config._ECRANS_OVERRIDES_WHITELIST.items():
            if type_attendu is bool:
                continue
            assert mini is not None and maxi is not None, cle
            assert mini < maxi, f"{cle} : bornes inversées ({mini} ≥ {maxi})"

    def test_valeur_par_defaut_dans_les_bornes(self):
        """Le défaut du dépôt doit lui-même être acceptable, sinon l'éditeur
        refuserait de réenregistrer la valeur déjà en vigueur."""
        for cle in config._ECRANS_OVERRIDES_WHITELIST:
            defaut = getattr(config, cle)
            assert config.valeur_ecran_valide(cle, defaut) is not None, (
                f"{cle} : le défaut {defaut!r} est hors de ses propres bornes"
            )


# ========================================================================================
# --- Validation des valeurs ---
# ========================================================================================

class TestValeurEcranValide:
    def test_accepte_valeur_nominale(self):
        assert config.valeur_ecran_valide("TAILLE_DECOMPTE", 250) == 250

    def test_refuse_cle_inconnue(self):
        assert config.valeur_ecran_valide("CLE_QUI_NEXISTE_PAS", 1) is None

    def test_refuse_hors_bornes_haut(self):
        assert config.valeur_ecran_valide("TAILLE_DECOMPTE", 10_000) is None

    def test_refuse_hors_bornes_bas(self):
        assert config.valeur_ecran_valide("TAILLE_DECOMPTE", 1) is None

    def test_bornes_str_portent_sur_la_longueur(self):
        assert config.valeur_ecran_valide("TXT_BOUTON_IMPRIMER", "OK") == "OK"
        assert config.valeur_ecran_valide("TXT_BOUTON_IMPRIMER", "x" * 500) is None

    def test_refuse_chaine_vide(self):
        assert config.valeur_ecran_valide("TXT_BOUTON_IMPRIMER", "") is None

    def test_refuse_bool_pour_un_int(self):
        """bool est un sous-type de int : True deviendrait une taille de 1 px."""
        assert config.valeur_ecran_valide("TAILLE_DECOMPTE", True) is None

    def test_accepte_bool_pour_une_bascule(self):
        assert config.valeur_ecran_valide("STRIP_FILIGRANE_ENABLED", False) is False

    def test_refuse_int_pour_une_bascule(self):
        assert config.valeur_ecran_valide("STRIP_FILIGRANE_ENABLED", 1) is None

    def test_tolere_int_pour_un_float(self):
        assert config.valeur_ecran_valide("DUREE_ECRAN_ERREUR", 5) == 5.0

    def test_refuse_texte_pour_un_nombre(self):
        assert config.valeur_ecran_valide("TAILLE_DECOMPTE", "gros") is None

    def test_accepte_les_deux_bornes_incluses(self):
        _, mini, maxi = config._ECRANS_OVERRIDES_WHITELIST["BANDEAU_ALPHA"]
        assert config.valeur_ecran_valide("BANDEAU_ALPHA", mini) == mini
        assert config.valeur_ecran_valide("BANDEAU_ALPHA", maxi) == maxi


# ========================================================================================
# --- Robustesse du boot ---
# ========================================================================================

class TestApplicationDesOverrides:
    """`_appliquer_overrides_ecrans()` doit être totalement inoffensif face à un
    fichier hostile : c'est la dernière chose qui tourne avant `_valider_config()`.
    """

    def _appliquer(self, tmp_path, monkeypatch, contenu):
        chemin = tmp_path / "ecrans_overrides.json"
        if isinstance(contenu, str):
            chemin.write_text(contenu, encoding="utf-8")
        else:
            chemin.write_text(json.dumps(contenu), encoding="utf-8")
        monkeypatch.setattr(config, "ECRANS_OVERRIDES_PATH", str(chemin))
        avant = config.TAILLE_DECOMPTE
        monkeypatch.setattr(config, "TAILLE_DECOMPTE", avant)
        config._appliquer_overrides_ecrans()
        return config.TAILLE_DECOMPTE

    def test_override_valide_applique(self, tmp_path, monkeypatch):
        assert self._appliquer(tmp_path, monkeypatch, {"TAILLE_DECOMPTE": 200}) == 200

    def test_json_corrompu_ignore(self, tmp_path, monkeypatch):
        avant = config.TAILLE_DECOMPTE
        assert self._appliquer(tmp_path, monkeypatch, "{ pas du json") == avant

    def test_json_non_dict_ignore(self, tmp_path, monkeypatch):
        avant = config.TAILLE_DECOMPTE
        assert self._appliquer(tmp_path, monkeypatch, [1, 2, 3]) == avant

    def test_valeur_hors_bornes_ignoree(self, tmp_path, monkeypatch):
        avant = config.TAILLE_DECOMPTE
        assert self._appliquer(tmp_path, monkeypatch, {"TAILLE_DECOMPTE": 99999}) == avant

    def test_type_invalide_ignore(self, tmp_path, monkeypatch):
        avant = config.TAILLE_DECOMPTE
        assert self._appliquer(tmp_path, monkeypatch, {"TAILLE_DECOMPTE": "énorme"}) == avant

    def test_cle_inconnue_ignoree(self, tmp_path, monkeypatch):
        avant = config.TAILLE_DECOMPTE
        assert self._appliquer(tmp_path, monkeypatch, {"RM_RF": "/"}) == avant

    def test_fichier_absent_silencieux(self, tmp_path, monkeypatch):
        monkeypatch.setattr(config, "ECRANS_OVERRIDES_PATH", str(tmp_path / "absent.json"))
        config._appliquer_overrides_ecrans()  # ne doit pas lever

    def test_valeur_invalide_nannule_pas_les_valides(self, tmp_path, monkeypatch):
        """Une clé pourrie ne doit pas faire tomber le reste du fichier."""
        chemin = tmp_path / "o.json"
        chemin.write_text(json.dumps({"TAILLE_DECOMPTE": 99999, "TAILLE_TEXTE_BANDEAU": 55}))
        monkeypatch.setattr(config, "ECRANS_OVERRIDES_PATH", str(chemin))
        avant_decompte = config.TAILLE_DECOMPTE
        monkeypatch.setattr(config, "TAILLE_DECOMPTE", avant_decompte)
        monkeypatch.setattr(config, "TAILLE_TEXTE_BANDEAU", config.TAILLE_TEXTE_BANDEAU)
        config._appliquer_overrides_ecrans()
        assert config.TAILLE_DECOMPTE == avant_decompte
        assert config.TAILLE_TEXTE_BANDEAU == 55


# ========================================================================================
# --- Lecture / écriture des overrides ---
# ========================================================================================

class TestOverridesFichier:
    def test_aller_retour(self, tmp_path):
        chemin = str(tmp_path / "e.json")
        ecrans.ecrire_overrides({"TAILLE_DECOMPTE": 210}, chemin)
        assert ecrans.charger_overrides(chemin) == {"TAILLE_DECOMPTE": 210}

    def test_ecriture_filtre_les_cles_invalides(self, tmp_path):
        """Le fichier sur disque doit toujours être applicable tel quel."""
        chemin = str(tmp_path / "e.json")
        ecrans.ecrire_overrides(
            {"TAILLE_DECOMPTE": 210, "INCONNUE": 1, "TAILLE_TEXTE_BANDEAU": 99999}, chemin,
        )
        assert ecrans.charger_overrides(chemin) == {"TAILLE_DECOMPTE": 210}

    def test_charger_fichier_absent(self, tmp_path):
        assert ecrans.charger_overrides(str(tmp_path / "rien.json")) == {}

    def test_charger_json_corrompu(self, tmp_path):
        chemin = tmp_path / "e.json"
        chemin.write_text("{{{")
        assert ecrans.charger_overrides(str(chemin)) == {}

    def test_ecriture_atomique_sans_residu(self, tmp_path):
        chemin = str(tmp_path / "e.json")
        ecrans.ecrire_overrides({"TAILLE_DECOMPTE": 210}, chemin)
        assert not os.path.exists(chemin + ".tmp")

    def test_reinitialiser(self, tmp_path):
        chemin = str(tmp_path / "e.json")
        ecrans.ecrire_overrides({"TAILLE_DECOMPTE": 210}, chemin)
        assert ecrans.reinitialiser_overrides(chemin) is True
        assert not os.path.exists(chemin)
        assert ecrans.reinitialiser_overrides(chemin) is False

    def test_reinitialiser_ne_touche_pas_les_reglages(self, tmp_path, monkeypatch):
        """Les deux fichiers d'overrides se réinitialisent indépendamment."""
        reglages = tmp_path / "config_overrides.json"
        reglages.write_text(json.dumps({"TEMPS_DECOMPTE": 4}))
        monkeypatch.setattr(config, "CONFIG_OVERRIDES_PATH", str(reglages))
        chemin = str(tmp_path / "ecrans_overrides.json")
        ecrans.ecrire_overrides({"TAILLE_DECOMPTE": 210}, chemin)
        ecrans.reinitialiser_overrides(chemin)
        assert reglages.exists()
        assert json.loads(reglages.read_text()) == {"TEMPS_DECOMPTE": 4}


# ========================================================================================
# --- Résolution des assets ---
# ========================================================================================

class TestResolutionAssets:
    def test_un_asset_par_ecran(self):
        assets = ecrans.resoudre_assets()
        assert set(assets) == {e.id for e in ecrans.REGISTRE}

    def test_ecran_sans_fond_signale_comme_tel(self):
        """« Pas d'image par conception » ≠ « image introuvable »."""
        assert ecrans.resoudre_assets()["erreur"].origine == ecrans.ORIGINE_SANS_FOND

    def test_transition_herite_du_fond_accueil(self, monkeypatch, tmp_path):
        fond = tmp_path / "background.jpg"
        fond.write_bytes(b"x")
        monkeypatch.setattr(config, "BG_ACCUEIL_EFFECTIF", str(fond))
        monkeypatch.setattr(config, "BG_TRANSITION_EFFECTIF", str(fond))
        monkeypatch.setattr(config, "FILE_BG_TRANSITION_ACTIF", str(tmp_path / "absent.jpg"))
        assert ecrans.resoudre_assets()["transition"].origine == ecrans.ORIGINE_HERITE

    def test_transition_dediee_signalee_active(self, monkeypatch, tmp_path):
        accueil = tmp_path / "background.jpg"
        accueil.write_bytes(b"x")
        dediee = tmp_path / "transition_actif.jpg"
        dediee.write_bytes(b"y")
        monkeypatch.setattr(config, "BG_ACCUEIL_EFFECTIF", str(accueil))
        monkeypatch.setattr(config, "BG_TRANSITION_EFFECTIF", str(dediee))
        monkeypatch.setattr(config, "FILE_BG_TRANSITION_ACTIF", str(dediee))
        assert ecrans.resoudre_assets()["transition"].origine == ecrans.ORIGINE_ACTIF

    def test_fichier_introuvable_signale(self, monkeypatch, tmp_path):
        monkeypatch.setattr(config, "BG_ACCUEIL_EFFECTIF", str(tmp_path / "disparu.jpg"))
        asset = ecrans.resoudre_assets()["accueil"]
        assert asset.origine == ecrans.ORIGINE_ABSENT
        assert asset.existe is False

    def test_toutes_les_origines_ont_un_libelle(self):
        for asset in ecrans.resoudre_assets().values():
            assert asset.libelle_origine != asset.origine, asset.origine


# ========================================================================================
# --- Empreinte et état du kiosque ---
# ========================================================================================

class TestEmpreinte:
    def test_stable_entre_deux_appels(self):
        assert ecrans.empreinte_config() == ecrans.empreinte_config()

    def test_change_avec_les_overrides(self, tmp_path, monkeypatch):
        chemin = str(tmp_path / "e.json")
        monkeypatch.setattr(config, "ECRANS_OVERRIDES_PATH", chemin)
        avant = ecrans.empreinte_config()
        ecrans.ecrire_overrides({"TAILLE_DECOMPTE": 211}, chemin)
        assert ecrans.empreinte_config() != avant

    def test_change_quand_un_asset_est_remplace(self, tmp_path, monkeypatch):
        """Remplacer un fond par un autre fichier de MÊME NOM doit être détecté :
        c'est le cas nominal quand l'admin active un nouveau fond."""
        fond = tmp_path / "background.jpg"
        fond.write_bytes(b"petit")
        monkeypatch.setattr(config, "BG_ACCUEIL_EFFECTIF", str(fond))
        avant = ecrans.empreinte_config()
        fond.write_bytes(b"un contenu nettement plus long")
        assert ecrans.empreinte_config() != avant


class TestEtatKiosque:
    def test_aller_retour(self, tmp_path):
        chemin = str(tmp_path / "etat.json")
        ecrit = ecrans.ecrire_etat_kiosque(chemin)
        relu = ecrans.lire_etat_kiosque(chemin)
        assert relu["empreinte"] == ecrit["empreinte"]
        assert relu["pid"] == os.getpid()

    def test_lecture_fichier_absent(self, tmp_path):
        assert ecrans.lire_etat_kiosque(str(tmp_path / "rien.json")) is None

    def test_lecture_fichier_corrompu(self, tmp_path):
        chemin = tmp_path / "etat.json"
        chemin.write_text("pas du json")
        assert ecrans.lire_etat_kiosque(str(chemin)) is None

    def test_ecriture_ne_leve_jamais(self, tmp_path):
        """Un état non écrivable ne doit jamais empêcher le kiosque de démarrer."""
        etat = ecrans.ecrire_etat_kiosque(str(tmp_path / "interdit" / "\0" / "etat.json"))
        assert "empreinte" in etat

    def test_redemarrage_inconnu_sans_etat(self, tmp_path, monkeypatch):
        monkeypatch.setattr(ecrans, "ETAT_KIOSQUE_PATH", str(tmp_path / "absent.json"))
        assert ecrans.redemarrage_requis() is None

    def test_pas_de_redemarrage_juste_apres_le_boot(self, tmp_path, monkeypatch):
        chemin = str(tmp_path / "etat.json")
        monkeypatch.setattr(ecrans, "ETAT_KIOSQUE_PATH", chemin)
        ecrans.ecrire_etat_kiosque(chemin)
        assert ecrans.redemarrage_requis() is False

    def test_redemarrage_requis_apres_modification(self, tmp_path, monkeypatch):
        chemin = str(tmp_path / "etat.json")
        overrides = str(tmp_path / "e.json")
        monkeypatch.setattr(ecrans, "ETAT_KIOSQUE_PATH", chemin)
        monkeypatch.setattr(config, "ECRANS_OVERRIDES_PATH", overrides)
        ecrans.ecrire_etat_kiosque(chemin)
        ecrans.ecrire_overrides({"TAILLE_DECOMPTE": 212}, overrides)
        assert ecrans.redemarrage_requis() is True
