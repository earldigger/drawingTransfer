"""The paint library: the tubes you own, grouped by medium, each with its
measured masstone color (CIELAB D50, as artistpigments.org lists it).

Paints come from a saved artistpigments.org collection page (File > Save
Page As in the browser) or are entered by hand. A paint without color data
can borrow the color of a similar paint ("stand-in"): chosen by hand, or
picked automatically by matching pigments and names.
"""

from __future__ import annotations

import difflib
import html
import json
import re
import uuid
from dataclasses import asdict, dataclass, field
from html.parser import HTMLParser
from pathlib import Path

SITE = "https://artistpigments.org"
LIBRARY_VERSION = 1

MEDIUM_LABELS = {"oil": "Oil", "watercolor": "Watercolor", "acrylic": "Acrylic", "gouache": "Gouache"}
OPACITY_LABELS = {"T": "Transparent", "ST": "Semi-Transparent", "SO": "Semi-Opaque", "O": "Opaque"}
SOURCE_LABELS = {
    "Chart": "Measured on a color chart",
    "Handmade masstone sample": "Measured on a handmade swatch",
    "Manufacturer data (Munsell)": "From the maker's Munsell notation (less exact)",
    "Entered by hand": "Entered by hand",
}
# words that describe a paint line rather than its color, ignored when comparing names
NAME_NOISE = {"genuine", "hue", "extra", "no", "the", "de", "of", "mars"}


def medium_label(medium: str) -> str:
    return MEDIUM_LABELS.get(medium, medium.title() or "Other")


@dataclass
class Paint:
    id: str
    medium: str
    brand: str
    name: str
    code: str = ""
    pigments: list[str] = field(default_factory=list)
    opacity: str = ""
    lab: tuple[float, float, float] | None = None  # CIELAB D50 of the masstone
    source: str = ""
    url: str = ""
    # yours, kept when the collection is imported again
    favorite: bool = False
    enabled: bool = True  # offered in matches and mixes
    stand_in: str | None = None  # None: automatic, "": no stand-in, else a paint id

    @property
    def manual(self) -> bool:
        return self.id.startswith("manual-")

    @property
    def is_white(self) -> bool:
        return bool(self.pigments) and all(p.upper().startswith("PW") for p in self.pigments)

    def label(self) -> str:
        return f"{self.brand} {self.code} {self.name}".replace("  ", " ").strip()

    def to_dict(self) -> dict:
        d = asdict(self)
        d["lab"] = list(self.lab) if self.lab else None
        return d

    @classmethod
    def from_dict(cls, d: dict) -> "Paint":
        known = {k: v for k, v in d.items() if k in cls.__dataclass_fields__}
        if known.get("lab") is not None:
            known["lab"] = tuple(float(v) for v in known["lab"])
        return cls(**known)


def new_manual_id() -> str:
    return f"manual-{uuid.uuid4().hex[:10]}"


@dataclass
class Palette:
    """A limited palette you made: a named set of paints from one medium."""

    id: str
    name: str
    medium: str
    paint_ids: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "Palette":
        return cls(**{k: v for k, v in d.items() if k in cls.__dataclass_fields__})


def new_palette_id() -> str:
    return f"palette-{uuid.uuid4().hex[:10]}"


# -- reading pasted color text -------------------------------------------

# a number not glued to a letter or a degree sign, so "D50 2°" in a pasted line is skipped
_NUMBER = re.compile(r"(?<![A-Za-z\d.,])[-+−]?\d+(?:[.,]\d+)?(?![\d°A-Za-z])")
_HEX = re.compile(r"#?\b([0-9a-fA-F]{6})\b")


def parse_lab_text(text: str) -> tuple[float, float, float] | None:
    """The first three numbers in pasted text, read as L*, a*, b*. Accepts
    lines like "L* 13.26 a* 22.45 b* -50.80", "13.26, 22.45, -50.80" or
    "CIELAB D50 2°: 13.26 22.45 -50.80".
    A lone hex code (#03196c) is converted from sRGB instead."""
    text = text.strip()
    if not text:
        return None
    numbers = [float(n.replace("−", "-").replace(",", ".")) for n in _NUMBER.findall(text)]
    hex_match = _HEX.search(text)
    if hex_match and len(numbers) < 3:
        from .color_study import lab_d50

        h = hex_match.group(1)
        return tuple(float(v) for v in lab_d50(tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))))
    if len(numbers) < 3:
        return None
    L, a, b = numbers[:3]
    if not 0 <= L <= 100:
        return None
    return (L, a, b)


# -- saved collection pages ------------------------------------------------

class _CollectionParser(HTMLParser):
    """Collects each paint's list entry (names, pigments, properties), its
    color-plane dot (Lab and data source) and its tooltip."""

    def __init__(self):
        super().__init__()
        self.items: dict[str, dict] = {}
        self.dots: dict[str, dict] = {}

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag == "span" and a.get("class") == "color" and "data-l" in a and "data-paint-id" in a:
            self.dots.setdefault(a["data-paint-id"], a)
        elif tag == "div" and "data-paint-id" in a and "data-brand-id" in a:
            # a paint appears in several lists (swatch box, full list); combine them
            merged = self.items.setdefault(a["data-paint-id"], {})
            for key, value in a.items():
                if value and not merged.get(key):
                    merged[key] = value


def _tooltip_small(text: str) -> str:
    text = html.unescape(text or "")
    m = re.search(r"<small>(.*?)</small>", text)
    return m.group(1).strip() if m else ""


def parse_collection_html(text: str) -> tuple[str, list[Paint]]:
    """(collection title, paints) from a saved artistpigments.org collection
    page. Raises ValueError if the page holds no paints."""
    parser = _CollectionParser()
    parser.feed(text)
    if not parser.items:
        raise ValueError("No paints found. Save the collection page itself (File > Save Page As) "
                         "while it shows your paints.")
    paints = []
    for pid, it in parser.items.items():
        dot = parser.dots.get(pid)
        code, name = it.get("data-code", ""), it.get("data-name", "")
        pigments = json.loads(html.unescape(it.get("data-pigment") or "[]"))
        key = it.get("data-filter-key", "")
        tail = " ".join(x for x in (code, name) if x)
        brand = html.unescape(it.get("data-brand", "")) or (
            key.split(f" {tail}")[0] if tail and f" {tail}" in key else it.get("data-brand-id", ""))
        lab, source, url = None, "", ""
        if dot:
            lab = (float(dot["data-l"]), float(dot["data-a"]), float(dot["data-b"]))
            source = _tooltip_small(dot.get("data-tooltip"))
            url = SITE + dot.get("data-path", "") if dot.get("data-path") else ""
        if not url:
            m = re.search(rf'/brands/[^"/]+/{re.escape(pid)}-[^"/]+(?=")', text)
            url = SITE + m.group(0) if m else ""
        paints.append(Paint(id=pid, medium=it.get("data-medium-id", "") or "other", brand=brand, name=name,
                            code=code, pigments=pigments, opacity=it.get("data-transparency", ""),
                            lab=lab, source=source, url=url))
    m = re.search(r'update_attr\?attr=name"[^>]*?raw-value="([^"]*)"', text)
    title = html.unescape(m.group(1)).strip() if m else ""
    return title or "collection", paints


# -- stand-ins -------------------------------------------------------------

def _name_tokens(name: str) -> list[str]:
    words = re.findall(r"[a-zà-ÿ]+", name.lower())
    return [w for w in words if w not in NAME_NOISE]


def name_similarity(a: str, b: str) -> float:
    """0..1: share of words the two names have in common, allowing small
    spelling differences ("Caput Mortum" ~ "Caput Mortuum")."""
    ta, tb = _name_tokens(a), _name_tokens(b)
    if not ta or not tb:
        return 0.0
    unmatched = list(tb)
    matched = 0
    for w in ta:
        best = max(unmatched, key=lambda u: difflib.SequenceMatcher(None, w, u).ratio(), default=None)
        if best is not None and difflib.SequenceMatcher(None, w, best).ratio() >= 0.8:
            matched += 1
            unmatched.remove(best)
    return 2 * matched / (len(ta) + len(tb))


def _pigment_set(paint: Paint) -> frozenset[str]:
    return frozenset(p.upper() for p in paint.pigments)


# -- the library -------------------------------------------------------------

class PaintLibrary:
    def __init__(self, paints: list[Paint] | None = None, path: Path | None = None,
                 palettes: list[Palette] | None = None):
        self.paints: list[Paint] = list(paints or [])
        self.palettes: list[Palette] = list(palettes or [])
        self.path = path
        self.revision = 0  # bumped on every change, so results can be cached

    # storage
    @classmethod
    def load(cls, path: Path) -> "PaintLibrary":
        path = Path(path)
        if not path.exists():
            return cls(path=path)
        data = json.loads(path.read_text(encoding="utf-8"))
        return cls([Paint.from_dict(d) for d in data.get("paints", [])], path=path,
                   palettes=[Palette.from_dict(d) for d in data.get("palettes", [])])

    def save(self) -> None:
        if self.path is None:
            return
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps({"version": LIBRARY_VERSION, "paints": [p.to_dict() for p in self.paints],
                                   "palettes": [p.to_dict() for p in self.palettes]}, indent=1), encoding="utf-8")
        tmp.replace(self.path)

    def changed(self) -> None:
        self.revision += 1
        self.save()

    # lookup
    def get(self, paint_id: str | None) -> Paint | None:
        return next((p for p in self.paints if p.id == paint_id), None)

    def media(self) -> list[str]:
        order = list(MEDIUM_LABELS)
        found = {p.medium for p in self.paints}
        return sorted(found, key=lambda m: (order.index(m) if m in order else len(order), m))

    def in_medium(self, medium: str) -> list[Paint]:
        return [p for p in self.paints if p.medium == medium]

    def get_palette(self, palette_id: str | None) -> Palette | None:
        return next((p for p in self.palettes if p.id == palette_id), None)

    def palette_paints(self, palette: Palette) -> list[Paint]:
        return [p for p in (self.get(i) for i in palette.paint_ids) if p is not None]

    # editing
    def add(self, paint: Paint) -> None:
        self.paints.append(paint)
        self.changed()

    def remove(self, paint_id: str) -> None:
        self.paints = [p for p in self.paints if p.id != paint_id]
        for p in self.paints:
            if p.stand_in == paint_id:
                p.stand_in = None
        for palette in self.palettes:
            if paint_id in palette.paint_ids:
                palette.paint_ids.remove(paint_id)
        self.changed()

    def merge(self, imported: list[Paint]) -> tuple[int, int]:
        """Add new paints and refresh the site data of known ones, keeping
        your favorites, on/off choices and stand-ins. Nothing is removed.
        Returns (added, updated)."""
        added = updated = 0
        for new in imported:
            old = self.get(new.id)
            if old is None:
                self.paints.append(new)
                added += 1
                continue
            for name in ("medium", "brand", "name", "code", "pigments", "opacity", "lab", "source", "url"):
                setattr(old, name, getattr(new, name))
            updated += 1
        self.changed()
        return added, updated

    # stand-ins
    def auto_stand_in(self, paint: Paint) -> Paint | None:
        """A measured paint of the same medium that should look similar:
        first the same pigments (closest name wins), then a near-identical
        name, then a similar name sharing a pigment."""
        candidates = [p for p in self.paints if p.medium == paint.medium and p.lab is not None and p.id != paint.id]
        if not candidates:
            return None
        pigments = _pigment_set(paint)
        same = [p for p in candidates if pigments and _pigment_set(p) == pigments]
        if same:
            return max(same, key=lambda p: name_similarity(paint.name, p.name))
        scored = [(name_similarity(paint.name, p.name), len(pigments & _pigment_set(p)), p) for p in candidates]
        good = [s for s in scored if s[0] >= 0.8 or (s[0] >= 0.6 and s[1])]
        return max(good, key=lambda s: (s[0], s[1]))[2] if good else None

    def stand_in_for(self, paint: Paint) -> Paint | None:
        """Automatic stand-ins stay within the paint's medium; one chosen by
        hand may come from any medium (e.g. a watercolor for an oil)."""
        if paint.lab is not None or paint.stand_in == "":
            return None
        if paint.stand_in:
            chosen = self.get(paint.stand_in)
            return chosen if chosen is not None and chosen.lab is not None else None
        return self.auto_stand_in(paint)

    def color_of(self, paint: Paint) -> tuple[float, float, float] | None:
        """The paint's own Lab, or its stand-in's."""
        if paint.lab is not None:
            return paint.lab
        stand_in = self.stand_in_for(paint)
        return stand_in.lab if stand_in else None
