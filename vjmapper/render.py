"""Composition: every strip as one quad, drawn additively into an RGBA texture.

The texture is what both the editor canvas and the output window show.
"""
from __future__ import annotations

import time
from pathlib import Path

import moderngl
import numpy as np

from .audio import Features
from .scene import Scene

SHADERS = Path(__file__).parent / "shaders"
_SPAN = 3.0            # quad half-width in strip half-widths (room for the glow)
_FLOATS = 20           # per vertex: pos2 uv2 col3 col2·3 p0·4 p1·4 p2·2


def load_program(ctx: moderngl.Context, name: str) -> moderngl.Program:
    return ctx.program(vertex_shader=(SHADERS / f"{name}.vert").read_text(),
                       fragment_shader=(SHADERS / f"{name}.frag").read_text())


class Compositor:
    def __init__(self, ctx: moderngl.Context, size: tuple[int, int] = (1920, 1080)):
        self.ctx = ctx
        self.prog = load_program(ctx, "strip")
        self.vbo = ctx.buffer(reserve=6 * _FLOATS * 4 * 64, dynamic=True)
        self.vao = ctx.vertex_array(self.prog, [(
            self.vbo, "2f 2f 3f 3f 4f 4f 2f",
            "in_pos", "in_uv", "in_col", "in_col2", "in_p0", "in_p1", "in_p2")])
        self.tex: moderngl.Texture | None = None
        self.fbo: moderngl.Framebuffer | None = None
        self.resize(size)
        self.t0 = time.perf_counter()

    @property
    def size(self) -> tuple[int, int]:
        return self.tex.size

    def resize(self, size: tuple[int, int]) -> None:
        if self.tex is not None and self.tex.size == tuple(size):
            return
        if self.fbo is not None:
            self.fbo.release()
            self.tex.release()
        self.tex = self.ctx.texture(size, 4)
        self.tex.filter = (moderngl.LINEAR, moderngl.LINEAR)
        self.fbo = self.ctx.framebuffer(color_attachments=[self.tex])

    def _vertices(self, scene: Scene, feats: Features, now: float) -> np.ndarray:
        w, h = self.size
        since = now - feats.last_kick
        order = {}                                   # running index per group → phase
        rows = []
        for s in scene.strips:
            g = scene.groups[s.group] if 0 <= s.group < len(scene.groups) else None
            if g is None or not g.enabled:
                continue
            k = order.get(s.group, 0)
            order[s.group] = k + 1

            a = np.array([s.a[0] * w, s.a[1] * h])
            b = np.array([s.b[0] * w, s.b[1] * h])
            d = b - a
            length = float(np.hypot(*d))
            if length < 1.0:
                continue
            t = d / length
            n = np.array([-t[1], t[0]])
            hw = max(s.width * h * 0.5, 0.5)
            ext = hw * _SPAN                         # caps + glow room
            u0, u1 = -ext / length, 1.0 + ext / length
            corners = [
                (a - t * ext - n * ext, u0, -_SPAN), (b + t * ext - n * ext, u1, -_SPAN),
                (b + t * ext + n * ext, u1, _SPAN), (a - t * ext + n * ext, u0, _SPAN),
            ]
            attrs = [*g.color, *g.color2,
                     g.effect, feats.band(g.band), g.speed, g.intensity,
                     k * g.spread, length, since, float(s.reverse),
                     hw, 0.0]
            quad = []
            for p, u, v in corners:
                quad.append([p[0] / w * 2 - 1, 1 - p[1] / h * 2, u, v, *attrs])
            rows += [quad[0], quad[1], quad[2], quad[0], quad[2], quad[3]]
        return np.array(rows, dtype="f4").reshape(-1, _FLOATS)

    def render(self, scene: Scene, feats: Features, calib: bool = False) -> None:
        now = time.perf_counter()
        verts = self._vertices(scene, feats, now)
        self.fbo.use()
        self.ctx.viewport = (0, 0, *self.size)
        self.fbo.clear(0.0, 0.0, 0.0, 0.0)
        if not len(verts):
            return
        data = verts.tobytes()
        if len(data) > self.vbo.size:
            self.vbo.orphan(len(data) * 2)
        self.vbo.write(data)
        self.ctx.enable(moderngl.BLEND)
        self.ctx.blend_func = moderngl.ONE, moderngl.ONE      # light adds up
        self.prog["u_time"].value = now - self.t0
        self.prog["u_calib"].value = int(calib)
        self.vao.render(moderngl.TRIANGLES, vertices=len(verts))
        self.ctx.disable(moderngl.BLEND)
