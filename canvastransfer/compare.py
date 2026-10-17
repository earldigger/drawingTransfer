"""Decides how each layer is displayed in each compare mode. Pure logic,
kept apart from Qt so the rules are easy to test and read.
"""

from __future__ import annotations

from dataclasses import dataclass

from .models import Project, CompareMode, BlendMode


@dataclass(frozen=True)
class DisplayState:
    visible: bool
    opacity: float
    multiply: bool
    clip: str | None = None  # None, "left" or "right" of the split line


HIDDEN = DisplayState(False, 1.0, False)
SOLO = DisplayState(True, 1.0, False)


def display_states(project: Project, blink_phase_on: bool) -> dict[str, DisplayState]:
    normal = {
        l.id: DisplayState(l.visible, l.opacity, l.blend_mode == BlendMode.MULTIPLY)
        for l in project.layers
    }
    a, b = project.compare_layer_a, project.compare_layer_b
    has_a, has_b = a in normal, b in normal
    mode = project.compare_mode

    if mode == CompareMode.BLINK and has_a and has_b:
        shown = a if blink_phase_on else b
        return {lid: (SOLO if lid == shown else HIDDEN) for lid in normal}

    if mode == CompareMode.BLINK_A and has_a:
        states = dict(normal)
        layer_a = normal[a]
        states[a] = DisplayState(blink_phase_on, layer_a.opacity, layer_a.multiply)
        return states

    if mode == CompareMode.SPLIT and has_a and has_b and a != b:
        states = {lid: HIDDEN for lid in normal}
        states[a] = DisplayState(True, 1.0, False, "left")
        states[b] = DisplayState(True, 1.0, False, "right")
        return states

    return normal


def uses_split_line(project: Project) -> bool:
    ids = {l.id for l in project.layers}
    return (
        project.compare_mode == CompareMode.SPLIT
        and project.compare_layer_a in ids
        and project.compare_layer_b in ids
        and project.compare_layer_a != project.compare_layer_b
    )
