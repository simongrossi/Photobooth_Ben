"""web/ — interface admin web optionnelle du photobooth.

Module totalement indépendant du kiosque pygame :
- N'importe que `core/*`, `config`, `stats.py`, `status.py`
- N'importe jamais `Photobooth_start`, ni `ui/*`
- Déployé comme service systemd séparé (deploy/photobooth-admin.service)

Voir docs/ADMIN.md pour l'installation et l'usage.
"""
