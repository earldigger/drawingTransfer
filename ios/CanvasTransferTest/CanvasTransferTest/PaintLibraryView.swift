import SwiftUI

/// Placeholder while the Paint library is built.
struct PaintLibraryView: View {
    var onClose: () -> Void
    var body: some View { Button("Close", action: onClose) }
}
