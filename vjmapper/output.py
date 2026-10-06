"""Output window: the composition alone, on the projector.

A second GLFW window sharing the control window's GL objects, so it shows the
composition texture directly — no copy through the CPU. Paced by vsync.
"""
from __future__ import annotations

import time
from collections import deque

import glfw
import moderngl

from .render import load_program


def gl_hints() -> None:
    """3.3 core everywhere — the only modern profile macOS offers (needs forward compat)."""
    glfw.window_hint(glfw.CONTEXT_VERSION_MAJOR, 3)
    glfw.window_hint(glfw.CONTEXT_VERSION_MINOR, 3)
    glfw.window_hint(glfw.OPENGL_PROFILE, glfw.OPENGL_CORE_PROFILE)
    glfw.window_hint(glfw.OPENGL_FORWARD_COMPAT, True)


def monitor_label(m) -> str:
    mode = glfw.get_video_mode(m)
    name = glfw.get_monitor_name(m)
    name = name.decode() if isinstance(name, bytes) else name
    return f"{name} · {mode.size.width}×{mode.size.height} @ {mode.refresh_rate} Hz"


class OutputWindow:
    def __init__(self, share, monitor, fullscreen: bool, src: moderngl.Texture):
        mode = glfw.get_video_mode(monitor)
        gl_hints()
        glfw.window_hint(glfw.AUTO_ICONIFY, False)      # stay up when focus goes to the UI
        glfw.window_hint(glfw.REFRESH_RATE, mode.refresh_rate)
        if fullscreen:
            self.win = glfw.create_window(mode.size.width, mode.size.height,
                                          "VJ Mapper — Sortie", monitor, share)
        else:
            self.win = glfw.create_window(1280, 720, "VJ Mapper — Sortie", None, share)
            mx, my = glfw.get_monitor_pos(monitor)
            glfw.set_window_pos(self.win, mx + (mode.size.width - 1280) // 2,
                                my + (mode.size.height - 720) // 2)
        if not self.win:
            raise RuntimeError("impossible de créer la fenêtre de sortie")
        glfw.set_input_mode(self.win, glfw.CURSOR, glfw.CURSOR_HIDDEN)
        glfw.set_key_callback(self.win, self._on_key)

        glfw.make_context_current(self.win)
        glfw.swap_interval(1)
        self.ctx = moderngl.create_context()
        self.prog = load_program(self.ctx, "blit")
        self.vao = self.ctx.vertex_array(self.prog, [])
        self.tex: moderngl.Texture | None = None
        self.set_source(src)
        self._frames: deque[float] = deque(maxlen=120)

    def set_source(self, src: moderngl.Texture) -> None:
        """Wrap the (shared) composition texture in this window's context."""
        self.tex = self.ctx.external_texture(src.glo, src.size, 4, 0, "f1")
        self.tex.filter = (moderngl.LINEAR, moderngl.LINEAR)

    def _on_key(self, win, key, scancode, action, mods):
        if key == glfw.KEY_ESCAPE and action == glfw.PRESS:
            glfw.set_window_should_close(win, True)

    @property
    def should_close(self) -> bool:
        return glfw.window_should_close(self.win)

    @property
    def fps(self) -> float:
        if len(self._frames) < 2:
            return 0.0
        span = self._frames[-1] - self._frames[0]
        return (len(self._frames) - 1) / span if span > 0 else 0.0

    def draw(self) -> None:
        glfw.make_context_current(self.win)
        w, h = glfw.get_framebuffer_size(self.win)
        self.ctx.screen.use()
        self.ctx.viewport = (0, 0, w, h)
        self.ctx.clear(0.0, 0.0, 0.0)
        self.tex.use(0)
        self.vao.render(moderngl.TRIANGLES, vertices=3)
        glfw.swap_buffers(self.win)
        self._frames.append(time.perf_counter())

    def close(self) -> None:
        glfw.make_context_current(self.win)
        self.vao.release()
        self.prog.release()
        glfw.destroy_window(self.win)
