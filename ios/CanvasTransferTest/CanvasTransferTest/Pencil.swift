import Observation
import PencilKit
import SwiftUI
import UIKit

/// The Pencil tool. While it's on, strokes are drawn with PencilKit on a
/// clear sheet over the canvas; when it's put away (Done, another tool, the
/// Gallery, or the app going to the background) the strokes are drawn into a
/// drawing layer: the selected one if it is one, or a new "Drawing n" on top.
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

/// The sheet the Pencil draws on. With "Only Draw with Apple Pencil" on (the
/// iPad's setting), fingers pass through it to the canvas, so pinch, pan and
/// the two-finger undo still work while drawing.
struct PencilCanvas: UIViewRepresentable {
    let controller: PencilController
    let tool: PKInkingTool
    let colorHex: String
    let size: CGSize

    func makeUIView(context: Context) -> PencilSheetView {
        let view = PencilSheetView()
        view.backgroundColor = .clear
        view.isOpaque = false
        view.isScrollEnabled = false
        view.overrideUserInterfaceStyle = .light  // ink keeps its color; PencilKit lightens dark ink in dark mode
        view.drawingPolicy = UIPencilInteraction.prefersPencilOnlyDrawing ? .pencilOnly : .anyInput
        view.delegate = controller
        controller.canvasView = view
        return view
    }

    func updateUIView(_ view: PencilSheetView, context: Context) {
        view.tool = tool
        controller.colorHex = colorHex
        controller.canvasSize = size
    }
}

final class PencilSheetView: PKCanvasView {
    /// Finger touches go through to the canvas when only the Pencil draws.
    override func hitTest(_ point: CGPoint, with event: UIEvent?) -> UIView? {
        if drawingPolicy == .pencilOnly, let touches = event?.allTouches, !touches.isEmpty,
           !touches.contains(where: { $0.type == .pencil }) {
            return nil
        }
        return super.hitTest(point, with: event)
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
    /// selected drawing layer, or a new one on top. One undo step.
    @MainActor
    static func commit(_ drawing: PKDrawing, sheet: CGSize, to session: TransferSession) {
        guard sheet.width > 0, sheet.height > 0 else { return }
        let aspect = session.canvasAspect
        let pixels = aspect >= 1 ? CGSize(width: longEdge, height: (longEdge / aspect).rounded())
                                 : CGSize(width: (longEdge * aspect).rounded(), height: longEdge)
        let target = session.selected.flatMap { isDrawingLayer($0) ? $0 : nil }
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

/// The Pencil's bar: size, opacity, color, and the 8 colors drawn with last.
struct PencilBar: View {
    @Binding var size: Double
    @Binding var opacity: Double
    @Binding var colorHex: String
    let recents: [String]
    var onDone: () -> Void

    var body: some View {
        HStack(spacing: BarSpacing.group) {
            BarTitle("Pencil", symbol: "pencil")
            HStack(spacing: BarSpacing.icon) {
                Text("Size")
                Slider(value: $size, in: 1...40).frame(width: 120)
                Text("\(Int(size.rounded())) pt").monospacedDigit().frame(width: 44, alignment: .leading)
            }
            HStack(spacing: BarSpacing.icon) {
                Text("Opacity")
                Slider(value: $opacity, in: 0.05...1).frame(width: 120)
                Text("\(Int((opacity * 100).rounded()))%").monospacedDigit().frame(width: 44, alignment: .leading)
            }
            HStack(spacing: 6) {
                ColorPicker("Color", selection: Binding(get: { Color(hex: colorHex) }, set: { colorHex = $0.hex }),
                            supportsOpacity: false)
                    .labelsHidden()
                    .padding(.trailing, 6)
                ForEach(recents, id: \.self) { hex in
                    Button { colorHex = hex } label: {
                        Circle()
                            .fill(Color(hex: hex))
                            .frame(width: 26, height: 26)
                            .overlay(Circle().stroke(Color.white.opacity(0.5), lineWidth: 1))
                            .padding(3)
                            .overlay(Circle().stroke(Theme.accent, lineWidth: hex == colorHex ? 3 : 0))
                    }
                    .accessibilityLabel("Color \(hex)")
                }
            }
            Spacer(minLength: 0)
            DoneButton(action: onDone)
        }
        .bottomBar()
    }
}
