import SwiftUI

@main
struct CanvasTransferTestApp: App {
    @State private var session: TransferSession
    @State private var history: History

    init() {
        let session = SessionStore.load()  // what was there last time
        _session = State(initialValue: session)
        _history = State(initialValue: History(session))
    }

    var body: some Scene {
        WindowGroup {
            WorkspaceView()
                .environment(session)
                .environment(history)
                .autosaves(session)
                .recordsHistory(of: session, in: history)
        }
    }
}
