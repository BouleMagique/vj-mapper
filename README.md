# VJ Mapper

Mapping 2D audio-réactif pour la projection en soirée : on trace des **barres de lumière** sur une photo de la surface (porte de garage, mur, structure), on les range en **groupes**, et chaque groupe joue un **effet** piloté par une **bande audio**. Sortie plein écran sur le projo.

> Statut : **V0** (2026-10-06) — tracé de barres, 6 effets, entrée son live, sortie projo, mode calibration. Pas encore de MIDI.

## Télécharger

Page **[Releases](https://github.com/BouleMagique/vj-mapper/releases)** :

| OS | Fichier | Lancer |
|----|---------|--------|
| **Linux** | `VJMapper-x86_64.AppImage` | `chmod +x` puis double-clic |
| **Windows** | `VJMapper.exe` | double-clic (SmartScreen : *Informations complémentaires → Exécuter quand même*) |
| **macOS Apple Silicon** | `VJMapper-macos-arm64.zip` | dézipper, `xattr -dr com.apple.quarantine VJMapper.app`, clic droit → Ouvrir |
| **macOS Intel (12+)** | `VJMapper-macos-x86_64.zip` | idem — compilé pour Monterey (Mac Pro 2013) |

Version packagée : les scènes sont dans `~/Documents/VJ Mapper` (la scène d'exemple y est copiée au premier lancement).
macOS demande l'accès au micro au premier *● Live* : nécessaire pour lire BlackHole.

## Lancer depuis les sources

```bash
python -m venv ~/Envs/vj-mapper
~/Envs/vj-mapper/bin/pip install -r requirements.txt
~/Envs/vj-mapper/bin/python main.py
```

## Utilisation

1. **Scène** → « Modèle porte de garage » (ou tracer avec l'outil *Tracer*, `Maj` = horizontal/vertical).
2. **Photo de la surface** : charger une photo prise depuis la position du projo, pour placer les barres.
3. **Sortie** → choisir l'écran du projo → *Ouvrir la sortie* → cocher **Mode calibration** et ajuster les barres
   dans le canevas en regardant le mur (rouge = début, vert = fin).
4. **Groupes** : effet, bande audio, couleurs, vitesse, *Décalage* (déphasage entre barres → vagues).
5. **Audio** : choisir la source (« Sortie PC : … » = ce que joue la machine) → *● Live*.
   *Simulation 128 BPM* pour régler sans musique.
6. **Enregistrer…** la scène (JSON, dans `scenes/`).

| Effet | Ce que ça fait |
|-------|----------------|
| Pulse | toute la barre suit la bande |
| Chase | pointillés qui défilent |
| VU | remplissage façon vu-mètre, pointe brillante |
| Comète | une étincelle parcourt la barre à chaque kick |
| Strobe | flash sur kick (le décalage crée une onde) |
| Flow | dégradé couleur 1 → 2 qui défile |

Canevas : clic = sélectionner, glisser une extrémité ou la barre, `Suppr` supprimer, flèches = déplacer (`Maj` ×10).

### Audio par plateforme
- **Linux** (PipeWire/Pulse) : les sorties apparaissent comme « Sortie PC : … ».
- **macOS** : [BlackHole](https://github.com/ExistentialAudio/BlackHole) + périphérique multi-sortie.
- **Windows** : « Mixage stéréo » ou VB-Cable.

## Builds

```bash
bash build-linux.sh                      # -> dist/VJMapper-x86_64.AppImage
bash build-macos.sh                      # -> dist/VJMapper-macos-<arch>.zip (arch native)
TARGET_ARCH=x86_64 bash build-macos.sh   # Intel/macOS 12 depuis Apple Silicon (Rosetta)
```
Windows : CI GitHub (`.github/workflows/build-windows.yml`), déclenchée par un tag `v*`.
Build Intel : imgui-bundle n'a pas de wheel x86_64 pour macOS < 14, il est compilé depuis les sources (long).

## Stack

Python · ModernGL (rendu) · GLFW (fenêtres) · Dear ImGui via imgui-bundle (interface) · sounddevice + numpy (audio).
