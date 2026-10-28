"""Matching a color to your paints, and mixing recipes.

Two mixing models, to compare:
  * Mixbox (CC BY-NC 4.0, personal use only), the same model the
    artistpigments.org mixer uses;
  * Kubelka-Munk (km_mixing), the published paint physics, free for a paid
    app.
Both treat every color as if it had the same tinting strength, so a recipe
names sensible paints, but its amounts are only a starting point: a strong
pigment such as phthalo blue needs far less than it says, a weak earth more.

Two searches run for a target color:
  * one paint, lightened with the chosen white (or water) in 1% steps;
  * two paints plus white: a coarse 10% grid over every pair, then 1%
    steps around the best twenty pairs.
Recipes are ranked by CIEDE2000 difference from the target. Two paints
plus white can reach almost any color, so many two-paint recipes match
within 1 (no visible difference); among those, recipes built on a paint
that is already close to the target on its own come first.
"""

from __future__ import annotations

from dataclasses import dataclass
from itertools import combinations

from typing import Callable

import mixbox
import numpy as np

from . import color_study as cs
from . import km_mixing
from .paints import Paint, PaintLibrary

RGB = tuple[int, int, int]

WATER = Paint(id="water", medium="", brand="", name="Water (paper white)", lab=(100.0, 0.0, 0.0),
              source="Thinning with water over white paper, approximated as mixing with white")

COARSE_STEPS = 10
REFINE_PAIRS = 20
REFINE_SPAN = 0.1
TOP = 5


def closeness(delta_e: float) -> str:
    if delta_e < 2:
        return "very close"
    if delta_e < 5:
        return "close"
    if delta_e < 10:
        return "noticeably different"
    return "far off"


@dataclass
class Recipe:
    parts: list[tuple[Paint, float]]  # paint and its share of the mix (0..1); shares add up to 1
    rgb: RGB
    delta_e: float
    off_screen: list[Paint]  # colors clipped to the screen before mixing
    stand_ins: list[Paint]  # paints mixed using a stand-in's color
    also: dict[str, list[Paint]]  # paint id -> other paints with the same color data
    paint_rgbs: dict[str, RGB]  # paint id -> the screen color it was mixed as

    def text(self) -> str:
        return "  +  ".join(f"{p.name} {round(share * 100)}%" for p, share in self.parts)


@dataclass
class MatchResult:
    singles: list[Recipe]
    pairs: list[Recipe]


def _latent(rgb: RGB) -> np.ndarray:
    return np.array(mixbox.rgb_to_latent(rgb))


def mix_latents(latents: np.ndarray) -> np.ndarray:
    """sRGB floats (N, 3) of Mixbox latent mixes (N, 7). Same math as
    mixbox.latent_to_float_rgb, run on whole arrays at once."""
    r, g, b = mixbox._eval_polynomial(latents[:, 0], latents[:, 1], latents[:, 2], latents[:, 3])
    return np.clip(np.stack([r, g, b], axis=1) + latents[:, 4:7], 0.0, 1.0)


@dataclass(frozen=True)
class MixModel:
    """A way of predicting paint mixes. A paint is encoded as a vector;
    shares times those vectors add up to the mix, which decode turns into
    sRGB floats (N, 3)."""
    id: str
    name: str
    size: int
    encode: Callable[[RGB], np.ndarray]
    decode: Callable[[np.ndarray], np.ndarray]


MIXBOX = MixModel("mixbox", "Mixbox", mixbox.LATENT_SIZE, _latent, mix_latents)
KUBELKA_MUNK = MixModel("km", "Kubelka-Munk", km_mixing.SIZE, km_mixing.encode, km_mixing.decode)
MODELS = (MIXBOX, KUBELKA_MUNK)


def mix(paint_rgbs: list[RGB], shares: list[float], model: MixModel = MIXBOX) -> RGB:
    z = sum(s * model.encode(c) for c, s in zip(paint_rgbs, shares))
    return tuple(int(round(v * 255)) for v in model.decode(z[None, :])[0])


class _Palette:
    """Screen colors and encoded colors for the paints being searched.
    Paints sharing the same color data (a stand-in and the paint it borrows
    from) are searched once; the measured paint represents them."""

    def __init__(self, library: PaintLibrary, paints: list[Paint], model: MixModel):
        self.paints: list[Paint] = []
        self.rgbs: list[RGB] = []
        self.off_screen: list[bool] = []
        self.stand_in: list[bool] = []
        self.also: dict[str, list[Paint]] = {}
        by_color: dict[tuple, int] = {}
        for paint in sorted(paints, key=lambda p: p.lab is None):  # measured paints first
            lab = paint.lab if paint is WATER else library.color_of(paint)
            if lab is None:
                continue
            key = tuple(round(v, 3) for v in lab)
            if key in by_color and paint is not WATER:
                self.also.setdefault(self.paints[by_color[key]].id, []).append(paint)
                continue
            by_color[key] = len(self.paints)
            rgb, in_gamut = cs.lab_d50_to_srgb(lab)
            self.paints.append(paint)
            self.rgbs.append(rgb)
            self.off_screen.append(not in_gamut)
            self.stand_in.append(paint.lab is None)
        self.latents = np.array([model.encode(c) for c in self.rgbs]).reshape(-1, model.size)

    def flags(self, indices) -> tuple[list[Paint], list[Paint]]:
        return ([self.paints[i] for i in indices if self.off_screen[i]],
                [self.paints[i] for i in indices if self.stand_in[i]])


def _score(model: MixModel, latents: np.ndarray, target_lab: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    rgb = model.decode(latents)
    return cs.delta_e(cs.srgb_to_lab_d50(rgb), target_lab), rgb


def _recipe(palette: _Palette, indices: list[int], shares: list[float], rgb, delta_e) -> Recipe:
    used = [(i, float(s)) for i, s in zip(indices, shares) if s >= 0.005]
    parts = [(palette.paints[i], s) for i, s in used]
    off, stand = palette.flags([i for i, _ in used])
    also = {p.id: palette.also[p.id] for p, _ in parts if p.id in palette.also}
    rgbs = {palette.paints[i].id: palette.rgbs[i] for i, _ in used}
    return Recipe(parts, tuple(int(round(v * 255)) for v in rgb), float(delta_e), off, stand, also, rgbs)


def find_recipes(target_rgb: RGB, library: PaintLibrary, paints: list[Paint],
                 lightener: Paint | None, model: MixModel = MIXBOX) -> MatchResult:
    """Best single-paint and two-paint recipes for target_rgb from `paints`,
    each lightened with `lightener` (a white paint, WATER, or None)."""
    colors = [p for p in paints if p is not lightener and not (lightener is not None and p.is_white)]
    palette = _Palette(library, colors, model)
    n = len(palette.paints)
    if lightener is not None:
        white = _Palette(library, [lightener], model)
        if white.paints:
            for name in ("paints", "rgbs", "off_screen", "stand_in"):
                getattr(palette, name).extend(getattr(white, name))
            palette.latents = np.vstack([palette.latents, white.latents])
    has_white = len(palette.paints) > n
    if n == 0:
        return MatchResult([], [])
    target_lab = cs.srgb_to_lab_d50(np.asarray(target_rgb, dtype=float) / 255.0)
    Z = palette.latents[:n]
    zw = palette.latents[n] if has_white else np.zeros(model.size)

    # one paint (+ white)
    shares = np.linspace(0.01, 1.0, 100) if has_white else np.array([1.0])
    lat = (shares[None, :, None] * Z[:, None, :] + (1 - shares)[None, :, None] * zw).reshape(-1, model.size)
    de, rgb = _score(model, lat, target_lab)
    de, rgb = de.reshape(n, -1), rgb.reshape(n, -1, 3)
    best = de.argmin(axis=1)
    alone = de[np.arange(n), best]  # how close each paint gets on its own (+ white)
    singles = []
    for i in np.argsort(alone)[:TOP]:
        a = float(shares[best[i]])
        idx, sh = ([i, n], [a, 1 - a]) if has_white else ([i], [1.0])
        singles.append(_recipe(palette, idx, sh, rgb[i, best[i]], de[i, best[i]]))

    # two paints (+ white)
    pairs: list[Recipe] = []
    if n >= 2:
        pair_idx = np.array(list(combinations(range(n), 2)))
        steps = COARSE_STEPS
        grid = np.array([(i, j) for i in range(1, steps) for j in range(1, steps)
                         if (i + j <= steps if has_white else i + j == steps)]) / steps
        a, b = grid[:, 0], grid[:, 1]
        w = 1 - a - b
        lat = (a[None, :, None] * Z[pair_idx[:, 0]][:, None, :] + b[None, :, None] * Z[pair_idx[:, 1]][:, None, :]
               + w[None, :, None] * zw).reshape(-1, model.size)
        de, _ = _score(model, lat, target_lab)
        de = de.reshape(len(pair_idx), -1)
        coarse_best = de.argmin(axis=1)
        refined = []
        for k in np.argsort(de[np.arange(len(pair_idx)), coarse_best])[:REFINE_PAIRS]:
            a0, b0 = grid[coarse_best[k]]
            fa = np.round(np.arange(a0 - REFINE_SPAN, a0 + REFINE_SPAN + 1e-9, 0.01), 2)
            fb = np.round(np.arange(b0 - REFINE_SPAN, b0 + REFINE_SPAN + 1e-9, 0.01), 2)
            fine = np.array([(x, y) for x in fa for y in fb if x >= 0.01 and y >= 0.01
                             and (x + y <= 1.0 + 1e-9 if has_white else abs(x + y - 1.0) < 1e-9)])
            i, j = pair_idx[k]
            fw = 1 - fine[:, 0] - fine[:, 1]
            lat = fine[:, :1] * Z[i] + fine[:, 1:2] * Z[j] + fw[:, None] * zw
            fde, frgb = _score(model, lat, target_lab)
            m = int(fde.argmin())
            idx, sh = [i, j], [fine[m, 0], fine[m, 1]]
            if has_white:
                idx, sh = idx + [n], sh + [max(0.0, 1 - fine[m, 0] - fine[m, 1])]
            refined.append((max(float(fde[m]), 1.0), min(alone[i], alone[j]),
                            _recipe(palette, idx, sh, frgb[m], fde[m])))
        pairs = [r for *_, r in sorted(refined, key=lambda t: (t[0], t[1]))[:TOP]]
        for r in pairs:  # main color first, white last
            colored = sorted([pt for pt in r.parts if pt[0] is not lightener], key=lambda pt: -pt[1])
            r.parts = colored + [pt for pt in r.parts if pt[0] is lightener]
    return MatchResult(singles, pairs)


def predict(recipe: Recipe, target_rgb: RGB, model: MixModel) -> tuple[RGB, float]:
    """What `model` says a recipe's amounts make, and how far that is from
    the target: the other model's view of the same recipe."""
    rgb = mix([recipe.paint_rgbs[p.id] for p, _ in recipe.parts], [s for _, s in recipe.parts], model)
    target_lab = cs.srgb_to_lab_d50(np.asarray(target_rgb, dtype=float) / 255.0)
    return rgb, float(cs.delta_e(cs.srgb_to_lab_d50(np.asarray(rgb, dtype=float) / 255.0), target_lab))
