import SwiftUI

/// What the Transform handles do (TransformMode in canvastransfer/geometry.py).
enum TransformMode: String, CaseIterable, Identifiable {
    case proportional = "Proportional"  // corners and edges scale evenly
    case free = "Free"  // corners scale width and height apart; edges stretch one way
    case skew = "Skew"  // edges slide along themselves; corners as Free
    case distort = "Distort"  // every corner moves on its own: perspective

    var id: String { rawValue }
}

/// A Transform handle: one of the four corners (0 top-left, 1 top-right,
/// 2 bottom-right, 3 bottom-left, in the image's own orientation) or edges
/// (edge i runs from corner i to corner i + 1: 0 top, 1 right, 2 bottom, 3 left).
enum TransformHandle: Equatable {
    case corner(Int)
    case edge(Int)
}

/// The prototype's transform geometry (canvastransfer/geometry.py), in Swift.
/// A quad is where the image's own corners land, [TL, TR, BR, BL], in canvas
/// points (the same units across and down). Every drag is computed from the
/// quad as it was when the drag started, so moves never drift.
enum QuadGeometry {
    static let minScale: CGFloat = 0.02
    static let minArea: CGFloat = 16  // square points

    static func centroid(_ q: [CGPoint]) -> CGPoint {
        CGPoint(x: q.map(\.x).reduce(0, +) / 4, y: q.map(\.y).reduce(0, +) / 4)
    }

    static func edgeMidpoints(_ q: [CGPoint]) -> [CGPoint] {
        (0..<4).map { i in mid(q[i], q[(i + 1) % 4]) }
    }

    static func area(_ q: [CGPoint]) -> CGFloat {
        var sum: CGFloat = 0
        for i in 0..<4 {
            let a = q[i], b = q[(i + 1) % 4]
            sum += a.x * b.y - b.x * a.y
        }
        return abs(sum) / 2
    }

    /// A non-folded, non-collapsed quad, either winding (a flipped layer winds the other way).
    static func isConvex(_ q: [CGPoint]) -> Bool {
        let signs = (0..<4).map { i in cross(q[(i + 1) % 4] - q[i], q[(i + 2) % 4] - q[(i + 1) % 4]) }
        return (signs.allSatisfy { $0 > 0 } || signs.allSatisfy { $0 < 0 }) && area(q) >= minArea
    }

    static func translate(_ q: [CGPoint], by d: CGPoint) -> [CGPoint] { q.map { $0 + d } }

    static func rotate(_ q: [CGPoint], by angle: CGFloat, about c: CGPoint) -> [CGPoint] {
        let cs = cos(angle), sn = sin(angle)
        return q.map { p in
            let d = p - c
            return CGPoint(x: c.x + d.x * cs - d.y * sn, y: c.y + d.x * sn + d.y * cs)
        }
    }

    static func scale(_ q: [CGPoint], by s: CGFloat, about a: CGPoint) -> [CGPoint] {
        q.map { a + ($0 - a) * s }
    }

    /// Mirrors the image inside the same box.
    static func flipHorizontal(_ q: [CGPoint]) -> [CGPoint] { [q[1], q[0], q[3], q[2]] }
    static func flipVertical(_ q: [CGPoint]) -> [CGPoint] { [q[3], q[2], q[1], q[0]] }

    /// The new quad for dragging `handle` from `start` to `current`, from
    /// `quad`; nil if it would fold over or collapse (keep the last good one).
    static func drag(_ mode: TransformMode, _ handle: TransformHandle, quad: [CGPoint],
                     start: CGPoint, current: CGPoint) -> [CGPoint]? {
        let delta = current - start
        var result: [CGPoint]?
        switch handle {
        case .corner(let i):
            switch mode {
            case .distort:
                var q = quad
                q[i] = quad[i] + delta
                result = q
            case .proportional:
                result = uniform(quad, anchor: quad[(i + 2) % 4], start: start, current: current)
            case .free, .skew:  // corners scale each axis on its own
                result = free(quad, anchor: quad[(i + 2) % 4], start: start, current: current, lockU: false, lockV: false)
            }
        case .edge(let i):
            let anchor = edgeMidpoints(quad)[(i + 2) % 4]
            switch mode {
            case .distort:
                var q = quad
                q[i] = quad[i] + delta
                q[(i + 1) % 4] = quad[(i + 1) % 4] + delta
                result = q
            case .skew:
                result = skewEdge(quad, edge: i, delta: delta)
            case .proportional:
                result = uniform(quad, anchor: anchor, start: start, current: current)
            case .free:  // top and bottom stretch the height only, left and right the width only
                let horizontal = i == 0 || i == 2
                result = free(quad, anchor: anchor, start: start, current: current, lockU: horizontal, lockV: !horizontal)
            }
        }
        guard let result, isConvex(result) else { return nil }
        return result
    }

    // MARK: the prototype's helpers

    private static func uniform(_ q: [CGPoint], anchor: CGPoint, start: CGPoint, current: CGPoint) -> [CGPoint] {
        let d0 = start - anchor, d1 = current - anchor
        let denom = dot(d0, d0)
        let s = denom > 1e-9 ? max(minScale, dot(d1, d0) / denom) : 1
        return scale(q, by: s, about: anchor)
    }

    private static func free(_ q: [CGPoint], anchor: CGPoint, start: CGPoint, current: CGPoint,
                             lockU: Bool, lockV: Bool) -> [CGPoint]? {
        let u = q[1] - q[0], v = q[3] - q[0]  // the layer's own x and y directions
        guard let c0 = toBasis(start - anchor, u, v), let c1 = toBasis(current - anchor, u, v) else { return nil }
        let su = lockU ? 1 : ratio(c1.x, c0.x), sv = lockV ? 1 : ratio(c1.y, c0.y)
        var out: [CGPoint] = []
        for p in q {
            guard let c = toBasis(p - anchor, u, v) else { return nil }
            out.append(anchor + u * (c.x * su) + v * (c.y * sv))
        }
        return out
    }

    /// Slides one edge along its own direction: a shear.
    private static func skewEdge(_ q: [CGPoint], edge: Int, delta: CGPoint) -> [CGPoint] {
        let a = edge, b = (edge + 1) % 4
        let e = q[b] - q[a]
        let length = hypot(e.x, e.y)
        guard length > 1e-9 else { return q }
        let eHat = e * (1 / length)
        let shift = eHat * dot(delta, eHat)
        var out = q
        out[a] = out[a] + shift
        out[b] = out[b] + shift
        return out
    }

    private static func toBasis(_ p: CGPoint, _ u: CGPoint, _ v: CGPoint) -> CGPoint? {
        let det = cross(u, v)
        guard abs(det) > 1e-9 else { return nil }
        return CGPoint(x: cross(p, v) / det, y: cross(u, p) / det)
    }

    private static func ratio(_ new: CGFloat, _ old: CGFloat) -> CGFloat {
        abs(old) < 1e-9 ? 1 : max(minScale, new / old)
    }

    private static func mid(_ a: CGPoint, _ b: CGPoint) -> CGPoint { (a + b) * 0.5 }
    private static func dot(_ a: CGPoint, _ b: CGPoint) -> CGFloat { a.x * b.x + a.y * b.y }
    static func cross(_ a: CGPoint, _ b: CGPoint) -> CGFloat { a.x * b.y - a.y * b.x }

    // MARK: drawing an image into a quad

    /// The projective transform that takes a `size` rectangle at the origin
    /// to `quad`: how a layer's image is drawn into its corners.
    static func projection(from size: CGSize, to quad: [CGPoint]) -> ProjectionTransform {
        // The unit square to the quad (Heckbert's square-to-quad mapping) ...
        let (x0, y0) = (quad[0].x, quad[0].y), (x1, y1) = (quad[1].x, quad[1].y)
        let (x2, y2) = (quad[2].x, quad[2].y), (x3, y3) = (quad[3].x, quad[3].y)
        let sx = x0 - x1 + x2 - x3, sy = y0 - y1 + y2 - y3
        var a, b, c, d, e, f, g, h: CGFloat
        if abs(sx) < 1e-9 && abs(sy) < 1e-9 {  // a parallelogram: affine
            a = x1 - x0; b = x3 - x0; c = x0
            d = y1 - y0; e = y3 - y0; f = y0
            g = 0; h = 0
        } else {
            let dx1 = x1 - x2, dx2 = x3 - x2, dy1 = y1 - y2, dy2 = y3 - y2
            let den = dx1 * dy2 - dx2 * dy1
            g = abs(den) < 1e-12 ? 0 : (sx * dy2 - dx2 * sy) / den
            h = abs(den) < 1e-12 ? 0 : (dx1 * sy - sx * dy1) / den
            a = x1 - x0 + g * x1; b = x3 - x0 + h * x3; c = x0
            d = y1 - y0 + g * y1; e = y3 - y0 + h * y3; f = y0
        }
        // ... after scaling the rectangle down to the unit square. SwiftUI's
        // transforms take row vectors: [x y 1] × M.
        let w = max(size.width, 1e-6), ht = max(size.height, 1e-6)
        var m = ProjectionTransform()
        m.m11 = a / w; m.m12 = d / w; m.m13 = g / w
        m.m21 = b / ht; m.m22 = e / ht; m.m23 = h / ht
        m.m31 = c; m.m32 = f; m.m33 = 1
        return m
    }

    /// Where a point of the image (in fractions of it, 0...1) lands in the quad.
    static func point(_ u: CGFloat, _ v: CGFloat, in quad: [CGPoint]) -> CGPoint {
        let m = projection(from: CGSize(width: 1, height: 1), to: quad)
        let x = m.m11 * u + m.m21 * v + m.m31, y = m.m12 * u + m.m22 * v + m.m32
        let w = m.m13 * u + m.m23 * v + m.m33
        return CGPoint(x: x / w, y: y / w)
    }

    /// The inverse: which point of the image (in fractions) is under `p`.
    static func imageFraction(of p: CGPoint, in quad: [CGPoint]) -> CGPoint? {
        let m = projection(from: CGSize(width: 1, height: 1), to: quad)
        // Invert the 3 × 3 matrix [[m11 m12 m13] [m21 m22 m23] [m31 m32 m33]].
        let a = m.m11, b = m.m12, c = m.m13, d = m.m21, e = m.m22, f = m.m23, g = m.m31, h = m.m32, i = m.m33
        let det = a * (e * i - f * h) - b * (d * i - f * g) + c * (d * h - e * g)
        guard abs(det) > 1e-12 else { return nil }
        let x = p.x, y = p.y
        let u = (x * (e * i - f * h) - y * (d * i - f * g) + (d * h - e * g)) / det
        let v = (-x * (b * i - c * h) + y * (a * i - c * g) - (a * h - b * g)) / det
        let w = (x * (b * f - c * e) - y * (a * f - c * d) + (a * e - b * d)) / det
        guard abs(w) > 1e-12 else { return nil }
        return CGPoint(x: u / w, y: v / w)
    }
}

extension CGPoint {
    static func + (a: CGPoint, b: CGPoint) -> CGPoint { CGPoint(x: a.x + b.x, y: a.y + b.y) }
    static func - (a: CGPoint, b: CGPoint) -> CGPoint { CGPoint(x: a.x - b.x, y: a.y - b.y) }
    static func * (a: CGPoint, s: CGFloat) -> CGPoint { CGPoint(x: a.x * s, y: a.y * s) }
}

/// The Transform handles on the selected layer: corners and edge midpoints,
/// in canvas points. What a drag does depends on the mode.
struct TransformHandles: View {
    @Bindable var layer: Layer
    let canvas: CGSize
    let mode: TransformMode
    var onBegin: () -> Void
    var onEnd: () -> Void

    @State private var start: [CGPoint]? = nil  // the quad when the drag began

    var body: some View {
        let quad = layer.quadPoints(in: canvas)
        let mids = QuadGeometry.edgeMidpoints(quad)
        ZStack(alignment: .topLeading) {
            Path { p in
                p.addLines(quad)
                p.closeSubpath()
            }
            .stroke(Color.blue, lineWidth: 2)
            .allowsHitTesting(false)
            ForEach(0..<4, id: \.self) { i in
                let horizontal = abs(quad[(i + 1) % 4].x - quad[i].x) >= abs(quad[(i + 1) % 4].y - quad[i].y)
                Capsule()
                    .fill(Color.white)
                    .overlay(Capsule().stroke(Color.blue, lineWidth: 2))
                    .frame(width: horizontal ? 26 : 8, height: horizontal ? 8 : 26)
                    .contentShape(Rectangle().inset(by: -18))
                    .position(mids[i])
                    .gesture(drag(.edge(i)))
            }
            ForEach(0..<4, id: \.self) { i in
                Rectangle()
                    .fill(Color.white)
                    .overlay(Rectangle().stroke(Color.blue, lineWidth: 2.5))
                    .frame(width: 18, height: 18)
                    .rotationEffect(mode == .distort ? .degrees(45) : .zero)  // a diamond: corners move on their own
                    .contentShape(Rectangle().inset(by: -14))  // 46 pt to touch
                    .position(quad[i])
                    .gesture(drag(.corner(i)))
            }
        }
        .frame(width: canvas.width, height: canvas.height, alignment: .topLeading)
        .coordinateSpace(.named("transform"))
    }

    private func drag(_ handle: TransformHandle) -> some Gesture {
        DragGesture(minimumDistance: 0, coordinateSpace: .named("transform"))
            .onChanged { value in
                if start == nil {
                    start = layer.quadPoints(in: canvas)
                    onBegin()
                }
                guard let start,
                      let quad = QuadGeometry.drag(mode, handle, quad: start, start: value.startLocation, current: value.location)
                else { return }  // would fold over: keep the last good shape
                layer.setQuad(points: quad, in: canvas)
            }
            .onEnded { _ in
                start = nil
                onEnd()
            }
    }
}

/// Shown while Transform is on: mode, Flip H / V, Fit, Cancel, Done.
struct TransformBar: View {
    @Bindable var layer: Layer
    @Binding var mode: TransformMode
    let canvasSize: CGSize  // inches
    var onCancel: () -> Void
    var onDone: () -> Void

    var body: some View {
        HStack(spacing: 14) {
            Label("Transform", systemImage: "arrow.up.and.down.and.arrow.left.and.right").font(.subheadline.weight(.semibold))
            Picker("Mode", selection: $mode) {
                ForEach(TransformMode.allCases) { Text($0.rawValue).tag($0) }
            }
            .pickerStyle(.segmented)
            .frame(width: 380)
            Button("Flip H", systemImage: "arrow.left.and.right") { layer.flipHorizontal() }
            Button("Flip V", systemImage: "arrow.up.and.down") { layer.flipVertical() }
            Button("Fit") { layer.fit(canvasAspect: canvasSize.width / canvasSize.height) }
            Button("Cancel", action: onCancel)
            Button("Done", action: onDone).buttonStyle(.borderedProminent)
        }
        .padding(.horizontal, 16)
        .frame(height: 56)
        .background(RoundedRectangle(cornerRadius: 14).fill(Color(white: 0.13).opacity(0.95)))
    }
}
