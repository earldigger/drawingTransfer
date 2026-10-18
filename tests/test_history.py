from canvastransfer.history import History, Snapshot


def snap(n):
    return Snapshot(project={"n": n}, images={})


def test_undo_redo_round_trip():
    h = History()
    h.record(snap(0))  # state goes 0 -> 1
    h.record(snap(1))  # 1 -> 2
    assert h.undo(snap(2)) == snap(1)
    assert h.undo(snap(1)) == snap(0)
    assert h.undo(snap(0)) is None
    assert h.redo(snap(0)) == snap(1)
    assert h.redo(snap(1)) == snap(2)
    assert not h.can_redo()


def test_new_change_clears_redo():
    h = History()
    h.record(snap(0))
    h.undo(snap(1))
    h.record(snap(0))
    assert not h.can_redo()


def test_same_key_in_quick_succession_is_one_step():
    h = History()
    assert h.record(snap(0), key="opacity", now=10.0)
    assert not h.record(snap(1), key="opacity", now=10.5)
    assert not h.record(snap(2), key="opacity", now=11.5)
    assert h.undo(snap(3)) == snap(0)
    assert not h.can_undo()


def test_same_key_after_pause_is_new_step():
    h = History()
    h.record(snap(0), key="opacity", now=10.0)
    assert h.record(snap(1), key="opacity", now=13.0)


def test_undo_breaks_coalescing():
    h = History()
    h.record(snap(0), key="k", now=1.0)
    h.undo(snap(1))
    assert h.record(snap(0), key="k", now=1.1)


def test_limit_drops_oldest():
    h = History(limit=3)
    for i in range(5):
        h.record(snap(i))
    states = []
    current = snap(5)
    while (prev := h.undo(current)) is not None:
        states.append(prev.project["n"])
        current = prev
    assert states == [4, 3, 2]


def test_commit_session_collapses_to_one_step():
    h = History()
    h.record(snap(0))  # unrelated earlier step
    h.begin_session()
    h.record(snap(1))
    h.record(snap(2))
    h.record(snap(3))
    h.commit_session()
    assert h.undo(snap(4)) == snap(1)  # whole session in one go
    assert h.undo(snap(1)) == snap(0)


def test_cancel_session_returns_start_state_and_drops_steps():
    h = History()
    h.record(snap(0))
    h.begin_session()
    h.record(snap(1))
    h.record(snap(2))
    assert h.cancel_session() == snap(1)
    assert h.undo(snap(1)) == snap(0)


def test_cancel_untouched_session_restores_nothing():
    h = History()
    h.record(snap(0))
    h.begin_session()
    assert h.cancel_session() is None
    assert h.can_undo()


def test_undo_inside_session_stops_at_session_start():
    h = History()
    h.record(snap(0))
    h.begin_session()
    h.record(snap(1))
    assert h.undo(snap(2)) == snap(1)
    assert not h.can_undo()  # earlier history is out of reach until Done/Cancel
    assert h.redo(snap(1)) == snap(2)


def test_pre_session_redo_is_not_reachable_inside_session():
    h = History()
    h.record(snap(0))
    h.undo(snap(1))
    h.begin_session()
    assert not h.can_redo()
    h.commit_session()
    assert h.can_redo()


def test_cancel_after_undoing_inside_session():
    h = History()
    h.begin_session()
    h.record(snap(1))
    h.record(snap(2))
    h.undo(snap(3))
    assert h.cancel_session() == snap(1)
    assert not h.can_redo() and not h.can_undo()
