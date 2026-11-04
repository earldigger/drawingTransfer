import SwiftUI
import UniformTypeIdentifiers

/// The Paint library (the prototype's Paint Library window): Paints and
/// Palettes, edited on a copy. Done keeps the changes on the iPad; Cancel
/// throws them away.
struct PaintLibraryView: View {
    var onClose: () -> Void

    enum Tab: String, CaseIterable, Identifiable {
        case paints = "Paints"
        case palettes = "Palettes"
        var id: String { rawValue }
    }

    @State private var library = PaintLibrary.shared
    @State private var paints: [Paint] = []
    @State private var palettes: [Palette] = []
    @State private var tab = Tab.paints
    @State private var loaded = false
    @State private var importing = false
    @State private var saveError: String? = nil

    var body: some View {
        NavigationStack {
            VStack(spacing: 12) {
                UnderlineTabs(tabs: Tab.allCases, selection: $tab) { $0.rawValue }
                switch tab {
                case .paints: PaintsTab(paints: $paints, palettes: $palettes, onImport: { importing = true })
                case .palettes: PalettesTab(paints: paints, palettes: $palettes)
                }
                footer
            }
            .padding(16)
            .background(Theme.background)
            .navigationTitle("Paint library")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .cancellationAction) { Button("Cancel", action: onClose) }
                ToolbarItem(placement: .confirmationAction) {
                    Button("Done") {
                        do {
                            try library.replace(paints: paints, palettes: palettes)
                            onClose()
                        } catch {
                            saveError = "Couldn't save the library: \(error.localizedDescription)"
                        }
                    }
                }
            }
            .alert("Not saved", isPresented: Binding(get: { saveError != nil }, set: { if !$0 { saveError = nil } })) {
                Button("OK", role: .cancel) {}
            } message: { Text(saveError ?? "") }
            .fileImporter(isPresented: $importing, allowedContentTypes: [.json]) { picked in
                do {
                    try library.importFile(at: picked.get())  // a newer paints.json from the prototype
                    paints = library.paints
                    palettes = library.palettes
                } catch {
                    saveError = "That isn't a paints.json from the prototype."
                }
            }
        }
        .themed()
        .onAppear {
            guard !loaded else { return }
            paints = library.paints
            palettes = library.palettes
            loaded = true
        }
    }

    private var footer: some View {
        let measured = paints.filter { $0.lab != nil }.count
        let standIn = paints.filter { $0.lab == nil && PaintLibrary.standIn(for: $0, among: paints) != nil }.count
        let none = paints.count - measured - standIn
        return HStack {
            Text("\(paints.count) paints · \(measured) measured · \(standIn) using a stand-in · \(none) without color data · ⚠ = can't be shown exactly on screen")
            Spacer()
            Text("Saved on this iPad · \(library.origin)")
        }
        .font(.caption).foregroundStyle(.secondary)
    }
}

// MARK: - colors on the working copy

/// A paint's own color, or its stand-in's, among `paints`.
private func color(of paint: Paint, among paints: [Paint]) -> [Double]? {
    paint.lab ?? PaintLibrary.standIn(for: paint, among: paints)?.lab
}

/// A small chip of the paint's color; dashed when it has none.
private struct PaintChip: View {
    let lab: [Double]?
    var size: CGFloat = 22

    var body: some View {
        if let lab {
            let c = PaintColor.srgb(lab).rgb
            RoundedRectangle(cornerRadius: 4)
                .fill(Color(red: Double(c.0) / 255, green: Double(c.1) / 255, blue: Double(c.2) / 255))
                .overlay(RoundedRectangle(cornerRadius: 4).stroke(Color.white.opacity(0.25)))
                .frame(width: size, height: size)
        } else {
            RoundedRectangle(cornerRadius: 4)
                .strokeBorder(style: StrokeStyle(lineWidth: 1, dash: [3]))
                .foregroundStyle(.secondary)
                .frame(width: size, height: size)
        }
    }
}

// MARK: - Paints

/// Your paints in a table grouped by medium, as in the prototype: favorite,
/// Use, color, name (✎ when changed from the site's data), brand, series,
/// pigments, opacity, lightfastness and where the color comes from.
private struct PaintsTab: View {
    @Binding var paints: [Paint]
    @Binding var palettes: [Palette]
    var onImport: () -> Void

    @State private var selectedID: String? = nil
    @State private var editing: PaintDraft? = nil
    @State private var confirmingDelete = false
    @Environment(\.openURL) private var openURL

    private var selected: Paint? { paints.first { $0.id == selectedID } }
    private var media: [String] {
        let order = ["oil", "watercolor", "acrylic", "gouache"]
        return Set(paints.map(\.medium)).sorted { (order.firstIndex(of: $0) ?? 9, $0) < (order.firstIndex(of: $1) ?? 9, $1) }
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 10) {
            HStack(spacing: 10) {
                Button("Add Paint…") {
                    let id = "manual-" + UUID().uuidString.prefix(8).lowercased()
                    var p = Paint(id: id, medium: selected?.medium ?? media.first ?? "oil", brand: "", name: "", lab: nil)
                    p.source = "Entered by hand"
                    editing = PaintDraft(paint: p, isNew: true)
                }
                Button("Edit…") { if let selected { editing = PaintDraft(paint: selected, isNew: false) } }
                    .disabled(selected == nil)
                Button("Delete", role: .destructive) { confirmingDelete = true }
                    .disabled(selected == nil)
                Button("Revert to Site Data") {
                    guard let i = paints.firstIndex(where: { $0.id == selectedID }) else { return }
                    paints[i].revertToSite()
                }
                .disabled(selected?.site.isEmpty ?? true || (selected?.edited.isEmpty ?? true))
                Button("Open Web Page") { if let s = selected, let url = URL(string: s.url) { openURL(url) } }
                    .disabled(selected?.url.isEmpty ?? true)
                Spacer()
                Button("Import paints…", action: onImport)
            }
            .buttonStyle(.bordered)
            header
            ScrollView {
                LazyVStack(alignment: .leading, spacing: 0, pinnedViews: [.sectionHeaders]) {
                    ForEach(media, id: \.self) { medium in
                        let list = paints.filter { $0.medium == medium }
                            .sorted { ($0.brand, $0.name) < ($1.brand, $1.name) }
                        Section {
                            ForEach(list) { paint in row(paint) }
                        } header: {
                            Text("\(medium.capitalized) (\(list.count))").font(.headline)
                                .frame(maxWidth: .infinity, alignment: .leading)
                                .padding(.vertical, 6).background(Theme.surface)
                        }
                    }
                }
            }
            .background(RoundedRectangle(cornerRadius: 8).fill(Theme.surface))
        }
        .sheet(item: $editing) { draft in
            PaintEditor(draft: draft, paints: paints) { saved in
                if let i = paints.firstIndex(where: { $0.id == saved.id }) { paints[i] = saved } else { paints.append(saved) }
                selectedID = saved.id
                editing = nil
            } onCancel: { editing = nil }
        }
        .confirmationDialog("Delete \(selected?.name ?? "this paint")?", isPresented: $confirmingDelete, titleVisibility: .visible) {
            Button("Delete", role: .destructive) {
                guard let id = selectedID else { return }
                paints.removeAll { $0.id == id }
                for i in palettes.indices { palettes[i].paintIDs.removeAll { $0 == id } }
                for i in paints.indices where paints[i].standIn == id { paints[i].standIn = nil }
                selectedID = nil
            }
        } message: { Text("It's also taken out of your palettes.") }
    }

    // Column widths.
    private let widths: [CGFloat] = [28, 34, 26, 230, 230, 50, 150, 130, 80]

    private var header: some View {
        HStack(spacing: 8) {
            Image(systemName: "star.fill").frame(width: widths[0])
            Text("Use").frame(width: widths[1])
            Text("").frame(width: widths[2])
            Text("Paint").frame(width: widths[3], alignment: .leading)
            Text("Brand").frame(width: widths[4], alignment: .leading)
            Text("Series").frame(width: widths[5], alignment: .leading)
            Text("Pigments").frame(width: widths[6], alignment: .leading)
            Text("Opacity").frame(width: widths[7], alignment: .leading)
            Text("Lightfast").frame(width: widths[8], alignment: .leading)
            Text("Color data").frame(maxWidth: .infinity, alignment: .leading)
        }
        .font(.caption.weight(.semibold)).foregroundStyle(.secondary)
        .padding(.horizontal, 8)
    }

    private func row(_ paint: Paint) -> some View {
        let isSelected = paint.id == selectedID
        let index = paints.firstIndex { $0.id == paint.id }
        return HStack(spacing: 8) {
            Button {
                if let index { paints[index].favorite.toggle() }
            } label: {
                Image(systemName: paint.favorite ? "star.fill" : "star").foregroundStyle(paint.favorite ? .yellow : .secondary)
            }
            .buttonStyle(.plain).frame(width: widths[0])
            .accessibilityLabel(paint.favorite ? "Favorite" : "Not a favorite")
            Button {
                if let index { paints[index].enabled.toggle() }
            } label: {
                Image(systemName: paint.enabled ? "checkmark.square.fill" : "square").foregroundStyle(paint.enabled ? Theme.accent : Color.secondary)
            }
            .buttonStyle(.plain).frame(width: widths[1])
            .accessibilityLabel(paint.enabled ? "Used in mixes" : "Not used in mixes")
            PaintChip(lab: color(of: paint, among: paints)).frame(width: widths[2])
            Text(paint.name + (paint.edited.isEmpty ? "" : " ✎")).lineLimit(1).frame(width: widths[3], alignment: .leading)
            Text(paint.brand).lineLimit(1).frame(width: widths[4], alignment: .leading)
            Text(paint.series).lineLimit(1).frame(width: widths[5], alignment: .leading)
            Text(paint.pigments.joined(separator: ", ")).lineLimit(1).frame(width: widths[6], alignment: .leading)
            Text(Paint.opacityLabels[paint.opacity] ?? paint.opacity).lineLimit(1).frame(width: widths[7], alignment: .leading)
            Text(paint.lightfastness).lineLimit(1).frame(width: widths[8], alignment: .leading)
            colorData(paint).lineLimit(1).frame(maxWidth: .infinity, alignment: .leading)
        }
        .font(.callout)
        .padding(.horizontal, 8).padding(.vertical, 6)
        .background(isSelected ? Theme.accent.opacity(0.35) : Color.clear)
        .contentShape(Rectangle())
        .onTapGesture(count: 2) { editing = PaintDraft(paint: paint, isNew: false) }
        .onTapGesture { selectedID = paint.id }
    }

    /// Where the color comes from; ⚠ when it can't be shown exactly on screen.
    private func colorData(_ paint: Paint) -> some View {
        if let lab = paint.lab {
            let off = !PaintColor.srgb(lab).inGamut
            return Text((off ? "⚠ " : "") + (paint.source.isEmpty ? "Measured" : paint.source))
                .foregroundStyle(off ? Color.orange : Color.primary)
        }
        if let stand = PaintLibrary.standIn(for: paint, among: paints), let lab = stand.lab {
            let off = !PaintColor.srgb(lab).inGamut
            return Text((off ? "⚠ " : "") + "Stand-in: \(stand.name)").foregroundStyle(off ? Color.orange : Color.primary)
        }
        return Text("No color data").foregroundStyle(Color.red)
    }
}

/// A paint being edited, new or not.
private struct PaintDraft: Identifiable {
    var paint: Paint
    var isNew: Bool
    var id: String { paint.id }
}

/// Edit Paint, as in the prototype: group, brand, name, series, pigments,
/// opacity, lightfastness, drying time, strength, color (CIELAB D50) and stand-in.
private struct PaintEditor: View {
    let draft: PaintDraft
    let paints: [Paint]
    var onSave: (Paint) -> Void
    var onCancel: () -> Void

    @State private var paint: Paint
    @State private var pigments: String
    @State private var labText: String

    init(draft: PaintDraft, paints: [Paint], onSave: @escaping (Paint) -> Void, onCancel: @escaping () -> Void) {
        self.draft = draft
        self.paints = paints
        self.onSave = onSave
        self.onCancel = onCancel
        _paint = State(initialValue: draft.paint)
        _pigments = State(initialValue: draft.paint.pigments.joined(separator: ", "))
        _labText = State(initialValue: draft.paint.lab.map { $0.map { String(format: "%.2f", $0) }.joined(separator: "  ") } ?? "")
    }

    /// Three numbers, or nothing (then a stand-in's color is borrowed); nil if it doesn't read.
    private var parsedLab: [Double]?? {
        let parts = labText.replacingOccurrences(of: ",", with: " ").split(whereSeparator: \.isWhitespace)
        if parts.isEmpty { return .some(nil) }
        let numbers = parts.compactMap { Double($0) }
        return numbers.count == 3 && parts.count == 3 ? .some(numbers) : nil
    }

    private var media: [String] { Array(Set(paints.map(\.medium) + ["oil", "watercolor", "acrylic", "gouache"])).sorted() }
    private static let lightfastChoices = ["★★★", "★★☆", "★☆☆", "ASTM I", "ASTM II", "ASTM III", "I", "II", "III"]

    var body: some View {
        NavigationStack {
            Form {
                Section {
                    HStack {
                        TextField("Group", text: $paint.medium).textInputAutocapitalization(.never)
                        Menu {
                            ForEach(media, id: \.self) { m in Button(m.capitalized) { paint.medium = m } }
                        } label: { Image(systemName: "chevron.down") }
                    }
                    .labeled("Group")
                    TextField("Brand", text: $paint.brand).labeled("Brand")
                    TextField("Name", text: $paint.name).labeled("Name")
                    TextField("Series", text: $paint.series).labeled("Series")
                    TextField("e.g. PB29, PV23", text: $pigments).textInputAutocapitalization(.characters).labeled("Pigments")
                    Picker("Opacity", selection: $paint.opacity) {
                        Text("—").tag("")
                        ForEach(["T", "ST", "SO", "O"], id: \.self) { Text(Paint.opacityLabels[$0] ?? $0).tag($0) }
                        if !["", "T", "ST", "SO", "O"].contains(paint.opacity) { Text(paint.opacity).tag(paint.opacity) }
                    }
                    HStack {
                        TextField("Lightfastness", text: $paint.lightfastness)
                        Menu {
                            ForEach(Self.lightfastChoices, id: \.self) { c in Button(c) { paint.lightfastness = c } }
                        } label: { Image(systemName: "chevron.down") }
                    }
                    .labeled("Lightfastness")
                    TextField("e.g. fast, medium, 2-3 days", text: $paint.drying).labeled("Drying time")
                    HStack {
                        Text(String(format: "×%.2f", paint.strength)).monospacedDigit()
                        Stepper("Strength", value: $paint.strength, in: 0.05...50, step: 0.05).labelsHidden()
                    }
                    .labeled("Strength")
                }
                Section {
                    HStack(spacing: 12) {
                        TextField("L*  a*  b*", text: $labText).keyboardType(.numbersAndPunctuation).monospacedDigit()
                        PaintChip(lab: (parsedLab ?? nil) ?? color(of: paint, among: paints), size: 36)
                    }
                    .labeled("Color")
                    if let lab = parsedLab ?? nil {
                        let screen = PaintColor.srgb(lab)
                        Text(String(format: "L* %.2f   a* %.2f   b* %.2f   screen #%02X%02X%02X", lab[0], lab[1], lab[2],
                                    screen.rgb.0, screen.rgb.1, screen.rgb.2)
                             + (screen.inGamut ? "" : "   ⚠ can't be shown exactly on screen"))
                            .font(.caption).foregroundStyle(screen.inGamut ? Color.secondary : Color.orange)
                    } else if parsedLab == nil {
                        Text("Enter three numbers: L* a* b*.").font(.caption).foregroundStyle(.red)
                    }
                    Picker("Stand-in", selection: Binding(get: { paint.standIn ?? "auto" },
                                                          set: { paint.standIn = $0 == "auto" ? nil : $0 })) {
                        Text(autoTitle).tag("auto")
                        Text("None").tag("")
                        ForEach(paints.filter { $0.lab != nil && $0.id != paint.id }.sorted { ($0.name, $0.brand) < ($1.name, $1.brand) }) {
                            Text("\($0.name) — \($0.brand)").tag($0.id)
                        }
                    }
                    .disabled((parsedLab ?? nil) != nil)  // only used without color data
                } footer: {
                    Text("On a paint's artistpigments.org page, open *All color measurement details* and copy the CIELAB D50 values. Leave Color empty to borrow a similar paint's color (stand-in).")
                }
            }
            .navigationTitle(draft.isNew ? "Add Paint" : "Edit Paint")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .cancellationAction) { Button("Cancel", action: onCancel) }
                ToolbarItem(placement: .confirmationAction) {
                    Button("OK") {
                        var p = paint
                        p.pigments = pigments.split(separator: ",").map { $0.trimmingCharacters(in: .whitespaces) }.filter { !$0.isEmpty }
                        p.lab = parsedLab ?? p.lab
                        p.medium = p.medium.trimmingCharacters(in: .whitespaces).lowercased()
                        p.updateEdited()
                        onSave(p)
                    }
                    .disabled(parsedLab == nil || paint.name.trimmingCharacters(in: .whitespaces).isEmpty)
                }
            }
        }
        .themed()
    }

    private var autoTitle: String {
        var probe = paint
        probe.lab = nil
        probe.standIn = nil
        probe.pigments = pigments.split(separator: ",").map { $0.trimmingCharacters(in: .whitespaces) }.filter { !$0.isEmpty }
        let others = paints.filter { $0.id != paint.id }
        return PaintLibrary.autoStandIn(for: probe, among: others).map { "Automatic (\($0.name))" } ?? "Automatic (none found)"
    }
}

private extension View {
    /// A form row with its label on the left, as in the prototype's dialog.
    func labeled(_ title: String) -> some View {
        LabeledContent(title) { self }
    }
}

// MARK: - Palettes

/// Your palettes and the classic ones: the list, and the selected one's paints.
private struct PalettesTab: View {
    let paints: [Paint]
    @Binding var palettes: [Palette]

    @State private var selected: String? = nil  // "palette:<id>" or "template:<key>"
    @State private var editing: Palette? = nil
    @State private var isNew = false
    @State private var confirmingDelete = false

    private var media: [String] { Array(Set(paints.map(\.medium))).sorted() }
    private var mine: Palette? {
        guard let s = selected, s.hasPrefix("palette:") else { return nil }
        return palettes.first { "palette:\($0.id)" == s }
    }
    private var classic: ClassicPalettes.Template? {
        guard let s = selected, s.hasPrefix("template:") else { return nil }
        return ClassicPalettes.templates.first { "template:\($0.id)" == s }
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 10) {
            HStack(spacing: 10) {
                Button("New Palette…") {
                    isNew = true
                    editing = Palette(id: "palette-" + UUID().uuidString.prefix(10).lowercased(), name: "",
                                      medium: media.first ?? "oil", paintIDs: [])
                }
                Button("Edit…") { if let mine { isNew = false; editing = mine } }.disabled(mine == nil)
                Button("Duplicate as My Palette") { duplicate() }.disabled(selected == nil)
                Button("Delete", role: .destructive) { confirmingDelete = true }.disabled(mine == nil)
                Spacer()
            }
            .buttonStyle(.bordered)
            HStack(alignment: .top, spacing: 12) {
                List(selection: $selected) {
                    Section("My palettes") {
                        ForEach(palettes) { p in
                            Text("\(p.name)   (\(p.medium.capitalized), \(p.paintIDs.count))").tag("palette:\(p.id)")
                        }
                    }
                    Section("Classic palettes") {
                        ForEach(ClassicPalettes.templates) { t in Text(t.name).tag("template:\(t.id)") }
                    }
                }
                .listStyle(.insetGrouped)
                .frame(width: 340)
                detail
                    .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .topLeading)
                    .padding(12)
                    .background(RoundedRectangle(cornerRadius: 8).fill(Theme.surface))
            }
        }
        .sheet(item: $editing) { palette in
            PaletteEditor(palette: palette, paints: paints, isNew: isNew) { saved in
                if let i = palettes.firstIndex(where: { $0.id == saved.id }) { palettes[i] = saved } else { palettes.append(saved) }
                selected = "palette:\(saved.id)"
                editing = nil
            } onCancel: { editing = nil }
        }
        .confirmationDialog("Delete \(mine?.name ?? "this palette")?", isPresented: $confirmingDelete, titleVisibility: .visible) {
            Button("Delete", role: .destructive) {
                palettes.removeAll { "palette:\($0.id)" == selected }
                selected = nil
            }
        } message: { Text("Its paints stay in your library.") }
    }

    @ViewBuilder
    private var detail: some View {
        if let mine {
            VStack(alignment: .leading, spacing: 8) {
                Text("\(mine.name) — \(mine.medium.capitalized)").font(.headline)
                ScrollView {
                    VStack(alignment: .leading, spacing: 8) {
                        ForEach(mine.paintIDs, id: \.self) { id in
                            if let p = paints.first(where: { $0.id == id }) { paintLine(p) }
                        }
                    }
                }
            }
        } else if let classic {
            let medium = media.first ?? "oil"
            let filled = ClassicPalettes.fill(classic, paints: paints, medium: medium) { color(of: $0, among: paints) != nil }
            VStack(alignment: .leading, spacing: 8) {
                Text("\(classic.name) — classic, from your \(medium) paints").font(.headline)
                Text(classic.note).font(.caption).foregroundStyle(.secondary)
                ScrollView {
                    VStack(alignment: .leading, spacing: 8) {
                        ForEach(filled.indices, id: \.self) { i in
                            let f = filled[i]
                            if let p = f.paint {
                                HStack {
                                    paintLine(p)
                                    Text("(\(f.role.name.lowercased())\(f.substitute ? ", a substitute" : ""))")
                                        .font(.caption).foregroundStyle(.secondary)
                                }
                            } else {
                                Text("\(f.role.name): none of your paints fits").foregroundStyle(.secondary)
                            }
                        }
                    }
                }
            }
        } else {
            Text("Choose a palette.").foregroundStyle(.secondary)
        }
    }

    private func paintLine(_ p: Paint) -> some View {
        let lab = color(of: p, among: paints)
        return HStack(spacing: 10) {
            PaintChip(lab: lab)
            Text("\(p.name) — \(p.brand)")
            if lab == nil { Text("(no color data: left out of mixing)") }
        }
        .foregroundStyle(lab == nil ? Color.red : Color.primary)
    }

    /// A classic palette's picks, or a copy of one of yours, as a new palette of yours.
    private func duplicate() {
        let id = "palette-" + UUID().uuidString.prefix(10).lowercased()
        if let mine {
            palettes.append(Palette(id: id, name: "\(mine.name) copy", medium: mine.medium, paintIDs: mine.paintIDs))
        } else if let classic {
            let medium = media.first ?? "oil"
            let filled = ClassicPalettes.fill(classic, paints: paints, medium: medium) { color(of: $0, among: paints) != nil }
            palettes.append(Palette(id: id, name: classic.name, medium: medium, paintIDs: filled.compactMap { $0.paint?.id }))
        } else { return }
        selected = "palette:\(id)"
    }
}

/// A palette's name, group and paints.
private struct PaletteEditor: View {
    @State var palette: Palette
    let paints: [Paint]
    let isNew: Bool
    var onSave: (Palette) -> Void
    var onCancel: () -> Void

    private var media: [String] { Array(Set(paints.map(\.medium))).sorted() }

    var body: some View {
        NavigationStack {
            Form {
                Section {
                    TextField("Name", text: $palette.name).labeled("Name")
                    Picker("Group", selection: $palette.medium) {
                        ForEach(media, id: \.self) { Text($0.capitalized).tag($0) }
                    }
                }
                Section("Paints (\(palette.paintIDs.count))") {
                    ForEach(paints.filter { $0.medium == palette.medium }.sorted { ($0.name, $0.brand) < ($1.name, $1.brand) }) { p in
                        Button {
                            if let i = palette.paintIDs.firstIndex(of: p.id) { palette.paintIDs.remove(at: i) } else { palette.paintIDs.append(p.id) }
                        } label: {
                            HStack(spacing: 10) {
                                Image(systemName: palette.paintIDs.contains(p.id) ? "checkmark.circle.fill" : "circle")
                                    .foregroundStyle(palette.paintIDs.contains(p.id) ? Theme.accent : Color.secondary)
                                PaintChip(lab: color(of: p, among: paints))
                                Text("\(p.name) — \(p.brand)").foregroundStyle(.primary)
                            }
                        }
                    }
                }
            }
            .navigationTitle(isNew ? "New Palette" : "Edit Palette")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .cancellationAction) { Button("Cancel", action: onCancel) }
                ToolbarItem(placement: .confirmationAction) {
                    Button("OK") {
                        var p = palette
                        p.name = p.name.trimmingCharacters(in: .whitespaces)
                        p.paintIDs = p.paintIDs.filter { id in paints.contains { $0.id == id && $0.medium == p.medium } }
                        onSave(p)
                    }
                    .disabled(palette.name.trimmingCharacters(in: .whitespaces).isEmpty)
                }
            }
        }
        .themed()
    }
}
