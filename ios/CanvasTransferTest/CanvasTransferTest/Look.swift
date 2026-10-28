import CoreImage
import SwiftUI
import UIKit

/// A layer's adjustments, as in the prototype (`Adjustments` in
/// canvastransfer/models.py), applied in this order: invert, levels,
/// hue / saturation (or colorize), lightness. Values use the prototype's
/// ranges: levels in 0...255, hue in degrees, the rest in -100...100.
struct Adjustments: Codable, Equatable {
    var invert = false
    var black: Double = 0  // levels dark point
    var gamma: Double = 1  // levels midtones; > 1 lightens, < 1 darkens
    var white: Double = 255  // levels light point
    var hue: Double = 0  // -180...180, around the color wheel
    var saturation: Double = 0  // -100 (gray) ... 100
    var lightness: Double = 0  // -100 (black) ... 100 (white)
    var colorize = false  // tint the whole layer one color instead
    var colorizeHue: Double = 0  // 0...360
    var colorizeSaturation: Double = 25  // 0...100, tint strength

    var isIdentity: Bool { self == Adjustments() }
    var levelsIsIdentity: Bool { !invert && black == 0 && white == 255 && gamma == 1 }
}

/// Applies `Adjustments` with Core Image, on the GPU.
enum Look {
    private static let context = CIContext()

    /// The adjusted image, or nil to show the original.
    static func adjusted(_ image: UIImage, _ a: Adjustments) -> UIImage? {
        guard !a.isIdentity, var ci = CIImage(image: image) else { return nil }
        if !a.levelsIsIdentity {
            ci = curve(ci) { x in
                let v = a.invert ? 1 - x : x
                let t = min(max((v * 255 - a.black) / max(a.white - a.black, 1), 0), 1)
                return pow(t, 1 / max(a.gamma, 0.001))
            }
        }
        if a.colorize {
            // Keep each pixel's brightness, give it one tint.
            let tint = UIColor(hue: CGFloat(a.colorizeHue.truncatingRemainder(dividingBy: 360) / 360),
                               saturation: CGFloat(min(max(a.colorizeSaturation, 0), 100) / 100),
                               brightness: 1, alpha: 1)
            ci = ci.applyingFilter("CIColorControls", parameters: [kCIInputSaturationKey: 0])
                .applyingFilter("CIColorMonochrome", parameters: [kCIInputColorKey: CIColor(color: tint),
                                                                   kCIInputIntensityKey: 1])
        } else {
            if a.hue != 0 {
                ci = ci.applyingFilter("CIHueAdjust", parameters: [kCIInputAngleKey: a.hue * .pi / 180])
            }
            if a.saturation != 0 {
                ci = ci.applyingFilter("CIColorControls",
                                       parameters: [kCIInputSaturationKey: 1 + min(max(a.saturation, -100), 100) / 100])
            }
        }
        if a.lightness != 0 {
            // Photoshop's Lightness: toward white (+) or black (-).
            let v = min(max(a.lightness, -100), 100) / 100
            ci = curve(ci) { x in v >= 0 ? x + (1 - x) * v : x * (1 + v) }
        }
        guard let cg = context.createCGImage(ci, from: ci.extent) else { return nil }
        return UIImage(cgImage: cg, scale: image.scale, orientation: .up)
    }

    /// The same 0...1 curve on red, green and blue, in sRGB like the
    /// prototype's 8-bit lookup tables.
    private static func curve(_ image: CIImage, _ f: (Double) -> Double) -> CIImage {
        var table: [Float] = []
        for i in 0..<256 {
            let y = Float(f(Double(i) / 255))
            table += [y, y, y]
        }
        let data = table.withUnsafeBufferPointer { Data(buffer: $0) }
        return image.applyingFilter("CIColorCurves", parameters: [
            "inputCurvesData": data,
            "inputCurvesDomain": CIVector(x: 0, y: 1),
            "inputColorSpace": CGColorSpace(name: CGColorSpace.sRGB) as Any,  // the key constant is iOS 26+
        ])
    }
}

/// The Adjust popover: invert, levels, hue / saturation / lightness,
/// colorize, reset. Live on the canvas; each slider drag is one undo step.
struct LookPanel: View {
    @Bindable var layer: Layer
    @Environment(History.self) private var history

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 14) {
                Toggle("Invert", isOn: $layer.adjustments.invert)

                section("Levels")
                slider("Black point", $layer.adjustments.black, 0...254, "%.0f")
                slider("Midtones", $layer.adjustments.gamma, 0.2...5, "%.2f")
                slider("White point", $layer.adjustments.white, 1...255, "%.0f")

                section("Hue / Saturation")
                Toggle("Colorize", isOn: $layer.adjustments.colorize)
                if layer.adjustments.colorize {
                    slider("Hue", $layer.adjustments.colorizeHue, 0...360, "%.0f°")
                    slider("Strength", $layer.adjustments.colorizeSaturation, 0...100, "%.0f")
                } else {
                    slider("Hue", $layer.adjustments.hue, -180...180, "%+.0f°")
                    slider("Saturation", $layer.adjustments.saturation, -100...100, "%+.0f")
                }
                slider("Lightness", $layer.adjustments.lightness, -100...100, "%+.0f")

                Button("Reset adjustments", role: .destructive) { layer.adjustments = Adjustments() }
                    .disabled(layer.adjustments.isIdentity)
                    .padding(.top, 6)
            }
            .padding(20)
        }
        .frame(width: 340)
        .frame(maxHeight: 560)
        .onChange(of: layer.adjustments.black) { keepLevelsInOrder(movedBlack: true) }
        .onChange(of: layer.adjustments.white) { keepLevelsInOrder(movedBlack: false) }
    }

    private func section(_ title: String) -> some View {
        Text(title).font(.headline).padding(.top, 6)
    }

    private func slider(_ title: String, _ value: Binding<Double>, _ range: ClosedRange<Double>,
                        _ format: String) -> some View {
        VStack(alignment: .leading, spacing: 2) {
            HStack {
                Text(title)
                Spacer()
                Text(String(format: format, value.wrappedValue)).monospacedDigit().foregroundStyle(.secondary)
            }
            Slider(value: value, in: range) { editing in
                if editing { history.hold("look") } else { history.release("look") }
            }
        }
    }

    /// The black point stays below the white point.
    private func keepLevelsInOrder(movedBlack: Bool) {
        let a = layer.adjustments
        guard a.black >= a.white else { return }
        if movedBlack { layer.adjustments.black = a.white - 1 } else { layer.adjustments.white = a.black + 1 }
    }
}
