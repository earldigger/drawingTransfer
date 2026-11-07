import Observation
import PencilKit
import SwiftUI
import UIKit

/// The Pencil tool. While it's on, strokes are drawn with PencilKit on a
/// clear sheet over the canvas; when another layer is chosen, a layer is
/// added, or the Pencil is put away (turned off, another tool, the Gallery,
/// the app going to the background) the strokes are drawn into a drawing
/// layer: the selected one if it is one, or a new "Drawing n" on top.
/// So a drawing layer is an ordinary image layer, saved like any other.
@Observable
final class PencilController: NSObject, PKCanvasViewDelegate {
    @ObservationIgnored weak var canvasView: PKCanvasView?
    @ObservationIgnored var canvasSize: CGSize = .zero  // the sheet's size in points, for drawing it into the layer
    @ObservationIgnored var colorHex = "#202020"  // the color being drawn with, for the recent colors

    private(set) var hasStrokes = false
    private(set) var canUndo = false
    private(set) var canRedo = false
    /// The last 8 colors drawn with, newest first, as #RRGGBB.
    private(set) var recents: [String] = UserDefaults.standard.stringArray(forKey: PencilController.recentsKey) ?? []

    private static let recentsKey = "pencilRecentColors"
    @ObservationIgnored private var strokeCount = 0

    func canvasViewDrawingDidChange(_ canvasView: PKCanvasView) {
        let count = canvasView.drawing.strokes.count
        if count > strokeCount { remember(colorHex) }  // a new stroke, not an undo
        strokeCount = count
        hasStrokes = count > 0
        canUndo = canvasView.undoManager?.canUndo ?? false
        canRedo = canvasView.undoManager?.canRedo ?? false
    }

    func undo() { canvasView?.undoManager?.undo() }
    func redo() { canvasView?.undoManager?.redo() }

    private func remember(_ hex: String) {
        recents = Array(([hex] + recents.filter { $0 != hex }).prefix(8))
        UserDefaults.standard.set(recents, forKey: Self.recentsKey)
    }

    /// The strokes so far, and a clear sheet (and no stroke undo) from here on.
    func take() -> PKDrawing? {
        guard let view = canvasView, !view.drawing.strokes.isEmpty else { return nil }
        let drawing = view.drawing
        view.drawing = PKDrawing()
        view.undoManager?.removeAllActions(withTarget: view)
        strokeCount = 0
        hasStrokes = false
        canUndo = false
        canRedo = false
        return drawing
    }
}

/// The sheet the Pencil draws on, with Apple Pencil or a finger. While it's
/// out, the canvas's own finger gestures (pinch, pan, two-finger undo) don't
/// reach the canvas.
struct PencilCanvas: UIViewRepresentable {
    let controller: PencilController
    let tool: PKInkingTool
    let colorHex: String
    let size: CGSize

    func makeUIView(context: Context) -> PKCanvasView {
        let view = PKCanvasView()
        view.backgroundColor = .clear
        view.isOpaque = false
        view.isScrollEnabled = false
        view.overrideUserInterfaceStyle = .light  // ink keeps its color; PencilKit lightens dark ink in dark mode
        view.drawingPolicy = .anyInput  // a finger draws too
        view.delegate = controller
        controller.canvasView = view
        return view
    }

    func updateUIView(_ view: PKCanvasView, context: Context) {
        view.tool = tool
        controller.colorHex = colorHex
        controller.canvasSize = size
    }
}

enum Pencil {
    static let longEdge: CGFloat = 2048  // a drawing layer's pixels on its long side

    /// A drawing layer: drawn with the Pencil and still filling the canvas as made.
    static func isDrawingLayer(_ layer: Layer) -> Bool {
        layer.name.hasPrefix("Drawing ") && layer.quad == Flatten.fullCanvas && layer.crop == Crop.full
            && layer.adjustments.isIdentity
    }

    /// Draws `drawing` (made on a sheet `sheet` points in size) into the
    /// drawing layer `layerID`, or a new one on top if that isn't one. One undo step.
    @MainActor
    static func commit(_ drawing: PKDrawing, sheet: CGSize, to session: TransferSession, layerID: UUID?) {
        guard sheet.width > 0, sheet.height > 0 else { return }
        let aspect = session.canvasAspect
        let pixels = aspect >= 1 ? CGSize(width: longEdge, height: (longEdge / aspect).rounded())
                                 : CGSize(width: (longEdge * aspect).rounded(), height: longEdge)
        let target = session.layers.first { $0.id == layerID && isDrawingLayer($0) }
        var strokes = UIImage()
        UITraitCollection(userInterfaceStyle: .light).performAsCurrent {  // ink as drawn, not dark-mode inverted
            strokes = drawing.image(from: CGRect(origin: .zero, size: sheet), scale: pixels.width / sheet.width)
        }
        let format = UIGraphicsImageRendererFormat()
        format.scale = 1
        format.opaque = false
        let rect = CGRect(origin: .zero, size: pixels)
        let image = UIGraphicsImageRenderer(size: pixels, format: format).image { _ in
            target?.image.draw(in: rect)
            strokes.draw(in: rect)
        }
        if let target {
            target.replaceImage(image)
        } else {
            let layer = Layer(name: "Drawing \(nextNumber(session))", image: image, canvasAspect: aspect)
            layer.opacity = 1
            layer.blend = .normal
            layer.quad = Flatten.fullCanvas
            session.add(layer)  // on top, and selected
        }
    }

    /// A new, empty (transparent) drawing layer on top, filling the canvas at
    /// Normal 100 %, selected; the Pencil draws into it. One undo step.
    @MainActor
    static func addBlankLayer(to session: TransferSession) {
        let aspect = session.canvasAspect
        let pixels = aspect >= 1 ? CGSize(width: longEdge, height: (longEdge / aspect).rounded())
                                 : CGSize(width: (longEdge * aspect).rounded(), height: longEdge)
        let format = UIGraphicsImageRendererFormat()
        format.scale = 1
        format.opaque = false
        let image = UIGraphicsImageRenderer(size: pixels, format: format).image { _ in }  // nothing drawn: clear
        let layer = Layer(name: "Drawing \(nextNumber(session))", image: image, canvasAspect: aspect)
        layer.opacity = 1
        layer.blend = .normal
        layer.quad = Flatten.fullCanvas
        session.add(layer)
    }

    /// One more than the highest "Drawing n" there is.
    static func nextNumber(_ session: TransferSession) -> Int {
        let numbers = session.layers.compactMap { layer -> Int? in
            guard layer.name.hasPrefix("Drawing ") else { return nil }
            return Int(layer.name.dropFirst("Drawing ".count))
        }
        return (numbers.max() ?? 0) + 1
    }
}

// MARK: - colors as #RRGGBB

extension Color {
    init(hex: String) {
        let digits = hex.replacingOccurrences(of: "#", with: "")
        let v = Int(digits, radix: 16) ?? 0x202020
        self.init(red: Double((v >> 16) & 0xFF) / 255, green: Double((v >> 8) & 0xFF) / 255, blue: Double(v & 0xFF) / 255)
    }

    /// #RRGGBB in sRGB, alpha dropped.
    var hex: String {
        var r: CGFloat = 0, g: CGFloat = 0, b: CGFloat = 0, a: CGFloat = 0
        UIColor(self).getRed(&r, green: &g, blue: &b, alpha: &a)
        func byte(_ c: CGFloat) -> Int { Int((min(max(c, 0), 1) * 255).rounded()) }
        return String(format: "#%02X%02X%02X", byte(r), byte(g), byte(b))
    }
}

// MARK: - the bar

/// The Pencil's panel at the left: size (in the drawing layer's pixels),
/// opacity, and the color, whose pop-up has the color picker and the 8
/// colors drawn with last. No Done: the Pencil draws until it's turned off.
struct PencilPanel: View {
    @Binding var size: Double
    @Binding var opacity: Double
    @Binding var colorHex: String
    let recents: [String]

    @State private var choosingColor = false

    var body: some View {
        VStack(spacing: 14) {
            Image(systemName: "pencil").font(.system(size: 20)).accessibilityLabel("Pencil")
            column("Size") {
                VerticalSlider(value: Binding(get: { size }, set: { size = $0.rounded() }), range: 1...100,
                               label: "\(Int(size.rounded()))", height: 170)
                    .accessibilityLabel("Size, pixels")
            }
            column("Opacity") {
                VerticalSlider(value: Binding(get: { (opacity * 100).rounded() }, set: { opacity = $0 / 100 }),
                               range: 5...100, label: "\(Int((opacity * 100).rounded()))", height: 170)
                    .accessibilityLabel("Opacity, percent")
            }
            Button { choosingColor = true } label: {
                Circle()
                    .fill(Color(hex: colorHex).opacity(opacity))
                    .frame(width: 36, height: 36)
                    .background(Checkerboard().clipShape(Circle()))
                    .overlay(Circle().stroke(Color.white, lineWidth: 2))
                    .frame(width: 44, height: 44)
            }
            .accessibilityLabel("Color")
            .popover(isPresented: $choosingColor, arrowEdge: .leading) { colorPopup }
        }
        .padding(.vertical, 14)
        .frame(width: 64)
        .themedBar()
    }

    private func column<Content: View>(_ title: String, @ViewBuilder content: () -> Content) -> some View {
        VStack(spacing: 6) {
            Text(title).font(.caption2).foregroundStyle(.secondary)
            content()
        }
    }

    /// The color picker, and the colors drawn with last.
    private var colorPopup: some View {
        VStack(alignment: .leading, spacing: 14) {
            ColorPicker("Color", selection: Binding(get: { Color(hex: colorHex) }, set: { colorHex = $0.hex }),
                        supportsOpacity: false)
            Text("Recent").font(.caption).foregroundStyle(.secondary)
            if recents.isEmpty {
                Text("Colors you draw with show here.").font(.caption).foregroundStyle(.secondary)
            }
            LazyVGrid(columns: Array(repeating: GridItem(.fixed(36), spacing: 8), count: 4), alignment: .leading, spacing: 8) {
                ForEach(recents, id: \.self) { hex in
                    Button { colorHex = hex } label: {
                        Circle()
                            .fill(Color(hex: hex))
                            .frame(width: 28, height: 28)
                            .overlay(Circle().stroke(Color.white.opacity(0.5), lineWidth: 1))
                            .padding(3)
                            .overlay(Circle().stroke(Theme.accent, lineWidth: hex == colorHex ? 3 : 0))
                    }
                    .accessibilityLabel("Color \(hex)")
                }
            }
        }
        .padding(18)
        .frame(width: 220)
        .themed()
    }
}

/// Light and dark gray squares, behind what may be see-through.
struct Checkerboard: View {
    var square: CGFloat = 6

    var body: some View {
        Canvas { context, size in
            context.fill(Path(CGRect(origin: .zero, size: size)), with: .color(Color(white: 0.85)))
            let columns = Int(ceil(size.width / square)), rows = Int(ceil(size.height / square))
            var dark = Path()
            for row in 0..<rows {
                for column in 0..<columns where (row + column) % 2 == 1 {
                    dark.addRect(CGRect(x: CGFloat(column) * square, y: CGFloat(row) * square, width: square, height: square))
                }
            }
            context.fill(dark, with: .color(Color(white: 0.65)))
        }
        .accessibilityHidden(true)
    }
}
