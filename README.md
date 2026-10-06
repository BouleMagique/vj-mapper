# VJ Mapper

Mapping 2D audio-réactif pour la projection en soirée : on trace des **barres de lumière** sur une photo de la surface (porte de garage, mur, structure), on les range en **groupes**, et chaque groupe joue un **effet** piloté par une **bande audio**. Sortie plein écran sur le projo.

> Statut : **V0** (2026-10-06) — tracé de barres, 6 effets, entrée son live, sortie projo, mode calibration. Pas encore de MIDI.

## Lancer

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

## Stack

Python · ModernGL (rendu) · GLFW (fenêtres) · Dear ImGui via imgui-bundle (interface) · sounddevice + numpy (audio).
