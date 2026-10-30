import SwiftUI
import UIKit

/// The two workspaces (decision B), switched in the top bar; same layers in both.
enum Workspace: String, CaseIterable, Identifiable {
    case transfer = "Transfer"
    case color = "Color"

    var id: String { rawValue }
}

/// A color picked from a layer (Swatch in canvastransfer/models.py). (u, v)
/// is where, in fractions of the layer's image, so its marker follows the
/// layer through every transform. Numbered by its place in the list.
struct Swatch: Codable, Equatable, Identifiable {
    var id = UUID()
    var layerID: UUID
    var u: Double
    var v: Double
    var red: Int
    var green: Int
    var blue: Int

    var color: Color { Color(red: Double(red) / 255, green: Double(green) / 255, blue: Double(blue) / 255) }
    var hex: String { String(format: "#%02X%02X%02X", red, green, blue) }

    /// CIELAB lightness, 0 (black) to 100 (white): the swatch's value.
    var value: Double {
        func linear(_ c: Int) -> Double {
            let s = Double(c) / 255
            return s <= 0.04045 ? s / 12.92 : pow((s + 0.055) / 1.055, 2.4)
        }
        let y = 0.2126 * linear(red) + 0.7152 * linear(green) + 0.0722 * linear(blue)
        return y > 216.0 / 24389 ? 116 * cbrt(y) - 16 : y * 24389 / 27
    }

    /// Black or white, whichever reads on top of the swatch.
    var labelColor: Color { value > 60 ? .black : .white }
}

/// How big an area Pick averages, in the layer image's pixels (the prototype's sample size).
enum SampleSize: Int, CaseIterable, Identifiable {
    case point = 0
    case small = 2  // 5 × 5
    case large = 5  // 11 × 11

    var id: Int { rawValue }
    var label: String {
        switch self {
        case .point: "1 px"
        case .small: "5 × 5"
        case .large: "11 × 11"
        }
    }
}

/// A layer image's pixels, read once, for picking.
final class PixelBuffer {
    let width: Int
    let height: Int
    private var bytes: [UInt8]  // RGBA, sRGB, 8 bits each

    init?(_ image: UIImage) {
        guard let cg = image.cgImage else { return nil }
        width = cg.width
        height = cg.height
        bytes = [UInt8](repeating: 0, count: width * height * 4)
        let drawn: Bool = bytes.withUnsafeMutableBytes { raw in
            guard let context = CGContext(data: raw.baseAddress, width: width, height: height, bitsPerComponent: 8,
                                          bytesPerRow: width * 4, space: CGColorSpace(name: CGColorSpace.sRGB)!,
                                          bitmapInfo: CGImageAlphaInfo.premultipliedLast.rawValue)
            else { return false }
            context.draw(cg, in: CGRect(x: 0, y: 0, width: width, height: height))
            return true
        }
        guard drawn else { return nil }
    }

    /// The mean color of the square `radius` pixels around (u, v) in fractions
    /// of the image, weighted by alpha (sample_average in color_study.py).
    func average(u: Double, v: Double, radius: Int) -> (Int, Int, Int)? {
        let cx = Int((u * Double(width)).rounded(.down)), cy = Int((v * Double(height)).rounded(.down))
        guard (0..<width).contains(cx), (0..<height).contains(cy) else { return nil }
        var r = 0.0, g = 0.0, b = 0.0, total = 0.0
        for y in max(0, cy - radius)...min(height - 1, cy + radius) {
            for x in max(0, cx - radius)...min(width - 1, cx + radius) {
                let i = (y * width + x) * 4
                let a = Double(bytes[i + 3]) / 255
                guard a > 0 else { continue }
                // Premultiplied: un-premultiply, then weight by alpha.
                r += Double(bytes[i]); g += Double(bytes[i + 1]); b += Double(bytes[i + 2])
                total += a
            }
        }
        guard total > 0 else { return nil }
        return (Int((r / total).rounded()), Int((g / total).rounded()), Int((b / total).rounded()))
    }

    /// A `size` × `size` block of pixels around (u, v), for the loupe.
    func patch(u: Double, v: Double, size: Int) -> UIImage? {
        let cx = Int(u * Double(width)), cy = Int(v * Double(height)), half = size / 2
        var out = [UInt8](repeating: 0, count: size * size * 4)
        for y in 0..<size {
            for x in 0..<size {
                let sx = cx - half + x, sy = cy - half + y
                guard (0..<width).contains(sx), (0..<height).contains(sy) else { continue }
                let i = (sy * width + sx) * 4, o = (y * size + x) * 4
                out[o] = bytes[i]; out[o + 1] = bytes[i + 1]; out[o + 2] = bytes[i + 2]; out[o + 3] = bytes[i + 3]
            }
        }
        let data = Data(out) as CFData
        guard let provider = CGDataProvider(data: data),
              let cg = CGImage(width: size, height: size, bitsPerComponent: 8, bitsPerPixel: 32, bytesPerRow: size * 4,
                               space: CGColorSpace(name: CGColorSpace.sRGB)!,
                               bitmapInfo: CGBitmapInfo(rawValue: CGImageAlphaInfo.premultipliedLast.rawValue),
                               provider: provider, decode: nil, shouldInterpolate: false, intent: .defaultIntent)
        else { return nil }
        return UIImage(cgImage: cg)
    }
}

/// What's under the finger while picking: where, and the color there.
struct PickProbe: Equatable {
    var location: CGPoint  // in canvas points
    var layerID: UUID
    var u: Double
    var v: Double
    var rgb: (Int, Int, Int)?  // nil = outside the layer, or cropped off
    var patch: UIImage?

    static func == (a: PickProbe, b: PickProbe) -> Bool {
        a.location == b.location && a.u == b.u && a.v == b.v && a.rgb?.0 == b.rgb?.0 && a.rgb?.1 == b.rgb?.1 && a.rgb?.2 == b.rgb?.2
    }

    /// Reads the selected layer at a canvas point, through its corners: what
    /// the canvas shows of it, so `shown` when it's simplified.
    static func at(_ location: CGPoint, layer: Layer, canvas: CGSize, sample: SampleSize,
                   shown: PixelBuffer? = nil) -> PickProbe? {
        guard let f = QuadGeometry.imageFraction(of: location, in: layer.quadPoints(in: canvas)) else { return nil }
        let inside = (0...1).contains(f.x) && (0...1).contains(f.y)
            && layer.crop.contains(CGPoint(x: min(f.x, 0.999_999), y: min(f.y, 0.999_999)))
        let pixels = shown ?? layer.pixels()
        return PickProbe(location: location, layerID: layer.id, u: f.x, v: f.y,
                         rgb: inside ? pixels?.average(u: f.x, v: f.y, radius: sample.rawValue) : nil,
                         patch: pixels?.patch(u: f.x, v: f.y, size: 15))
    }
}

/// The loupe above the finger: the layer's pixels, magnified, with the
/// sample area marked, and the averaged color with its hex code.
struct Loupe: View {
    let probe: PickProbe
    let sample: SampleSize

    var body: some View {
        let size: CGFloat = 120, cell = size / 15
        VStack(spacing: 0) {
            ZStack {
                if let patch = probe.patch {
                    Image(uiImage: patch).interpolation(.none).resizable().frame(width: size, height: size)
                } else {
                    Color.black.frame(width: size, height: size)
                }
                Rectangle()
                    .stroke(Color.white, lineWidth: 1.5)
                    .shadow(color: .black, radius: 1)
                    .frame(width: cell * CGFloat(sample.rawValue * 2 + 1), height: cell * CGFloat(sample.rawValue * 2 + 1))
            }
            .frame(width: size, height: size)
            HStack {
                if let rgb = probe.rgb {
                    Text(String(format: "#%02X%02X%02X", rgb.0, rgb.1, rgb.2)).font(.caption.monospaced())
                } else {
                    Text("Not on this layer").font(.caption)
                }
            }
            .frame(width: size, height: 30)
            .background(probe.rgb.map { Color(red: Double($0.0) / 255, green: Double($0.1) / 255, blue: Double($0.2) / 255) } ?? Color(white: 0.15))
            .foregroundStyle(probe.rgb.map { Swatch(layerID: probe.layerID, u: 0, v: 0, red: $0.0, green: $0.1, blue: $0.2).labelColor } ?? .white)
        }
        .clipShape(RoundedRectangle(cornerRadius: 12))
        .overlay(RoundedRectangle(cornerRadius: 12).stroke(Color.white, lineWidth: 3))
        .shadow(radius: 8)
        .allowsHitTesting(false)
    }
}

/// Numbered markers where each swatch was picked, following its layer.
struct SwatchMarkers: View {
    let swatches: [Swatch]
    let layers: [Layer]
    let canvas: CGSize
    let selectedID: UUID?
    let scale: CGFloat  // the view's zoom, so markers keep their size on screen

    var body: some View {
        ZStack(alignment: .topLeading) {
            ForEach(Array(swatches.enumerated()), id: \.element.id) { index, swatch in
                if let layer = layers.first(where: { $0.id == swatch.layerID }), layer.isVisible {
                    let point = QuadGeometry.point(swatch.u, swatch.v, in: layer.quadPoints(in: canvas))
                    let selected = swatch.id == selectedID
                    Text("\(index + 1)")
                        .font(.caption2.weight(.bold))
                        .foregroundStyle(swatch.labelColor)
                        .frame(width: 22, height: 22)
                        .background(Circle().fill(swatch.color))
                        .overlay(Circle().stroke(selected ? Color.blue : Color.white, lineWidth: selected ? 3 : 2))
                        .shadow(color: .black.opacity(0.5), radius: 2)
                        .scaleEffect(1 / scale)
                        .position(point)
                }
            }
        }
        .frame(width: canvas.width, height: canvas.height, alignment: .topLeading)
        .allowsHitTesting(false)
    }
}

/// The Color workspace's bottom bar: the swatches as numbered chips, the
/// selected one's details, and the sample size.
struct SwatchBar: View {
    @Bindable var session: TransferSession
    @Binding var selectedID: UUID?
    @Binding var sample: SampleSize

    var body: some View {
        HStack(spacing: 14) {
            Label("Swatches", systemImage: "eyedropper").font(.subheadline.weight(.semibold))
            if session.swatches.isEmpty {
                Text("Touch the canvas to pick a color from the selected layer.")
                    .font(.caption).foregroundStyle(.secondary)
            } else {
                ScrollView(.horizontal, showsIndicators: false) {
                    HStack(spacing: 8) {
                        ForEach(Array(session.swatches.enumerated()), id: \.element.id) { index, swatch in
                            chip(swatch, number: index + 1)
                        }
                    }
                    .padding(.vertical, 4)
                }
                .frame(maxWidth: 420)
                if let swatch = session.swatches.first(where: { $0.id == selectedID }) {
                    VStack(alignment: .leading, spacing: 1) {
                        Text(swatch.hex).font(.caption.monospaced().weight(.semibold))
                        Text("RGB \(swatch.red) \(swatch.green) \(swatch.blue) · value \(Int(swatch.value.rounded()))")
                            .font(.caption2).foregroundStyle(.secondary)
                    }
                    .frame(width: 150, alignment: .leading)
                }
            }
            Picker("Sample", selection: $sample) {
                ForEach(SampleSize.allCases) { Text($0.label).tag($0) }
            }
            .pickerStyle(.segmented)
            .frame(width: 200)
        }
        .padding(.horizontal, 16)
        .frame(height: 56)
        .background(RoundedRectangle(cornerRadius: 14).fill(Color(white: 0.13).opacity(0.95)))
    }

    private func chip(_ swatch: Swatch, number: Int) -> some View {
        let selected = swatch.id == selectedID
        return Button {
            selectedID = selected ? nil : swatch.id
        } label: {
            Text("\(number)")
                .font(.caption.weight(.bold))
                .foregroundStyle(swatch.labelColor)
                .frame(width: 36, height: 36)
                .background(RoundedRectangle(cornerRadius: 8).fill(swatch.color))
                .overlay(RoundedRectangle(cornerRadius: 8).stroke(selected ? Color.blue : Color.white.opacity(0.4),
                                                                  lineWidth: selected ? 3 : 1))
        }
        .contextMenu {
            Button("Delete swatch \(number)", systemImage: "trash", role: .destructive) {
                session.swatches.removeAll { $0.id == swatch.id }
                if selectedID == swatch.id { selectedID = nil }
            }
        }
        .accessibilityLabel("Swatch \(number), \(swatch.hex)")
    }
}
