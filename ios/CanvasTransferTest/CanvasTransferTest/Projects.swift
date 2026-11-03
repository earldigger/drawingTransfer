import Observation
import OSLog
import SwiftUI
import UIKit

private let projectLog = Logger(subsystem: "CanvasTransferTest", category: "projects")

/// One painting: its name, canvas size and dates. The rest (layers,
/// swatches, grid) is its session, saved in the same folder.
struct ProjectInfo: Codable, Identifiable, Equatable {
    var id: UUID
    var name: String
    var created: Date
    var modified: Date
    var canvasSize: CGSize  // inches
}

/// The paintings on this iPad, each a folder in Application Support/Projects
/// named <id>.ctproj (the iPad's own layout, not the prototype's .ctproj):
/// project.json, thumbnail.jpg, and the session's files.
@Observable
final class ProjectStore {
    static let shared = ProjectStore()

    private(set) var projects: [ProjectInfo] = []  // most recently changed first
    private(set) var thumbnails: [UUID: UIImage] = [:]

    static let root = URL.applicationSupportDirectory.appending(path: "Projects", directoryHint: .isDirectory)

    func folder(_ id: UUID) -> URL { Self.root.appending(path: "\(id.uuidString).ctproj", directoryHint: .isDirectory) }
    private func infoURL(_ id: UUID) -> URL { folder(id).appending(path: "project.json") }
    private func thumbnailURL(_ id: UUID) -> URL { folder(id).appending(path: "thumbnail.jpg") }

    private init() {
        try? FileManager.default.createDirectory(at: Self.root, withIntermediateDirectories: true)
        moveOldSession()
        reload()
    }

    func info(_ id: UUID) -> ProjectInfo? { projects.first { $0.id == id } }

    private func reload() {
        let names = (try? FileManager.default.contentsOfDirectory(atPath: Self.root.path)) ?? []
        projects = names.filter { $0.hasSuffix(".ctproj") }.compactMap { name in
            let url = Self.root.appending(path: name).appending(path: "project.json")
            return (try? Data(contentsOf: url)).flatMap { try? JSONDecoder().decode(ProjectInfo.self, from: $0) }
        }
        .sorted { $0.modified > $1.modified }
        for p in projects where thumbnails[p.id] == nil {
            thumbnails[p.id] = UIImage(contentsOfFile: thumbnailURL(p.id).path)
        }
    }

    private func write(_ info: ProjectInfo) {
        do {
            try FileManager.default.createDirectory(at: folder(info.id), withIntermediateDirectories: true)
            try JSONEncoder().encode(info).write(to: infoURL(info.id), options: .atomic)
        } catch {
            projectLog.error("Couldn't save project \(info.name): \(error)")
        }
    }

    /// The one session from before projects becomes the first project.
    private func moveOldSession() {
        let old = SessionStore.legacyFolder, files = FileManager.default
        guard files.fileExists(atPath: old.appending(path: "session.json").path) else { return }
        let id = UUID()
        let size = (try? Data(contentsOf: old.appending(path: "session.json")))
            .flatMap { try? JSONDecoder().decode(SessionSnapshot.self, from: $0) }?.canvasSize ?? CGSize(width: 16, height: 20)
        do {
            try files.moveItem(at: old, to: folder(id))
            write(ProjectInfo(id: id, name: "My painting", created: Date(), modified: Date(), canvasSize: size))
            projectLog.notice("Moved the old session into the project My painting")
        } catch {
            projectLog.error("Couldn't move the old session: \(error)")
        }
    }

    // MARK: changes

    /// A new, empty project, saved at once.
    func create(name: String, canvasSize: CGSize) -> ProjectInfo {
        let info = ProjectInfo(id: UUID(), name: name, created: Date(), modified: Date(), canvasSize: canvasSize)
        write(info)
        let session = TransferSession()
        session.canvasSize = canvasSize
        SessionStore.save(session.snapshot, images: [:], sources: [:], to: folder(info.id))
        projects.insert(info, at: 0)
        return info
    }

    /// After each save: the date, and the canvas size if it changed.
    func touched(_ id: UUID, canvasSize: CGSize) {
        guard var info = info(id) else { return }
        info.modified = Date()
        info.canvasSize = canvasSize
        write(info)
        projects = ([info] + projects.filter { $0.id != id })
    }

    func rename(_ id: UUID, to name: String) {
        guard var info = info(id), !name.trimmingCharacters(in: .whitespaces).isEmpty else { return }
        info.name = name.trimmingCharacters(in: .whitespaces)
        write(info)
        projects = projects.map { $0.id == id ? info : $0 }
    }

    /// A copy, named "… copy", once every save asked for has been written.
    func duplicate(_ id: UUID) {
        guard let original = info(id) else { return }
        let copy = ProjectInfo(id: UUID(), name: "\(original.name) copy", created: Date(), modified: Date(),
                               canvasSize: original.canvasSize)
        let from = folder(id), to = folder(copy.id)
        SessionStore.afterSaves { [weak self] in
            do {
                try FileManager.default.copyItem(at: from, to: to)
                DispatchQueue.main.async {
                    self?.write(copy)
                    self?.thumbnails[copy.id] = self?.thumbnails[id]
                    self?.projects.insert(copy, at: 0)
                }
            } catch {
                projectLog.error("Couldn't duplicate \(original.name): \(error)")
            }
        }
    }

    func delete(_ id: UUID) {
        let target = folder(id)
        projects.removeAll { $0.id == id }
        thumbnails[id] = nil
        SessionStore.afterSaves { try? FileManager.default.removeItem(at: target) }
    }

    /// A small picture of the canvas, for the Gallery.
    @MainActor
    func saveThumbnail(_ id: UUID, session: TransferSession) {
        let size = fitRect(session.canvasSize, in: CGSize(width: 300, height: 300)).size
        let renderer = ImageRenderer(content: CanvasContent(layers: session.layers, size: size))
        renderer.scale = 2
        guard let image = renderer.uiImage else { return }
        thumbnails[id] = image
        try? image.jpegData(compressionQuality: 0.8)?.write(to: thumbnailURL(id), options: .atomic)
    }
}

// MARK: - Gallery

/// The Gallery: your paintings as cards, the most recent first, and New.
/// Long-press a card to rename, duplicate or delete it.
struct GalleryView: View {
    @Bindable var store: ProjectStore
    var onOpen: (UUID) -> Void

    @State private var creating = false
    @State private var renaming: ProjectInfo? = nil
    @State private var newName = ""
    @State private var deleting: ProjectInfo? = nil

    private let columns = [GridItem(.adaptive(minimum: 220, maximum: 260), spacing: 24)]

    var body: some View {
        NavigationStack {
            ScrollView {
                LazyVGrid(columns: columns, spacing: 28) {
                    Button { creating = true } label: {
                        VStack(spacing: 10) {
                            RoundedRectangle(cornerRadius: 12)
                                .strokeBorder(style: StrokeStyle(lineWidth: 2, dash: [8]))
                                .foregroundStyle(.secondary)
                                .frame(height: 240)
                                .overlay(Image(systemName: "plus").font(.system(size: 40)).foregroundStyle(.secondary))
                            Text("New project").font(.headline)
                            Text(" ").font(.caption)
                        }
                    }
                    .buttonStyle(.plain)
                    ForEach(store.projects) { project in card(project) }
                }
                .padding(32)
            }
            .navigationTitle("Gallery")
            .background(Color(white: 0.11))
        }
        .environment(\.colorScheme, .dark)
        .sheet(isPresented: $creating) {
            NewProjectSheet(defaultName: "Painting \(store.projects.count + 1)") { name, size in
                creating = false
                onOpen(store.create(name: name, canvasSize: size).id)
            } onCancel: { creating = false }
        }
        .alert("Rename", isPresented: Binding(get: { renaming != nil }, set: { if !$0 { renaming = nil } })) {
            TextField("Name", text: $newName)
            Button("Cancel", role: .cancel) {}
            Button("Rename") { if let r = renaming { store.rename(r.id, to: newName) } }
        }
        .confirmationDialog("Delete \(deleting?.name ?? "this project")?",
                            isPresented: Binding(get: { deleting != nil }, set: { if !$0 { deleting = nil } }),
                            titleVisibility: .visible) {
            Button("Delete", role: .destructive) { if let d = deleting { store.delete(d.id) } }
        } message: { Text("Its layers and swatches are deleted from this iPad.") }
    }

    private func card(_ project: ProjectInfo) -> some View {
        Button { onOpen(project.id) } label: {
            VStack(spacing: 10) {
                ZStack {
                    RoundedRectangle(cornerRadius: 12).fill(Color(white: 0.18))
                    if let thumb = store.thumbnails[project.id] {
                        Image(uiImage: thumb).resizable().scaledToFit().padding(12).shadow(radius: 4)
                    } else {
                        let fit = fitRect(project.canvasSize, in: CGSize(width: 200, height: 216))
                        Rectangle().fill(Color.white).frame(width: fit.width, height: fit.height).shadow(radius: 4)
                    }
                }
                .frame(height: 240)
                Text(project.name).font(.headline).lineLimit(1)
                Text("\(Int(project.canvasSize.width)) × \(Int(project.canvasSize.height)) in · "
                     + project.modified.formatted(date: .abbreviated, time: .shortened))
                    .font(.caption).foregroundStyle(.secondary)
            }
        }
        .buttonStyle(.plain)
        .contextMenu {
            Button("Rename", systemImage: "pencil") { newName = project.name; renaming = project }
            Button("Duplicate", systemImage: "plus.square.on.square") { store.duplicate(project.id) }
            Button("Delete", systemImage: "trash", role: .destructive) { deleting = project }
        }
    }
}

/// New project: name, canvas size (the presets, or your own in inches or
/// centimeters) and orientation. Saved at once.
struct NewProjectSheet: View {
    let defaultName: String
    var onCreate: (String, CGSize) -> Void
    var onCancel: () -> Void

    enum Units: String, CaseIterable, Identifiable {
        case inches = "in", centimeters = "cm"
        var id: String { rawValue }
    }

    @State private var name = ""
    @State private var preset = 4  // 16 × 20
    @State private var custom = false
    @State private var units = Units.inches
    @State private var width = 16.0
    @State private var height = 20.0
    @State private var landscape = false

    /// The size in inches, portrait or landscape.
    private var size: CGSize {
        var s = custom ? CGSize(width: width, height: height) : TransferSession.canvasSizes[preset]
        if custom && units == .centimeters { s = CGSize(width: s.width / 2.54, height: s.height / 2.54) }
        let short = min(s.width, s.height), long = max(s.width, s.height)
        return landscape ? CGSize(width: long, height: short) : CGSize(width: short, height: long)
    }

    var body: some View {
        NavigationStack {
            Form {
                TextField("Name", text: $name, prompt: Text(defaultName))
                Section("Canvas") {
                    Picker("Size", selection: $preset) {
                        ForEach(TransferSession.canvasSizes.indices, id: \.self) { i in
                            let s = TransferSession.canvasSizes[i]
                            Text("\(Int(s.width)) × \(Int(s.height)) in").tag(i)
                        }
                    }
                    .disabled(custom)
                    Toggle("Custom size", isOn: $custom)
                    if custom {
                        Picker("Units", selection: $units) {
                            ForEach(Units.allCases) { Text($0.rawValue).tag($0) }
                        }
                        .pickerStyle(.segmented)
                        LabeledContent("Width") {
                            TextField("Width", value: $width, format: .number).keyboardType(.decimalPad).multilineTextAlignment(.trailing)
                        }
                        LabeledContent("Height") {
                            TextField("Height", value: $height, format: .number).keyboardType(.decimalPad).multilineTextAlignment(.trailing)
                        }
                    }
                    Picker("Orientation", selection: $landscape) {
                        Text("Portrait").tag(false)
                        Text("Landscape").tag(true)
                    }
                    .pickerStyle(.segmented)
                }
            }
            .navigationTitle("New project")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .cancellationAction) { Button("Cancel", action: onCancel) }
                ToolbarItem(placement: .confirmationAction) {
                    Button("Create") {
                        let trimmed = name.trimmingCharacters(in: .whitespaces)
                        onCreate(trimmed.isEmpty ? defaultName : trimmed, size)
                    }
                    .disabled(custom && (width <= 0 || height <= 0))
                }
            }
        }
        .environment(\.colorScheme, .dark)
    }
}

// MARK: - the app's root

/// The Gallery, or the open project's workspace. The project you had open
/// last opens again at launch, as the single session used to.
struct RootView: View {
    @State private var store = ProjectStore.shared
    @State private var open: OpenProject? = nil
    @AppStorage("lastProject") private var lastProject = ""
    @Environment(\.scenePhase) private var scenePhase

    struct OpenProject {
        let id: UUID
        let session: TransferSession
        let history: History
    }

    var body: some View {
        Group {
            if let open, let info = store.info(open.id) {
                WorkspaceView(projectName: info.name) { close() }
                    .environment(open.session)
                    .environment(open.history)
                    .autosaves(open.session, to: store.folder(open.id)) {
                        store.touched(open.id, canvasSize: open.session.canvasSize)
                    }
                    .recordsHistory(of: open.session, in: open.history)
                    .id(open.id)
            } else {
                GalleryView(store: store) { openProject($0) }
            }
        }
        .onAppear {
            if open == nil, let id = UUID(uuidString: lastProject), store.info(id) != nil { openProject(id) }
        }
        .onChange(of: scenePhase) { _, phase in
            // The Gallery's picture stays current even if the app is closed from here.
            if phase == .background, let open { store.saveThumbnail(open.id, session: open.session) }
        }
    }

    private func openProject(_ id: UUID) {
        let session = SessionStore.load(from: store.folder(id))
        open = OpenProject(id: id, session: session, history: History(session))
        lastProject = id.uuidString
    }

    private func close() {
        if let open { store.saveThumbnail(open.id, session: open.session) }
        open = nil
        lastProject = ""
    }
}
