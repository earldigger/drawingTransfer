import SwiftUI

/// The shape a crop keeps while you drag it.
enum CropShape: String, CaseIterable, Identifiable {
    case free = "Free"
    case original = "Original"  // the photo's own proportions
    case square = "Square"

    var id: String { rawValue }
}

/// Which part of the crop frame is being dragged.
enum CropHandle: Equatable {
    case move
    case corner(Int)  // 0 top-left, 1 top-right, 2 bottom-right, 3 bottom-left
    case edge(Int)  // 0 top, 1 right, 2 bottom, 3 left
}

/// A crop is a rectangle in fractions (0...1) of the layer's own image, so it
/// moves with every move, scale and twist of the layer, and never deletes
/// anything. The same math as `drag_crop` in canvastransfer/geometry.py.
enum Crop {
    static let full = CGRect(x: 0, y: 0, width: 1, height: 1)
    static let minSide: CGFloat = 0.02  // smallest crop side, as a fraction of the image

    /// Crop width ÷ height, in fractions, that keeps `shape`; nil = any.
    static func ratio(_ shape: CropShape, imageAspect: CGFloat) -> CGFloat? {
        switch shape {
        case .free: nil
        case .original: 1  // same fraction of width and height
        case .square: 1 / max(imageAspect, 0.01)  // equal pixels across and down
        }
    }

    /// The largest crop of `ratio` inside `crop`, about its center.
    static func shaped(_ crop: CGRect, ratio: CGFloat) -> CGRect {
        let w = min(crop.width, crop.height * ratio), h = w / ratio
        return CGRect(x: crop.midX - w / 2, y: crop.midY - h / 2, width: w, height: h)
    }

    /// New crop for dragging `handle` by (du, dv) image fractions from `crop`.
    /// Stays inside the image and never gets smaller than `minSide`; moving
    /// keeps its size; with a `ratio`, corners keep the shape.
    static func dragged(_ crop: CGRect, _ handle: CropHandle, du: CGFloat, dv: CGFloat, ratio: CGFloat?) -> CGRect {
        var left = crop.minX, top = crop.minY, right = crop.maxX, bottom = crop.maxY
        switch handle {
        case .move:
            let u = min(max(du, -left), 1 - right), v = min(max(dv, -top), 1 - bottom)
            return crop.offsetBy(dx: u, dy: v)
        case .corner(let i):
            let movesLeft = i == 0 || i == 3, movesTop = i == 0 || i == 1
            if let ratio {
                return keepingShape(crop, corner: i, du: du, dv: dv, ratio: ratio)
            }
            if movesLeft { left = min(max(left + du, 0), right - minSide) } else { right = max(min(right + du, 1), left + minSide) }
            if movesTop { top = min(max(top + dv, 0), bottom - minSide) } else { bottom = max(min(bottom + dv, 1), top + minSide) }
        case .edge(let i):
            switch i {
            case 0: top = min(max(top + dv, 0), bottom - minSide)
            case 1: right = max(min(right + du, 1), left + minSide)
            case 2: bottom = max(min(bottom + dv, 1), top + minSide)
            default: left = min(max(left + du, 0), right - minSide)
            }
        }
        return CGRect(x: left, y: top, width: right - left, height: bottom - top)
    }

    /// A corner drag that keeps `ratio`: the opposite corner stays put, and the
    /// crop follows whichever way the finger went further.
    private static func keepingShape(_ crop: CGRect, corner i: Int, du: CGFloat, dv: CGFloat, ratio: CGFloat) -> CGRect {
        let movesLeft = i == 0 || i == 3, movesTop = i == 0 || i == 1
        let anchorX = movesLeft ? crop.maxX : crop.minX, anchorY = movesTop ? crop.maxY : crop.minY
        let fromU = crop.width + (movesLeft ? -du : du)
        let fromV = (crop.height + (movesTop ? -dv : dv)) * ratio
        let maxW = min(movesLeft ? anchorX : 1 - anchorX, (movesTop ? anchorY : 1 - anchorY) * ratio)
        let w = min(max(max(fromU, fromV), minSide, minSide * ratio), maxW)
        let h = w / ratio
        return CGRect(x: movesLeft ? anchorX - w : anchorX, y: movesTop ? anchorY - h : anchorY, width: w, height: h)
    }
}

/// The crop frame on the selected layer: corner and edge handles, and drag
/// inside to slide it. Lives in the layer's own (unrotated) space, so the
/// handles turn and scale with it.
struct CropFrame: View {
    @Bindable var layer: Layer
    let canvas: CGSize
    let shape: CropShape

    @State private var start: CGRect? = nil

    var body: some View {
        let w = layer.width * canvas.width, h = w / layer.aspect
        let c = layer.crop
        let r = CGRect(x: c.minX * w, y: c.minY * h, width: c.width * w, height: c.height * h)
        let ratio = Crop.ratio(shape, imageAspect: layer.aspect)
        ZStack(alignment: .topLeading) {
            Rectangle()
                .fill(Color.white.opacity(0.001))  // catches drags inside the frame
                .frame(width: r.width, height: r.height)
                .position(x: r.midX, y: r.midY)
                .gesture(drag(.move, size: CGSize(width: w, height: h), ratio: ratio))
            Rectangle()
                .stroke(Color.blue, lineWidth: 2)
                .frame(width: r.width, height: r.height)
                .position(x: r.midX, y: r.midY)
                .allowsHitTesting(false)
            if ratio == nil {
                let edges = [CGPoint(x: r.midX, y: r.minY), CGPoint(x: r.maxX, y: r.midY),
                             CGPoint(x: r.midX, y: r.maxY), CGPoint(x: r.minX, y: r.midY)]
                ForEach(0..<4, id: \.self) { i in
                    Capsule()
                        .fill(Color.white)
                        .overlay(Capsule().stroke(Color.blue, lineWidth: 2))
                        .frame(width: i % 2 == 0 ? 30 : 8, height: i % 2 == 0 ? 8 : 30)
                        .contentShape(Rectangle().inset(by: -16))  // 40 pt or more to touch
                        .position(edges[i])
                        .gesture(drag(.edge(i), size: CGSize(width: w, height: h), ratio: ratio))
                }
            }
            let corners = [CGPoint(x: r.minX, y: r.minY), CGPoint(x: r.maxX, y: r.minY),
                           CGPoint(x: r.maxX, y: r.maxY), CGPoint(x: r.minX, y: r.maxY)]
            ForEach(0..<4, id: \.self) { i in
                Circle()
                    .fill(Color.white)
                    .overlay(Circle().stroke(Color.blue, lineWidth: 3))
                    .frame(width: 24, height: 24)
                    .contentShape(Circle().inset(by: -11))  // 46 pt to touch
                    .position(corners[i])
                    .gesture(drag(.corner(i), size: CGSize(width: w, height: h), ratio: ratio))
            }
        }
        .frame(width: w, height: h, alignment: .topLeading)
        .coordinateSpace(.named("crop"))
        .rotationEffect(layer.rotation)
        .position(x: layer.center.x * canvas.width, y: layer.center.y * canvas.height)
    }

    /// Measured in the layer's own space, so a rotated or zoomed layer drags true.
    private func drag(_ handle: CropHandle, size: CGSize, ratio: CGFloat?) -> some Gesture {
        DragGesture(minimumDistance: 0, coordinateSpace: .named("crop"))
            .onChanged { value in
                if start == nil { start = layer.crop }
                guard let start else { return }
                layer.crop = Crop.dragged(start, handle, du: value.translation.width / max(size.width, 1),
                                          dv: value.translation.height / max(size.height, 1), ratio: ratio)
            }
            .onEnded { _ in start = nil }
    }
}

/// Shown instead of the Look bar while cropping.
struct CropBar: View {
    @Bindable var layer: Layer
    @Binding var shape: CropShape
    var onCancel: () -> Void
    var onDone: () -> Void

    var body: some View {
        HStack(spacing: 16) {
            Label("Crop", systemImage: "crop").font(.subheadline.weight(.semibold))
            Picker("Shape", selection: $shape) {
                ForEach(CropShape.allCases) { Text($0.rawValue).tag($0) }
            }
            .pickerStyle(.segmented)
            .frame(width: 260)
            Button("Reset") { layer.crop = reshaped(Crop.full) }
            Button("Cancel", action: onCancel)
            Button("Done", action: onDone).buttonStyle(.borderedProminent)
        }
        .padding(.horizontal, 16)
        .frame(height: 56)
        .background(RoundedRectangle(cornerRadius: 14).fill(Color(white: 0.13).opacity(0.95)))
        .onChange(of: shape) { layer.crop = reshaped(layer.crop) }
    }

    private func reshaped(_ crop: CGRect) -> CGRect {
        guard let ratio = Crop.ratio(shape, imageAspect: layer.aspect) else { return crop }
        return Crop.shaped(crop, ratio: ratio)
    }
}
