import SwiftUI

/// The app's look: deep navy, slightly lighter navy cards with large rounded
/// corners, one soft sky-blue accent, and rounded type. The area right around
/// the canvas stays neutral gray, so the surround doesn't tint how the
/// painting's colors are judged.
enum Theme {
    static let background = Color(red: 0.075, green: 0.094, blue: 0.20)  // deep navy
    static let surface = Color(red: 0.118, green: 0.145, blue: 0.29)  // cards and bars
    static let raised = Color(red: 0.165, green: 0.196, blue: 0.37)  // controls and icon tiles on a card
    static let popup = Color(red: 0.27, green: 0.31, blue: 0.54)  // pop-ups over the bars: lighter, to stand out
    static let accent = Color(red: 0.55, green: 0.81, blue: 0.93)  // sky blue
    static let onAccent = Color(red: 0.06, green: 0.08, blue: 0.18)  // text and icons on the accent
    static let lavender = Color(red: 0.73, green: 0.62, blue: 0.96)  // a color tool that's on
    static let purple = Color(red: 0.46, green: 0.30, blue: 0.95)  // "has swatches" on a layer
    static let bar = surface.opacity(0.96)  // bars floating over the canvas area
    static let canvasSurround = Color(white: 0.23)  // neutral, for judging color

    static let cardRadius: CGFloat = 22
    static let barRadius: CGFloat = 20
    static let controlRadius: CGFloat = 12

    /// Running on an iPhone (upright only): bars stack into rows, and a few
    /// iPad tools (the color tools, the Paint library) aren't offered yet.
    static let isPhone = UIDevice.current.userInterfaceIdiom == .phone
    static let device = isPhone ? "iPhone" : "iPad"  // "on this iPhone"
}

extension View {
    /// The app-wide look: dark, rounded type, sky-blue tint.
    func themed() -> some View {
        self
            .environment(\.colorScheme, .dark)
            .fontDesign(.rounded)
            .tint(Theme.accent)
    }

    /// A floating bar or panel: navy, with large rounded corners.
    func themedBar(radius: CGFloat = Theme.barRadius) -> some View {
        background(RoundedRectangle(cornerRadius: radius, style: .continuous).fill(Theme.bar))
    }

    /// A tool's bar at the bottom: the whole width, navy; 64 pt tall, or on
    /// the phone as tall as its rows.
    @ViewBuilder
    func bottomBar() -> some View {
        if Theme.isPhone {
            padding(.horizontal, 14)
                .padding(.vertical, 12)
                .frame(maxWidth: .infinity)
                .themedBar()
        } else {
            padding(.horizontal, 20)
                .frame(maxWidth: .infinity)
                .frame(height: 64)
                .themedBar()
        }
    }

    /// A text field in a raised navy box.
    func boxed() -> some View {
        padding(.horizontal, 12)
            .frame(height: 44)
            .background(RoundedRectangle(cornerRadius: Theme.controlRadius, style: .continuous).fill(Theme.raised))
    }

    /// A Gallery size card: navy, or sky blue with navy text when chosen.
    func sizeCardStyle(selected: Bool) -> some View {
        padding(16)
            .frame(width: 168, height: 150, alignment: .topLeading)
            .foregroundStyle(selected ? Theme.onAccent : Color.white)
            .background(RoundedRectangle(cornerRadius: Theme.cardRadius, style: .continuous)
                .fill(selected ? Theme.accent : Theme.surface))
    }
}

/// Spacing in the bottom bars: between groups of controls, and between icon
/// buttons in a group (as in the top bar). On a narrow screen (an iPad held
/// upright) the groups sit closer.
enum BarSpacing {
    static let group: CGFloat = 32
    static let narrowGroup: CGFloat = 18
    static let icon: CGFloat = 16

    static func group(_ narrow: Bool) -> CGFloat { narrow ? narrowGroup : group }
}

extension EnvironmentValues {
    /// The bottom bars are on a narrow screen (an iPad held upright): closer
    /// spacing, shorter sliders, and titles as icons only.
    @Entry var narrowBars = false
}

/// A bottom bar's title: its tool's icon and name (on the phone, or a narrow
/// iPad screen, the icon only).
struct BarTitle: View {
    let title: String
    let symbol: String
    @Environment(\.narrowBars) private var narrow

    init(_ title: String, symbol: String) {
        self.title = title
        self.symbol = symbol
    }

    var body: some View {
        HStack(spacing: 12) {
            Image(systemName: symbol).font(.system(size: 20))
            if !Theme.isPhone && !narrow { Text(title).font(.headline) }
        }
        .fixedSize()
        .accessibilityElement(children: .ignore)
        .accessibilityLabel(title)
    }
}

/// A bottom bar's Done, the same width in every bar.
struct DoneButton: View {
    var action: () -> Void

    var body: some View {
        Button(action: action) {
            Text("Done").lineLimit(1).fixedSize().frame(minWidth: 42)  // never wraps, whatever the text size
        }
        .buttonStyle(.accent)
    }
}

/// The main action (Done, Create project): a sky-blue capsule with navy text.
struct AccentButtonStyle: ButtonStyle {
    @Environment(\.isEnabled) private var isEnabled

    func makeBody(configuration: Configuration) -> some View {
        configuration.label
            .font(.body.weight(.semibold))
            .padding(.horizontal, 18)
            .padding(.vertical, 9)
            .background(Capsule().fill(Theme.accent.opacity(isEnabled ? 1 : 0.35)))
            .foregroundStyle(Theme.onAccent)
            .opacity(configuration.isPressed ? 0.75 : 1)
    }
}

extension ButtonStyle where Self == AccentButtonStyle {
    static var accent: AccentButtonStyle { AccentButtonStyle() }
}

/// A pop-up above a bar: a navy rounded box with a small arrow pointing
/// down at the button it belongs to (or, `below`, under a bar with the arrow
/// pointing up). `arrowInset` is from the box's leading edge (or trailing, if
/// `trailing`) to the middle of the arrow; nil puts the arrow in the middle.
struct Callout<Content: View>: View {
    var arrowInset: CGFloat? = nil
    var trailing = false
    var below = false
    var fill = Theme.surface
    @ViewBuilder var content: Content

    var body: some View {
        VStack(alignment: arrowInset == nil ? .center : trailing ? .trailing : .leading, spacing: 0) {
            if below { arrow.rotationEffect(.degrees(180)) }
            content
                .padding(18)
                .background(RoundedRectangle(cornerRadius: 26, style: .continuous).fill(fill))
            if !below { arrow }
        }
        .shadow(color: .black.opacity(0.35), radius: 10, y: 4)
    }

    private var arrow: some View {
        DownArrow()
            .fill(fill)
            .frame(width: 22, height: 11)
            .padding(trailing ? .trailing : .leading, (arrowInset ?? 11) - 11)
    }
}

struct DownArrow: Shape {
    func path(in rect: CGRect) -> Path {
        Path { p in
            p.move(to: CGPoint(x: rect.minX, y: rect.minY))
            p.addLine(to: CGPoint(x: rect.maxX, y: rect.minY))
            p.addLine(to: CGPoint(x: rect.midX, y: rect.maxY))
            p.closeSubpath()
        }
    }
}

/// An upright slider: a thin track filled sky blue from the bottom and a
/// white knob, with the value in the knob if `label` is given.
struct VerticalSlider: View {
    @Binding var value: Double
    let range: ClosedRange<Double>
    var step: Double = 1
    var label: String? = nil
    var height: CGFloat = 190

    private let knob: CGFloat = 44

    var body: some View {
        let travel = height - knob
        let fraction = (value - range.lowerBound) / max(range.upperBound - range.lowerBound, .ulpOfOne)
        let top = (1 - fraction) * travel  // the knob's top
        ZStack(alignment: .top) {
            Capsule().fill(Theme.raised).frame(width: 6)
            Capsule().fill(Theme.accent)
                .frame(width: 6, height: max(height - top - knob / 2, 0))
                .frame(maxHeight: .infinity, alignment: .bottom)
            Circle()
                .fill(Color.white)
                .frame(width: knob, height: knob)
                .overlay {
                    if let label {
                        Text(label).font(.headline).monospacedDigit().foregroundStyle(Theme.onAccent)
                    }
                }
                .shadow(color: .black.opacity(0.3), radius: 3, y: 1)
                .offset(y: top)
        }
        .frame(width: knob, height: height)
        .contentShape(Rectangle())
        .gesture(
            DragGesture(minimumDistance: 0)
                .onChanged { drag in
                    let f = min(max(1 - (drag.location.y - knob / 2) / travel, 0), 1)
                    let raw = range.lowerBound + f * (range.upperBound - range.lowerBound)
                    let stepped = min(max((raw / step).rounded() * step, range.lowerBound), range.upperBound)
                    if stepped != value { value = stepped }
                }
        )
        .accessibilityElement()
        .accessibilityValue(label ?? "\(Int(value))")
        .accessibilityAdjustableAction { direction in
            switch direction {
            case .increment: value = min(value + step, range.upperBound)
            case .decrement: value = max(value - step, range.lowerBound)
            @unknown default: break
            }
        }
    }
}

/// Text tabs with a small pill under the chosen one.
struct UnderlineTabs<Tab: Hashable & Identifiable>: View {
    let tabs: [Tab]
    @Binding var selection: Tab
    let title: (Tab) -> String

    var body: some View {
        HStack(spacing: 28) {
            ForEach(tabs) { tab in
                let on = tab == selection
                Button { withAnimation(.snappy) { selection = tab } } label: {
                    VStack(spacing: 8) {
                        Text(title(tab))
                            .font(.body.weight(on ? .semibold : .regular))
                            .foregroundStyle(on ? Color.white : Color.secondary)
                        Capsule().fill(on ? Theme.accent : Color.clear).frame(width: 26, height: 4)
                    }
                }
                .buttonStyle(.plain)
            }
        }
    }
}
