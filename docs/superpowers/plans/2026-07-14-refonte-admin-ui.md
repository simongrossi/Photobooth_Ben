# Refonte UI admin (volet 1) — Plan d'implémentation

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Dashboard 4 étages (santé, aujourd'hui, KPI, historique par journée) + thème automatique clair/sombre sur toutes les pages de l'admin, sans dépendance externe.

**Architecture:** Les calculs « du jour » et « par journée » deviennent des fonctions pures dans `stats.py` (testées). `dashboard.py` assemble santé matérielle (is_ready imprimantes ×2, disque, CPU) + stats. `admin.css` est refondu en custom properties avec `@media (prefers-color-scheme: dark)`, en conservant tous les sélecteurs existants (Galerie/Templates/Réglages héritent du thème sans changement HTML).

**Tech Stack:** Flask + Jinja2, CSS custom properties (zéro CDN/framework — booth hors-ligne), pytest.

**Spec :** `docs/superpowers/specs/2026-07-14-refonte-admin-ui-design.md`
**Branche :** `refonte-admin-ui`

---

## Structure des fichiers

| Fichier | Rôle |
|---|---|
| `stats.py` | + `stats_du_jour(sessions, date_str)` et `stats_par_jour(sessions, limite=14)` (pures) |
| `test_stats.py` | Tests des 2 nouvelles fonctions (fixture `jsonl_factice` existante : sessions du 2026-04-20/21) |
| `web/routes/dashboard.py` | Assemble `sante`, `jour`, `taux_imprimees`, `historique` ; singleton `printer_mgr` |
| `web/templates/dashboard.html` | Restructuré 4 étages |
| `web/static/admin.css` | Refonte complète, thème auto (tous les sélecteurs existants conservés) |
| `test_web_app.py` | Tests rendu dashboard (sections présentes, pastilles, zéro session OK) |
| `docs/ADMIN.md` | Description du dashboard |

---

### Task 1 : Fonctions pures `stats_du_jour` / `stats_par_jour`

**Files:**
- Modify: `stats.py` (après `filtrer_par_date`, ~ligne 56)
- Test: `test_stats.py` (fin de fichier)

- [ ] **Step 1 : Écrire les tests (échec attendu)**

Ajouter en fin de `test_stats.py` :

```python
# --- Tests stats_du_jour / stats_par_jour (dashboard v2) ---


class TestStatsDuJour:
    def test_jour_actif(self, jsonl_factice):
        sessions = load_sessions(jsonl_factice)
        jour = stats_du_jour(sessions, "2026-04-20")
        assert jour["total"] == 7          # s6 est le 21
        assert jour["printed"] == 3
        assert jour["abandoned"] == 1
        assert jour["capture_failed"] == 1
        # histogramme du jour uniquement : 14h → 2 sessions, 22h absent
        assert jour["heures"][14] == 2
        assert 22 not in jour["heures"]

    def test_jour_sans_session_retourne_zeros(self, jsonl_factice):
        sessions = load_sessions(jsonl_factice)
        jour = stats_du_jour(sessions, "2030-01-01")
        assert jour["total"] == 0
        assert jour["printed"] == 0
        assert jour["abandoned"] == 0
        assert jour["capture_failed"] == 0
        assert jour["heures"] == {}

    def test_ts_malforme_ignore(self):
        sessions = [{"issue": "printed", "ts": "n'importe quoi"},
                    {"issue": "printed", "ts": "2026-04-20 14:00:00"}]
        jour = stats_du_jour(sessions, "2026-04-20")
        assert jour["total"] == 1


class TestStatsParJour:
    def test_agrege_et_trie_desc(self, jsonl_factice):
        sessions = load_sessions(jsonl_factice)
        hist = stats_par_jour(sessions)
        assert [j["date"] for j in hist] == ["2026-04-21", "2026-04-20"]
        assert hist[1]["total"] == 7
        assert hist[1]["printed"] == 3
        assert hist[0]["total"] == 1
        assert hist[0]["printed"] == 1

    def test_limite(self, jsonl_factice):
        sessions = load_sessions(jsonl_factice)
        hist = stats_par_jour(sessions, limite=1)
        assert len(hist) == 1
        assert hist[0]["date"] == "2026-04-21"  # le plus récent d'abord

    def test_ts_malforme_ignore(self):
        sessions = [{"issue": "printed", "ts": ""},
                    {"issue": "printed"},
                    {"issue": "printed", "ts": "2026-04-20 14:00:00"}]
        hist = stats_par_jour(sessions)
        assert len(hist) == 1
        assert hist[0]["total"] == 1
```

Et compléter l'import en tête de `test_stats.py` (il importe déjà depuis `stats`) :
ajouter `stats_du_jour, stats_par_jour` à la liste importée.

- [ ] **Step 2 : Vérifier l'échec**

Run: `pytest test_stats.py -v -k "StatsDuJour or StatsParJour"`
Expected: FAIL — `ImportError: cannot import name 'stats_du_jour'`.

- [ ] **Step 3 : Implémenter dans `stats.py`** (après `filtrer_par_date`)

```python
def stats_du_jour(sessions, date_str):
    """Stats d'une seule journée (YYYY-MM-DD), clés toujours présentes.

    Contrairement à calculer_stats() qui renvoie {"total": 0} à vide, le
    dashboard a besoin de toutes les clés pour l'étage « Aujourd'hui ».
    """
    stats = calculer_stats(filtrer_par_date(sessions, date_str))
    return {
        "date": date_str,
        "total": stats.get("total", 0),
        "printed": stats.get("printed", 0),
        "abandoned": stats.get("abandoned", 0),
        "capture_failed": stats.get("capture_failed", 0),
        "heures": stats.get("heures", {}),
    }


def stats_par_jour(sessions, limite=14):
    """Agrégat par journée (date desc), pour l'historique du dashboard.

    Retourne au plus `limite` journées actives : [{date, total, printed}, ...].
    Les sessions au `ts` malformé (pas de date YYYY-MM-DD) sont ignorées.
    """
    par_jour = {}
    for s in sessions:
        ts = s.get("ts", "") or ""
        date_str = ts.split(" ")[0]
        if len(date_str) != 10 or date_str.count("-") != 2:
            continue
        jour = par_jour.setdefault(date_str, {"date": date_str, "total": 0, "printed": 0})
        jour["total"] += 1
        if s.get("issue") == "printed":
            jour["printed"] += 1
    return [par_jour[d] for d in sorted(par_jour, reverse=True)[:limite]]
```

- [ ] **Step 4 : Vérifier le succès**

Run: `pytest test_stats.py -v`
Expected: PASS (nouveaux + anciens).

- [ ] **Step 5 : Commit**

```bash
git add stats.py test_stats.py
git commit -m "feat(stats): stats_du_jour + stats_par_jour pour le dashboard v2"
```

---

### Task 2 : Dashboard — collecte + gabarit 4 étages

**Files:**
- Modify: `web/routes/dashboard.py` (remplacement complet du corps)
- Modify: `web/templates/dashboard.html` (remplacement complet)
- Test: `test_web_app.py` (fin de fichier)

- [ ] **Step 1 : Écrire les tests de rendu (échec attendu)**

Ajouter en fin de `test_web_app.py` :

```python
class TestDashboardV2:
    def test_quatre_etages_presents(self, client, monkeypatch):
        import web.routes.dashboard as dash
        monkeypatch.setattr(dash.printer_mgr, "is_ready", lambda mode: True)
        r = client.get("/dashboard/", headers=HEADERS)
        html = r.get_data(as_text=True)
        assert "Aujourd'hui" in html
        assert "Historique par journée" in html
        assert "pastille--ok" in html          # imprimantes mockées prêtes
        assert "Imprimante 10×15" in html

    def test_imprimante_en_erreur_pastille_rouge(self, client, monkeypatch):
        import web.routes.dashboard as dash
        monkeypatch.setattr(dash.printer_mgr, "is_ready",
                            lambda mode: "FILE D'ATTENTE PLEINE")
        r = client.get("/dashboard/", headers=HEADERS)
        html = r.get_data(as_text=True)
        assert "pastille--err" in html
        assert "FILE D&#39;ATTENTE PLEINE" in html or "FILE D'ATTENTE PLEINE" in html

    def test_zero_session_ne_crashe_pas(self, client, monkeypatch):
        import web.routes.dashboard as dash
        monkeypatch.setattr(dash.printer_mgr, "is_ready", lambda mode: True)
        r = client.get("/dashboard/", headers=HEADERS)
        assert r.status_code == 200
```

Note : la fixture `client` de `test_web_app.py` pointe `PATH_DATA` vers un tmp
sans `sessions.jsonl` → zéro session, c'est le cas testé.
Vérifier que `HEADERS` existe déjà en tête du fichier (même pattern que les
autres tests) ; sinon reprendre :
`HEADERS = {"Authorization": "Basic " + base64.b64encode(b"admin:test").decode()}`.

- [ ] **Step 2 : Vérifier l'échec**

Run: `pytest test_web_app.py::TestDashboardV2 -v`
Expected: FAIL — `AttributeError: module 'web.routes.dashboard' has no attribute 'printer_mgr'`.

- [ ] **Step 3 : Remplacer `web/routes/dashboard.py`**

```python
"""dashboard.py — vue d'ensemble : santé matériel, jour courant, totaux, historique."""
from __future__ import annotations

import os
from datetime import date

from flask import Blueprint, render_template

from config import (
    INTERVALLE_CHECK_DISQUE_S,
    INTERVALLE_CHECK_TEMP_S,
    NOM_IMPRIMANTE_10X15,
    NOM_IMPRIMANTE_STRIP,
    PATH_DATA,
    PATH_PRINT,
    SEUIL_DISQUE_CRITIQUE_MB,
    SEUIL_TEMP_CRITIQUE_C,
    TEMP_PATH,
)
from core.monitoring import DiskMonitor, TempMonitor
from core.printer import PrinterManager
from stats import calculer_stats, load_sessions, stats_du_jour, stats_par_jour
from web.auth import require_auth

bp = Blueprint("dashboard", __name__, url_prefix="/dashboard")

# Singleton module (pattern projet) — monkeypatché dans les tests.
printer_mgr = PrinterManager(NOM_IMPRIMANTE_10X15, NOM_IMPRIMANTE_STRIP)


def _pastille_imprimante(mode: str, libelle: str) -> dict:
    """is_ready renvoie True (prête) ou une chaîne d'erreur (contrat PrinterManager)."""
    resultat = printer_mgr.is_ready(mode)
    if resultat is True:
        return {"libelle": libelle, "etat": "ok", "detail": "prête"}
    return {"libelle": libelle, "etat": "err", "detail": str(resultat)}


def _construire_sante(disk: DiskMonitor, temp: TempMonitor) -> list[dict]:
    sante = [
        _pastille_imprimante("10x15", "Imprimante 10×15"),
        _pastille_imprimante("strips", "Imprimante strip"),
    ]
    if disk.libre_mb is None:
        sante.append({"libelle": "Disque", "etat": "na", "detail": "N/A"})
    else:
        libre = f"{disk.libre_mb / 1024:.0f} Go" if disk.libre_mb >= 1024 else f"{disk.libre_mb:.0f} Mo"
        sante.append({"libelle": "Disque", "etat": "err" if disk.critique else "ok", "detail": libre})
    if temp.temp_c is None:
        sante.append({"libelle": "CPU", "etat": "na", "detail": "N/A"})
    else:
        sante.append({
            "libelle": "CPU",
            "etat": "err" if temp.critique else "ok",
            "detail": f"{temp.temp_c:.0f} °C",
        })
    return sante


@bp.route("/")
@require_auth
def index():
    sessions_path = os.path.join(PATH_DATA, "sessions.jsonl")
    sessions = load_sessions(sessions_path) or []
    stats = calculer_stats(sessions)

    disk = DiskMonitor(
        path=PATH_DATA,
        seuil_mb=SEUIL_DISQUE_CRITIQUE_MB,
        intervalle_s=INTERVALLE_CHECK_DISQUE_S,
    )
    disk.intervalle_s = 0  # force un check immédiat pour le dashboard
    disk.tick()

    temp = TempMonitor(
        path=TEMP_PATH,
        seuil_c=SEUIL_TEMP_CRITIQUE_C,
        intervalle_s=INTERVALLE_CHECK_TEMP_S,
    )
    temp.intervalle_s = 0
    temp.tick()

    jour = stats_du_jour(sessions, date.today().strftime("%Y-%m-%d"))
    historique = stats_par_jour(sessions, limite=14)
    max_total = max((j["total"] for j in historique), default=0)
    for j in historique:
        j["pct_barre"] = round(j["total"] * 100 / max_total) if max_total else 0

    total = stats.get("total", 0)
    taux_imprimees = round(stats.get("printed", 0) * 100 / total) if total else None

    return render_template(
        "dashboard.html",
        sante=_construire_sante(disk, temp),
        jour=jour,
        date_affichee=date.today().strftime("%d/%m/%Y"),
        stats=stats,
        taux_imprimees=taux_imprimees,
        historique=historique,
        sessions_path=sessions_path,
        print_path=PATH_PRINT,
    )
```

- [ ] **Step 4 : Remplacer `web/templates/dashboard.html`**

```html
{% extends "base.html" %}
{% block titre %}Dashboard · Photobooth{% endblock %}
{% block contenu %}
<h1>Dashboard</h1>

<!-- Étage 1 : santé matériel -->
<section class="pastilles">
  {% for p in sante %}
    <span class="pastille pastille--{{ p.etat }}">● {{ p.libelle }} : {{ p.detail }}</span>
  {% endfor %}
</section>

<!-- Étage 2 : aujourd'hui -->
<section class="panel hero">
  <div class="hero__label">Aujourd'hui — {{ date_affichee }}</div>
  <div class="hero__valeur">{{ jour.total }}<span class="hero__unite"> sessions</span></div>
  <div class="hero__detail">
    <span class="ok">{{ jour.printed }} imprimées</span> ·
    <span class="warn">{{ jour.abandoned }} abandons</span> ·
    <span class="err">{{ jour.capture_failed }} échecs</span>
  </div>
  {% if jour.heures %}
    {% set max_h = jour.heures.values() | list | max %}
    <div class="barres">
      {% for h in jour.heures.keys() | sort %}
        <div class="barres__col" title="{{ '%02d'|format(h) }}h : {{ jour.heures[h] }}">
          <div class="barres__bar" style="height: {{ (jour.heures[h] * 100 / max_h) | round }}%"></div>
          <div class="barres__h">{{ '%02d'|format(h) }}</div>
        </div>
      {% endfor %}
    </div>
    <div class="hero__label">sessions par heure</div>
  {% else %}
    <p class="muted">Aucune session aujourd'hui pour l'instant.</p>
  {% endif %}
</section>

<!-- Étage 3 : totaux -->
<section class="cards">
  <div class="card">
    <div class="card__label">Sessions (total)</div>
    <div class="card__value">{{ stats.total }}</div>
  </div>
  <div class="card card--ok">
    <div class="card__label">Taux imprimées</div>
    <div class="card__value">{% if taux_imprimees is not none %}{{ taux_imprimees }} %{% else %}—{% endif %}</div>
  </div>
  <div class="card">
    <div class="card__label">Photos prises</div>
    <div class="card__value">{{ stats.nb_photos_total or 0 }}</div>
  </div>
  <div class="card">
    <div class="card__label">Durée moyenne</div>
    <div class="card__value">{{ stats.duree_moyenne_s or 0 }} s</div>
  </div>
  {% for mode, n in (stats.modes or {}).items() %}
  <div class="card">
    <div class="card__label">{{ mode or 'inconnu' }}</div>
    <div class="card__value">{{ n }}</div>
  </div>
  {% endfor %}
</section>

<!-- Étage 4 : historique -->
<section class="panel">
  <h2>Historique par journée</h2>
  {% if historique %}
    <table class="histo-table">
      <tr><th>Date</th><th>Sessions</th><th>Imprimées</th><th class="histo-table__barre-col"></th></tr>
      {% for j in historique %}
      <tr>
        <td>{{ j.date }}</td>
        <td>{{ j.total }}</td>
        <td class="ok">{{ j.printed }}</td>
        <td><div class="histo-table__barre" style="width: {{ j.pct_barre }}%"></div></td>
      </tr>
      {% endfor %}
    </table>
  {% else %}
    <p class="muted">Aucune session enregistrée.</p>
  {% endif %}
  <p class="muted">
    Journal : <code>{{ sessions_path }}</code> · Impressions : <code>{{ print_path }}</code>
  </p>
</section>
{% endblock %}
```

- [ ] **Step 5 : Vérifier le succès**

Run: `pytest test_web_app.py -v`
Expected: PASS — y compris les anciens tests dashboard (`test_sans_sessions_affiche_zero`,
`test_avec_sessions`) ; si l'un d'eux asserte un texte disparu (ex. « Répartition
horaire »), adapter **le test** au nouveau gabarit en conservant son intention.

- [ ] **Step 6 : Commit**

```bash
git add web/routes/dashboard.py web/templates/dashboard.html test_web_app.py
git commit -m "feat(admin): dashboard 4 étages (santé, aujourd'hui, totaux, historique)"
```

---

### Task 3 : Refonte `admin.css` — thème automatique clair/sombre

**Files:**
- Modify: `web/static/admin.css` (remplacement complet)

Contrainte : **tous les sélecteurs existants restent définis** (inventaire :
topbar/nav/logo, content, flashes/flash--*, cards/card--*/card__*, panel, grid-2,
kv, histo (ancien, gardé pour compat), form/form--settings, btn/btn--*, badge/badge--*,
galerie__*, templates__*, reglages, pagination, actions, alerte, muted, etats,
form.inline, code, a, h1/h2) + les nouveaux (pastilles, hero, barres, histo-table).

- [ ] **Step 1 : Remplacer `web/static/admin.css`**

```css
/* admin.css — thème automatique clair/sombre (custom properties).
   Palette validée en maquette (2026-07-14). Aucune ressource externe. */

:root {
  --bg: #f4f6fa;
  --carte: #ffffff;
  --texte: #1e2333;
  --texte2: #8b93a7;
  --bord: #e5e9f2;
  --ombre: 0 2px 8px rgba(30, 40, 70, .08);
  --accent: #6366f1;
  --accent-tx: #ffffff;
  --ok: #16a34a;   --ok-bg: #dcfce7;   --ok-tx: #166534;
  --warn: #d97706; --warn-bg: #fef3c7; --warn-tx: #92400e;
  --err: #dc2626;  --err-bg: #fee2e2;  --err-tx: #991b1b;
  --na-bg: #eceff5; --na-tx: #6b7387;
}

@media (prefers-color-scheme: dark) {
  :root {
    --bg: #0f1218;
    --carte: #181d26;
    --texte: #f2f5f9;
    --texte2: #7a8699;
    --bord: #232a36;
    --ombre: none;
    --accent: #818cf8;
    --accent-tx: #0f1218;
    --ok: #4ade80;   --ok-bg: #14351f;   --ok-tx: #4ade80;
    --warn: #fbbf24; --warn-bg: #3a2c0a; --warn-tx: #fbbf24;
    --err: #f87171;  --err-bg: #3d1418;  --err-tx: #f87171;
    --na-bg: #1f2530; --na-tx: #7a8699;
  }
}

* { box-sizing: border-box; }

body {
  margin: 0;
  background: var(--bg);
  color: var(--texte);
  font-family: -apple-system, system-ui, "Segoe UI", sans-serif;
  line-height: 1.45;
}

a { color: var(--accent); text-decoration: none; }
a:hover { text-decoration: underline; }
h1 { font-size: 1.5rem; margin: 0 0 1rem; }
h2 { font-size: 1.05rem; margin: 0 0 .8rem; color: var(--texte); }
code {
  background: var(--na-bg); color: var(--texte2);
  padding: .1em .4em; border-radius: 6px; font-size: .85em; word-break: break-all;
}
.muted { color: var(--texte2); font-size: .9rem; }
.alerte { color: var(--err); }
.ok { color: var(--ok); font-weight: 600; }
.warn { color: var(--warn); font-weight: 600; }
.err { color: var(--err); font-weight: 600; }

/* --- Barre du haut --- */
.topbar {
  display: flex; align-items: center; justify-content: space-between;
  flex-wrap: wrap; gap: .5rem;
  background: var(--carte); border-bottom: 1px solid var(--bord);
  padding: .7rem 1.2rem; position: sticky; top: 0; z-index: 10;
}
.logo { font-weight: 700; color: var(--texte); }
.nav { display: flex; gap: .2rem; flex-wrap: wrap; }
.nav a { color: var(--texte2); padding: .35rem .7rem; border-radius: 8px; font-weight: 500; }
.nav a:hover { color: var(--texte); background: var(--bg); text-decoration: none; }

.content { max-width: 960px; margin: 0 auto; padding: 1.2rem; }

/* --- Flashes --- */
.flashes { list-style: none; padding: 0; margin: 0 0 1rem; }
.flash { padding: .6rem .9rem; border-radius: 10px; margin-bottom: .4rem; font-weight: 500; }
.flash--success { background: var(--ok-bg); color: var(--ok-tx); }
.flash--error { background: var(--err-bg); color: var(--err-tx); }
.flash--info { background: var(--na-bg); color: var(--na-tx); }

/* --- Panneaux & grilles --- */
.panel {
  background: var(--carte); border: 1px solid var(--bord); border-radius: 14px;
  box-shadow: var(--ombre); padding: 1rem 1.1rem; margin-bottom: 1rem;
}
.grid-2 { display: grid; grid-template-columns: 1fr 1fr; gap: 1rem; }
@media (max-width: 640px) { .grid-2 { grid-template-columns: 1fr; } }

/* --- Cartes KPI --- */
.cards {
  display: grid; grid-template-columns: repeat(auto-fill, minmax(140px, 1fr));
  gap: .7rem; margin-bottom: 1rem;
}
.card {
  background: var(--carte); border: 1px solid var(--bord); border-radius: 12px;
  box-shadow: var(--ombre); padding: .8rem .9rem;
}
.card__label {
  color: var(--texte2); font-size: .68rem; text-transform: uppercase;
  letter-spacing: .08em; margin-bottom: .15rem;
}
.card__value { font-size: 1.6rem; font-weight: 700; }
.card--ok .card__value { color: var(--ok); }
.card--warn .card__value { color: var(--warn); }
.card--err .card__value { color: var(--err); }

/* --- Étage 1 : pastilles santé --- */
.pastilles { display: flex; gap: .45rem; flex-wrap: wrap; margin-bottom: 1rem; }
.pastille {
  border-radius: 999px; padding: .3rem .8rem; font-size: .82rem; font-weight: 600;
}
.pastille--ok { background: var(--ok-bg); color: var(--ok-tx); }
.pastille--warn { background: var(--warn-bg); color: var(--warn-tx); }
.pastille--err { background: var(--err-bg); color: var(--err-tx); }
.pastille--na { background: var(--na-bg); color: var(--na-tx); }

/* --- Étage 2 : héros « aujourd'hui » --- */
.hero { text-align: center; }
.hero__label {
  color: var(--texte2); font-size: .72rem; text-transform: uppercase; letter-spacing: .08em;
}
.hero__valeur { font-size: 3rem; font-weight: 800; line-height: 1.1; }
.hero__unite { font-size: 1rem; color: var(--texte2); font-weight: 400; }
.hero__detail { font-size: .95rem; margin-top: .2rem; }

.barres {
  display: flex; align-items: flex-end; gap: 4px;
  height: 90px; margin: .8rem auto .2rem; max-width: 480px;
}
.barres__col { flex: 1; display: flex; flex-direction: column; justify-content: flex-end; height: 100%; }
.barres__bar { background: var(--accent); border-radius: 3px 3px 0 0; min-height: 2px; }
.barres__h { color: var(--texte2); font-size: .62rem; text-align: center; margin-top: 2px; }

/* --- Étage 4 : historique --- */
.histo-table { width: 100%; border-collapse: collapse; font-size: .9rem; }
.histo-table th {
  text-align: left; color: var(--texte2); font-size: .68rem;
  text-transform: uppercase; letter-spacing: .08em; font-weight: 500; padding-bottom: .3rem;
}
.histo-table td { padding: .3rem 0; border-top: 1px solid var(--bord); }
.histo-table__barre-col { width: 38%; }
.histo-table__barre { height: 7px; background: var(--accent); border-radius: 4px; min-width: 2px; }

/* --- Ancien histogramme horizontal (compat, plus utilisé par le dashboard) --- */
.histo { list-style: none; padding: 0; margin: 0; }
.histo li { display: flex; align-items: center; gap: .5rem; margin-bottom: .25rem; }
.histo__hour { width: 2.4rem; color: var(--texte2); font-size: .85rem; }
.histo__bar { height: 9px; background: var(--accent); border-radius: 4px; }
.histo__n { color: var(--texte2); font-size: .85rem; }

/* --- Listes clé/valeur --- */
.kv { list-style: none; padding: 0; margin: 0; }
.kv li {
  display: flex; justify-content: space-between; gap: 1rem;
  padding: .4rem 0; border-bottom: 1px solid var(--bord);
}
.kv li:last-child { border-bottom: none; }
.kv li span { color: var(--texte2); }

/* --- Formulaires --- */
.form { display: flex; flex-direction: column; gap: .7rem; max-width: 460px; }
.form label { display: flex; flex-direction: column; gap: .25rem; color: var(--texte2); font-size: .88rem; }
.form input[type="text"],
.form input[type="number"],
.form select {
  background: var(--bg); color: var(--texte);
  border: 1px solid var(--bord); border-radius: 8px; padding: .5rem .6rem; font-size: .95rem;
}
.form--settings { max-width: none; }

/* --- Boutons --- */
.btn, button {
  background: var(--na-bg); color: var(--texte);
  border: 1px solid var(--bord); border-radius: 8px;
  padding: .45rem .9rem; font-size: .9rem; font-weight: 600; cursor: pointer;
}
.btn:hover, button:hover { filter: brightness(1.06); }
.btn--primary { background: var(--accent); color: var(--accent-tx); border-color: transparent; }
.btn--primary:hover { filter: brightness(1.1); }
.btn--danger { background: var(--err-bg); color: var(--err-tx); border-color: transparent; }
.btn--danger:hover { filter: brightness(1.08); }
form.inline { display: inline; margin: 0; }

/* --- Badges --- */
.badge {
  display: inline-block; border-radius: 999px; padding: .12rem .55rem;
  font-size: .72rem; font-weight: 600; background: var(--na-bg); color: var(--na-tx);
}
.badge--10x15 { background: var(--accent); color: var(--accent-tx); }
.badge--strip { background: var(--warn-bg); color: var(--warn-tx); }
.badge--actif { background: var(--ok-bg); color: var(--ok-tx); }

/* --- Galerie --- */
.galerie {
  display: grid; grid-template-columns: repeat(auto-fill, minmax(180px, 1fr));
  gap: .8rem; list-style: none; padding: 0;
}
.galerie__item {
  background: var(--carte); border: 1px solid var(--bord); border-radius: 12px;
  box-shadow: var(--ombre); overflow: hidden;
}
.galerie__item img { width: 100%; display: block; }
.galerie__meta { padding: .5rem .6rem; font-size: .8rem; color: var(--texte2); }
.galerie__taille { float: right; }
.pagination { display: flex; gap: .6rem; justify-content: center; margin: 1rem 0; }

/* --- Templates --- */
.templates { list-style: none; padding: 0; display: flex; flex-direction: column; gap: .7rem; }
.templates__item {
  display: flex; gap: .8rem; align-items: flex-start;
  background: var(--carte); border: 1px solid var(--bord); border-radius: 12px;
  box-shadow: var(--ombre); padding: .7rem;
}
.templates__item--actif { border-color: var(--ok); }
.templates__item img {
  width: 96px; border-radius: 8px; background: var(--na-bg); flex-shrink: 0;
}
.templates__info h3 { margin: 0 0 .25rem; font-size: 1rem; }
.actions { display: flex; gap: .5rem; margin-top: .4rem; flex-wrap: wrap; }
.etats { list-style: none; padding: 0; }
.etats li { margin: .4rem 0; display: flex; align-items: center; gap: .6rem; flex-wrap: wrap; }

/* --- Réglages --- */
.reglages { width: 100%; border-collapse: collapse; }
.reglages th, .reglages td { text-align: left; padding: .45rem .3rem; border-bottom: 1px solid var(--bord); }
.reglages th { color: var(--texte2); font-size: .8rem; }
.reglages input[type="text"],
.reglages input[type="number"] {
  background: var(--bg); color: var(--texte);
  border: 1px solid var(--bord); border-radius: 8px; padding: .35rem .5rem;
}
```

- [ ] **Step 2 : Vérifier la suite + le rendu réel**

Run: `pytest -q && ruff check .`
Expected: tous verts.

Smoke visuel : `PHOTOBOOTH_ADMIN_PASS=smoke PHOTOBOOTH_ADMIN_PORT=8099 python3 -m web.app`
puis ouvrir `http://127.0.0.1:8099/dashboard/` (et /gallery/, /templates/, /settings/)
dans le Browser pane — vérifier clair ET sombre (préférence système), aucune page cassée.

- [ ] **Step 3 : Commit**

```bash
git add web/static/admin.css
git commit -m "feat(admin): thème automatique clair/sombre (custom properties, zéro CDN)"
```

---

### Task 4 : Docs + vérification finale

**Files:**
- Modify: `docs/ADMIN.md`

- [ ] **Step 1 : Mettre à jour la puce Dashboard dans `docs/ADMIN.md`**

Remplacer :

```markdown
- **Dashboard** : stats de sessions, état disque/CPU, dossier d'impression.
```

par :

```markdown
- **Dashboard** : santé matériel en un coup d'œil (imprimantes, disque, CPU),
  compteurs du jour avec activité par heure, totaux (taux d'impression, photos,
  durées, modes) et historique par journée. Thème clair/sombre automatique
  (suit le réglage du navigateur/téléphone).
```

- [ ] **Step 2 : Suite complète + lint + couverture**

Run: `pytest -q && ruff check . && pytest -q --cov --cov-report=term | tail -3`
Expected: tout vert, couverture totale ≥ 75 %.

- [ ] **Step 3 : Commit**

```bash
git add docs/ADMIN.md
git commit -m "docs: ADMIN.md — dashboard 4 étages + thème automatique"
```

---

## Auto-revue (faite à l'écriture du plan)

- **Couverture spec** : fonctions pures (T1), collecte+contrat de rendu 4 étages (T2),
  thème auto + restyle global sans changement HTML des autres pages (T3), docs (T4),
  gestion d'erreurs (zéro session T2 test 3, ts malformé T1, CUPS absent = chaîne
  d'is_ready affichée en pastille rouge — testé via mock T2 test 2). ✔
- **Sélecteurs CSS** : inventaire complet de l'ancien fichier repris dans le nouveau. ✔
- **Types cohérents** : `sante` = liste de dicts `{libelle, etat, detail}` (T2 code + gabarit),
  `historique` = `{date, total, printed, pct_barre}` (T2 code + gabarit), `jour` = sortie
  `stats_du_jour` (T1) consommée par le gabarit (T2). ✔
- **Pas de placeholder** : code complet à chaque étape. ✔
