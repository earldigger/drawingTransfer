import SwiftUI

@main
struct CanvasTransferTestApp: App {
    @State private var session = TransferSession()

    var body: some Scene {
        WindowGroup {
            WorkspaceView()
                .environment(session)
        }
    }
}
