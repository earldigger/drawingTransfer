"""Data model for a Canvas Transfer project.

Mirrors the "Basic Project Data" section of the project spec:
Project (name, canvas width/height, units), Layer (name, image, visibility,
opacity, blend mode, position, scale, rotation, skew, perspective corners),
and Grid (rows, columns, opacity, line thickness).

All transforms are stored as parameters, never baked into pixels, so the
model stays nondestructive -- the same requirement as the spec's Image
Transform and Core Image sections.
"""

from __future__ import annotations

from dataclasses import dataclass, field, asdict
from enum import Enum
import itertools
import uuid


class Units(str, Enum):
    INCHES = "in"
    CENTIMETERS = "cm"


class BlendMode(str, Enum):
    NORMAL = "normal"
    MULTIPLY = "multiply"


class CompareMode(str, Enum):
    OVERLAY = "overlay"
    BLINK = "blink"
    SPLIT = "split"


_id_counter = itertools.count(1)


def new_id(prefix: str) -> str:
    return f"{prefix}-{next(_id_counter)}-{uuid.uuid4().hex[:8]}"


@dataclass
class Transform:
    """Nondestructive 2D transform applied to a layer's (already
    perspective-corrected) image before it is composited onto the canvas.
    """

    offset_x: float = 0.0
    offset_y: float = 0.0
    scale_x: float = 1.0
    scale_y: float = 1.0
    rotation_deg: float = 0.0
    skew_x_deg: float = 0.0
    skew_y_deg: float = 0.0

    def to_dict(self) -> dict:
        return asdict(self)

    @staticmethod
    def from_dict(data: dict) -> "Transform":
        return Transform(**data)


@dataclass
class PerspectiveCorners:
    """Four corner points (image pixel space, origin top-left) used to
    correct the perspective of a photographed drawing or canvas.
    Order: top-left, top-right, bottom-right, bottom-left.
    """

    top_left: tuple[float, float]
    top_right: tuple[float, float]
    bottom_right: tuple[float, float]
    bottom_left: tuple[float, float]

    def as_list(self) -> list[tuple[float, float]]:
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


@dataclass
class Layer:
    id: str
    name: str
    image_filename: str  # relative to the project package's images/ dir
    visible: bool = True
    opacity: float = 1.0  # 0..1
    blend_mode: BlendMode = BlendMode.NORMAL
    transform: Transform = field(default_factory=Transform)
    perspective_corners: PerspectiveCorners | None = None

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "image_filename": self.image_filename,
            "visible": self.visible,
            "opacity": self.opacity,
            "blend_mode": self.blend_mode.value,
            "transform": self.transform.to_dict(),
            "perspective_corners": (
                self.perspective_corners.to_dict() if self.perspective_corners else None
            ),
        }

    @staticmethod
    def from_dict(data: dict) -> "Layer":
        return Layer(
            id=data["id"],
            name=data["name"],
            image_filename=data["image_filename"],
            visible=data.get("visible", True),
            opacity=data.get("opacity", 1.0),
            blend_mode=BlendMode(data.get("blend_mode", "normal")),
            transform=Transform.from_dict(data.get("transform", {})) if data.get("transform") else Transform(),
            perspective_corners=(
                PerspectiveCorners.from_dict(data["perspective_corners"])
                if data.get("perspective_corners")
                else None
            ),
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
class Project:
    name: str
    canvas_width: float
    canvas_height: float
    units: Units = Units.INCHES
    layers: list[Layer] = field(default_factory=list)
    grid: GridSettings = field(default_factory=GridSettings)
    active_layer_id: str | None = None
    compare_mode: CompareMode = CompareMode.OVERLAY
    compare_layer_a: str | None = None
    compare_layer_b: str | None = None
    split_position: float = 0.5  # 0..1, used by CompareMode.SPLIT

    def add_layer(self, layer: Layer) -> None:
        self.layers.append(layer)
        self.active_layer_id = layer.id

    def remove_layer(self, layer_id: str) -> None:
        self.layers = [l for l in self.layers if l.id != layer_id]
        if self.active_layer_id == layer_id:
            self.active_layer_id = self.layers[-1].id if self.layers else None

    def get_layer(self, layer_id: str) -> Layer | None:
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
        )
