# VJ Mapper — Plan d'implémentation post-V0

> Généré le 2026-10-07 (sous-agent Plan) à partir du code au commit `4f15db4`. Point de reprise : **§4 Checklist de reprise**.
> Remarque : le venv `~/Envs/vj-mapper` contient déjà `mido 1.3.3` et `python-rtmidi 1.5.8`, pas dans `requirements.txt`.

---

## 1. État V0 et lacunes concrètes

**Ce qui marche** : scène barres/groupes JSON, 6 effets (`strip.frag`), éditeur ImGui, audio live + simulation 128 BPM, sortie projo (2ᵉ fenêtre GLFW, contexte partagé via `external_texture`), calibration.

| # | Où | Problème | Gravité live |
|---|----|----------|--------------|
| 1 | `app.py:97-119` | Aucune isolation d'erreur dans la boucle : une exception dans l'UI, le rendu ou l'audio ferme l'app → projo noir | **Critique** |
| 2 | `editor.py:136-147,153` | `pfd.open_file/save_file(...).result()` bloque la boucle → **la sortie projo gèle** pendant le dialogue | **Critique** |
| 3 | `output.py:65-67` | Échap ferme la sortie (appui accidentel = noir) ; Cmd+Q sur macOS quitte sans confirmation | **Critique** |
| 4 | `app.py:57`, `editor.py:53-54` | Démarrage toujours sur le modèle porte de garage ; rien de persisté (dernière scène, écran, source audio) → après crash, tout refaire à la main | Haute |
| 5 | `scene.py:66-68` | Save non atomique, pas de `.bak` ; `scene.py:70-85` + `editor.py:139` : JSON invalide = crash ; `app.py:73` : image illisible = crash (PIL) | Haute |
| 6 | `scene.py:13,28-29,43` | `effect`, `band`, `group` = **index entiers** : insérer un effet ou réordonner les groupes casse les vieux fichiers. Pas d'`id` stable (impossible d'y accrocher des mappings MIDI ou des looks). Pas de `version` dans le JSON | Haute (bloque V1/V3) |
| 7 | `scene.py:51` | `background` = chemin absolu, casse entre Linux et Mac | Moyenne |
| 8 | `audio.py:149-188,229,239` | Constantes appliquées **par frame** (`AGC_DECAY .998`, `SMOOTH`, `kick *= .80`) : le comportement change avec le refresh du projo (50/60/75 Hz) ou une chute de FPS | Moyenne |
| 9 | `audio.py:113` | `status` ignoré. Si BlackHole ou le périphérique disparaît, le flux meurt sans rien dire, sans reconnexion. Liste PortAudio en cache : il faut `sd._terminate()/_initialize()` pour voir un nouveau périphérique | Moyenne |
| 10 | `render.py:91` | `time.perf_counter()` en dur → aucun rendu déterministe pour les tests. `render.py:53-88` reconstruit la géométrie en Python à chaque frame (~20 µs/barre) : OK jusqu'à ~200 barres | Basse |
| 11 | `render.py:83` | Slot `in_p2.y` **libre** → peut porter la base de temps beat-sync en V1 sans changer le layout des vertex | Opportunité |
| 12 | `output.py:62` | `external_texture` lié une seule fois : un `compositor.resize()` après ouverture laisse une texture morte → rappeler `set_source` | Basse |
| 13 | `app.py:55-56` | `scenes/` créé à côté du package : en lecture seule dans un `.app` PyInstaller | Haute (packaging) |
| 14 | `app.py:81-84` | Échec d'ouverture de la sortie avalé sans message ; `editor.py:228-233` : écran choisi par **index**, et l'ordre peut changer d'un branchement à l'autre | Moyenne |
| 15 | `editor.py:48,300-307` | Une seule sélection, pas d'undo, magnétisme limité à H/V avec Maj | Confort |
| 16 | `requirements.txt` | Aucune version épinglée. Pas de `tests/` ni `tools/` : le script de validation headless de la V0 n'a pas été versionné | Moyenne |

**Points macOS non vérifiés** (rien n'a encore tourné sur le Mac Pro)
- Vsync sur 2 fenêtres : `swap_interval(0)` côté contrôle et `1` côté sortie (`app.py:87`). Un swap avec vsync sur une fenêtre masquée se comporte mal sous macOS.
- Barre de menus visible sur le projo si « Les écrans disposent de Spaces distincts » est actif.
- Permission micro (TCC) pour lire BlackHole.
- HiDPI : la taille du video mode est en points, pas en pixels.
- Disponibilité des wheels `imgui-bundle` / `python-rtmidi` en x86_64 sur macOS 12 pour la version de Python choisie.

---

## 2. Feuille de route

Ordre : **H0 → V1 → V2 → V3 → H1/packaging**. H0 est court mais obligatoire : sans ids ni schéma versionné, ni le MIDI learn ni les looks ne tiennent. Blackout et dimmer passent dès la V1, parce que ce sont les premières cibles MIDI dont on a besoin en soirée.

Arborescence cible :
```
vjmapper/
  app.py        boucle, sous-systèmes, isolation d'erreurs
  scene.py      dataclasses + ids + schéma + migrations + save atomique
  state.py      dossiers user (config/logs/autosave), state.json
  geom.py       seg dist, polygones, homographie, snapping (numpy pur)
  undo.py       historique par snapshots
  audio.py      + normalisation dt, reconnexion, spectre 32 bandes (V2)
  clock.py      BeatClock : MIDI Clock / tap / simu
  midi.py       ports rtmidi, parsing, queue
  control.py    registre de paramètres, bindings, learn, soft takeover
  render.py     strips (existant) + master pass
  shapes.py     rendu des formes (V2)
  fills.py      registre des remplissages + compilation isolée (V2)
  show.py       looks, cues, crossfade (V3)
  editor/       découpé quand editor.py dépasse ~600 lignes : canvas.py, panels.py, live.py
  shaders/      strip.*, blit/warp.*, master.frag, shape.*, shape_common.glsl, fills/*.glsl
tests/          unittest stdlib + rendu headless
tools/          gl_probe.py, midi_clock_sim.py
build-macos.sh, run-live.sh
```

### H0 : fondations (1 session)

**Objectif** : code testable, scène versionnée, pas d'écran noir sur incident, état retrouvé après redémarrage.

**Tâches, dans l'ordre**
1. *(Si l'utilisateur valide)* Déplacer le repo vers `/mnt/dev/DEV/vj-mapper`, puis `gh repo create BouleMagique/vj-mapper --private --source . --push`. Le venv reste dans `~/Envs`. Mettre à jour les chemins dans CLAUDE.md et README. Ajouter `vj-mapper` au tableau de `/mnt/dev/DEV/CLAUDE.md` **seulement avec l'accord de l'utilisateur**.
2. **Rendu déterministe**
   - `Compositor.render(scene, feats, now, calib)` reçoit `now` au lieu de l'appeler.
   - `LiveAudio.update(now, dt)`.
   - Analyzer normalisé en dt : `a = 1 - (1-c)**(dt*60)` pour SMOOTH, AGC et la retombée du kick.
3. **`tools/gl_probe.py`**
   - Crée un contexte standalone `require=330`.
   - Affiche `GL_VERSION`, `GL_RENDERER`, `MAX_FRAGMENT_UNIFORM_COMPONENTS`, `MAX_TEXTURE_SIZE`.
   - Compile tous les shaders et rend `example_garage_door.json` dans un PNG.
   - C'est le **premier truc à lancer sur le Mac**.
4. **`tests/`** (`unittest` stdlib)
   - `test_render.py` : rendu 320×180 à `now` et features fixes. Vérifier : pixel au centre d'une barre > seuil, pixel entre deux barres ≈ 0, calibration = rouge/vert aux extrémités.
   - `test_scene.py` : aller-retour save/load + migration v0→v1.
   - `test_audio.py` : sinus 60 Hz pulsé à 128 BPM → kicks détectés à ±1 par mesure.
5. **Schéma v1** (`scene.py`)
   - `"version": 1`.
   - `Group.id` et `Strip.id` = `uuid4().hex[:8]`.
   - `effect` et `band` en clés texte (`pulse|chase|vu|comet|strobe|flow`, `bass|mid|high|kick|level`).
   - `Strip.group` devient l'id du groupe.
   - `migrate(data)` en chaîne `_v0_to_v1`.
   - Sauvegarde atomique (`tmp` + `os.replace`) et `.bak`.
   - `background` relatif au fichier de scène quand c'est possible.
   - Le chargement lève `SceneError`, affichée dans un toast UI.
   - Le shader garde un entier pour l'effet : correspondance au moment de construire les vertex (`EFFECT_KEYS.index`).
6. **Isolation d'erreurs** (`app.py`)
   - Trois `try` indépendants : audio+rendu, UI, sortie. Une exception est loguée (traceback + `faulthandler.enable(file)`), un compteur d'erreurs s'affiche dans l'UI, la frame continue.
   - Si le rendu échoue, la sortie garde la dernière texture valide.
   - Si l'UI échoue, passer par la récupération d'erreurs ImGui 1.92 (`io.config_error_recovery*`). **Noms exacts à vérifier dans imgui-bundle 1.92.9**, et vérifier que `IM_ASSERT` remonte bien en exception Python.
7. **Dialogues non bloquants** : garder l'objet `pfd` et le sonder avec `.ready()` à chaque frame (`editor.py:136-153`).
8. **Protection de la sortie**
   - Échap ne ferme plus. Fermeture par Maj+Échap ou depuis l'UI.
   - Callback de fermeture sur la fenêtre de contrôle : Cmd+Q et la croix demandent une confirmation (`glfw.set_window_should_close(win, False)` + modale).
9. **`state.py`**
   - Dossier user : `~/.config/vj-mapper` sous Linux, `~/Library/Application Support/VJ Mapper` sous macOS.
   - `state.json` : dernière scène, écran (nom + position + taille, pas l'index), plein écran, libellé de la source audio, ports MIDI.
   - Autosave toutes les 10 s si la scène est modifiée → `autosave.json`.
   - `main.py --restore` : recharge tout, rouvre la sortie, relance l'audio.
   - `scenes_dir` passe dans le dossier user ; les exemples sont copiés au premier lancement.
10. **Panneau Perf** : temps par section (audio, vertices, GL, UI, sortie) en moyenne glissante, max sur 2 s, FPS.
11. **Audio robuste** : `status` remonté ; si aucun callback depuis 1 s, reconnexion périodique sur le même libellé de source.

**Critères d'acceptation**
- `python -m unittest` passe en headless sur CachyOS.
- Un `raise` volontaire dans `editor.draw` ne coupe pas la sortie.
- Un dialogue ouvert ne gèle pas la sortie.
- `kill -9` puis `--restore` remet la sortie sur le bon écran avec la scène autosauvée.
- Une scène V0 se charge et se resauve en v1.

### V1 : MIDI learn + MIDI Clock + masters (2-3 sessions)

**Ce que voit l'utilisateur**
- **Onglet Live** (vue opérateur) : BPM et sa source, LED de beat (4 pas), **Tap** (Espace), **Resync « 1 »**, dimmer master, **Blackout** (B), faders d'intensité par groupe, pads de déclenchement manuel par groupe.
- **Onglet MIDI** : choix des ports (mémorisés par nom), **Learn** (Ctrl+L), liste des bindings éditables et supprimables, moniteur des 10 derniers messages, LED d'activité.
- **Learn** : on active Learn, on clique un widget (il se surligne), on bouge un contrôle physique, c'est assigné. Badge « M » sur les widgets mappés. Clic droit → « Apprendre MIDI / Oublier ».
- **Par groupe** :
  - **Sync** : libre / beat ;
  - **Rate** : 1/4, 1/2, 1, 2, 4 ou 8 beats ;
  - **Déclencheur** : kick / beat / mesure / manuel ;
  - deux nouveaux effets : **Step** (une barre par beat, dans l'ordre du groupe) et **Alterné** (pairs/impairs un beat sur deux).

**Architecture**
- **`midi.py`, `MidiHub`**
  - `python-rtmidi` directement, sans mido : le parsing des octets de statut tient en ~30 lignes.
  - Un `rtmidi.MidiIn` par port. Activer `ignore_types(timing=False)`, sinon les 0xF8 sont filtrés.
  - Le callback (thread rtmidi) fait seulement `queue.SimpleQueue.put((time.perf_counter(), port, bytes))`. Le thread principal vide la queue en début de frame.
  - Nouveau scan des ports toutes les 2 s, réouverture automatique par nom.
  - `MidiOut` optionnel pour le retour LED (nanoKONTROL2 en mode CC).
- **`clock.py`, `BeatClock`**
  - `on_tick(t)` (0xF8, 24 ppqn), `on_start` (0xFA : beat = 0), `on_continue`, `on_stop`, `on_spp`.
  - BPM : régression linéaire sur les ~48 derniers ticks, ticks aberrants (> 3σ) rejetés, affichage lissé.
  - `beat` (float continu) = ticks/24 + extrapolation depuis le dernier tick, plafonnée à 1/24 de beat.
  - `phase_offset_ms` et `downbeat_offset`, réglés par **Resync** (« maintenant = 1 »).
  - Sources par priorité : `midi` (tick reçu < 0,5 s) > `tap` (moyenne des 4 derniers intervalles, reset après 2 s sans tap) > `sim` (BPM réglable, remplace la simu fixe à 128).
  - Expose `ClockState(bpm, beat, phase, bar_phase, source, running)`.
- **`control.py`**
  - `Param(target, kind: continuous|toggle|trigger|select, lo, hi, get, set)`, construit par `build_registry(app)` à chaque changement de scène.
  - **Cibles par slot de groupe**, pas par id : `group#1.intensity`, `.speed`, `.hue`, `.effect` (select ou cycle), `.enabled`, `.trigger`. Un même contrôleur pilote « groupe 1..8 » quelle que soit la scène.
  - Autres cibles : `master.dimmer`, `master.blackout`, `master.hue`, `clock.tap`, `clock.resync`, `scene.next/prev` (puis en V3 `look.recall:n`, `cue.go`).
  - `Binding(port|"*", type: cc|note, ch, num, target, mode: abs|rel|toggle|momentary|trigger, lo, hi, curve)`.
  - Bindings **globaux** (propres au rig) dans `<user>/midi_map.json` (`"version": 1`), pas dans la scène.
  - Soft takeover pour les faders absolus : la valeur n'est prise qu'une fois que le fader a croisé la valeur courante.
  - Les changements venus du MIDI ne vont pas dans l'undo.
- **Groupe** (schéma v1, champs ajoutés) : `sync: "free"|"beat"`, `rate: float`, `trigger: "kick"|"beat"|"bar"|"manual"`, `hue: float`.
- **Rendu**
  - `since` par groupe (secondes depuis le dernier déclenchement selon `trigger`) dans `in_p1.z`.
  - `tbase` (`beat*rate` en mode sync, sinon `u_time*speed`) dans `in_p2.y`.
  - `strip.frag` : Chase et Flow utilisent `tbase` ; effets 6 (Step) et 7 (Alterné) ; `uniform float u_master`.
  - Blackout : la sortie dessine du noir en dur, ce qui marche même si le compositeur est cassé.
- **`App.master`** : `Master(dimmer=1.0, blackout=False, hue=0.0)`, persisté dans `state.json`.

**Tâches, dans l'ordre**
1. `python-rtmidi` dans `requirements.txt`.
2. `midi.py` + `tools/midi_clock_sim.py` : port virtuel qui émet clock, start et CC à N BPM, avec jitter réglable. Permet de développer sans Traktor.
3. `clock.py` + `tests/test_clock.py` : à 128 BPM avec ±2 ms de jitter → erreur BPM < 0,2, erreur de phase < 0,02 beat, convergence en < 2 s. Tester aussi le tap tempo et le stop/start.
4. Master (dimmer, blackout) + `u_master` + garde-fou côté sortie.
5. sync/rate/trigger/hue, `since`/`tbase` par groupe, effets Step/Alterné. Test headless : position du chase décalée comme attendu entre beat = 0,5 et beat = 1,0.
6. `control.py` + `tests/test_control.py`.
7. UI : onglets Live et MIDI, helper `learnable(target)`.
8. README « Setup Traktor » :
   - activer IAC (Configuration audio et MIDI → Studio MIDI → IAC → en ligne) ;
   - Traktor Preferences → MIDI Clock → **Send MIDI Clock** + bouton clock du Master Clock ;
   - Controller Manager → Generic MIDI, Out-Port = IAC Bus 1 ;
   - recette Output pour le S4, réglage de l'offset.

**Contrainte Traktor S4 MK3 (HID)**
- VJ Mapper ne verra **jamais** le S4 directement.
- Seule option : Controller Manager → Generic MIDI, Out-Port IAC, avec des assignations **Output** qui renvoient en CC des états internes de Traktor (volume de deck, knob FX, boutons, Beat Phase Monitor, niveaux).
- Ça couvre le mode « suivre le DJ », mais ça ne remplace pas une surface de contrôle VJ.
- **Recommandation : un nanoKONTROL2** (~60 €), éventuellement un LPD8 pour les pads. Les deux passent par le même code (`port: "*"`).

**Critères d'acceptation**
- Avec `midi_clock_sim` à 128 BPM : LED de beat stable, chase verrouillé, BPM à ±0,1.
- Learn d'un CC en moins de 3 actions ; mapping retrouvé après redémarrage.
- Débrancher puis rebrancher le contrôleur : pas de crash, reconnexion en moins de 2 s.
- Aucune frame > 25 ms causée par le MIDI.
- Sur le Mac avec Traktor : BPM à ±0,1 du master Traktor, beat calé après Resync, et le CPU meter de Traktor ne bouge pas (pas de décrochage audio).

**Risques**

| Risque | Parade |
|--------|--------|
| Jitter de la MIDI Clock Traktor | Régression + offset réglable, afficher l'écart-type |
| Traktor n'envoie pas d'info de downbeat | Resync manuel mappable, ou CC « Beat Phase Monitor » en Output |
| Pas de wheel `python-rtmidi` pour Python 3.14 x86_64 sur macOS | Python 3.12/3.13 sur le Mac |
| Port IAC renommé selon la langue (« Bus IAC 1 ») | Correspondance par sous-chaîne « IAC » |

Alternative à évaluer : **Ableton Link** (`aalink`) donne tempo + phase + mesure exacte. C'est une question ouverte.

### V2 : formes, remplissages, effets de contour, photo + correction 4 coins (4-5 sessions)

**Ce que voit l'utilisateur**
- Outils **Polyligne**, **Polygone** (Entrée ou double-clic pour fermer), **Ellipse** (Ctrl pour un cercle).
- Édition des sommets : glisser, double-clic sur une arête pour insérer, Suppr pour retirer.
- **Multi-sélection** (Maj+clic, rectangle), aligner / distribuer.
- **Magnétisme** : sommets et extrémités à moins de 8 px, grille, angle de 15° avec Maj ; Alt désactive.
- **Undo/redo**.
- Par groupe : **Remplissage** (aucun, solide, dégradé, plasma, mycelium, julia, swamp, void, nuclear, spectre) et **Contour** (aucun, néon au kick, ondes depuis les bords, balayage, chase de contour).
- **Calage photo** : 4 points sur la photo ↔ 4 points sortie, la photo est redressée.
- **Corner-pin 4 coins** de la sortie, avec mire.

**Schéma v2**
```json
{"version": 2,
 "output": {"warp": [[0,0],[1,0],[1,1],[0,1]]},
 "background": {"path": "garage.jpg", "opacity": 0.6, "pin_photo": null, "pin_out": null},
 "groups": [{"id","name","effect","band","color","color2","speed","intensity","spread",
             "enabled","sync","rate","trigger","hue",
             "fill": "none", "fill_params": {}, "edge": "none", "edge_width": 0.01}],
 "shapes": [{"id","type": "line|polyline|polygon|ellipse","points": [[x,y],...],
             "closed": false,"width": 0.012,"group": "<gid>","reverse": false}]}
```
- Migration v1→v2 : `strips` → shapes de type `line`. L'ellipse est stockée en paramétrique et tessellée en 48 points au rendu.
- Le pipeline strip actuel est conservé pour `type == "line"`.

**Rendu des formes**
- **Pas de triangulation.** Chaque forme = un quad (sa bbox + la marge de glow). Le fragment shader calcule la distance signée analytique au polygone (crossing number + distance au segment le plus proche) et la coordonnée de périmètre `s`.
- Points dans une **texture RGBA32F** (x_px, y_px, cumlen), une ligne par forme, 256 points max, lus par `texelFetch` (GLSL 330, compatible Mac).
- Draw **instancié** (GL 3.3).
- `depth_scale` par forme (≈ rayon inscrit) pour le balayage.
- Effets de contour :
  - néon = `exp(-|d|/w)*kick` ;
  - ondes = `sin(d*k - tbase*TAU)` ;
  - balayage = `step(1-level, dnorm)` ;
  - chase de contour = tirets sur `s` décalés par `tbase`.
- **Remplissages (`fills.py`)** :
  - un programme par type : `#version 330 core` + `shape_common.glsl` + `fills/<nom>.glsl` (`vec3 fill(vec2 uv, FillIn i)`) + un main commun, avec des directives `#line` ;
  - paramètres dans `u_fp[2]` (8 floats) ;
  - compilation paresseuse dans un `try` : en cas d'échec, fallback `solid` et erreur dans l'UI. Hot-reload seulement en mode dev.
- **Portage depuis l'AV** (copie assumée) :
  - d'abord `radial.frag` modes 12 Mycelium, 13 Julia, 15 Swamp ;
  - puis 11 Void et 10 Nuclear ;
  - helpers `vnoise`, `pnoise`, `pfbm`, `psySat`, `pal`, `hueShiftRGB` (lignes 133-235) ;
  - les modes 0-9 dépendent du spectre (`u_bars_tex`) : pas avant d'avoir le spectre 32 bandes (`Features.spectrum`, texture R32F 32×1).
- Remplissages rendus dans un FBO à résolution réduite (0,5 / 0,75 / 1,0) ; contours et strips en pleine résolution.

**Homographies (`geom.py`, numpy pur)**
- DLT 8×8 résolu par `numpy.linalg.solve`. **Piège moderngl** : les mat3 sont column-major, il faut écrire `H.T`.
- Photo : passe `warp.frag` rendue **une seule fois** à chaque changement.
- Sortie : `blit.frag` → `warp.frag`, `uv = H⁻¹·p`, noir en dehors de [0,1].
- Deux workflows :
  - (A) photo calée sur l'espace projo ;
  - (B) recommandé pour la porte : corner-pin de la sortie sur les 4 coins physiques + photo redressée sur le même rectangle.

**Éditeur**
- `undo.py` : snapshots `asdict(scene)` dans un anneau de 100.
- Raccourcis via `imgui.is_key_chord_pressed` (Ctrl devient Cmd sur macOS) : V/L/P/G/E pour les outils, Ctrl+D, Suppr, flèches, Ctrl+S/O/Z/Y, C calibration, B blackout, Espace tap, Tab masquer l'UI.

**Tâches, dans l'ordre**
1. `geom.py` + tests.
2. Schéma v2 + migration.
3. Undo, multi-sélection, magnétisme.
4. Texture de points + `shape.frag` (contours seuls) + tests headless.
5. Outils de forme et édition des sommets.
6. `fills.py` (solide, dégradé, plasma, puis mycelium, julia, swamp) + tests de compilation.
7. FBO réduit pour les remplissages.
8. Calage photo et corner-pin de la sortie.
9. Void, Nuclear, spectre.

**Critères d'acceptation**
- La scène V0 migrée donne un rendu identique (diff < 1/255).
- 20 polygones mycelium à 50 % de résolution + contours à **≥ 60 fps en 1080p sur le Mac Pro**, Traktor ouvert.
- Un shader de remplissage cassé n'interrompt pas la sortie.
- Corner-pin réglable en moins de 2 min.

**Risques**

| Risque | Parade |
|--------|--------|
| fbm lourd sur FirePro D300 | Échelle de résolution + octaves réglables |
| Coût de la boucle SDF | Plafond de 64 arêtes par forme |
| Compilateur GLSL Apple/AMD plus strict | Passer chaque shader dans `gl_probe.py` sur le Mac |

### V3 : looks/scènes en live, crossfade, masters, cues (2-3 sessions)

**Ce que voit l'utilisateur**
- **Looks** : snapshot de tous les paramètres des groupes + master, rappelé sur pads. Fondu en beats ou en secondes, GO quantifié à la mesure (option).
- **Cue list** : look + fondu + auto-avance après N mesures, GO / BACK.
- Masters : strobe synchronisé, flash, rotation de teinte, freeze.
- LFO d'animation par groupe : translation, rotation, échelle.

**Modèle** : `looks: [{id, name, groups: {gid: {params}}, master}]` et `cues: [{look, fade_beats, auto_bars}]`. Les groupes absents d'un look ne bougent pas.

**Rendu**
- FBO A/B + `mix.frag`, seulement pendant un fondu.
- `master.frag` (dimmer, strobe, flash, hue, freeze) donne la texture finale, puis la sortie applique le warp.

**Tâches** : `show.py` → FBO A/B + mix → `master.frag` → cibles MIDI `look.recall:n`, `cue.go/back`, `master.strobe/flash` → UI cue list → LFO → migration v2→v3 + tests.

**Critères d'acceptation**
- 8 looks sur pads, fondu d'1 mesure sans passer sous 55 fps sur le Mac.
- Blackout et flash à ≤ 1 frame de latence.
- GO quantifié qui tombe sur le beat avec le simulateur.

### H1 : robustesse live + packaging

- **Mode `--live`** :
  - édition verrouillée, UI réduite à Live + MIDI ;
  - confirmations sur Échap et Cmd+Q ;
  - pas de hot-reload.
- **`run-live.sh`** :
  - `until python main.py --live --restore; do sleep 1; done` ;
  - sous `caffeinate -dimsu` ;
  - logs dans `~/Library/Logs/VJ Mapper/`.
- **Watchdog** : un thread heartbeat logue un warning si la boucle est bloquée plus de 2 s.
- **App Nap** : `LSAppNapIsDisabled` dans l'Info.plist, ou `defaults write ... NSAppSleepDisabled`.
- **`build-macos.sh`** (adapté de l'AV) :
  - PyInstaller `--windowed` ;
  - `--add-data vjmapper/shaders:vjmapper/shaders`, `--collect-data imgui_bundle`, `--collect-binaries glfw`, `--collect-all _sounddevice_data` ;
  - Info.plist avec `NSMicrophoneUsageDescription` (obligatoire pour lire BlackHole) et `LSAppNapIsDisabled` ;
  - `codesign -s -` (ad-hoc) ;
  - release GitHub sous BouleMagique.
- **Premières soirées : lancer depuis les sources**. La permission micro est alors attribuée au Terminal, c'est plus simple.
- **Budget de perf** (Mac Pro, 16,6 ms par frame) :

  | Poste | Budget |
  |-------|--------|
  | Audio | ≤ 0,5 ms |
  | Vertices strips | ≤ 1 ms |
  | Formes + remplissages (GPU) | ≤ 8 ms |
  | UI | ≤ 3 ms |

  Si l'UI dépasse : en mode live, elle tourne à 30 Hz pendant que la sortie reste à 60.
- **Checklist avant soirée** (README) : IAC en ligne, BlackHole + périphérique agrégé, Send Clock actif, Spaces distincts désactivés, veille coupée, `run-live.sh`, test du blackout.

---

## 3. Dépendances

| Dépendance | Décision | Justification |
|------------|----------|---------------|
| moderngl, glfw, PyOpenGL, imgui-bundle, numpy, sounddevice, pillow | Gardées | Justifiées en V0 |
| **python-rtmidi** (V1) | Ajout | La stdlib n'a aucun accès à CoreMIDI ou ALSA |
| mido | **Non** | Parsing des octets en ~30 lignes ; à désinstaller du venv |
| OpenCV | **Non** | Homographie = système 8×8 avec numpy |
| Triangulation | **Non** | SDF analytique sur la bbox |
| pytest | **Non** | `unittest` suffit |
| pyobjc | **Non** | `caffeinate` + Info.plist suffisent |
| python-osc | Non pour l'instant | OSC sur socket UDP stdlib si besoin un jour |
| aalink (Ableton Link) | Option | Seulement pour la phase de mesure exacte |
| PyInstaller | Outil de build | Hors runtime |
| Python | 3.11+ | Mac : 3.12/3.13 via `uv` (wheels x86_64) ; épingler `requirements.txt` (`~=`) après le test sur le Mac |

---

## 4. Checklist de reprise (prochaine session)

1. Lire ce plan, `CLAUDE.md` et `git log`. Poser les questions ouvertes 1, 2, 3 et 7 avant de coder.
2. Si accord : déplacer le repo vers `/mnt/dev/DEV/vj-mapper`, créer `BouleMagique/vj-mapper`, push, corriger les chemins.
3. Vérifier les wheels Mac sans le Mac :
   ```
   pip download imgui-bundle python-rtmidi moderngl glfw numpy sounddevice pillow pyopengl \
     --only-binary=:all: --platform macosx_12_0_x86_64 --python-version 3.12 -d <scratch>
   ```
   Recommencer avec 3.13, puis choisir la version de Python pour le Mac.
4. H0 étapes 2-4 : `now` injecté, audio normalisé en dt, `tools/gl_probe.py`, tests headless qui passent.
5. H0 étapes 5-9 : schéma v1 + ids + migration, isolation d'erreurs, dialogues non bloquants, protection Échap/Cmd+Q, `state.py` + autosave + `--restore`. Commit à chaque étape.
6. Préparer la procédure Mac : uv + venv + `gl_probe.py` + lancement avec le projo. Points à vérifier : barre de menus sur le projo, fps de la sortie quand la fenêtre de contrôle est au premier plan, permission micro BlackHole, routage Traktor → BlackHole, CPU meter de Traktor. **Attendre le retour de l'utilisateur** avant les formes de V2.
7. Démarrer la V1 : `midi.py` + `tools/midi_clock_sim.py` + `clock.py` et ses tests (tout faisable sous Linux).
8. Mettre à jour `CLAUDE.md` (État + décisions : rtmidi sans mido, cibles par slot, bindings globaux).

---

## 5. Questions ouvertes

1. **Date de la prochaine soirée ?** Elle fixe le périmètre minimal (H0 + V1 + masters probablement).
2. **Contrôleur** : nanoKONTROL2 / LPD8, Output Traktor depuis le S4, ou les deux ?
3. **Repo** : `/mnt/dev/DEV/vj-mapper` + `BouleMagique/vj-mapper`, privé ou public ? Ajout au tableau de `DEV/CLAUDE.md` ?
4. **Mac Pro** : GPU (D300/D500/D700), RAM, écran de contrôle en plus du projo ? Résolution et connectique du projo ?
5. **Routage audio** : périphérique agrégé S4 + BlackHole, entrée ligne depuis la table, ou MIDI Clock seul sans analyse audio ?
6. **Ableton Link**, ou MIDI Clock + Resync ?
7. **Lancement** : depuis les sources pour les premières soirées, ou `.app` packagée tout de suite ?
8. **Calage** : photo prise depuis la position du projo, ou workflow B (corner-pin sur la porte + photo redressée) ?
9. Mappings MIDI **par rig** (proposé) ou par show ?
10. Crossfade V3 : fondu complet (coût GPU doublé pendant le fondu), ou coupe franche quantifiée sur le beat ?

---

### Fichiers critiques
- `vjmapper/app.py`, `scene.py`, `render.py`, `shaders/strip.frag`, `editor.py`
- Référence pour le portage, sans modification : `/mnt/dev/DEV/Audio-Visualizer/render/shaders/radial.frag` (modes 10-15, helpers lignes 133-235) et `build-macos.sh`
