"""Decides how each layer is displayed in each compare mode. Pure logic,
kept apart from Qt so the rules are easy to test and read.
"""

from __future__ import annotations

from dataclasses import dataclass

from .models import Project, CompareMode, BlendMode, LayerKind


@dataclass(frozen=True)
class DisplayState:
    visible: bool
    opacity: float
    blend: BlendMode
    clip: str | None = None  # None, "left" or "right" of the split line


HIDDEN = DisplayState(False, 1.0, BlendMode.NORMAL)
SOLO = DisplayState(True, 1.0, BlendMode.NORMAL)


def display_states(project: Project, blink_phase_on: bool) -> dict[str, DisplayState]:
    normal = {l.id: DisplayState(l.visible, l.opacity, l.blend_mode) for l in project.layers}
    a, b = project.compare_layer_a, project.compare_layer_b
    has_a, has_b = a in normal, b in normal
    mode = project.compare_mode

    if mode == CompareMode.BLINK and has_a and has_b:
        shown = a if blink_phase_on else b
        return {lid: (SOLO if lid == shown else HIDDEN) for lid in normal}

    if mode == CompareMode.BLINK_A and has_a:
        states = dict(normal)
        layer_a = normal[a]
        states[a] = DisplayState(blink_phase_on, layer_a.opacity, layer_a.blend)
        return states

    if mode == CompareMode.SPLIT and has_a and has_b and a != b:
        states = {lid: HIDDEN for lid in normal}
        states[a] = DisplayState(True, 1.0, BlendMode.NORMAL, "left")
        states[b] = DisplayState(True, 1.0, BlendMode.NORMAL, "right")
        return states

    return normal


def default_compare_layers(project: Project) -> tuple[str | None, str | None]:
    """A = the top reference, B = the newest canvas photo (the top one, since a
    new canvas photo goes above the older ones). Falls back to the top layers."""
    references = [l.id for l in project.layers if l.kind == LayerKind.REFERENCE]
    canvases = [l.id for l in project.layers if l.kind == LayerKind.CANVAS]
    stack = [l.id for l in reversed(project.layers)]
    a = references[-1] if references else (stack[0] if stack else None)
    b = canvases[-1] if canvases else next((lid for lid in stack if lid != a), a)
    return a, b


def uses_split_line(project: Project) -> bool:
    ids = {l.id for l in project.layers}
    return (
        project.compare_mode == CompareMode.SPLIT
        and project.compare_layer_a in ids
        and project.compare_layer_b in ids
        and project.compare_layer_a != project.compare_layer_b
    )
