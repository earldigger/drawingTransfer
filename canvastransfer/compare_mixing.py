"""Mixbox next to Kubelka-Munk, as an HTML page.

    python -m canvastransfer.compare_mixing [--library paints.json] [out.html]

Two parts:
  * Pair strips: two paints mixed in 10% steps, as plain RGB averaging (what
    a screen does), Mixbox and Kubelka-Munk, with the difference between the
    two models at each step.
  * Recipes: sample colors matched with each model, and each winning recipe
    checked with the other model: if the other model says the same amounts
    make something far off, the amounts are a guess either way.

Neither model is checked against real paint here: that needs swatches of
real mixes photographed or measured. The page shows where the models agree
(trust the result more) and where they disagree (mix a test swatch).

Without --library the paints are rough screen colors of common pigments,
not measurements. With your library (paints.json, in the app's data
folder) the recipes use your own paints, all of one medium.
"""

from __future__ import annotations

import argparse
import html
from pathlib import Path

import numpy as np

from . import color_study as cs
from .mixing import KUBELKA_MUNK, MIXBOX, MODELS, MixModel, find_recipes, mix, predict
from .paints import Paint, PaintLibrary

RGB = tuple[int, int, int]

# Rough screen colors of common oil pigments: for the comparison only.
SAMPLE_PAINTS = {
    "Titanium White": "#F4F4F0",
    "Ivory Black": "#2A2826",
    "Lemon Yellow": "#F1E21E",
    "Cadmium Yellow Medium": "#F6B500",
    "Yellow Ochre": "#C68A2E",
    "Cadmium Red Light": "#E2401E",
    "Alizarin Crimson": "#7A1E2A",
    "Burnt Sienna": "#8A3F22",
    "Burnt Umber": "#4A3225",
    "Ultramarine Blue": "#23297A",
    "Phthalo Blue": "#0C2B5C",
    "Phthalo Green": "#00433A",
    "Viridian": "#1F6A5A",
}

PAIRS = [
    ("Ultramarine Blue", "Cadmium Yellow Medium"),
    ("Phthalo Blue", "Lemon Yellow"),
    ("Cadmium Yellow Medium", "Ivory Black"),
    ("Cadmium Red Light", "Titanium White"),
    ("Ultramarine Blue", "Titanium White"),
    ("Alizarin Crimson", "Titanium White"),
    ("Ultramarine Blue", "Burnt Sienna"),
    ("Phthalo Green", "Alizarin Crimson"),
    ("Cadmium Red Light", "Ultramarine Blue"),
    ("Yellow Ochre", "Ivory Black"),
]

TARGETS = {
    "Light skin": "#E8B8A0",
    "Skin in shadow": "#9A6A55",
    "Sky": "#8FB4D8",
    "Foliage": "#4E6B35",
    "Deep green": "#2F4A3A",
    "Orange": "#E07A2A",
    "Warm gray": "#8C857C",
    "Violet": "#6A4A8A",
}

ZORN = ["Titanium White", "Yellow Ochre", "Cadmium Red Light", "Ivory Black"]
STEPS = np.linspace(0.0, 1.0, 11)


def _rgb(hex_code: str) -> RGB:
    h = hex_code.lstrip("#")
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))


def _hex(rgb: RGB) -> str:
    return cs.hex_code(rgb)


def _lab(rgb: RGB) -> np.ndarray:
    return cs.srgb_to_lab_d50(np.asarray(rgb, dtype=float) / 255.0)


def delta_e(a: RGB, b: RGB) -> float:
    return float(cs.delta_e(_lab(a), _lab(b)))


def sample_library() -> PaintLibrary:
    paints = [Paint(id=name.lower().replace(" ", "-"), medium="oil", brand="Sample", name=name,
                    pigments=["PW6"] if name == "Titanium White" else [],  # so it lightens the mixes
                    lab=tuple(float(v) for v in _lab(_rgb(code))))
              for name, code in SAMPLE_PAINTS.items()]
    return PaintLibrary(paints)


def screen_rgb(library: PaintLibrary, paint: Paint) -> RGB:
    return cs.lab_d50_to_srgb(library.color_of(paint))[0]


def strip(a: RGB, b: RGB, model: MixModel | None) -> list[RGB]:
    """a to b in 10% steps; model None is plain RGB averaging."""
    if model is None:
        return [tuple(int(round((1 - t) * x + t * y)) for x, y in zip(a, b)) for t in STEPS]
    return [mix([a, b], [1 - t, t], model) for t in STEPS]


def pair_rows(library: PaintLibrary) -> list[dict]:
    by_name = {p.name: p for p in library.paints}
    rows = []
    for na, nb in PAIRS:
        if na not in by_name or nb not in by_name:
            continue
        a, b = screen_rgb(library, by_name[na]), screen_rgb(library, by_name[nb])
        strips = {name: strip(a, b, m) for name, m in (("RGB average", None), ("Mixbox", MIXBOX),
                                                         ("Kubelka-Munk", KUBELKA_MUNK))}
        gaps = [delta_e(x, y) for x, y in zip(strips["Mixbox"], strips["Kubelka-Munk"])]
        rows.append({"name": f"{na} + {nb}", "strips": strips, "gaps": gaps})
    return rows


def recipe_rows(library: PaintLibrary, paints: list[Paint], white: Paint | None) -> list[dict]:
    rows = []
    for name, code in TARGETS.items():
        target = _rgb(code)
        row = {"name": name, "target": target, "models": {}}
        for model in MODELS:
            result = find_recipes(target, library, paints, white, model)
            best = result.pairs[0] if result.pairs else (result.singles[0] if result.singles else None)
            if best is None:
                continue
            other = next(m for m in MODELS if m is not model)
            other_rgb, other_de = predict(best, target, other)
            row["models"][model.name] = {"recipe": best, "other": other.name,
                                         "other_rgb": other_rgb, "other_de": other_de}
        rows.append(row)
    return rows


def _chips(colors: list[RGB], size: int = 34) -> str:
    return "".join(f'<span class="c" style="background:{_hex(c)};width:{size}px"></span>' for c in colors)


def _recipe_html(entry: dict, target: RGB) -> str:
    r = entry["recipe"]
    lines = "<br>".join(f"{round(s * 100)}% {html.escape(p.name)}" for p, s in r.parts)
    return (f'<div class="pair"><span class="c big" style="background:{_hex(target)}"></span>'
            f'<span class="c big" style="background:{_hex(r.rgb)}"></span>'
            f'<span class="c big" style="background:{_hex(entry["other_rgb"])}"></span></div>'
            f'<div class="small">ΔE {r.delta_e:.1f} · {entry["other"]} says ΔE {entry["other_de"]:.1f}</div>'
            f'<div>{lines}</div>')


def _recipe_table(title: str, rows: list[dict]) -> str:
    out = [f"<h2>{html.escape(title)}</h2>",
           "<p class='small'>Each cell: your color, that model's best mix, and what the other model "
           "says the same amounts make.</p>",
           "<table><tr><th>Color</th><th>Mixbox's recipe</th><th>Kubelka-Munk's recipe</th></tr>"]
    for row in rows:
        cells = "".join(f"<td>{_recipe_html(row['models'][m.name], row['target'])}</td>"
                        if m.name in row["models"] else "<td>—</td>" for m in MODELS)
        out.append(f"<tr><td><b>{html.escape(row['name'])}</b><br><span class='small'>"
                   f"{_hex(row['target'])}</span></td>{cells}</tr>")
    out.append("</table>")
    return "\n".join(out)


def report(library: PaintLibrary, medium: str, sample: bool) -> str:
    paints = [p for p in library.in_medium(medium) if library.color_of(p) is not None and p.enabled]
    whites = [p for p in paints if p.is_white]
    white = next((p for p in whites if "titanium" in p.name.lower()), whites[0] if whites else None)
    parts = ["<!doctype html><meta charset='utf-8'><title>Mixbox vs Kubelka-Munk</title>",
             """<style>
body{font:14px -apple-system,system-ui,sans-serif;margin:24px;color:#222;background:#fafafa;max-width:1100px}
.c{display:inline-block;height:34px;vertical-align:middle}.c.big{width:44px;height:44px}
.strip{display:flex;align-items:center;gap:10px;margin:2px 0}.label{width:110px;color:#555}
.gaps{display:flex;margin-left:120px;color:#888;font-size:11px}.gaps span{width:34px;text-align:center}
table{border-collapse:collapse;width:100%}td,th{border-top:1px solid #ddd;padding:8px;vertical-align:top;text-align:left}
.small{color:#777;font-size:12px}.pair{display:flex;margin-bottom:4px}h3{margin:18px 0 4px}
</style>""",
             "<h1>Mixbox vs Kubelka-Munk</h1>",
             "<p>Neither model is checked against real paint here. Where they agree, trust the prediction "
             "more; where they disagree, mix a test swatch. "
             + ("Paint colors are rough screen colors of common pigments, not measurements."
                if sample else f"Paints: your {html.escape(medium)} paints with color data.") + "</p>",
             "<h2>Two paints, 0–100% in 10% steps</h2>",
             "<p class='small'>Grey numbers: ΔE between Mixbox and Kubelka-Munk at that step "
             "(under 2 is hard to see, over 10 is a different color).</p>"]
    for row in pair_rows(library):
        parts.append(f"<h3>{html.escape(row['name'])}</h3>")
        for name, colors in row["strips"].items():
            parts.append(f'<div class="strip"><span class="label">{name}</span><span>{_chips(colors)}</span></div>')
        parts.append('<div class="gaps">' + "".join(f"<span>{g:.0f}</span>" for g in row["gaps"]) + "</div>")
    if sample:
        zorn = [p for p in paints if p.name in ZORN]
        parts.append(_recipe_table("Recipes: Zorn palette (white, ochre, red, black)",
                                   recipe_rows(library, zorn, white)))
    parts.append(_recipe_table(f"Recipes: all {len(paints)} paints", recipe_rows(library, paints, white)))
    return "\n".join(parts)


def main(argv=None) -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("out", nargs="?", default="mixing-comparison.html")
    ap.add_argument("--library", type=Path, help="your paints.json; without it, sample paints")
    ap.add_argument("--medium", default="oil")
    args = ap.parse_args(argv)
    library = PaintLibrary.load(args.library) if args.library else sample_library()
    Path(args.out).write_text(report(library, args.medium, args.library is None), encoding="utf-8")
    print(f"Wrote {args.out}")


if __name__ == "__main__":
    main()
