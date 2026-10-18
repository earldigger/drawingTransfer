"""Undo/redo as whole-project snapshots, plus transform sessions that can
be committed as a single step (Done) or rolled back (Cancel).

A snapshot is the project's JSON-able dict plus a shallow copy of the
layer-image dict. Images never change after import, so sharing the arrays
between snapshots costs nothing; it only keeps deleted layers' images
alive so undoing a delete can bring them back.
"""

from __future__ import annotations

import time
from dataclasses import dataclass

import numpy as np

COALESCE_SECONDS = 1.5
MAX_STEPS = 100


@dataclass(frozen=True)
class Snapshot:
    project: dict
    images: dict[str, np.ndarray]


class History:
    def __init__(self, limit: int = MAX_STEPS):
        self._limit = limit
        self._undo: list[Snapshot] = []
        self._redo: list[Snapshot] = []
        self._last_key = None
        self._last_time = 0.0
        self._session: tuple[int, int] | None = None  # (undo depth, redo depth) at start

    def clear(self) -> None:
        self.__init__(self._limit)

    # -- recording ------------------------------------------------------

    def record(self, before: Snapshot, key=None, now: float | None = None) -> bool:
        """Call before changing the project, with its current state.
        Repeated changes with the same `key` in quick succession (one
        slider drag) merge into a single step. Returns True if a step was
        added."""
        now = time.monotonic() if now is None else now
        if key is not None and key == self._last_key and now - self._last_time < COALESCE_SECONDS:
            self._last_time = now
            return False
        self._undo.append(before)
        self._redo.clear()
        if self._session is not None:
            self._session = (self._session[0], 0)
        if len(self._undo) > self._limit and (self._session is None or self._session[0] > 0):
            del self._undo[0]
            if self._session is not None:
                self._session = (self._session[0] - 1, self._session[1])
        self._last_key, self._last_time = key, now
        return True

    # -- undo / redo ----------------------------------------------------

    def can_undo(self) -> bool:
        floor = self._session[0] if self._session else 0
        return len(self._undo) > floor

    def can_redo(self) -> bool:
        floor = self._session[1] if self._session else 0
        return len(self._redo) > floor

    def undo(self, current: Snapshot) -> Snapshot | None:
        if not self.can_undo():
            return None
        self._redo.append(current)
        self._last_key = None
        return self._undo.pop()

    def redo(self, current: Snapshot) -> Snapshot | None:
        if not self.can_redo():
            return None
        self._undo.append(current)
        self._last_key = None
        return self._redo.pop()

    # -- transform sessions ---------------------------------------------------

    @property
    def in_session(self) -> bool:
        return self._session is not None

    def begin_session(self) -> None:
        self._session = (len(self._undo), len(self._redo))
        self._last_key = None

    def commit_session(self) -> None:
        """Done: everything since begin_session becomes one undo step."""
        if self._session is None:
            return
        mark, redo_floor = self._session
        del self._undo[mark + 1:]
        del self._redo[redo_floor:]
        self._session = None
        self._last_key = None

    def cancel_session(self) -> Snapshot | None:
        """Cancel: drop the session's steps and return the state to restore
        (None if nothing changed during the session)."""
        if self._session is None:
            return None
        mark, redo_floor = self._session
        start = self._undo[mark] if len(self._undo) > mark else None
        del self._undo[mark:]
        del self._redo[redo_floor:]
        self._session = None
        self._last_key = None
        return start
