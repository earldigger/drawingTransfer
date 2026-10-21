"""Classic limited palettes, described by role ("yellow ochre", "a cool
red") and filled from the paints you own.

Each role lists the pigments and name words that fit it, plus fallback
pigments for a modern substitute (cadmium or pyrrole red for vermilion,
titanium for lead white). A role with no fitting paint stays empty. The
palettes are traditions rather than exact historical inventories; see
each one's note.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .paints import Paint, PaintLibrary


@dataclass(frozen=True)
class Role:
    name: str
    pigments: frozenset[str]
    words: tuple[str, ...] = ()
    fallback: frozenset[str] = frozenset()
    prefer: tuple[str, ...] = ()  # tie-breaking name words, e.g. "scarlet" for a warm red


def _words(text: str) -> tuple[str, ...]:
    return tuple(w.strip() for w in text.split(",") if w.strip())


def role(name: str, pigments: str, words: str = "", fallback: str = "", prefer: str = "") -> Role:
    split = lambda text: frozenset(p.strip().upper() for p in text.split(",") if p.strip())  # noqa: E731
    return Role(name, split(pigments), _words(words), split(fallback), _words(prefer))


LEAD_WHITE = role("Lead white", "PW1", "lead white, flake white, cremnitz", "PW6, PW4, PW5")
TITANIUM_WHITE = role("White", "PW6", "titanium white", "PW1, PW4, PW5")
YELLOW_OCHRE = role("Yellow ochre", "PY43, PY42", "yellow ochre")
VERMILION = role("Vermilion", "PR106", "vermilion, vermillion", "PR108, PR255, PR254")
IVORY_BLACK = role("Ivory black", "PBK9", "ivory black, bone black", "PBK8, PBK11, PBK6")
RED_EARTH = role("Red earth", "PR101, PR102", "english red, light red, venetian red, indian red, red ochre")
ALIZARIN = role("Alizarin crimson / madder", "PR83", "alizarin, madder, crimson", "PR177, PV19, PR264, PR176")
CADMIUM_YELLOW = role("Cadmium yellow", "PY35, PY37", "cadmium yellow")
VIRIDIAN = role("Viridian", "PG18", "viridian")
COBALT_BLUE = role("Cobalt blue", "PB28", "cobalt blue")
ULTRAMARINE = role("Ultramarine", "PB29", "ultramarine")
BURNT_UMBER = role("Burnt umber", "PBR7", "burnt umber, raw umber, umber")


@dataclass(frozen=True)
class Template:
    key: str
    name: str
    note: str
    roles: tuple[Role, ...]


TEMPLATES = (
    Template("zorn", "Zorn", "Anders Zorn's well-known four colors: lead white, yellow ochre, vermilion and ivory "
             "black. His surviving palettes show he added other colors at times.",
             (LEAD_WHITE, YELLOW_OCHRE, VERMILION, IVORY_BLACK)),
    Template("sargent", "Sargent (as commonly cited)",
             "The colors usually given for John Singer Sargent. Published lists vary and are poorly sourced; "
             "pigment studies of his work confirm vermilion, red lake, ochres, cobalt, ultramarine and lead white.",
             (LEAD_WHITE, IVORY_BLACK, VERMILION, ALIZARIN, RED_EARTH, YELLOW_OCHRE, CADMIUM_YELLOW,
              VIRIDIAN, COBALT_BLUE, ULTRAMARINE)),
    Template("classical", "Classical four-color",
             "White, yellow ochre, red earth and black: the four-color palette Pliny credits to the ancient Greek "
             "painters. Cool notes come from black against the warm earths.",
             (LEAD_WHITE, YELLOW_OCHRE, RED_EARTH, IVORY_BLACK)),
    Template("triad", "Primary triad", "One yellow, one crimson and one blue plus white.",
             (TITANIUM_WHITE, role("Yellow", "PY35, PY37, PY3, PY74, PY65, PY184", "cadmium yellow, lemon, hansa"),
              role("Crimson", "PR83, PR177, PV19, PR122, PR202, PR264", "alizarin, crimson, quinacridone, magenta, rose",
                   "PR108, PR255"),
              ULTRAMARINE)),
    Template("split", "Split primary", "A warm and a cool version of each primary, plus white.",
             (TITANIUM_WHITE,
              role("Cool yellow", "PY35, PY3, PY175, PY184", "lemon, primrose"),
              role("Warm yellow", "PY35, PY37, PY65, PY110, PY83", "deep, medium, orange"),
              role("Warm red", "PR108, PR255, PR254, PR106", "cadmium red, vermilion, scarlet, pyrrole",
                   prefer="scarlet, light, medium"),
              role("Cool red", "PR83, PR177, PV19, PR122, PR202, PR264", "alizarin, crimson, quinacridone, magenta"),
              role("Warm blue", "PB29", "ultramarine"),
              role("Cool blue", "PB15, PB15:1, PB15:3, PB15:4, PB27", "phthalo, prussian", "PB35, PB36"))),
    Template("earth", "Earth palette", "Earths with ultramarine and black: low chroma, very harmonious.",
             (TITANIUM_WHITE, YELLOW_OCHRE, RED_EARTH, BURNT_UMBER, ULTRAMARINE, IVORY_BLACK)),
)


def template(key: str) -> Template | None:
    return next((t for t in TEMPLATES if t.key == key), None)


@dataclass
class Filled:
    role: Role
    paint: Paint | None
    substitute: bool = False  # a fallback pigment, e.g. cadmium red for vermilion


@dataclass
class FilledTemplate:
    template: Template
    medium: str
    roles: list[Filled] = field(default_factory=list)

    def paints(self) -> list[Paint]:
        return [f.paint for f in self.roles if f.paint is not None]


def _pigments(paint: Paint) -> frozenset[str]:
    return frozenset(p.upper() for p in paint.pigments)


def _score(r: Role, paint: Paint) -> tuple[float, bool]:
    """(score, is substitute); 0 means the paint doesn't fit the role."""
    pig = _pigments(paint)
    name = paint.name.lower()
    score = 0.0
    if pig and pig <= r.pigments:
        score += 3
    elif pig & r.pigments:
        score += 1
    if any(w in name for w in r.words):
        score += 3
    substitute = False
    if score < 3 and pig and pig <= r.fallback:
        score, substitute = 2, True
    if score < 2:
        return 0.0, False
    score += 1 if any(w in name for w in r.prefer) else 0
    return score + (0.5 if paint.lab is not None else 0) + (0.25 if paint.favorite else 0), substitute


def fill(t: Template, library: PaintLibrary, medium: str) -> FilledTemplate:
    """Fill each role with the best-fitting paint you own in `medium` that
    has color data and is ticked Use; no paint is used twice."""
    candidates = [p for p in library.in_medium(medium) if p.enabled and library.color_of(p) is not None]
    used: set[str] = set()
    result = FilledTemplate(t, medium)
    for r in t.roles:
        scored = [(_score(r, p), p) for p in candidates if p.id not in used]
        scored = [(s, sub, p) for (s, sub), p in scored if s > 0]
        if not scored:
            result.roles.append(Filled(r, None))
            continue
        s, sub, best = max(scored, key=lambda x: x[0])
        used.add(best.id)
        result.roles.append(Filled(r, best, sub))
    return result
