"""Gestion admin des événements, tags, activation et exports."""
from __future__ import annotations

import csv
import io
import json
import os
import uuid
from datetime import datetime

from flask import (
    Blueprint,
    abort,
    flash,
    redirect,
    render_template,
    request,
    send_file,
    url_for,
)

import config
from stats import calculer_stats, load_sessions
from web import backups, exports
from web.auth import require_auth
from web.db import connexion
from web.evenements import (
    EMPLACEMENTS_TEMPLATES,
    ecrire_evenement_actif,
    enregistrer_selection_templates,
    lister_evenements,
    parser_tags,
    remplacer_tags,
    retirer_evenement_actif,
    selection_templates_evenement,
    slugifier,
    trouver_evenement,
)
from web.routes.gallery import _lister_tous
from web.routes.templates_route import appliquer_selection_templates
from web.session_guard import refuser_mutation_pendant_session

bp = Blueprint("evenements", __name__, url_prefix="/evenements")

STATUTS = {
    "brouillon": "Brouillon",
    "actif": "Actif",
    "termine": "Terminé",
    "archive": "Archivé",
}

EMPLACEMENTS_FORM = (
    {"couche": "fond", "type": "10x15", "champ": "template_fond_10x15", "libelle": "Fond 10×15"},
    {"couche": "overlay", "type": "10x15", "champ": "template_overlay_10x15", "libelle": "Overlay 10×15"},
    {"couche": "fond", "type": "strip", "champ": "template_fond_strip", "libelle": "Fond strip"},
    {"couche": "overlay", "type": "strip", "champ": "template_overlay_strip", "libelle": "Overlay strip"},
)


def _templates_disponibles() -> dict[tuple[str, str], list[dict]]:
    with connexion() as conn:
        rows = conn.execute(
            "SELECT id, nom, type, couche FROM template ORDER BY type, couche, nom COLLATE NOCASE"
        ).fetchall()
    resultat = {emplacement: [] for emplacement in EMPLACEMENTS_TEMPLATES}
    for row in rows:
        resultat[(row["couche"], row["type"])].append(dict(row))
    return resultat


def _emplacements_avec_templates() -> list[dict]:
    disponibles = _templates_disponibles()
    return [
        {**emplacement, "templates": disponibles[(emplacement["couche"], emplacement["type"])]}
        for emplacement in EMPLACEMENTS_FORM
    ]


def _selection_par_champ(selection: dict[tuple[str, str], int | None]) -> dict[str, int | None]:
    return {
        emplacement["champ"]: selection[(emplacement["couche"], emplacement["type"])]
        for emplacement in EMPLACEMENTS_FORM
    }


def _selection_active_courante() -> dict[tuple[str, str], int | None]:
    with connexion() as conn:
        rows = conn.execute("SELECT id, type, couche FROM template WHERE actif = 1").fetchall()
    actifs = {(row["couche"], row["type"]): row["id"] for row in rows}
    return {emplacement: actifs.get(emplacement) for emplacement in EMPLACEMENTS_TEMPLATES}


def _lire_selection_formulaire(defaut: dict[tuple[str, str], int | None]) -> tuple[dict, list[str]]:
    selection = {}
    erreurs = []
    with connexion() as conn:
        for emplacement in EMPLACEMENTS_FORM:
            cle = (emplacement["couche"], emplacement["type"])
            brut = request.form.get(emplacement["champ"])
            if brut is None:
                selection[cle] = defaut.get(cle)
                continue
            if not brut:
                selection[cle] = None
                continue
            try:
                template_id = int(brut)
            except ValueError:
                erreurs.append(f"{emplacement['libelle']} invalide.")
                continue
            row = conn.execute(
                "SELECT type, couche FROM template WHERE id = ?", (template_id,),
            ).fetchone()
            if row is None or (row["couche"], row["type"]) != cle:
                erreurs.append(f"{emplacement['libelle']} incompatible.")
                continue
            selection[cle] = template_id
    return selection, erreurs


def _noms_templates_evenements() -> dict[str, list[str]]:
    with connexion() as conn:
        rows = conn.execute(
            "SELECT et.evenement_id, et.type, et.couche, t.nom "
            "FROM evenement_template et LEFT JOIN template t ON t.id = et.template_id "
            "ORDER BY et.type, et.couche"
        ).fetchall()
    resultat: dict[str, list[str]] = {}
    for row in rows:
        if row["nom"]:
            resultat.setdefault(row["evenement_id"], []).append(
                f"{row['type']} {row['couche']} : {row['nom']}"
            )
    return resultat


def _valider_formulaire() -> tuple[dict, list[str]]:
    nom = (request.form.get("nom") or "").strip()
    debut = (request.form.get("debut") or "").strip()
    fin = (request.form.get("fin") or "").strip()
    notes = (request.form.get("notes") or "").strip()
    erreurs = []
    if not nom:
        erreurs.append("Le nom est obligatoire.")
    try:
        debut_dt = datetime.fromisoformat(debut)
        fin_dt = datetime.fromisoformat(fin)
        if fin_dt <= debut_dt:
            erreurs.append("La fin doit être postérieure au début.")
    except ValueError:
        erreurs.append("Les dates de début et de fin sont invalides.")
    return {
        "nom": nom,
        "debut": debut,
        "fin": fin,
        "notes": notes,
        "tags": parser_tags(request.form.get("tags") or ""),
    }, erreurs


def _chevauchements(debut: str, fin: str, evenement_id: str | None = None) -> list[str]:
    requete = (
        "SELECT nom FROM evenement WHERE statut != 'archive' "
        "AND debut < ? AND fin > ?"
    )
    params: list[str] = [fin, debut]
    if evenement_id:
        requete += " AND id != ?"
        params.append(evenement_id)
    with connexion() as conn:
        return [row["nom"] for row in conn.execute(requete, params).fetchall()]


@bp.route("/")
@require_auth
def index():
    evenements = lister_evenements()
    sauvegardes = backups.lister()
    return render_template(
        "evenements.html",
        evenements=evenements,
        actif=next((e for e in evenements if e.statut == "actif"), None),
        statuts=STATUTS,
        emplacements_templates=_emplacements_avec_templates(),
        selection_creation=_selection_par_champ(_selection_active_courante()),
        templates_par_evenement=_noms_templates_evenements(),
        sauvegardes=sauvegardes,
        octets_lisibles=exports.octets_lisibles,
    )


@bp.route("/creer", methods=["POST"])
@require_auth
def creer():
    donnees, erreurs = _valider_formulaire()
    selection, erreurs_templates = _lire_selection_formulaire(_selection_active_courante())
    erreurs.extend(erreurs_templates)
    if erreurs:
        for erreur in erreurs:
            flash(erreur, "error")
        return redirect(url_for("evenements.index"))

    evenement_id = uuid.uuid4().hex
    slug_base = slugifier(donnees["nom"]) or "evenement"
    slug = slug_base
    with connexion() as conn:
        if conn.execute("SELECT 1 FROM evenement WHERE slug = ?", (slug,)).fetchone():
            slug = f"{slug_base}-{evenement_id[:8]}"
        conn.execute(
            "INSERT INTO evenement (id, nom, slug, debut, fin, notes) VALUES (?, ?, ?, ?, ?, ?)",
            (evenement_id, donnees["nom"], slug, donnees["debut"], donnees["fin"], donnees["notes"]),
        )
        remplacer_tags(conn, evenement_id, donnees["tags"])
        enregistrer_selection_templates(conn, evenement_id, selection)

    chevauchements = _chevauchements(donnees["debut"], donnees["fin"], evenement_id)
    flash(f"Événement « {donnees['nom']} » créé.", "success")
    if chevauchements:
        flash("Dates en chevauchement avec : " + ", ".join(chevauchements), "info")
    return redirect(url_for("evenements.index"))


@bp.route("/<evenement_id>/modifier", methods=["GET", "POST"])
@require_auth
def modifier(evenement_id: str):
    evenement = trouver_evenement(evenement_id)
    if evenement is None:
        abort(404)
    if request.method == "GET":
        return render_template(
            "evenement_modifier.html",
            evenement=evenement,
            emplacements_templates=_emplacements_avec_templates(),
            selection_templates=_selection_par_champ(selection_templates_evenement(evenement_id)),
        )

    if evenement.statut == "actif":
        refus = refuser_mutation_pendant_session(
            "evenements.index",
            action="modifier l'événement actif ou ses templates",
        )
        if refus is not None:
            return refus

    donnees, erreurs = _valider_formulaire()
    selection, erreurs_templates = _lire_selection_formulaire(
        selection_templates_evenement(evenement_id)
    )
    erreurs.extend(erreurs_templates)
    if erreurs:
        for erreur in erreurs:
            flash(erreur, "error")
        return redirect(url_for("evenements.modifier", evenement_id=evenement_id))

    with connexion() as conn:
        conn.execute(
            "UPDATE evenement SET nom = ?, debut = ?, fin = ?, notes = ?, "
            "updated_at = datetime('now') WHERE id = ?",
            (donnees["nom"], donnees["debut"], donnees["fin"], donnees["notes"], evenement_id),
        )
        remplacer_tags(conn, evenement_id, donnees["tags"])
        enregistrer_selection_templates(conn, evenement_id, selection)
    evenement = trouver_evenement(evenement_id)
    if evenement.statut == "actif":
        try:
            appliquer_selection_templates(selection)
        except (ValueError, FileNotFoundError, OSError) as e:
            flash(f"Événement enregistré, mais templates non appliqués : {e}", "error")
            return redirect(url_for("evenements.modifier", evenement_id=evenement_id))
        ecrire_evenement_actif(evenement)
    chevauchements = _chevauchements(donnees["debut"], donnees["fin"], evenement_id)
    flash("Événement mis à jour.", "success")
    if chevauchements:
        flash("Dates en chevauchement avec : " + ", ".join(chevauchements), "info")
    return redirect(url_for("evenements.index"))


@bp.route("/<evenement_id>/activer", methods=["POST"])
@require_auth
def activer(evenement_id: str):
    evenement = trouver_evenement(evenement_id)
    if evenement is None:
        abort(404)
    refus = refuser_mutation_pendant_session(
        "evenements.index",
        action="activer un événement",
    )
    if refus is not None:
        return refus
    if evenement.statut == "archive":
        flash("Un événement archivé ne peut pas être réactivé.", "error")
        return redirect(url_for("evenements.index"))
    try:
        appliquer_selection_templates(selection_templates_evenement(evenement_id))
    except (ValueError, FileNotFoundError, OSError) as e:
        flash(f"Activation impossible : {e}", "error")
        return redirect(url_for("evenements.index"))
    with connexion() as conn:
        conn.execute(
            "UPDATE evenement SET statut = 'termine', updated_at = datetime('now') "
            "WHERE statut = 'actif' AND id != ?", (evenement_id,),
        )
        conn.execute(
            "UPDATE evenement SET statut = 'actif', updated_at = datetime('now') WHERE id = ?",
            (evenement_id,),
        )
    evenement = trouver_evenement(evenement_id)
    ecrire_evenement_actif(evenement)
    flash(f"« {evenement.nom} » est maintenant l'événement actif.", "success")
    return redirect(url_for("evenements.index"))


def _changer_statut(evenement_id: str, statut: str) -> None:
    evenement = trouver_evenement(evenement_id)
    if evenement is None:
        abort(404)
    with connexion() as conn:
        conn.execute(
            "UPDATE evenement SET statut = ?, updated_at = datetime('now') WHERE id = ?",
            (statut, evenement_id),
        )
    retirer_evenement_actif(evenement_id)


@bp.route("/<evenement_id>/terminer", methods=["POST"])
@require_auth
def terminer(evenement_id: str):
    if trouver_evenement(evenement_id) is None:
        abort(404)
    refus = refuser_mutation_pendant_session(
        "evenements.index",
        action="terminer l'événement actif",
    )
    if refus is not None:
        return refus
    evenement = trouver_evenement(evenement_id)
    _changer_statut(evenement_id, "termine")
    flash("Événement terminé. Les prochaines sessions seront sans événement jusqu'à une activation.", "success")
    # La sauvegarde part en fond : un échec ne doit pas empêcher de terminer.
    if _lancer_sauvegarde(evenement) is None:
        flash(
            "Sauvegarde impossible : disque trop plein. Copiez puis validez une sauvegarde "
            "existante, puis relancez-la depuis « Sauvegarder ».",
            "error",
        )
    else:
        flash("Sauvegarde complète en cours de préparation dans data/backups/.", "success")
    return redirect(url_for("evenements.index"))


@bp.route("/<evenement_id>/archiver", methods=["POST"])
@require_auth
def archiver(evenement_id: str):
    evenement = trouver_evenement(evenement_id)
    if evenement is None:
        abort(404)
    if evenement.statut == "actif":
        refus = refuser_mutation_pendant_session(
            "evenements.index",
            action="archiver l'événement actif",
        )
        if refus is not None:
            return refus
    _changer_statut(evenement_id, "archive")
    flash("Événement archivé.", "success")
    return redirect(url_for("evenements.index"))


def _sessions_evenement(evenement_id: str) -> list[dict]:
    sessions = load_sessions(os.path.join(config.PATH_DATA, "sessions.jsonl")) or []
    return [session for session in sessions if session.get("event_id") == evenement_id]


def _contenu_archive(evenement, inclure_raw: bool) -> tuple[list[tuple[str, str]], dict[str, str], int]:
    """Fichiers et pièces jointes de l'archive d'un événement.

    Partagé par l'export manuel et la sauvegarde automatique : les deux
    produisent exactement la même archive, seule leur destination diffère.
    """
    sessions = _sessions_evenement(evenement.id)
    ids = {session.get("session_id") for session in sessions if session.get("session_id")}
    items = [
        item for item in _lister_tous("all")
        if item.session_id in ids and (inclure_raw or item.mode != "raw")
    ]

    csv_buffer = io.StringIO()
    champs = ["session_id", "ts", "mode", "issue", "nb_photos", "duree_s", "event_id", "event_name", "event_tags"]
    writer = csv.DictWriter(csv_buffer, fieldnames=champs, extrasaction="ignore")
    writer.writeheader()
    for session in sessions:
        ligne = dict(session)
        ligne["event_tags"] = ", ".join(session.get("event_tags", []))
        writer.writerow(ligne)

    manifeste = {
        "evenement": evenement.__dict__,
        "statistiques": calculer_stats(sessions),
        "nb_fichiers": len(items),
        "photos_brutes_incluses": inclure_raw,
    }
    extras = {
        "manifest.json": json.dumps(manifeste, ensure_ascii=False, indent=2),
        "sessions.jsonl": "".join(json.dumps(s, ensure_ascii=False) + "\n" for s in sessions),
        "sessions.csv": csv_buffer.getvalue(),
    }
    fichiers = [(item.chemin, f"photos/{item.mode}/{item.nom}") for item in items]
    return fichiers, extras, len(items)


@bp.route("/<evenement_id>/export.zip")
@require_auth
def exporter(evenement_id: str):
    """Prépare l'archive de l'événement en tâche de fond et suit la progression.

    Avec les photos brutes, l'archive pèse plusieurs Go et met une minute à se
    construire : la construction part dans un thread et la page de suivi montre
    l'avancement plutôt qu'un navigateur figé.
    """
    evenement = trouver_evenement(evenement_id)
    if evenement is None:
        abort(404)
    inclure_raw = request.args.get("inclure_raw") == "1"
    fichiers, extras, nb = _contenu_archive(evenement, inclure_raw)
    try:
        tache_id = exports.demarrer(
            nom_fichier=f"{evenement.slug}.zip",
            libelle=f"{evenement.nom} — {nb} fichier{'s' if nb > 1 else ''}"
                    f"{' (photos brutes incluses)' if inclure_raw else ''}",
            fichiers=fichiers,
            extras=extras,
            retour=url_for("evenements.index"),
            role_requis="admin",
        )
    except exports.EspaceInsuffisant as manque:
        flash(f"Disque trop plein pour cette archive : {manque}.", "error")
        return redirect(url_for("evenements.index"))
    return redirect(url_for("export.suivi", tache_id=tache_id))


def _lancer_sauvegarde(evenement) -> str | None:
    """Construit la sauvegarde complète de l'événement dans `data/backups/`.

    Renvoie l'identifiant de la tâche, ou None si le disque ne peut pas
    l'accueillir — dans ce cas l'appelant prévient sans bloquer l'action en
    cours : ne pas pouvoir sauvegarder ne doit jamais empêcher de terminer un
    événement.
    """
    fichiers, extras, nb = _contenu_archive(evenement, inclure_raw=True)
    destination = backups.chemin_pour(evenement.slug)
    try:
        return exports.demarrer(
            nom_fichier=os.path.basename(destination),
            libelle=f"Sauvegarde — {evenement.nom} · {nb} fichier{'s' if nb > 1 else ''} (photos brutes incluses)",
            fichiers=fichiers,
            extras=extras,
            retour=url_for("evenements.index"),
            role_requis="admin",
            destination=destination,
        )
    except exports.EspaceInsuffisant:
        return None


@bp.route("/<evenement_id>/sauvegarder", methods=["POST"])
@require_auth
def sauvegarder(evenement_id: str):
    """(Re)génère à la demande la sauvegarde complète d'un événement."""
    evenement = trouver_evenement(evenement_id)
    if evenement is None:
        abort(404)
    tache_id = _lancer_sauvegarde(evenement)
    if tache_id is None:
        flash(
            "Disque trop plein pour la sauvegarde : copiez puis validez une sauvegarde "
            "existante pour libérer de la place.",
            "error",
        )
        return redirect(url_for("evenements.index"))
    return redirect(url_for("export.suivi", tache_id=tache_id))


@bp.route("/sauvegardes/<nom>/copiee", methods=["POST"])
@require_auth
def sauvegarde_copiee(nom: str):
    """Confirme la copie sur clé USB : c'est la seule chose qui supprime une sauvegarde."""
    if not backups.supprimer(nom):
        abort(404)
    flash("Sauvegarde supprimée — la place disque est libérée.", "success")
    return redirect(url_for("evenements.index"))


@bp.route("/sauvegardes/<nom>")
@require_auth
def telecharger_sauvegarde(nom: str):
    """Téléchargement direct, pour copier sans passer par la machine."""
    chemin = backups.resoudre(nom)
    if chemin is None:
        abort(404)
    return send_file(
        chemin, mimetype="application/zip", as_attachment=True,
        download_name=nom, conditional=True,
    )
