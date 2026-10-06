"""Scene model: strips (light lines mapped onto a surface) grouped by effect.

Coordinates are normalised to the output: (0, 0) top-left, (1, 1) bottom-right.
A strip's width is a fraction of the output height, so a scene survives a change
of projector resolution.
"""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path

EFFECTS = ["Pulse", "Chase", "VU", "Comète", "Strobe", "Flow"]
EFFECT_HELP = [
    "Toute la barre s'allume avec la bande audio",
    "Pointillés qui défilent, plus vifs avec la bande",
    "Se remplit comme un vu-mètre selon la bande",
    "Une étincelle parcourt la barre à chaque kick",
    "Flash sur chaque kick",
    "Dégradé couleur 1 → couleur 2 qui défile, plus vif avec la bande",
]
BANDS = ["Basses", "Médiums", "Aigus", "Kick", "Niveau"]


@dataclass
class Group:
    name: str
    effect: int = 0
    band: int = 0
    color: list[float] = field(default_factory=lambda: [0.2, 0.6, 1.0])
    color2: list[float] = field(default_factory=lambda: [1.0, 0.2, 0.8])
    speed: float = 1.0
    intensity: float = 1.0
    spread: float = 0.15        # phase offset between consecutive strips → waves
    enabled: bool = True


@dataclass
class Strip:
    a: list[float]
    b: list[float]
    width: float = 0.012        # fraction of output height
    group: int = 0
    reverse: bool = False


@dataclass
class Scene:
    groups: list[Group] = field(default_factory=list)
    strips: list[Strip] = field(default_factory=list)
    background: str | None = None
    bg_opacity: float = 0.6

    def remove_group(self, gi: int) -> None:
        """Drop a group; its strips fall back to group 0 (at least one group remains)."""
        if len(self.groups) <= 1:
            return
        del self.groups[gi]
        for s in self.strips:
            if s.group == gi:
                s.group = 0
            elif s.group > gi:
                s.group -= 1

    # ── Persistence ──────────────────────────────────────────────
    def save(self, path: str | Path) -> None:
        Path(path).write_text(json.dumps(asdict(self), indent=2, ensure_ascii=False),
                              encoding="utf-8")

    @classmethod
    def load(cls, path: str | Path) -> "Scene":
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        gf = Group.__dataclass_fields__
        sf = Strip.__dataclass_fields__
        scene = cls(
            groups=[Group(**{k: v for k, v in g.items() if k in gf})
                    for g in data.get("groups", [])],
            strips=[Strip(**{k: v for k, v in s.items() if k in sf})
                    for s in data.get("strips", [])],
            background=data.get("background"),
            bg_opacity=data.get("bg_opacity", 0.6),
        )
        if not scene.groups:
            scene.groups.append(Group("Groupe 1"))
        return scene


def default_groups() -> list[Group]:
    return [
        Group("Verticales centre", effect=2, band=0, color=[0.25, 0.55, 1.0],
              color2=[1.0, 1.0, 1.0], spread=0.0),
        Group("Verticales côtés", effect=3, band=3, color=[1.0, 0.3, 0.75],
              color2=[1.0, 0.85, 0.4], speed=1.2, spread=0.25),
        Group("Horizontales", effect=1, band=2, color=[0.4, 1.0, 0.6],
              color2=[0.1, 0.4, 1.0], speed=0.8, spread=0.1),
    ]


def garage_door_template() -> Scene:
    """Rough garage door: 3 centre verticals, 2 side verticals, 4 horizontals.
    Meant to be dragged onto the real bars, not used as is."""
    scene = Scene(groups=default_groups())
    x0, x1, y0, y1 = 0.15, 0.85, 0.12, 0.92
    # Verticals run bottom → top, so VU fills and comets rise
    for x in (0.4, 0.5, 0.6):
        scene.strips.append(Strip([x, y1], [x, y0], group=0))
    for x in (x0, x1):
        scene.strips.append(Strip([x, y1], [x, y0], group=1))
    for i in range(4):
        y = y0 + (y1 - y0) * (i + 0.5) / 4
        scene.strips.append(Strip([x0, y], [x1, y], group=2, reverse=bool(i % 2)))
    return scene
