"""Live audio: capture what the machine plays, turn it into a few control values.

Capture is the same approach as Audio-Visualizer's core/live_input.py:
* Linux (PipeWire / PulseAudio): Pulse sources listed via `pactl`, sink monitors
  first, opened through PortAudio's `pulse` device with PULSE_SOURCE.
* elsewhere: PortAudio input devices (BlackHole preselected on macOS).

Analysis gives bass / mid / high / level in 0..1 (per-band auto-gain) and a kick
onset detector on the sub band.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import threading
import time
from dataclasses import dataclass

import numpy as np
import sounddevice as sd

SR = 48000
_BLOCK = 256
_RING = 16384


# ── Sources ─────────────────────────────────────────────────────────
@dataclass(frozen=True)
class Source:
    label: str
    device: str | int
    pulse_source: str | None = None


def _pulse_sources() -> list[Source]:
    if not sys.platform.startswith("linux") or not shutil.which("pactl"):
        return []
    try:
        out = subprocess.run(["pactl", "-f", "json", "list", "sources"],
                             capture_output=True, text=True, timeout=3).stdout
        sources = json.loads(out)
    except (OSError, subprocess.SubprocessError, ValueError):
        return []
    monitors, inputs = [], []
    for s in sources:
        name = s.get("name", "")
        desc = s.get("description") or name
        if name.endswith(".monitor"):
            monitors.append(Source(f"Sortie PC : {desc.removeprefix('Monitor of ')}",
                                   "pulse", name))
        else:
            inputs.append(Source(f"Entrée : {desc}", "pulse", name))
    return monitors + inputs


def list_sources() -> tuple[list[Source], int]:
    """→ (sources, index to preselect)."""
    sources = _pulse_sources()
    if sources:
        try:
            sink = subprocess.run(["pactl", "get-default-sink"], capture_output=True,
                                  text=True, timeout=3).stdout.strip()
        except (OSError, subprocess.SubprocessError):
            sink = ""
        idx = next((i for i, s in enumerate(sources)
                    if s.pulse_source == f"{sink}.monitor"), 0)
        return sources, idx

    sources, idx = [], 0
    default_in = sd.default.device[0] if sd.default.device else -1
    for i, d in enumerate(sd.query_devices()):
        if d["max_input_channels"] > 0:
            if i == default_in:
                idx = len(sources)
            sources.append(Source(d["name"], i))
    for j, s in enumerate(sources):
        if "blackhole" in s.label.lower() or "loopback" in s.label.lower():
            idx = j
            break
    return sources, idx


class Capture:
    """Ring-buffered mono capture; latest(n) is safe from any thread."""

    def __init__(self, source: Source):
        self.source = source
        self._ring = np.zeros(_RING, dtype=np.float32)
        self._pos = 0
        self._lock = threading.Lock()
        self._stream: sd.InputStream | None = None

    def start(self) -> None:
        if self.source.pulse_source:
            os.environ["PULSE_SOURCE"] = self.source.pulse_source
            channels = 2
        else:
            channels = min(2, sd.query_devices(self.source.device)["max_input_channels"])
        self._stream = sd.InputStream(device=self.source.device, channels=channels,
                                      samplerate=SR, blocksize=_BLOCK, latency="low",
                                      dtype="float32", callback=self._callback)
        self._stream.start()

    def stop(self) -> None:
        if self._stream is not None:
            self._stream.stop()
            self._stream.close()
            self._stream = None

    def _callback(self, indata, frames, time_info, status) -> None:
        mono = indata.mean(axis=1)
        with self._lock:
            i = self._pos % _RING
            first = min(frames, _RING - i)
            self._ring[i:i + first] = mono[:first]
            self._ring[:frames - first] = mono[first:]
            self._pos += frames

    def latest(self, n: int) -> np.ndarray:
        with self._lock:
            end = self._pos % _RING
            if end >= n:
                return self._ring[end - n:end].copy()
            return np.concatenate((self._ring[end - n:], self._ring[:end]))


# ── Analysis ────────────────────────────────────────────────────────
@dataclass
class Features:
    bass: float = 0.0
    mid: float = 0.0
    high: float = 0.0
    kick: float = 0.0           # impulse, decays fast
    level: float = 0.0
    last_kick: float = -100.0   # time.perf_counter() of the last kick

    def band(self, i: int) -> float:
        return (self.bass, self.mid, self.high, self.kick, self.level)[i]


class Analyzer:
    N = 2048                                     # ~21 ms of delay at 48 kHz
    BANDS = {"bass": (30, 150), "mid": (300, 2000), "high": (4000, 12000)}
    KICK_BAND = (40, 120)
    SMOOTH = {"bass": .35, "mid": .25, "high": .3}
    AGC_DECAY = .998
    PEAK_FLOOR = .5
    KICK_THRESH = .18
    KICK_COOLDOWN = .12

    def __init__(self):
        self.gain = 1.0
        self.f = Features()
        self._win = np.hanning(self.N).astype(np.float32)
        self._freqs = np.fft.rfftfreq(self.N, 1.0 / SR)
        self._masks = {k: (self._freqs >= lo) & (self._freqs < hi)
                       for k, (lo, hi) in self.BANDS.items()}
        self._kmask = (self._freqs >= self.KICK_BAND[0]) & (self._freqs < self.KICK_BAND[1])
        self._peak = {k: self.PEAK_FLOOR for k in self.BANDS}
        self._kpeak = self.PEAK_FLOOR
        self._kbase = 0.0
        self._lvl_peak = 1e-3

    def update(self, samples: np.ndarray, now: float) -> Features:
        f = self.f
        spec = np.abs(np.fft.rfft(samples * self._win))
        for k, m in self._masks.items():
            e = float(spec[m].mean())
            self._peak[k] = max(e, self._peak[k] * self.AGC_DECAY, self.PEAK_FLOOR)
            cur = getattr(f, k)
            setattr(f, k, cur + (min(e / self._peak[k] * self.gain, 1.0) - cur) * self.SMOOTH[k])

        ke = float(spec[self._kmask].mean())
        self._kpeak = max(ke, self._kpeak * self.AGC_DECAY, self.PEAK_FLOOR)
        kn = ke / self._kpeak
        if (kn - self._kbase > self.KICK_THRESH and kn > .5
                and now - f.last_kick > self.KICK_COOLDOWN):
            f.kick = max(f.kick, min(kn * self.gain, 1.0))
            f.last_kick = now
        self._kbase += (kn - self._kbase) * .08
        f.kick *= .80

        rms = float(np.sqrt(np.mean(samples ** 2)))
        self._lvl_peak = max(rms, self._lvl_peak * self.AGC_DECAY, 1e-3)
        f.level += (min(rms / self._lvl_peak * self.gain, 1.0) - f.level) * .3
        return f


class LiveAudio:
    """Capture + analysis, driven once per rendered frame."""

    def __init__(self):
        self.analyzer = Analyzer()
        self.capture: Capture | None = None
        self.error: str | None = None
        self.simulate = False

    @property
    def running(self) -> bool:
        return self.capture is not None

    def start(self, source: Source) -> None:
        self.stop()
        cap = Capture(source)
        try:
            cap.start()
        except Exception as e:        # PortAudio raises plain Exceptions on open
            self.error = str(e)
            return
        self.error = None
        self.capture = cap

    def stop(self) -> None:
        if self.capture is not None:
            self.capture.stop()
            self.capture = None

    def update(self) -> Features:
        now = time.perf_counter()
        f = self.analyzer.f
        if self.capture is not None:
            self.analyzer.update(self.capture.latest(Analyzer.N), now)
        elif self.simulate:
            self._simulate(now)
        else:                       # no input: let everything fall back to dark
            f.bass *= .9; f.mid *= .9; f.high *= .9; f.level *= .9; f.kick *= .8
        return f

    def _simulate(self, now: float) -> None:
        """Fake 128 BPM four-on-the-floor, to set a scene up without music."""
        f = self.analyzer.f
        beat = 60.0 / 128.0
        ph = (now % beat) / beat
        if now - f.last_kick > beat * 0.9 and ph < 0.1:
            f.kick, f.last_kick = 1.0, now
        f.kick *= .80
        f.bass += (np.exp(-ph * 5.0) - f.bass) * .4
        f.mid += ((np.sin(now * 2.5) * .5 + .5) * .7 - f.mid) * .1
        f.high += (((np.sin(now * 7.1) * .5 + .5) * .5) * (ph > .5) - f.high) * .3
        f.level += ((f.bass + f.mid + f.high) / 3 - f.level) * .2
