"""Kubelka-Munk pigment mixing: a free alternative to Mixbox.

Kubelka-Munk is the long-published physics of paint: each pigment absorbs
(K) and scatters (S) light differently at each wavelength, and in a mix
those add up in proportion to how much of each pigment there is. With the
single-constant form used here, only K/S matters per wavelength:

    K/S = (1 - R)^2 / (2R)        R = 1 + K/S - sqrt((K/S)^2 + 2 K/S)

where R is the reflectance (0..1). Mixing adds the K/S curves, weighted by
each paint's share, and turns the result back into a color.

The library only has one color per paint, not its spectrum, so each color
is turned into the smoothest reflectance curve that produces it (the
problem Meng et al. 2015 solve; solved directly here, ~25x faster than
colour-science's general optimizer) -- the same idea as spectral.js. A real
measured spectrum would be more faithful; this is the free stand-in.

Plain Kubelka-Munk with one color per paint lets dark paints swamp light
ones: half red, half white comes out nearly pure red. As in spectral.js,
each paint is weighted by its lightness (Y) times its share squared, which
stands in for the scattering that a single color can't tell us. So white
and yellow count for more than their share, black and dark blues for less,
and a small share counts for little. Checked against the artistpigments.org
mixer's Spectral.js mode: brown ochre to lemon yellow in 13 steps is within
ΔE 1 on the yellow half and ΔE 5 on the dark end, where the two guess the
brown's spectrum differently.

Weakest on near-black paints: their color says little about their spectrum,
so their tints are a guess (e.g. a dark indanthrone blue tints to lavender
here, where Mixbox, trained on real pigments, tints it blue). Like Mixbox,
this is a guess at tinting strength, so the amounts are a
guide only. Everything here is free to use in a paid app.
"""

from __future__ import annotations

import numpy as np

RGB = tuple[int, int, int]

SHARE_POWER = 2  # spectral.js weights each paint by share² × lightness
R_MIN = 1e-4  # a reflectance of exactly 0 would make K/S infinite
WAVELENGTHS = (380, 730, 10)  # nm: 36 bands, enough for smooth paint spectra

# linear sRGB from XYZ (D65), the sRGB standard's matrix
_XYZ_TO_RGB = np.array([[3.2404542, -1.5371385, -0.4985314],
                        [-0.9692660, 1.8760108, 0.0415560],
                        [0.0556434, -0.2040259, 1.0572252]])

_RGB_TO_XYZ = np.linalg.inv(_XYZ_TO_RGB)

_cache: dict[RGB, np.ndarray] = {}
_weights: np.ndarray | None = None


def _setup() -> np.ndarray:
    """Weights (bands, 3) turning a reflectance curve into XYZ in daylight:
    the CIE 1931 2° observer times D65, scaled so a perfect white has Y = 1.
    Loaded once; colour-science is slow to import."""
    global _weights
    if _weights is None:
        import colour

        shape = colour.SpectralShape(*WAVELENGTHS)
        cmfs = colour.MSDS_CMFS["CIE 1931 2 Degree Standard Observer"].copy().align(shape)
        illuminant = colour.SDS_ILLUMINANTS["D65"].copy().align(shape)
        weights = cmfs.values * illuminant.values[:, None]
        _weights = weights / weights[:, 1].sum()
    return _weights


def _smoothest(xyz: np.ndarray) -> np.ndarray:
    """The reflectance curve with the smallest steps between neighbouring
    bands that gives `xyz`, kept between R_MIN and 1. Solves the equations
    for the best curve, pins any band that went out of range to its limit,
    and solves again for the rest until none do."""
    a = _setup().T  # (3, bands)
    n = a.shape[1]
    d = np.diff(np.eye(n), axis=0)
    h = 2 * d.T @ d
    pinned = np.full(n, np.nan)
    for _ in range(n):
        free = np.isnan(pinned)
        fixed = np.where(free, 0.0, pinned)
        k = int(free.sum())
        af = a[:, free]
        system = np.block([[h[np.ix_(free, free)], af.T], [af, np.zeros((3, 3))]])
        rhs = np.concatenate([-h[np.ix_(free, ~free)] @ fixed[~free], xyz - a[:, ~free] @ fixed[~free]])
        curve = fixed.copy()
        curve[free] = np.linalg.lstsq(system, rhs, rcond=None)[0][:k]
        low, high = free & (curve < R_MIN), free & (curve > 1.0)
        if not (low.any() or high.any()):
            break
        pinned[low], pinned[high] = R_MIN, 1.0
    return np.clip(curve, R_MIN, 1.0)


def _srgb_to_linear(rgb: np.ndarray) -> np.ndarray:
    return np.where(rgb <= 0.04045, rgb / 12.92, ((rgb + 0.055) / 1.055) ** 2.4)


def reflectance(rgb: RGB) -> np.ndarray:
    """The smoothest reflectance curve (bands,) that looks like this sRGB color in daylight."""
    rgb = tuple(int(v) for v in rgb)
    if rgb not in _cache:
        linear = _srgb_to_linear(np.asarray(rgb, dtype=float) / 255.0)
        _cache[rgb] = _smoothest(_RGB_TO_XYZ @ linear)
    return _cache[rgb]


def ks(r: np.ndarray) -> np.ndarray:
    r = np.clip(r, R_MIN, 1.0)
    return (1.0 - r) ** 2 / (2.0 * r)


def reflectance_from_ks(k: np.ndarray) -> np.ndarray:
    return 1.0 + k - np.sqrt(k * k + 2.0 * k)


def lightness(r: np.ndarray) -> float:
    """Y (0..1) of a reflectance curve in daylight."""
    return float(r @ _setup()[:, 1])


def encode(rgb: RGB) -> np.ndarray:
    """A paint as what gets added up when mixing: its K/S curve weighted by
    its lightness, then the lightness itself (bands + 1,). Shares squared
    times these add up linearly, like Mixbox latents; decode divides the two
    back out."""
    r = reflectance(rgb)
    y = max(lightness(r), R_MIN)
    return np.append(y * ks(r), y)


def decode(mixes: np.ndarray) -> np.ndarray:
    """sRGB floats (N, 3), 0..1, of mixes (N, bands + 1) of encoded paints."""
    weights = _setup()
    curves = mixes[:, :-1] / np.maximum(mixes[:, -1:], 1e-12)
    xyz = reflectance_from_ks(np.maximum(curves, 0.0)) @ weights
    linear = np.clip(xyz @ _XYZ_TO_RGB.T, 0.0, 1.0)
    return np.where(linear <= 0.0031308, 12.92 * linear, 1.055 * linear ** (1 / 2.4) - 0.055)


BANDS = (WAVELENGTHS[1] - WAVELENGTHS[0]) // WAVELENGTHS[2] + 1
SIZE = BANDS + 1  # what encode returns: a K/S value per band, then lightness


def mix(paint_rgbs: list[RGB], shares: list[float]) -> RGB:
    curve = sum(s ** SHARE_POWER * encode(c) for c, s in zip(paint_rgbs, shares))
    return tuple(int(round(v * 255)) for v in decode(curve[None, :])[0])
