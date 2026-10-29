import Observation
import SwiftUI
import UIKit

/// Undo and redo for the session.
///
/// Each step is the session's snapshot plus its layers' images (references,
/// so a deleted layer can come back). A step is recorded once the session
/// settles after a change, so a gesture, a slider drag or a whole crop is
/// one step: views `hold` the history while one of those is under way, and
/// nothing is recorded until every hold is released. Selecting a layer and
/// changing the grid aren't steps.
@Observable
final class History {
    struct Step {
        var snapshot: SessionSnapshot
        var images: [UUID: UIImage]  // by image id, so undoing Edit corners brings the old image back
        var sources: [UUID: UIImage]  // original photos, by source id

        init(_ session: TransferSession) {
            snapshot = session.snapshot
            images = Dictionary(session.layers.map { ($0.imageID, $0.image) }, uniquingKeysWith: { a, _ in a })
            sources = Dictionary(session.layers.compactMap { l in l.sourceID.flatMap { id in l.source.map { (id, $0) } } },
                                 uniquingKeysWith: { a, _ in a })
        }
    }

    static let limit = 50  // steps kept; the oldest go first
    private static let settleDelay = Duration.milliseconds(400)

    private(set) var undoStack: [Step] = []
    private(set) var redoStack: [Step] = []
    @ObservationIgnored private let session: TransferSession
    @ObservationIgnored private var committed: Step  // the state the stacks lead to and from
    @ObservationIgnored private var holds: Set<String> = []
    @ObservationIgnored private var pending: Task<Void, Never>? = nil

    init(_ session: TransferSession) {
        self.session = session
        committed = Step(session)
    }

    var canUndo: Bool { !undoStack.isEmpty }
    var canRedo: Bool { !redoStack.isEmpty }

    /// Something that should be one step has started (a gesture, a slider drag, a crop).
    func hold(_ reason: String) {
        holds.insert(reason)
        pending?.cancel()
    }

    func release(_ reason: String) {
        holds.remove(reason)
        sessionChanged()
    }

    /// Called on every change; records a step once changes stop.
    func sessionChanged() {
        pending?.cancel()
        guard holds.isEmpty else { return }
        pending = Task { @MainActor in
            try? await Task.sleep(for: Self.settleDelay)
            guard !Task.isCancelled else { return }
            settle()
        }
    }

    func undo() {
        settle()  // a change that hasn't settled yet is the one to undo
        guard let previous = undoStack.popLast() else { return }
        redoStack.append(committed)
        restore(previous)
    }

    func redo() {
        settle()  // a new change since the undo drops the redo steps
        guard let next = redoStack.popLast() else { return }
        undoStack.append(committed)
        restore(next)
    }

    private func settle() {
        pending?.cancel()
        pending = nil
        guard holds.isEmpty else { return }
        let now = Step(session)
        if now.snapshot.edits != committed.snapshot.edits {
            undoStack.append(committed)
            if undoStack.count > Self.limit { undoStack.removeFirst() }
            redoStack.removeAll()
        }
        committed = now  // also keeps the latest selection
    }

    private func restore(_ step: Step) {
        committed = step
        var snapshot = step.snapshot
        snapshot.grid = session.grid  // the grid stays as it is
        session.apply(snapshot, images: { step.images[$0] }, sources: { step.sources[$0] })
    }
}

extension SessionSnapshot {
    /// What undo cares about: not the selection, and not the grid, which is
    /// a way of looking rather than an edit.
    var edits: SessionSnapshot {
        var copy = self
        copy.selectedID = nil
        copy.grid = nil
        return copy
    }
}

/// Tells the history about every change to the session.
struct RecordsHistory: ViewModifier {
    let session: TransferSession
    let history: History

    func body(content: Content) -> some View {
        content.onChange(of: session.snapshot) { history.sessionChanged() }
    }
}

extension View {
    func recordsHistory(of session: TransferSession, in history: History) -> some View {
        modifier(RecordsHistory(session: session, history: history))
    }
}
