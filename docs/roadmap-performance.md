# Roadmap de Performance — Photobooth Ben

Ce document détaille les chantiers d'optimisation des performances et de la réactivité du photobooth pour garantir une expérience fluide (boucle principale à 30 FPS et transitions rapides) sur le Raspberry Pi.

---

## Synthèse des Chantiers d'Optimisation

| Chantier | Cible / Fichiers | Objectif & Bénéfice | Complexité | Statut |
|---|---|---|---|---|
| **1. Décodage JPEG rapide (Validation)** | `Photobooth_start.py` | Utiliser `.draft()` pour charger l'aperçu de validation. Temps de transition : **~3 s → < 150 ms**. | Simple | Terminé |
| **2. Scaling LiveView asynchrone (OpenCV)** | `core/camera.py`, `Photobooth_start.py` | Déporter le redimensionnement du LiveView dans le thread de fond via `cv2.resize`. Libère le thread principal. | Moyen | Terminé |
| **3. Cache fonds/overlays transformés** | `core/montage.py` | Cacher directement les backgrounds et overlays déjà tournés et mis à l'échelle. | Simple | Terminé |
| **4. Choix d'interpolation selon le contexte** | `core/montage.py` | Utiliser `BILINEAR` ou `BICUBIC` pour les previews, réserver `LANCZOS` pour l'impression finale HD. | Simple | Terminé |
| **5. Cache de rendu de texte ombré** | `ui/helpers.py` | Éviter de réallouer des surfaces et de restituer les glyphes de polices à chaque frame. | Simple | Terminé |

---

## 1. Décodage JPEG rapide lors de la Validation

### Contexte
Dans `Photobooth_start.py` (état `VALIDATION`), la dernière photo prise est chargée pour servir d'aperçu d'écran :
```python
with Image.open(derniere_photo) as raw_img:
    oriented = ImageOps.exif_transpose(raw_img)
pil_img = ImageOps.fit(oriented, (largeur_cible, hauteur_cible), Image.Resampling.LANCZOS)
```
Ce traitement sur une image brute de 24 Mpx (rotation et fit Lanczos) fige le Raspberry Pi.

### Optimisation
Appliquer `raw_img.draft("RGB", (largeur_cible, hauteur_cible))` immédiatement après l'ouverture. Le décodeur JPEG décompressera uniquement la résolution minimale requise, ce qui rendra l'opération instantanée.

---

## 2. Scaling LiveView asynchrone (OpenCV)

### Contexte
Le flux vidéo LiveView acquiert des frames à 12-18 FPS. Pygame redimensionne chaque nouvelle surface logiciellement sur le thread principal :
```python
derniere_preview_affichee = pygame.transform.scale(surf, (WIDTH, HEIGHT))
```

### Optimisation
Faire le redimensionnement dans le thread d'arrière-plan `camera-liveview` (dans `core/camera.py`) en appelant `cv2.resize` d'OpenCV (hautement optimisé pour ARM/NEON). Le thread Pygame principal reçoit une surface prête à bliter aux dimensions de l'écran, sans calcul supplémentaire.

---

## 3. Mise en cache des fonds/overlays transformés

### Contexte
À chaque montage (preview ou impression), le programme recharge le background et l'overlay, effectue des rotations et les redimensionne à la taille cible.

### Optimisation
Adapter le dictionnaire `_asset_cache` dans `MontageBase` pour inclure la taille cible et la rotation dans la clé de cache, afin de conserver l'image prête à être fusionnée.

---

## 4. Choix de l'interpolation selon le contexte

### Contexte
L'interpolation de haute qualité `LANCZOS` est appliquée systématiquement via `_composer`, même pour les miniatures écran de prévisualisation.

### Optimisation
Ajouter un paramètre `resampling` dans la méthode interne de composition de `MontageBase`. Les previews utiliseront une interpolation rapide `BILINEAR` ou `BICUBIC`, tandis que les sorties d'impression HD conserveront la qualité maximale avec `LANCZOS`.

---

## 5. Cache de rendu de texte ombré

### Contexte
La fonction `draw_text_shadow_soft` dessine à chaque frame l'ombre noire transparente (en créant une `pygame.Surface` alpha temporaire et en faisant deux rendus de police) pour les textes d'information (ex: compteur "PHOTO N/3").

### Optimisation
Introduire un cache local de surfaces texturées ombrées pour réutiliser directement la texture d'interface tant que le texte ne change pas, évitant la pression sur le ramasse-miettes.
