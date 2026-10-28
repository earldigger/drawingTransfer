import SwiftUI

/// Viewing two layers against each other (CompareMode in canvastransfer/models.py).
enum CompareMode: String, CaseIterable, Identifiable {
    case blinkA = "Blink A"  // everything, with layer A flashing on and off
    case blinkAB = "Blink A / B"  // A alone, then B alone
    case split = "Split"  // A left of a draggable line, B right of it

    var id: String { rawValue }
    var blinks: Bool { self != .split }
    var needsB: Bool { self != .blinkA }
}

/// Compare is a way of looking, so it's neither saved nor an undo step.
struct CompareState: Equatable {
    static let intervalRange: ClosedRange<Double> = 0.1...5  // seconds, as in the design

    var mode = CompareMode.blinkA
    var a: UUID?
    var b: UUID?
    var interval = 0.8
    var paused = false
    var split: CGFloat = 0.5  // the line, as a fraction of the canvas width

    /// A is the selected layer (or the top one); B the layer under it, or over it.
    init(session: TransferSession) {
        let layers = session.layers
        a = session.selectedID ?? layers.last?.id
        if let i = layers.firstIndex(where: { $0.id == a }) {
            b = i > 0 ? layers[i - 1].id : (layers.count > 1 ? layers[i + 1].id : nil)
        }
    }

    /// Which layers show right now; nil = the normal stack.
    func shown(in layers: [Layer], blinkOn: Bool) -> (left: Set<UUID>?, right: Set<UUID>?) {
        let visible = Set(layers.filter(\.isVisible).map(\.id))
        let a = layers.first { $0.id == self.a }?.id, b = layers.first { $0.id == self.b }?.id
        switch mode {
        case .blinkA:
            guard let a else { return (nil, nil) }
            let set = blinkOn ? visible.union([a]) : visible.subtracting([a])
            return (set, set)
        case .blinkAB:
            let one = (blinkOn ? a : b).map { Set([$0]) } ?? []
            return (one, one)
        case .split:
            return (a.map { [$0] } ?? [], b.map { [$0] } ?? [])
        }
    }
}

/// Keeps the part of a view left of `fraction` of its width.
struct LeftPart: Shape {
    var fraction: CGFloat

    func path(in rect: CGRect) -> Path {
        Path(CGRect(x: rect.minX, y: rect.minY, width: rect.width * fraction, height: rect.height))
    }
}

/// The Split line: drag the knob, with A and B marked on either side.
struct SplitHandle: View {
    @Binding var split: CGFloat
    let canvas: CGSize

    @State private var start: CGFloat? = nil

    var body: some View {
        let x = split * canvas.width
        ZStack(alignment: .topLeading) {
            Rectangle()
                .fill(Color.white)
                .frame(width: 2, height: canvas.height)
                .shadow(color: .black.opacity(0.5), radius: 2)
                .position(x: x, y: canvas.height / 2)
                .allowsHitTesting(false)
            tag("A").position(x: x - 22, y: 22)
            tag("B").position(x: x + 22, y: 22)
            Circle()
                .fill(Color.white)
                .overlay(Image(systemName: "arrow.left.and.right").font(.system(size: 13, weight: .bold)).foregroundStyle(.black))
                .frame(width: 34, height: 34)
                .shadow(radius: 3)
                .contentShape(Circle().inset(by: -6))  // 46 pt to touch
                .position(x: x, y: canvas.height / 2)
                .gesture(
                    DragGesture(minimumDistance: 0, coordinateSpace: .named("split"))
                        .onChanged { value in
                            if start == nil { start = split }
                            guard let start else { return }
                            split = min(max(start + value.translation.width / max(canvas.width, 1), 0.02), 0.98)
                        }
                        .onEnded { _ in start = nil }
                )
                .accessibilityLabel("Split line")
        }
        .frame(width: canvas.width, height: canvas.height, alignment: .topLeading)
        .coordinateSpace(.named("split"))
    }

    private func tag(_ text: String) -> some View {
        Text(text)
            .font(.caption.weight(.bold))
            .frame(width: 24, height: 24)
            .background(Circle().fill(Color.blue))
            .foregroundStyle(.white)
            .allowsHitTesting(false)
    }
}

/// Shown at the bottom while comparing: mode, A and B, swap, speed, pause, Done.
struct CompareBar: View {
    @Binding var state: CompareState
    let layers: [Layer]
    let blinkOn: Bool
    var onDone: () -> Void

    var body: some View {
        HStack(spacing: 14) {
            Label("Compare", systemImage: "rectangle.split.2x1").font(.subheadline.weight(.semibold))
            Picker("Mode", selection: $state.mode) {
                ForEach(CompareMode.allCases) { Text($0.rawValue).tag($0) }
            }
            .pickerStyle(.segmented)
            .frame(width: 300)
            layerPicker("A", $state.a)
            if state.mode.needsB {
                layerPicker("B", $state.b)
                Button("Swap", systemImage: "arrow.left.arrow.right") { (state.a, state.b) = (state.b, state.a) }
                    .labelStyle(.iconOnly)
            }
            if state.mode.blinks {
                Text(String(format: "%.1f s", state.interval)).monospacedDigit().frame(width: 44)
                Slider(value: $state.interval, in: CompareState.intervalRange).frame(width: 120)
                Button(state.paused ? "Play" : "Pause", systemImage: state.paused ? "play.fill" : "pause.fill") {
                    state.paused.toggle()
                }
                .labelStyle(.iconOnly)
                Text(showing).font(.caption).foregroundStyle(.secondary).frame(width: 74, alignment: .leading)
            }
            Button("Done", action: onDone).buttonStyle(.borderedProminent)
        }
        .padding(.horizontal, 16)
        .frame(height: 56)
        .background(RoundedRectangle(cornerRadius: 14).fill(Color(white: 0.13).opacity(0.95)))
    }

    private var showing: String {
        switch state.mode {
        case .blinkA: blinkOn ? "A shown" : "A hidden"
        case .blinkAB: blinkOn ? "Showing A" : "Showing B"
        case .split: ""
        }
    }

    /// Layers by position, 1 at the bottom, as numbered in the layer bar while comparing.
    private func layerPicker(_ title: String, _ selection: Binding<UUID?>) -> some View {
        Picker(title, selection: selection) {
            ForEach(Array(layers.enumerated()).reversed(), id: \.element.id) { i, layer in
                Text("\(title): Layer \(i + 1)").tag(Optional(layer.id))
            }
        }
        .pickerStyle(.menu)
        .fixedSize()
    }
}
