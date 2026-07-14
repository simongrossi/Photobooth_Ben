"""Gestion admin des événements, tags, activation et exports."""
from __future__ import annotations

import csv
import io
import json
import os
import tempfile
import uuid
import zipfile
from datetime import datetime

from flask import (
    Blueprint,
    abort,
    after_this_request,
    flash,
    redirect,
    render_template,
    request,
    send_file,
    url_for,
)

import config
from stats import calculer_stats, load_sessions
from web.auth import require_auth
from web.db import connexion
from web.evenements import (
    ecrire_evenement_actif,
    lister_evenements,
    parser_tags,
    remplacer_tags,
    retirer_evenement_actif,
    slugifier,
    trouver_evenement,
)
from web.routes.gallery import _lister_tous

bp = Blueprint("evenements", __name__, url_prefix="/evenements")

STATUTS = {
    "brouillon": "Brouillon",
    "actif": "Actif",
    "termine": "Terminé",
    "archive": "Archivé",
}


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
    return render_template(
        "evenements.html",
        evenements=evenements,
        actif=next((e for e in evenements if e.statut == "actif"), None),
        statuts=STATUTS,
    )


@bp.route("/creer", methods=["POST"])
@require_auth
def creer():
    donnees, erreurs = _valider_formulaire()
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
        return render_template("evenement_modifier.html", evenement=evenement)

    donnees, erreurs = _valider_formulaire()
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
    evenement = trouver_evenement(evenement_id)
    if evenement.statut == "actif":
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
    if evenement.statut == "archive":
        flash("Un événement archivé ne peut pas être réactivé.", "error")
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
    _changer_statut(evenement_id, "termine")
    flash("Événement terminé. Les prochaines sessions seront sans événement jusqu'à une activation.", "success")
    return redirect(url_for("evenements.index"))


@bp.route("/<evenement_id>/archiver", methods=["POST"])
@require_auth
def archiver(evenement_id: str):
    _changer_statut(evenement_id, "archive")
    flash("Événement archivé.", "success")
    return redirect(url_for("evenements.index"))


def _sessions_evenement(evenement_id: str) -> list[dict]:
    sessions = load_sessions(os.path.join(config.PATH_DATA, "sessions.jsonl")) or []
    return [session for session in sessions if session.get("event_id") == evenement_id]


@bp.route("/<evenement_id>/export.zip")
@require_auth
def exporter(evenement_id: str):
    evenement = trouver_evenement(evenement_id)
    if evenement is None:
        abort(404)
    sessions = _sessions_evenement(evenement_id)
    ids = {session.get("session_id") for session in sessions if session.get("session_id")}
    inclure_raw = request.args.get("inclure_raw") == "1"
    items = [
        item for item in _lister_tous("all")
        if item.session_id in ids and (inclure_raw or item.mode != "raw")
    ]

    fichier_tmp = tempfile.NamedTemporaryFile(prefix="photobooth-export-", suffix=".zip", delete=False)
    fichier_tmp.close()
    with zipfile.ZipFile(fichier_tmp.name, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        manifeste = {
            "evenement": evenement.__dict__,
            "statistiques": calculer_stats(sessions),
            "nb_fichiers": len(items),
            "photos_brutes_incluses": inclure_raw,
        }
        archive.writestr("manifest.json", json.dumps(manifeste, ensure_ascii=False, indent=2))
        archive.writestr(
            "sessions.jsonl",
            "".join(json.dumps(s, ensure_ascii=False) + "\n" for s in sessions),
        )
        csv_buffer = io.StringIO()
        champs = ["session_id", "ts", "mode", "issue", "nb_photos", "duree_s", "event_id", "event_name", "event_tags"]
        writer = csv.DictWriter(csv_buffer, fieldnames=champs, extrasaction="ignore")
        writer.writeheader()
        for session in sessions:
            ligne = dict(session)
            ligne["event_tags"] = ", ".join(session.get("event_tags", []))
            writer.writerow(ligne)
        archive.writestr("sessions.csv", csv_buffer.getvalue())
        for item in items:
            archive.write(item.chemin, f"photos/{item.mode}/{item.nom}")

    @after_this_request
    def supprimer_temporaire(response):
        try:
            os.unlink(fichier_tmp.name)
        except OSError:
            pass
        return response

    return send_file(
        fichier_tmp.name,
        mimetype="application/zip",
        as_attachment=True,
        download_name=f"{evenement.slug}.zip",
    )
