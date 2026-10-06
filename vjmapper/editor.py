"""Control UI (Dear ImGui): side panel + mapping canvas.

Canvas tools
------------
* Sélection: click a strip to select it, drag its ends or its body. Suppr deletes,
  arrows nudge (Maj = ×10).
* Tracer: drag to draw a new strip in the current group. Maj snaps it horizontal /
  vertical — the reinforcement bars of a garage door are exactly that.
"""
from __future__ import annotations

import copy
import math
from typing import TYPE_CHECKING

import glfw
from imgui_bundle import imgui
from imgui_bundle import portable_file_dialogs as pfd

from .output import monitor_label
from .scene import BANDS, EFFECT_HELP, EFFECTS, Group, Scene, Strip, garage_door_template

if TYPE_CHECKING:
    from .app import App

PANEL_W = 380
HANDLE_PX = 9.0
TOOL_SELECT, TOOL_DRAW = 0, 1


def _u32(rgb, a: float = 1.0) -> int:
    return imgui.color_convert_float4_to_u32(imgui.ImVec4(rgb[0], rgb[1], rgb[2], a))


def _seg_dist(p, a, b) -> float:
    ax, ay = a
    bx, by = b
    dx, dy = bx - ax, by - ay
    l2 = dx * dx + dy * dy
    t = 0.0 if l2 == 0 else max(0.0, min(1.0, ((p[0] - ax) * dx + (p[1] - ay) * dy) / l2))
    return math.hypot(p[0] - (ax + t * dx), p[1] - (ay + t * dy))


class Editor:
    def __init__(self, app: "App"):
        self.app = app
        self.tool = TOOL_SELECT
        self.sel: int | None = None          # selected strip index
        self.group = 0                       # current group (new strips go there)
        self.drag = None                     # (kind, strip, mouse_start, a0, b0)
        self.drawing = None                  # [a, b] while drawing
        self.calib = False
        self.monitor_idx = 0
        self.fullscreen = True
        self.sources, self.source_idx = [], 0
        self._rect = (0.0, 0.0, 1.0, 1.0)   # canvas rect on screen (x, y, w, h)
        self.refresh_sources()

    @property
    def scene(self) -> Scene:
        return self.app.scene

    # ── Coordinates ──────────────────────────────────────────────
    def to_screen(self, p) -> imgui.ImVec2:
        x, y, w, h = self._rect
        return imgui.ImVec2(x + p[0] * w, y + p[1] * h)

    def to_norm(self, sp) -> list[float]:
        x, y, w, h = self._rect
        return [(sp[0] - x) / w, (sp[1] - y) / h]

    # ── Frame ────────────────────────────────────────────────────
    def draw(self) -> None:
        vp = imgui.get_main_viewport()
        fixed = (imgui.WindowFlags_.no_move | imgui.WindowFlags_.no_resize
                 | imgui.WindowFlags_.no_collapse)

        imgui.set_next_window_pos(vp.pos)
        imgui.set_next_window_size(imgui.ImVec2(PANEL_W, vp.size.y))
        imgui.begin("VJ Mapper", None, fixed)
        if imgui.begin_tab_bar("tabs"):
            for label, fn in (("Scène", self._tab_scene), ("Groupes", self._tab_groups),
                              ("Audio", self._tab_audio), ("Sortie", self._tab_output)):
                if imgui.begin_tab_item(label)[0]:
                    fn()
                    imgui.end_tab_item()
            imgui.end_tab_bar()
        imgui.end()

        imgui.set_next_window_pos(imgui.ImVec2(vp.pos.x + PANEL_W, vp.pos.y))
        imgui.set_next_window_size(imgui.ImVec2(vp.size.x - PANEL_W, vp.size.y))
        imgui.begin("Canevas", None, fixed | imgui.WindowFlags_.no_title_bar
                    | imgui.WindowFlags_.no_scrollbar)
        self._canvas()
        imgui.end()

    # ── Tabs ─────────────────────────────────────────────────────
    def _tab_scene(self) -> None:
        sc = self.scene
        imgui.separator_text("Outil")
        if imgui.radio_button("Sélection", self.tool == TOOL_SELECT):
            self.tool = TOOL_SELECT
        imgui.same_line()
        if imgui.radio_button("Tracer", self.tool == TOOL_DRAW):
            self.tool = TOOL_DRAW
        imgui.text_disabled("Maj : horizontal / vertical · Suppr · flèches")
        names = [g.name for g in sc.groups]
        _, self.group = imgui.combo("Groupe courant", min(self.group, len(names) - 1), names)

        imgui.separator_text("Barre sélectionnée")
        if self.sel is not None and self.sel < len(sc.strips):
            s = sc.strips[self.sel]
            _, s.group = imgui.combo("Groupe##strip", min(s.group, len(names) - 1), names)
            _, s.width = imgui.slider_float("Épaisseur", s.width, 0.002, 0.06, "%.3f")
            _, s.reverse = imgui.checkbox("Sens inversé", s.reverse)
            if imgui.button("Dupliquer"):
                dup = copy.deepcopy(s)
                dup.a = [dup.a[0] + 0.02, dup.a[1] + 0.02]
                dup.b = [dup.b[0] + 0.02, dup.b[1] + 0.02]
                sc.strips.append(dup)
                self.sel = len(sc.strips) - 1
            imgui.same_line()
            if imgui.button("Supprimer"):
                self._delete_selected()
        else:
            imgui.text_disabled("Aucune — clique une barre (outil Sélection)")

        imgui.separator_text("Scène")
        imgui.text(f"{len(sc.strips)} barres · {len(sc.groups)} groupes")
        if imgui.button("Modèle porte de garage"):
            self._set_scene(garage_door_template())
        imgui.same_line()
        if imgui.button("Vider"):
            self._set_scene(Scene(groups=copy.deepcopy(sc.groups)))
        if imgui.button("Ouvrir..."):
            res = pfd.open_file("Ouvrir une scène", str(self.app.scenes_dir),
                                ["Scènes", "*.json"]).result()
            if res:
                self._set_scene(Scene.load(res[0]))
                self.app.load_background(self.scene.background)
        imgui.same_line()
        if imgui.button("Enregistrer..."):
            path = pfd.save_file("Enregistrer la scène",
                                 str(self.app.scenes_dir / "scene.json"),
                                 ["Scènes", "*.json"]).result()
            if path:
                sc.save(path if path.endswith(".json") else path + ".json")

        imgui.separator_text("Photo de la surface")
        imgui.text_wrapped("Photo du mur / de la porte prise depuis le projo : "
                           "sert de repère pour tracer (jamais envoyée au projo).")
        if imgui.button("Charger..."):
            res = pfd.open_file("Photo de fond", "",
                                ["Images", "*.png *.jpg *.jpeg *.webp"]).result()
            if res:
                sc.background = res[0]
                self.app.load_background(res[0])
        imgui.same_line()
        if imgui.button("Retirer"):
            sc.background = None
            self.app.load_background(None)
        _, sc.bg_opacity = imgui.slider_float("Opacité photo", sc.bg_opacity, 0.0, 1.0)

    def _tab_groups(self) -> None:
        sc = self.scene
        imgui.text_wrapped("Chaque groupe = un effet + une bande audio. "
                           "Les barres d'un groupe sont décalées (Décalage) → vagues.")
        for i, g in enumerate(sc.groups):
            imgui.color_button(f"##c{i}", imgui.ImVec4(*g.color, 1.0),
                               size=imgui.ImVec2(14, 14))
            imgui.same_line()
            n = sum(1 for s in sc.strips if s.group == i)
            if imgui.selectable(f"{g.name}  ({n})##g{i}", self.group == i)[0]:
                self.group = i
        if imgui.button("+ Groupe"):
            sc.groups.append(Group(f"Groupe {len(sc.groups) + 1}"))
            self.group = len(sc.groups) - 1
        imgui.same_line()
        if imgui.button("Supprimer le groupe") and len(sc.groups) > 1:
            sc.remove_group(self.group)
            self.group = max(0, self.group - 1)

        self.group = min(self.group, len(sc.groups) - 1)
        g = sc.groups[self.group]
        imgui.separator_text(g.name)
        _, g.name = imgui.input_text("Nom", g.name)
        _, g.enabled = imgui.checkbox("Actif", g.enabled)
        _, g.effect = imgui.combo("Effet", g.effect, EFFECTS)
        imgui.text_disabled(EFFECT_HELP[g.effect])
        _, g.band = imgui.combo("Réagit à", g.band, BANDS)
        _, g.color = imgui.color_edit3("Couleur 1", g.color)
        _, g.color2 = imgui.color_edit3("Couleur 2", g.color2)
        _, g.speed = imgui.slider_float("Vitesse", g.speed, 0.05, 4.0)
        _, g.intensity = imgui.slider_float("Intensité", g.intensity, 0.0, 2.0)
        _, g.spread = imgui.slider_float("Décalage", g.spread, 0.0, 1.0)

    def _tab_audio(self) -> None:
        audio = self.app.audio
        labels = [s.label for s in self.sources] or ["(aucune source)"]
        _, self.source_idx = imgui.combo("Source", min(self.source_idx, len(labels) - 1), labels)
        if imgui.button("Rafraîchir"):
            self.refresh_sources()
        imgui.same_line()
        if audio.running:
            if imgui.button("■ Stop"):
                audio.stop()
        elif imgui.button("● Live") and self.sources:
            audio.simulate = False
            audio.start(self.sources[self.source_idx])
        if audio.error:
            imgui.text_colored(imgui.ImVec4(1, .4, .4, 1), audio.error)
        changed, sim = imgui.checkbox("Simulation 128 BPM (sans musique)", audio.simulate)
        if changed:
            if sim:
                audio.stop()
            audio.simulate = sim
        _, audio.analyzer.gain = imgui.slider_float("Gain", audio.analyzer.gain, 0.2, 3.0)

        imgui.separator_text("Analyse")
        f = audio.analyzer.f
        for name, v in zip(BANDS, (f.bass, f.mid, f.high, f.kick, f.level)):
            imgui.progress_bar(float(v), imgui.ImVec2(-90, 0), "")
            imgui.same_line()
            imgui.text(name)

    def _tab_output(self) -> None:
        app = self.app
        monitors = glfw.get_monitors() or []
        labels = [monitor_label(m) for m in monitors] or ["(aucun écran)"]
        if self.monitor_idx >= len(labels):
            self.monitor_idx = len(labels) - 1
        _, self.monitor_idx = imgui.combo("Écran", self.monitor_idx, labels)
        _, self.fullscreen = imgui.checkbox("Plein écran", self.fullscreen)
        if app.output is None:
            if imgui.button("Ouvrir la sortie") and monitors:
                app.open_output(monitors[self.monitor_idx], self.fullscreen)
        else:
            if imgui.button("Fermer la sortie"):
                app.close_output()
            if app.output is not None:
                imgui.text(f"{app.output.fps:.0f} i/s")
        imgui.text_disabled("Échap dans la sortie : fermer")
        w, h = app.compositor.size
        imgui.text(f"Rendu : {w}×{h}")
        imgui.separator_text("Calage")
        _, self.calib = imgui.checkbox("Mode calibration (barres blanches)", self.calib)
        imgui.text_wrapped("Rouge = début de barre, vert = fin. Ajuste les barres dans le "
                           "canevas en regardant le mur.")

    # ── Canvas ───────────────────────────────────────────────────
    def _canvas(self) -> None:
        app = self.app
        avail = imgui.get_content_region_avail()
        cw, ch = app.compositor.size
        scale = min(avail.x / cw, avail.y / ch)
        w, h = cw * scale, ch * scale
        origin = imgui.get_cursor_screen_pos()
        x = origin.x + (avail.x - w) * 0.5
        y = origin.y + (avail.y - h) * 0.5
        self._rect = (x, y, w, h)
        p0, p1 = imgui.ImVec2(x, y), imgui.ImVec2(x + w, y + h)

        dl = imgui.get_window_draw_list()
        dl.add_rect_filled(p0, p1, _u32((0, 0, 0)))
        if app.bg_tex is not None and self.scene.bg_opacity > 0:
            dl.add_image(imgui.ImTextureRef(app.bg_tex.glo), p0, p1,
                         imgui.ImVec2(0, 0), imgui.ImVec2(1, 1),
                         _u32((1, 1, 1), self.scene.bg_opacity))
        # Composition texture is bottom-up (GL): flip V
        dl.add_image(imgui.ImTextureRef(app.compositor.tex.glo), p0, p1,
                     imgui.ImVec2(0, 1), imgui.ImVec2(1, 0))

        imgui.set_cursor_screen_pos(p0)
        imgui.invisible_button("canvas", imgui.ImVec2(max(w, 1), max(h, 1)))
        hovered = imgui.is_item_hovered()
        self._handle_mouse(hovered)
        self._handle_keys(hovered or imgui.is_window_focused())
        self._overlay(dl)

    def _hit(self, mouse) -> tuple[str, int] | None:
        sc = self.scene
        if self.sel is not None and self.sel < len(sc.strips):
            s = sc.strips[self.sel]
            for kind, p in (("a", s.a), ("b", s.b)):
                sp = self.to_screen(p)
                if math.hypot(mouse[0] - sp.x, mouse[1] - sp.y) <= HANDLE_PX:
                    return kind, self.sel
        best, best_d = None, 1e9
        for i, s in enumerate(sc.strips):
            a, b = self.to_screen(s.a), self.to_screen(s.b)
            d = _seg_dist(mouse, (a.x, a.y), (b.x, b.y))
            if d < best_d:
                best, best_d = i, d
        if best is not None:
            tol = max(8.0, sc.strips[best].width * self._rect[3])
            if best_d <= tol:
                return "body", best
        return None

    def _snap(self, anchor, p) -> list[float]:
        """Maj held: align p with anchor horizontally or vertically (in screen space)."""
        if not imgui.get_io().key_shift:
            return p
        _, _, w, h = self._rect
        if abs((p[0] - anchor[0]) * w) >= abs((p[1] - anchor[1]) * h):
            return [p[0], anchor[1]]
        return [anchor[0], p[1]]

    def _handle_mouse(self, hovered: bool) -> None:
        sc = self.scene
        io = imgui.get_io()
        mouse = (io.mouse_pos.x, io.mouse_pos.y)
        m = self.to_norm(mouse)

        if self.tool == TOOL_DRAW:
            if hovered and imgui.is_mouse_clicked(0):
                self.drawing = [m, m]
            if self.drawing is not None:
                self.drawing[1] = self._snap(self.drawing[0], m)
                if imgui.is_mouse_released(0):
                    a, b = self.drawing
                    _, _, w, h = self._rect
                    if math.hypot((b[0] - a[0]) * w, (b[1] - a[1]) * h) > 8:
                        sc.strips.append(Strip(list(a), list(b), group=self.group))
                        self.sel = len(sc.strips) - 1
                    self.drawing = None
            return

        if hovered and imgui.is_mouse_clicked(0):
            hit = self._hit(mouse)
            if hit is None:
                self.sel = None
            else:
                kind, i = hit
                self.sel = i
                s = sc.strips[i]
                self.drag = (kind, i, m, list(s.a), list(s.b))
        if self.drag is not None:
            kind, i, m0, a0, b0 = self.drag
            if i < len(sc.strips):
                s = sc.strips[i]
                if kind == "a":
                    s.a = self._snap(s.b, m)
                elif kind == "b":
                    s.b = self._snap(s.a, m)
                else:
                    dx, dy = m[0] - m0[0], m[1] - m0[1]
                    s.a = [a0[0] + dx, a0[1] + dy]
                    s.b = [b0[0] + dx, b0[1] + dy]
            if imgui.is_mouse_released(0):
                self.drag = None

    def _handle_keys(self, active: bool) -> None:
        if not active or self.sel is None or self.sel >= len(self.scene.strips):
            return
        if imgui.get_io().want_text_input:
            return
        if imgui.is_key_pressed(imgui.Key.delete) or imgui.is_key_pressed(imgui.Key.backspace):
            self._delete_selected()
            return
        _, _, w, h = self._rect
        step = 10.0 if imgui.get_io().key_shift else 1.0
        dx = dy = 0.0
        if imgui.is_key_pressed(imgui.Key.left_arrow):
            dx = -step / w
        if imgui.is_key_pressed(imgui.Key.right_arrow):
            dx = step / w
        if imgui.is_key_pressed(imgui.Key.up_arrow):
            dy = -step / h
        if imgui.is_key_pressed(imgui.Key.down_arrow):
            dy = step / h
        if dx or dy:
            s = self.scene.strips[self.sel]
            s.a = [s.a[0] + dx, s.a[1] + dy]
            s.b = [s.b[0] + dx, s.b[1] + dy]

    def _overlay(self, dl) -> None:
        sc = self.scene
        for i, s in enumerate(sc.strips):
            g = sc.groups[s.group] if s.group < len(sc.groups) else sc.groups[0]
            a, b = self.to_screen(s.a), self.to_screen(s.b)
            if i == self.sel:
                dl.add_line(a, b, _u32((1, 1, 1), 0.9), 2.0)
                dl.add_circle_filled(a, HANDLE_PX * 0.7, _u32((1, .25, .25)))
                dl.add_circle_filled(b, HANDLE_PX * 0.7, _u32((.25, 1, .35)))
            else:
                dl.add_line(a, b, _u32(g.color, 0.35), 1.0)
        if self.drawing is not None:
            g = sc.groups[min(self.group, len(sc.groups) - 1)]
            dl.add_line(self.to_screen(self.drawing[0]), self.to_screen(self.drawing[1]),
                        _u32(g.color, 0.9), 2.0)

    # ── Helpers ──────────────────────────────────────────────────
    def _delete_selected(self) -> None:
        if self.sel is not None and self.sel < len(self.scene.strips):
            del self.scene.strips[self.sel]
        self.sel = None
        self.drag = None

    def _set_scene(self, scene: Scene) -> None:
        self.app.scene = scene
        self.sel = None
        self.drag = None
        self.group = 0

    def refresh_sources(self) -> None:
        from .audio import list_sources
        self.sources, self.source_idx = list_sources()
