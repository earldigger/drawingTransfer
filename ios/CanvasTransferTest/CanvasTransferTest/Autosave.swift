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
        var quad: [CGPoint]?  // the placement; nil in sessions from before, which have the four below
        var center: CGPoint?
        var width: CGFloat?
        var rotation: Double?  // radians
        var crop: CGRect
        var adjustments: Adjustments?  // optional, so sessions saved before Look still open
        var flipH: Bool?  // before the quad, with center, width and rotation
        var flipV: Bool?
        var imageID: UUID?  // the image's file; nil = named by the layer's id, as before Edit corners
        var sourceID: UUID?  // the original photo's file, if kept
        var corners: Corners?  // in the original photo's pixels
        var flattenedFrom: [UUID]?  // a flattened layer's sources; nil for any other
    }

    var version = 1
    var canvasSize: CGSize
    var layers: [LayerState]  // bottom to top
    var selectedID: UUID?
    var grid: GridSettings?  // optional, so sessions saved before the grid still open
    var swatches: [Swatch]?  // optional, so sessions saved before Color still open
}

extension TransferSession {
    var snapshot: SessionSnapshot {
        SessionSnapshot(
            canvasSize: canvasSize,
            layers: layers.map {
                .init(id: $0.id, name: $0.name, opacity: $0.opacity, blend: $0.blend, isVisible: $0.isVisible,
                      quad: $0.quad, crop: $0.crop, adjustments: $0.adjustments,
                      imageID: $0.imageID, sourceID: $0.sourceID, corners: $0.corners,
                      flattenedFrom: $0.flattenedFrom)
            },
            selectedID: selectedID,
            grid: grid,
            swatches: swatches)
    }

    /// Makes the session match `snapshot`. Layers that are already here are
    /// updated in place; others are made from `images` (by image id; a layer
    /// without one is skipped). `sources` gives original photos by their id.
    func apply(_ snapshot: SessionSnapshot, images: (UUID) -> UIImage?, sources: (UUID) -> UIImage?) {
        canvasSize = snapshot.canvasSize
        if let saved = snapshot.grid { grid = saved }
        swatches = snapshot.swatches ?? []
        let existing = Dictionary(uniqueKeysWithValues: layers.map { ($0.id, $0) })
        layers = snapshot.layers.compactMap { state in
            let imageID = state.imageID ?? state.id
            let layer: Layer
            if let here = existing[state.id] {
                layer = here
                if layer.imageID != imageID, let image = images(imageID) { layer.replaceImage(image, id: imageID) }
            } else if let image = images(imageID) {
                layer = Layer(id: state.id, name: state.name, image: image, imageID: imageID, canvasAspect: canvasAspect)
            } else {
                return nil
            }
            if layer.sourceID != state.sourceID {
                layer.sourceID = state.sourceID
                layer.source = state.sourceID.flatMap(sources)
            }
            layer.corners = state.corners
            layer.flattenedFrom = state.flattenedFrom
            layer.name = state.name
            layer.opacity = state.opacity
            layer.blend = state.blend
            layer.isVisible = state.isVisible
            if let quad = state.quad, quad.count == 4 {
                layer.quad = quad
            } else {  // a session from before the quad
                layer.quad = Layer.rectangle(center: state.center ?? CGPoint(x: 0.5, y: 0.5), width: state.width ?? 1,
                                             rotation: state.rotation ?? 0, flipH: state.flipH ?? false,
                                             flipV: state.flipV ?? false, imageAspect: layer.aspect,
                                             canvasAspect: snapshot.canvasSize.width / max(snapshot.canvasSize.height, 1e-9))
            }
            layer.crop = state.crop
            layer.adjustments = state.adjustments ?? Adjustments()
            return layer
        }
        selectedID = snapshot.selectedID.flatMap { id in layers.contains { $0.id == id } ? id : nil }
            ?? layers.last?.id
    }
}

/// The current session, kept on the iPad in Application Support/Session:
/// session.json; each layer's image as a PNG named by its image id; each
/// original photo as a JPEG named by its source id. Neither ever changes
/// under its name (Edit corners makes a new image id), so each file is
/// written once.
enum SessionStore {
    static let folder = URL.applicationSupportDirectory.appending(path: "Session", directoryHint: .isDirectory)
    private static var file: URL { folder.appending(path: "session.json") }
    private static func imageURL(_ id: UUID) -> URL { folder.appending(path: "\(id.uuidString).png") }
    private static func sourceURL(_ id: UUID) -> URL { folder.appending(path: "\(id.uuidString)-source.jpg") }
    private static let queue = DispatchQueue(label: "autosave")  // one save at a time, in order

    /// The saved session, or a new one. A layer whose image is missing is skipped.
    static func load() -> TransferSession {
        let session = TransferSession()
        guard let data = try? Data(contentsOf: file) else { return session }
        do {
            let saved = try JSONDecoder().decode(SessionSnapshot.self, from: data)
            session.apply(saved, images: { id in
                let image = UIImage(contentsOfFile: imageURL(id).path)
                if image == nil { saveLog.error("No image \(id), skipped its layer") }
                return image
            }, sources: { UIImage(contentsOfFile: sourceURL($0).path) })
            saveLog.notice("Opened the saved session: \(session.layers.count) layers")
        } catch {
            saveLog.error("Couldn't read session.json, starting empty: \(error)")
        }
        return session
    }

    /// Writes new images and photos, then session.json, and removes files no
    /// layer uses any more. Runs off the main thread; a PNG can take a moment.
    static func save(_ snapshot: SessionSnapshot, images: [UUID: UIImage], sources: [UUID: UIImage]) {
        queue.async {
            do {
                let files = FileManager.default
                try files.createDirectory(at: folder, withIntermediateDirectories: true)
                for (id, image) in images where !files.fileExists(atPath: imageURL(id).path) {
                    guard let png = image.pngData() else { continue }
                    try png.write(to: imageURL(id), options: .atomic)
                }
                for (id, photo) in sources where !files.fileExists(atPath: sourceURL(id).path) {
                    guard let jpeg = photo.jpegData(compressionQuality: 0.95) else { continue }
                    try jpeg.write(to: sourceURL(id), options: .atomic)
                }
                // Files first: session.json never names one that isn't there yet.
                try JSONEncoder().encode(snapshot).write(to: file, options: .atomic)
                let keep = Set(snapshot.layers.flatMap { state in
                    [imageURL(state.imageID ?? state.id).lastPathComponent]
                        + (state.sourceID.map { [sourceURL($0).lastPathComponent] } ?? [])
                })
                for name in try files.contentsOfDirectory(atPath: folder.path)
                where (name.hasSuffix(".png") || name.hasSuffix("-source.jpg")) && !keep.contains(name) {
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
        let layers = session.layers
        SessionStore.save(session.snapshot,
                          images: Dictionary(layers.map { ($0.imageID, $0.image) }, uniquingKeysWith: { a, _ in a }),
                          sources: Dictionary(layers.compactMap { l in l.sourceID.flatMap { id in l.source.map { (id, $0) } } },
                                              uniquingKeysWith: { a, _ in a }))
    }
}

extension View {
    func autosaves(_ session: TransferSession) -> some View { modifier(Autosave(session: session)) }
}
