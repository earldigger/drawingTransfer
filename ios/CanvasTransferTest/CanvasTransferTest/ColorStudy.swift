import CoreImage
import simd
import SwiftUI
import UIKit

/// Simplify and Highlight (color_study.py in the prototype), on a layer's
/// shown image, on the GPU. Each comes down to a rule from a color to a
/// color (the nearest palette color; the highlight color, or gray), which is
/// worked out on the CPU from a small sample, written into a Core Image
/// color cube, and applied to every pixel at once.
enum ColorStudy {
    static let workingEdge: CGFloat = 1000  // the result's long edge: plenty to see masses and ranges
    static let sampleEdge: CGFloat = 128  // the sample's long edge: about 16,000 pixels (SIMPLIFY_SAMPLE is 20,000)
    static let cubeSize = 32  // entries per channel in the color cube

    /// One highlight color per swatch number, bright and far apart in hue
    /// (HIGHLIGHT_COLORS); they repeat after eight.
    static let highlightColors: [(Int, Int, Int)] = [
        (255, 236, 0), (0, 224, 255), (255, 60, 200), (90, 255, 70),
        (255, 140, 0), (70, 120, 255), (255, 40, 40), (185, 95, 255),
    ]

    static func highlightColor(_ index: Int) -> Color {
        let c = highlightColors[index % highlightColors.count]
        return Color(red: Double(c.0) / 255, green: Double(c.1) / 255, blue: Double(c.2) / 255)
    }

    private static let context = CIContext()
    private static let sRGB = CGColorSpace(name: CGColorSpace.sRGB)!

    // MARK: images

    /// The image scaled to fit `edge`, smoothed by `smoothing` passes of a
    /// median filter, which flattens texture and noise but keeps edges.
    private static func working(_ image: UIImage, edge: CGFloat, smoothing: Int) -> CIImage? {
        guard var ci = CIImage(image: image) else { return nil }
        let scale = min(1, edge / max(ci.extent.width, ci.extent.height, 1))
        if scale < 1 {
            ci = ci.applyingFilter("CILanczosScaleTransform", parameters: [kCIInputScaleKey: scale, kCIInputAspectRatioKey: 1])
        }
        let extent = ci.extent.integral
        ci = ci.cropped(to: extent)
        for _ in 0..<smoothing { ci = ci.applyingFilter("CIMedianFilter").cropped(to: extent) }
        return ci
    }

    /// The opaque pixels of a small copy, as RGB bytes.
    private static func samplePixels(_ ci: CIImage) -> [(UInt8, UInt8, UInt8)] {
        let scale = min(1, sampleEdge / max(ci.extent.width, ci.extent.height, 1))
        let small = ci.transformed(by: CGAffineTransform(scaleX: scale, y: scale))
        let extent = small.extent.integral
        let width = Int(extent.width), height = Int(extent.height)
        guard width > 0, height > 0 else { return [] }
        var rgba = [UInt8](repeating: 0, count: width * height * 4)
        context.render(small, toBitmap: &rgba, rowBytes: width * 4, bounds: extent, format: .RGBA8, colorSpace: sRGB)
        var out: [(UInt8, UInt8, UInt8)] = []
        out.reserveCapacity(width * height)
        for i in 0..<(width * height) where rgba[i * 4 + 3] > 200 {
            out.append((rgba[i * 4], rgba[i * 4 + 1], rgba[i * 4 + 2]))
        }
        return out
    }

    /// Applies `rule` (sRGB 0...1 in, sRGB 0...1 out) to every pixel, through a color cube.
    private static func apply(_ rule: (Float, Float, Float) -> (Float, Float, Float), to ci: CIImage) -> UIImage? {
        let n = cubeSize
        var cube = [Float](repeating: 1, count: n * n * n * 4)
        for b in 0..<n {
            for g in 0..<n {
                for r in 0..<n {
                    let out = rule(Float(r) / Float(n - 1), Float(g) / Float(n - 1), Float(b) / Float(n - 1))
                    let i = ((b * n + g) * n + r) * 4  // red changes fastest
                    cube[i] = out.0; cube[i + 1] = out.1; cube[i + 2] = out.2
                }
            }
        }
        let data = cube.withUnsafeBufferPointer { Data(buffer: $0) }
        let result = ci.applyingFilter("CIColorCubeWithColorSpace", parameters: [
            "inputCubeDimension": n, "inputCubeData": data, "inputColorSpace": sRGB,
        ])
        guard let cg = context.createCGImage(result, from: ci.extent) else { return nil }
        return UIImage(cgImage: cg)
    }

    // MARK: CIELAB (D65), as the prototype's

    static func lab(_ r: Float, _ g: Float, _ b: Float) -> SIMD3<Float> {
        func linear(_ s: Float) -> Float { s <= 0.04045 ? s / 12.92 : powf((s + 0.055) / 1.055, 2.4) }
        let R = linear(r), G = linear(g), B = linear(b)
        let x = (0.4124 * R + 0.3576 * G + 0.1805 * B) / 0.95047
        let y = 0.2126 * R + 0.7152 * G + 0.0722 * B
        let z = (0.0193 * R + 0.1192 * G + 0.9505 * B) / 1.08883
        let e: Float = 216 / 24389, k: Float = 24389 / 27
        let fx = x > e ? cbrtf(x) : (k * x + 16) / 116
        let fy = y > e ? cbrtf(y) : (k * y + 16) / 116
        let fz = z > e ? cbrtf(z) : (k * z + 16) / 116
        return SIMD3(116 * fy - 16, 500 * (fx - fy), 200 * (fy - fz))
    }

    static func lab(_ r: UInt8, _ g: UInt8, _ b: UInt8) -> SIMD3<Float> {
        lab(Float(r) / 255, Float(g) / 255, Float(b) / 255)
    }

    static func rgb(_ lab: SIMD3<Float>) -> (Int, Int, Int) {
        let fy = (lab.x + 16) / 116, fx = fy + lab.y / 500, fz = fy - lab.z / 200
        func inv(_ t: Float) -> Float { t * t * t > 216 / 24389 ? t * t * t : (116 * t - 16) * 27 / 24389 }
        let x = inv(fx) * 0.95047, y = inv(fy), z = inv(fz) * 1.08883
        let lin = [3.2406 * x - 1.5372 * y - 0.4986 * z, -0.9689 * x + 1.8758 * y + 0.0415 * z,
                   0.0557 * x - 0.2040 * y + 1.0570 * z]
        let s = lin.map { v -> Int in
            let c = min(max(v, 0), 1)
            let g = c <= 0.0031308 ? 12.92 * c : 1.055 * powf(c, 1 / 2.4) - 0.055
            return Int((g * 255).rounded())
        }
        return (s[0], s[1], s[2])
    }

    // MARK: simplify

    enum SimplifyMode: String, CaseIterable, Identifiable {
        case colors = "Colors"  // the image's own dominant colors
        case values = "Values"  // its own dominant lightnesses, as grays
        case valueScale = "Value scale"  // equal steps from black to white, the same for every image

        var id: String { rawValue }
    }

    struct Simplified {
        var image: UIImage
        var colors: [(Int, Int, Int)]  // darkest first
        var shares: [Double]  // of the image, each color's (measured on the sample)
    }

    /// The image reduced to `count` colors or values (simplify() in the prototype).
    static func simplify(_ source: UIImage, count: Int, smoothing: Int, mode: SimplifyMode) -> Simplified? {
        guard let ci = working(source, edge: workingEdge, smoothing: smoothing) else { return nil }
        let sample = samplePixels(ci).map { lab($0.0, $0.1, $0.2) }
        guard !sample.isEmpty else { return nil }
        let lightnessOnly = mode != .colors
        func feature(_ v: SIMD3<Float>) -> SIMD3<Float> { lightnessOnly ? SIMD3(v.x, 0, 0) : v }

        var centers: [SIMD3<Float>]
        var band: ((SIMD3<Float>) -> Int)
        if mode == .valueScale {
            // Bands of lightness, each shown at its middle: 5 steps are L* 10, 30, 50, 70, 90.
            centers = (0..<count).map { SIMD3((Float($0) + 0.5) * 100 / Float(count), 0, 0) }
            band = { v in min(max(Int(v.x * Float(count) / 100), 0), count - 1) }
        } else {
            let features = sample.map(feature)
            centers = kMeans(features, k: min(count, features.count)).sorted { $0.x < $1.x }  // darkest first
            let found = centers
            band = { v in nearest(feature(v), found) }
            // An image with fewer colors than asked: drop centers nothing went to.
            var used = [Int](repeating: 0, count: centers.count)
            for v in sample { used[band(v)] += 1 }
            centers = centers.indices.filter { used[$0] > 0 }.map { centers[$0] }
            let kept = centers
            band = { v in nearest(feature(v), kept) }
        }
        var counts = [Int](repeating: 0, count: centers.count)
        for v in sample { counts[band(v)] += 1 }
        let colors = centers.map { lightnessOnly ? rgb(SIMD3($0.x, 0, 0)) : rgb($0) }
        let palette = colors.map { (Float($0.0) / 255, Float($0.1) / 255, Float($0.2) / 255) }
        var output = ci
        if let image = apply({ r, g, b in palette[band(lab(r, g, b))] }, to: ci), let flat = CIImage(image: image) {
            output = flat
            // Remove specks: a median of a few flat colors keeps them flat.
            if smoothing > 0 {
                let passes = mode == .valueScale ? (smoothing < 4 ? 2 : 3) : (smoothing < 4 ? 1 : 2)
                for _ in 0..<passes { output = output.applyingFilter("CIMedianFilter").cropped(to: flat.extent) }
            }
        }
        guard let cg = context.createCGImage(output, from: ci.extent) else { return nil }
        let total = Double(max(1, counts.reduce(0, +)))
        return Simplified(image: UIImage(cgImage: cg), colors: colors, shares: counts.map { Double($0) / total })
    }

    /// k-means with k-means++ starts, seeded so the same image gives the same colors.
    private static func kMeans(_ points: [SIMD3<Float>], k: Int) -> [SIMD3<Float>] {
        guard k > 0, !points.isEmpty else { return [] }
        var seed: UInt64 = 1
        func random() -> Float {  // a small LCG: deterministic, and plenty for choosing starts
            seed = seed &* 6364136223846793005 &+ 1442695040888963407
            return Float(seed >> 40) / Float(1 << 24)
        }
        var centers = [points[points.count / 2]]
        var distances = points.map { simd_distance_squared($0, centers[0]) }
        while centers.count < k {
            let total = distances.reduce(0, +)
            guard total > 0 else { break }
            var target = random() * total, chosen = points.count - 1
            for (i, d) in distances.enumerated() {
                target -= d
                if target <= 0 { chosen = i; break }
            }
            centers.append(points[chosen])
            for i in points.indices { distances[i] = min(distances[i], simd_distance_squared(points[i], points[chosen])) }
        }
        for _ in 0..<25 {
            var sums = [SIMD3<Float>](repeating: .zero, count: centers.count)
            var counts = [Int](repeating: 0, count: centers.count)
            for p in points {
                let i = nearest(p, centers)
                sums[i] += p
                counts[i] += 1
            }
            var moved: Float = 0
            for i in centers.indices where counts[i] > 0 {
                let c = sums[i] / Float(counts[i])
                moved = max(moved, simd_distance(c, centers[i]))
                centers[i] = c
            }
            if moved < 0.2 { break }
        }
        return centers
    }

    private static func nearest(_ p: SIMD3<Float>, _ centers: [SIMD3<Float>]) -> Int {
        var best = 0, bestD = Float.infinity
        for (i, c) in centers.enumerated() {
            let d = simd_distance_squared(p, c)
            if d < bestD { bestD = d; best = i }
        }
        return best
    }

    // MARK: highlight

    /// A gray copy of the image with the colors within `tolerance` (CIELAB
    /// distance) of a swatch painted that swatch's highlight color; where
    /// ranges overlap, the closer swatch wins (similarity_labels and
    /// highlight_overlay in the prototype). `swatches` pairs each color with
    /// its highlight color's index.
    static func highlight(_ source: UIImage, swatches: [(rgb: (Int, Int, Int), index: Int)], tolerance: Double) -> UIImage? {
        guard let ci = working(source, edge: workingEdge, smoothing: 0) else { return nil }
        let refs = swatches.map { lab(UInt8($0.rgb.0), UInt8($0.rgb.1), UInt8($0.rgb.2)) }
        let paints = swatches.map { s -> (Float, Float, Float) in
            let c = highlightColors[s.index % highlightColors.count]
            return (Float(c.0) / 255, Float(c.1) / 255, Float(c.2) / 255)
        }
        let limit = Float(tolerance * tolerance)
        return apply({ r, g, b in
            let v = lab(r, g, b)
            var best = limit, chosen = -1
            for (j, ref) in refs.enumerated() {
                let d = simd_distance_squared(v, ref)
                if d <= best { best = d; chosen = j }
            }
            if chosen >= 0 { return paints[chosen] }
            let gray = 0.299 * r + 0.587 * g + 0.114 * b
            return (gray, gray, gray)
        }, to: ci)
    }
}

// MARK: - the Color tools' bars

/// What the Color workspace shows of the selected layer.
enum ColorView: Equatable {
    case normal, simplify, highlight
}

struct SimplifySettings: Equatable {
    var mode = ColorStudy.SimplifyMode.values
    var count = 5
    var smoothing = 2
}

struct HighlightSettings: Equatable {
    var tolerance = 12.0  // DEFAULT_HIGHLIGHT_TOLERANCE; about 2.3 is a just-noticeable difference
    var selectedOnly = false
}

/// Simplify's options and the colors it found, with each one's share.
struct SimplifyBar: View {
    @Binding var settings: SimplifySettings
    let result: ColorStudy.Simplified?
    let working: Bool
    var onDone: () -> Void

    var body: some View {
        HStack(spacing: 14) {
            Label("Simplify", systemImage: "circle.lefthalf.filled").font(.subheadline.weight(.semibold))
            Picker("Mode", selection: $settings.mode) {
                ForEach(ColorStudy.SimplifyMode.allCases) { Text($0.rawValue).tag($0) }
            }
            .pickerStyle(.segmented)
            .frame(width: 270)
            Stepper("\(settings.count)", value: $settings.count, in: 2...12).fixedSize()
            Text("Smoothing")
            Slider(value: Binding(get: { Double(settings.smoothing) }, set: { settings.smoothing = Int($0.rounded()) }),
                   in: 0...6, step: 1)
                .frame(width: 110)
            HStack(spacing: 2) {
                if let result {
                    ForEach(result.colors.indices, id: \.self) { i in
                        let c = result.colors[i]
                        Rectangle()
                            .fill(Color(red: Double(c.0) / 255, green: Double(c.1) / 255, blue: Double(c.2) / 255))
                            .frame(width: max(6, 180 * result.shares[i]), height: 26)
                            .overlay(Text("\(Int((result.shares[i] * 100).rounded()))").font(.system(size: 9))
                                .foregroundStyle(Swatch(layerID: UUID(), u: 0, v: 0, red: c.0, green: c.1, blue: c.2).labelColor)
                                .opacity(result.shares[i] > 0.06 ? 1 : 0))
                    }
                }
            }
            .frame(width: 200, alignment: .leading)
            .clipShape(RoundedRectangle(cornerRadius: 5))
            .overlay(alignment: .trailing) { if working { ProgressView().controlSize(.small) } }
            Button("Done", action: onDone).buttonStyle(.borderedProminent)
        }
        .padding(.horizontal, 16)
        .frame(height: 56)
        .background(RoundedRectangle(cornerRadius: 14).fill(Color(white: 0.13).opacity(0.95)))
    }
}

/// Highlight's options and which highlight color is whose.
struct HighlightBar: View {
    @Binding var settings: HighlightSettings
    let swatches: [Swatch]
    @Binding var selectedID: UUID?
    let working: Bool
    var onDone: () -> Void

    var body: some View {
        HStack(spacing: 14) {
            Label("Highlight", systemImage: "highlighter").font(.subheadline.weight(.semibold))
            if swatches.isEmpty {
                Text("Pick a swatch first.").font(.caption).foregroundStyle(.secondary)
            } else {
                ScrollView(.horizontal, showsIndicators: false) {
                    HStack(spacing: 8) {
                        ForEach(Array(swatches.enumerated()), id: \.element.id) { i, swatch in
                            Button {
                                selectedID = swatch.id
                            } label: {
                                Text("\(i + 1)")
                                    .font(.caption.weight(.bold))
                                    .foregroundStyle(swatch.labelColor)
                                    .frame(width: 30, height: 30)
                                    .background(RoundedRectangle(cornerRadius: 7).fill(swatch.color))
                                    .padding(3)
                                    .overlay(RoundedRectangle(cornerRadius: 9)  // its highlight color
                                        .stroke(ColorStudy.highlightColor(i), lineWidth: swatch.id == selectedID ? 4 : 2))
                            }
                        }
                    }
                    .padding(.vertical, 2)
                }
                .frame(maxWidth: 300)
                Picker("Show", selection: $settings.selectedOnly) {
                    Text("All").tag(false)
                    Text("Selected").tag(true)
                }
                .pickerStyle(.segmented)
                .frame(width: 150)
                Text("Range \(Int(settings.tolerance.rounded()))").monospacedDigit().frame(width: 74, alignment: .leading)
                Slider(value: $settings.tolerance, in: 2...40).frame(width: 140)
            }
            if working { ProgressView().controlSize(.small) }
            Button("Done", action: onDone).buttonStyle(.borderedProminent)
        }
        .padding(.horizontal, 16)
        .frame(height: 56)
        .background(RoundedRectangle(cornerRadius: 14).fill(Color(white: 0.13).opacity(0.95)))
    }
}
