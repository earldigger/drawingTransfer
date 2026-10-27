"""Data model for a Canvas Transfer project.

Mirrors the "Basic Project Data" section of the project spec. A layer's
placement on the canvas is stored as four corner points (its "quad") rather
than baked into pixels, so every move/scale/rotate/skew/distort/flip stays
editable and nondestructive.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field, fields
from enum import Enum
import itertools
import uuid

Point = tuple[float, float]


class Units(str, Enum):
    INCHES = "in"
    CENTIMETERS = "cm"


class BlendMode(str, Enum):
    NORMAL = "normal"
    MULTIPLY = "multiply"
    SCREEN = "screen"
    LINEAR_LIGHT = "linear_light"


class LayerKind(str, Enum):
    CANVAS = "canvas"  # a photo of the real canvas, corrected to fill it exactly
    REFERENCE = "reference"  # the photo or drawing being transferred


# How a new layer of each kind starts: (opacity, blend mode, auto levels).
# A reference at Multiply 60 % lets white paper disappear over the canvas
# photo; a canvas photo shows the painting as it is, values untouched.
DEFAULT_LOOK = {
    LayerKind.CANVAS: (1.0, BlendMode.NORMAL, False),
    LayerKind.REFERENCE: (0.6, BlendMode.MULTIPLY, True),
}


class CompareMode(str, Enum):
    OVERLAY = "overlay"
    BLINK = "blink"  # alternate between layer A alone and layer B alone
    BLINK_A = "blink_a"  # normal stack, only layer A toggles on/off
    SPLIT = "split"


_id_counter = itertools.count(1)


def new_id(prefix: str) -> str:
    return f"{prefix}-{next(_id_counter)}-{uuid.uuid4().hex[:8]}"


@dataclass
class PerspectiveCorners:
    """Four corner points (raw image pixel space, origin top-left) marking
    the photographed drawing or canvas. Order: TL, TR, BR, BL.
    """

    top_left: Point
    top_right: Point
    bottom_right: Point
    bottom_left: Point

    def as_list(self) -> list[Point]:
        return [self.top_left, self.top_right, self.bottom_right, self.bottom_left]

    def to_dict(self) -> dict:
        return {
            "top_left": list(self.top_left),
            "top_right": list(self.top_right),
            "bottom_right": list(self.bottom_right),
            "bottom_left": list(self.bottom_left),
        }

    @staticmethod
    def from_dict(data: dict) -> "PerspectiveCorners":
        return PerspectiveCorners(
            top_left=tuple(data["top_left"]),
            top_right=tuple(data["top_right"]),
            bottom_right=tuple(data["bottom_right"]),
            bottom_left=tuple(data["bottom_left"]),
        )

    @staticmethod
    def default_for_image(width: int, height: int) -> "PerspectiveCorners":
        return PerspectiveCorners(
            top_left=(0.0, 0.0),
            top_right=(float(width), 0.0),
            bottom_right=(float(width), float(height)),
            bottom_left=(0.0, float(height)),
        )


@dataclass(frozen=True)
class Adjustments:
    """Per-layer value and color adjustments in Photoshop's units, applied
    in this order to what the layer shows: invert, levels, hue/saturation
    (or colorize), lightness.
    """

    invert: bool = False
    black: int = 0  # levels dark point, 0..255
    gamma: float = 1.0  # levels midtones; >1 lightens, <1 darkens
    white: int = 255  # levels light point, 0..255
    hue: int = 0  # -180..180 degrees around the color wheel
    saturation: int = 0  # -100 (gray) .. 100
    lightness: int = 0  # -100 (black) .. 100 (white)
    colorize: bool = False  # tint the whole layer one color instead
    colorize_hue: int = 0  # 0..360, the tint color when colorizing
    colorize_saturation: int = 25  # 0..100, tint strength when colorizing

    def to_dict(self) -> dict:
        return asdict(self)

    @staticmethod
    def from_dict(data: dict | None) -> "Adjustments":
        names = {f.name for f in fields(Adjustments)}
        return Adjustments(**{k: v for k, v in (data or {}).items() if k in names})


@dataclass
class Layer:
    id: str
    name: str
    image_filename: str  # relative to the project package's images/ dir
    visible: bool = True
    opacity: float = 1.0  # 0..1
    blend_mode: BlendMode = BlendMode.NORMAL
    # Where the layer's image corners land on the canvas, as fractions of
    # canvas width/height (TL, TR, BR, BL). None = fit to canvas on next use.
    quad: list[Point] | None = None
    perspective_corners: PerspectiveCorners | None = None
    # True for canvas photos: the corrected image fills the canvas exactly.
    perspective_fill_canvas: bool = False
    adjustments: Adjustments = field(default_factory=Adjustments)
    kind: LayerKind = LayerKind.REFERENCE
    # The part of the image that shows: (left, top, right, bottom) as fractions
    # of the displayed image, so it moves with the layer. None = all of it.
    crop: tuple[float, float, float, float] | None = None

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "image_filename": self.image_filename,
            "visible": self.visible,
            "opacity": self.opacity,
            "blend_mode": self.blend_mode.value,
            "quad": [list(p) for p in self.quad] if self.quad else None,
            "perspective_corners": (
                self.perspective_corners.to_dict() if self.perspective_corners else None
            ),
            "perspective_fill_canvas": self.perspective_fill_canvas,
            "adjustments": self.adjustments.to_dict(),
            "kind": self.kind.value,
            "crop": list(self.crop) if self.crop else None,
        }

    @staticmethod
    def from_dict(data: dict) -> "Layer":
        quad = data.get("quad")
        return Layer(
            id=data["id"],
            name=data["name"],
            image_filename=data["image_filename"],
            visible=data.get("visible", True),
            opacity=data.get("opacity", 1.0),
            blend_mode=BlendMode(data.get("blend_mode", "normal")),
            quad=[tuple(p) for p in quad] if quad else None,
            perspective_corners=(
                PerspectiveCorners.from_dict(data["perspective_corners"])
                if data.get("perspective_corners")
                else None
            ),
            perspective_fill_canvas=data.get("perspective_fill_canvas", False),
            adjustments=Adjustments.from_dict(data.get("adjustments")),
            # projects saved before layers had a kind: a canvas photo is the one that fills the canvas
            kind=LayerKind(data["kind"]) if "kind" in data else
            (LayerKind.CANVAS if data.get("perspective_fill_canvas") else LayerKind.REFERENCE),
            crop=tuple(data["crop"]) if data.get("crop") else None,
        )


@dataclass
class GridSettings:
    enabled: bool = False
    rows: int = 4
    columns: int = 4
    opacity: float = 0.6
    thickness_px: float = 2.0
    color: tuple[int, int, int] = (255, 40, 40)

    def to_dict(self) -> dict:
        return {
            "enabled": self.enabled,
            "rows": self.rows,
            "columns": self.columns,
            "opacity": self.opacity,
            "thickness_px": self.thickness_px,
            "color": list(self.color),
        }

    @staticmethod
    def from_dict(data: dict) -> "GridSettings":
        return GridSettings(
            enabled=data.get("enabled", False),
            rows=data.get("rows", 4),
            columns=data.get("columns", 4),
            opacity=data.get("opacity", 0.6),
            thickness_px=data.get("thickness_px", 2.0),
            color=tuple(data.get("color", (255, 40, 40))),
        )


@dataclass
class Swatch:
    """A color sampled from a layer. (u, v) is where it was picked, as
    fractions of the layer image's width/height, so its marker follows the
    layer through every transform."""

    id: str
    layer_id: str
    u: float
    v: float
    rgb: tuple[int, int, int]
    highlight: bool = False

    def to_dict(self) -> dict:
        return {"id": self.id, "layer_id": self.layer_id, "u": self.u, "v": self.v,
                "rgb": list(self.rgb), "highlight": self.highlight}

    @staticmethod
    def from_dict(data: dict) -> "Swatch":
        return Swatch(id=data["id"], layer_id=data["layer_id"], u=data["u"], v=data["v"],
                      rgb=tuple(data["rgb"]), highlight=data.get("highlight", False))


DEFAULT_HIGHLIGHT_TOLERANCE = 12.0  # CIELAB distance; ~2.3 is a just-noticeable difference


@dataclass
class SimplifySettings:
    """Viewing the selected layer reduced to a few flat colors or values."""

    enabled: bool = False
    values: bool = False  # gray values instead of colors
    fixed_scale: bool = False  # values: equal steps from black to white, instead of fitted to the image
    colors: int = 8  # how many colors in color mode
    value_steps: int = 5  # how many values in value mode
    smoothing: int = 2  # 0..6

    def key(self) -> tuple[int, int, bool]:
        return (self.value_steps if self.values else self.colors, self.smoothing, self.values,
                self.values and self.fixed_scale)

    def to_dict(self) -> dict:
        return {"enabled": self.enabled, "values": self.values, "fixed_scale": self.fixed_scale, "colors": self.colors,
                "value_steps": self.value_steps, "smoothing": self.smoothing}

    @staticmethod
    def from_dict(data: dict) -> "SimplifySettings":
        known = {k: v for k, v in data.items() if k in SimplifySettings.__dataclass_fields__}
        return SimplifySettings(**known)


@dataclass
class Project:
    name: str
    canvas_width: float
    canvas_height: float
    units: Units = Units.INCHES
    layers: list[Layer] = field(default_factory=list)  # index 0 = bottom of stack
    grid: GridSettings = field(default_factory=GridSettings)
    active_layer_id: str | None = None
    compare_mode: CompareMode = CompareMode.OVERLAY
    compare_layer_a: str | None = None
    compare_layer_b: str | None = None
    split_position: float = 0.5  # 0..1, used by CompareMode.SPLIT
    swatches: list[Swatch] = field(default_factory=list)
    highlight_tolerance: float = DEFAULT_HIGHLIGHT_TOLERANCE
    simplify: SimplifySettings = field(default_factory=SimplifySettings)

    def add_layer(self, layer: Layer) -> None:
        """References go on top; a canvas photo goes just under the lowest
        reference, so references always stay over the canvas photos."""
        index = len(self.layers)
        if layer.kind == LayerKind.CANVAS:
            index = next((i for i, l in enumerate(self.layers) if l.kind == LayerKind.REFERENCE), index)
        self.layers.insert(index, layer)
        self.active_layer_id = layer.id

    def remove_layer(self, layer_id: str) -> None:
        self.layers = [l for l in self.layers if l.id != layer_id]
        self.swatches = [s for s in self.swatches if s.layer_id != layer_id]
        if self.active_layer_id == layer_id:
            self.active_layer_id = self.layers[-1].id if self.layers else None

    def get_swatch(self, swatch_id: str | None) -> Swatch | None:
        return next((s for s in self.swatches if s.id == swatch_id), None)

    def get_layer(self, layer_id: str | None) -> Layer | None:
        for l in self.layers:
            if l.id == layer_id:
                return l
        return None

    def move_layer(self, layer_id: str, new_index: int) -> None:
        idx = next((i for i, l in enumerate(self.layers) if l.id == layer_id), None)
        if idx is None:
            return
        layer = self.layers.pop(idx)
        new_index = max(0, min(new_index, len(self.layers)))
        self.layers.insert(new_index, layer)

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "canvas_width": self.canvas_width,
            "canvas_height": self.canvas_height,
            "units": self.units.value,
            "layers": [l.to_dict() for l in self.layers],
            "grid": self.grid.to_dict(),
            "active_layer_id": self.active_layer_id,
            "compare_mode": self.compare_mode.value,
            "compare_layer_a": self.compare_layer_a,
            "compare_layer_b": self.compare_layer_b,
            "split_position": self.split_position,
            "swatches": [s.to_dict() for s in self.swatches],
            "highlight_tolerance": self.highlight_tolerance,
            "simplify": self.simplify.to_dict(),
        }

    @staticmethod
    def from_dict(data: dict) -> "Project":
        return Project(
            name=data["name"],
            canvas_width=data["canvas_width"],
            canvas_height=data["canvas_height"],
            units=Units(data.get("units", "in")),
            layers=[Layer.from_dict(l) for l in data.get("layers", [])],
            grid=GridSettings.from_dict(data.get("grid", {})),
            active_layer_id=data.get("active_layer_id"),
            compare_mode=CompareMode(data.get("compare_mode", "overlay")),
            compare_layer_a=data.get("compare_layer_a"),
            compare_layer_b=data.get("compare_layer_b"),
            split_position=data.get("split_position", 0.5),
            swatches=[Swatch.from_dict(s) for s in data.get("swatches", [])],
            highlight_tolerance=data.get("highlight_tolerance", DEFAULT_HIGHLIGHT_TOLERANCE),
            simplify=SimplifySettings.from_dict(data.get("simplify", {})),
        )
