"""Main loop: audio → composition texture → control window (+ output window)."""
from __future__ import annotations

import os
import sys
from pathlib import Path

import glfw

# moderngl attaches to an existing context through GLX only, and the ImGui Python
# backend's PyOpenGL must agree: on a Wayland session, run GLFW through XWayland.
_WAYLAND = (sys.platform.startswith("linux") and os.environ.get("WAYLAND_DISPLAY")
            and os.environ.get("DISPLAY"))
if _WAYLAND:
    os.environ.setdefault("PYOPENGL_PLATFORM", "x11")

import moderngl  # noqa: E402
import imgui_bundle  # noqa: E402
from imgui_bundle import imgui  # noqa: E402
from imgui_bundle.python_backends.glfw_backend import GlfwRenderer  # noqa: E402
from PIL import Image  # noqa: E402

from .audio import LiveAudio  # noqa: E402
from .editor import Editor  # noqa: E402
from .output import OutputWindow, gl_hints  # noqa: E402
from .render import Compositor  # noqa: E402
from .scene import garage_door_template  # noqa: E402

DEFAULT_SIZE = (1920, 1080)


class App:
    def __init__(self):
        if _WAYLAND:
            glfw.init_hint(glfw.PLATFORM, glfw.PLATFORM_X11)
        if not glfw.init():
            raise RuntimeError("GLFW init failed")
        gl_hints()
        self.win = glfw.create_window(1500, 900, "VJ Mapper", None, None)
        if not self.win:
            raise RuntimeError("impossible de créer la fenêtre (OpenGL 3.3 core requis)")
        glfw.make_context_current(self.win)
        glfw.swap_interval(1)
        self.ctx = moderngl.create_context()

        imgui.create_context()
        imgui.get_io().config_flags |= imgui.ConfigFlags_.nav_enable_keyboard
        imgui.get_io().set_ini_filename("")
        imgui.style_colors_dark()
        font = Path(imgui_bundle.__file__).parent / "assets" / "fonts" / "DroidSans.ttf"
        if font.exists():
            imgui.get_io().fonts.add_font_from_file_ttf(str(font), 17.0)
        self.imgui = GlfwRenderer(self.win)

        self.scenes_dir = Path(__file__).resolve().parent.parent / "scenes"
        self.scenes_dir.mkdir(exist_ok=True)
        self.scene = garage_door_template()
        self.audio = LiveAudio()
        self.audio.simulate = True              # something moves before music is wired
        self.compositor = Compositor(self.ctx, DEFAULT_SIZE)
        self.bg_tex: moderngl.Texture | None = None
        self.output: OutputWindow | None = None
        self.editor = Editor(self)

    # ── Background photo (editor only) ───────────────────────────
    def load_background(self, path: str | None) -> None:
        glfw.make_context_current(self.win)
        if self.bg_tex is not None:
            self.bg_tex.release()
            self.bg_tex = None
        if not path or not Path(path).exists():
            return
        img = Image.open(path).convert("RGBA")
        self.bg_tex = self.ctx.texture(img.size, 4, img.tobytes())
        self.bg_tex.build_mipmaps()

    # ── Output window ────────────────────────────────────────────
    def open_output(self, monitor, fullscreen: bool) -> None:
        mode = glfw.get_video_mode(monitor)
        self.compositor.resize((mode.size.width, mode.size.height))   # native resolution
        try:
            self.output = OutputWindow(self.win, monitor, fullscreen, self.compositor.tex)
        except RuntimeError:
            self.output = None
        glfw.make_context_current(self.win)
        # The output's vsync paces the loop now; don't wait twice per frame
        glfw.swap_interval(0 if self.output else 1)

    def close_output(self) -> None:
        if self.output is not None:
            self.output.close()
            self.output = None
        glfw.make_context_current(self.win)
        glfw.swap_interval(1)

    # ── Loop ─────────────────────────────────────────────────────
    def run(self) -> None:
        while not glfw.window_should_close(self.win):
            glfw.poll_events()
            if self.output is not None and self.output.should_close:
                self.close_output()

            glfw.make_context_current(self.win)
            self.imgui.process_inputs()
            feats = self.audio.update()
            self.compositor.render(self.scene, feats, calib=self.editor.calib)

            imgui.new_frame()
            self.editor.draw()
            imgui.render()
            fw, fh = glfw.get_framebuffer_size(self.win)
            self.ctx.screen.use()
            self.ctx.viewport = (0, 0, fw, fh)
            self.ctx.clear(0.07, 0.07, 0.09)
            self.imgui.render(imgui.get_draw_data())
            glfw.swap_buffers(self.win)

            if self.output is not None:
                self.output.draw()
        self.shutdown()

    def shutdown(self) -> None:
        self.audio.stop()
        self.close_output()
        self.imgui.shutdown()
        glfw.terminate()
