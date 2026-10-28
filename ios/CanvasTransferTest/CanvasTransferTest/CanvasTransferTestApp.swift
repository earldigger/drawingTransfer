import SwiftUI

@main
struct CanvasTransferTestApp: App {
    @State private var session = SessionStore.load()  // what was there last time

    var body: some Scene {
        WindowGroup {
            WorkspaceView()
                .environment(session)
                .autosaves(session)
        }
    }
}
