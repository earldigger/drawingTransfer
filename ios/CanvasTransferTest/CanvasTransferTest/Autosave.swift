import OSLog
import SwiftUI
import UIKit

private let saveLog = Logger(subsystem: "CanvasTransferTest", category: "autosave")

/// Everything about the session except the image pixels: what is written to
/// session.json. Equatable, so the workspace can tell when something changed.
struct SessionSnapshot: Codable, Equatable {
    struct LayerState: Codable, Equatable {
        var id: UUID
        var name: String
        var opacity: Double
        var blend: Blend
        var isVisible: Bool
        var center: CGPoint
        var width: CGFloat
        var rotation: Double  // radians
        var crop: CGRect
        var adjustments: Adjustments?  // optional, so sessions saved before Look still open
    }

    var version = 1
    var canvasSize: CGSize
    var layers: [LayerState]  // bottom to top
    var selectedID: UUID?
    var grid: GridSettings?  // optional, so sessions saved before the grid still open
}

extension TransferSession {
    var snapshot: SessionSnapshot {
        SessionSnapshot(
            canvasSize: canvasSize,
            layers: layers.map {
                .init(id: $0.id, name: $0.name, opacity: $0.opacity, blend: $0.blend, isVisible: $0.isVisible,
                      center: $0.center, width: $0.width, rotation: $0.rotation.radians, crop: $0.crop,
                      adjustments: $0.adjustments)
            },
            selectedID: selectedID,
            grid: grid)
    }

    /// Makes the session match `snapshot`. Layers that are already here are
    /// updated in place; others are made from `images` (a layer without one
    /// is skipped).
    func apply(_ snapshot: SessionSnapshot, images: (UUID) -> UIImage?) {
        canvasSize = snapshot.canvasSize
        if let saved = snapshot.grid { grid = saved }
        let existing = Dictionary(uniqueKeysWithValues: layers.map { ($0.id, $0) })
        layers = snapshot.layers.compactMap { state in
            guard let layer = existing[state.id]
                ?? images(state.id).map({ Layer(id: state.id, name: state.name, image: $0, canvasAspect: canvasAspect) })
            else { return nil }
            layer.name = state.name
            layer.opacity = state.opacity
            layer.blend = state.blend
            layer.isVisible = state.isVisible
            layer.center = state.center
            layer.width = state.width
            layer.rotation = .radians(state.rotation)
            layer.crop = state.crop
            layer.adjustments = state.adjustments ?? Adjustments()
            return layer
        }
        selectedID = snapshot.selectedID.flatMap { id in layers.contains { $0.id == id } ? id : nil }
            ?? layers.last?.id
    }
}

/// The current session, kept on the iPad in Application Support/Session:
/// session.json, and one PNG per layer, named by its id. A layer's image
/// never changes, so each PNG is written once.
enum SessionStore {
    static let folder = URL.applicationSupportDirectory.appending(path: "Session", directoryHint: .isDirectory)
    private static var file: URL { folder.appending(path: "session.json") }
    private static func imageURL(_ id: UUID) -> URL { folder.appending(path: "\(id.uuidString).png") }
    private static let queue = DispatchQueue(label: "autosave")  // one save at a time, in order

    /// The saved session, or a new one. A layer whose image is missing is skipped.
    static func load() -> TransferSession {
        let session = TransferSession()
        guard let data = try? Data(contentsOf: file) else { return session }
        do {
            let saved = try JSONDecoder().decode(SessionSnapshot.self, from: data)
            session.apply(saved) { id in
                let image = UIImage(contentsOfFile: imageURL(id).path)
                if image == nil { saveLog.error("No image for layer \(id), skipped it") }
                return image
            }
            saveLog.notice("Opened the saved session: \(session.layers.count) layers")
        } catch {
            saveLog.error("Couldn't read session.json, starting empty: \(error)")
        }
        return session
    }

    /// Writes new layer images, then session.json, and removes the images of
    /// deleted layers. Runs off the main thread; a PNG can take a moment.
    static func save(_ snapshot: SessionSnapshot, images: [UUID: UIImage]) {
        queue.async {
            do {
                let files = FileManager.default
                try files.createDirectory(at: folder, withIntermediateDirectories: true)
                for (id, image) in images where !files.fileExists(atPath: imageURL(id).path) {
                    guard let png = image.pngData() else { continue }
                    try png.write(to: imageURL(id), options: .atomic)
                }
                // Images first: session.json never names a layer whose image isn't there yet.
                try JSONEncoder().encode(snapshot).write(to: file, options: .atomic)
                let keep = Set(snapshot.layers.map { imageURL($0.id).lastPathComponent })
                for name in try files.contentsOfDirectory(atPath: folder.path) where name.hasSuffix(".png") && !keep.contains(name) {
                    try? files.removeItem(at: folder.appending(path: name))
                }
            } catch {
                saveLog.error("Autosave failed: \(error)")
            }
        }
    }
}

/// Saves the session half a second after it stops changing (a gesture
/// changes it every frame), and at once when the app leaves the screen.
struct Autosave: ViewModifier {
    let session: TransferSession

    @Environment(\.scenePhase) private var scenePhase
    @State private var pending: Task<Void, Never>? = nil

    func body(content: Content) -> some View {
        content
            .onChange(of: session.snapshot) {
                pending?.cancel()
                pending = Task {
                    try? await Task.sleep(for: .milliseconds(500))
                    guard !Task.isCancelled else { return }
                    saveNow()
                }
            }
            .onChange(of: scenePhase) { _, phase in
                if phase != .active { saveNow() }
            }
    }

    private func saveNow() {
        pending?.cancel()
        pending = nil
        SessionStore.save(session.snapshot,
                          images: Dictionary(uniqueKeysWithValues: session.layers.map { ($0.id, $0.image) }))
    }
}

extension View {
    func autosaves(_ session: TransferSession) -> some View { modifier(Autosave(session: session)) }
}
