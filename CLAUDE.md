# VJ Mapper — CLAUDE.md

## Objectif
Appli VJ séparée de l'Audio-Visualizer (« piste B ») : mapping 2D de barres lumineuses audio-réactives
sur une surface réelle, projetée en soirée. Premier cas : porte de garage grise à renforts verticaux /
horizontaux. Machine cible en soirée : **Mac Pro 2013** (macOS Monterey) + projo ; dev sur la workstation CachyOS.

**Cible d'exécution : workstation / Mac (GPU + affichage) — jamais dans le LXC devbox.**

## État
> **Plan complet post-V0 : `PLAN.md`** (reprendre à « §4 Checklist de reprise »).

- [x] V0 (2026-10-06) : scène (barres + groupes, JSON), 6 effets GLSL, éditeur ImGui (tracer, sélection,
      drag, Maj = H/V, photo de fond), entrée son live + simulation, sortie projo plein écran vsync, calibration.
- [ ] Test réel Mac Pro + projo
- [ ] V1 : MIDI learn (contrôleur) + MIDI Clock Traktor
- [ ] V2 : formes (polygones), shader par forme, effets suivant le contour (distance au bord), correction 4 coins
- [ ] Scènes / presets enchaînables en live

## Décisions techniques
- **Pas de Qt** (contrairement à l'AV) : fenêtre de sortie = 2ᵉ fenêtre GLFW qui **partage le contexte**
  de la fenêtre de contrôle → la texture de composition est affichée directement (`external_texture`), sans copie CPU.
- **Dear ImGui (imgui-bundle, backend Python + PyOpenGL)** : UI immédiate, adaptée à un outil live ; pas de
  framework widget à maintenir. Justification doctrine : Qt aurait remis les problèmes de contexte de l'AV.
- **Wayland** : moderngl ne détecte un contexte existant que via GLX → GLFW forcé en X11 (`PLATFORM_X11`)
  et `PYOPENGL_PLATFORM=x11` (même piège que l'AV, branche `live`).
- **OpenGL 3.3 core + forward compat** partout (seul profil moderne sur macOS).
- Une barre = un quad (u le long, v en travers), tout est redessiné en un draw call additif par frame.
  Coordonnées normalisées à la sortie, épaisseur en fraction de la hauteur → indépendant de la résolution projo.
- Audio : capture reprise de `Audio-Visualizer/core/live_input.py` (copie assumée, projets indépendants) ;
  analyse bass/mid/high/kick reprise du test TouchDesigner (auto-gain par bande, onset kick 40-120 Hz).
- Pas de MIDI dans l'Audio-Visualizer : tout le contrôle live va ici.

## Lancer
`~/Envs/vj-mapper/bin/python main.py` (venv : `requirements.txt`).
