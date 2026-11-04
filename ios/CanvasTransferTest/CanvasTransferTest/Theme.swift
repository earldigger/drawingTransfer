import SwiftUI

/// The app's look: deep navy, slightly lighter navy cards with large rounded
/// corners, one soft sky-blue accent, and rounded type. The area right around
/// the canvas stays neutral gray, so the surround doesn't tint how the
/// painting's colors are judged.
enum Theme {
    static let background = Color(red: 0.075, green: 0.094, blue: 0.20)  // deep navy
    static let surface = Color(red: 0.118, green: 0.145, blue: 0.29)  // cards and bars
    static let raised = Color(red: 0.165, green: 0.196, blue: 0.37)  // controls and icon tiles on a card
    static let accent = Color(red: 0.55, green: 0.81, blue: 0.93)  // sky blue
    static let onAccent = Color(red: 0.06, green: 0.08, blue: 0.18)  // text and icons on the accent
    static let bar = surface.opacity(0.96)  // bars floating over the canvas area
    static let canvasSurround = Color(white: 0.23)  // neutral, for judging color

    static let cardRadius: CGFloat = 22
    static let barRadius: CGFloat = 20
    static let controlRadius: CGFloat = 12
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
