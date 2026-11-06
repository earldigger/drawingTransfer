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

/// The paintings, each a folder named <id>.ctproj (the iPad's own layout,
/// not the prototype's .ctproj): project.json, thumbnail.jpg, and the
/// session's files. They're kept on this iPad (Application Support/Projects)
/// or in a folder you choose in Files, such as one in iCloud Drive, which
/// iCloud then syncs; that needs no iCloud entitlement, so it works with a
/// free developer account.
@Observable
final class ProjectStore {
    static let shared = ProjectStore()

    private(set) var projects: [ProjectInfo] = []  // most recently changed first
    private(set) var thumbnails: [UUID: UIImage] = [:]
    private(set) var root: URL = ProjectStore.localRoot
    private(set) var folderName: String? = nil  // the chosen folder; nil = on this iPad
    private(set) var storageProblem: String? = nil
    private(set) var downloading = 0  // project files iCloud is still bringing down

    static let localRoot = URL.applicationSupportDirectory.appending(path: "Projects", directoryHint: .isDirectory)
    private static let bookmarkKey = "projectsFolderBookmark"

    func folder(_ id: UUID) -> URL { root.appending(path: "\(id.uuidString).ctproj", directoryHint: .isDirectory) }
    private func infoURL(_ id: UUID) -> URL { folder(id).appending(path: "project.json") }
    private func thumbnailURL(_ id: UUID) -> URL { folder(id).appending(path: "thumbnail.jpg") }

    private init() {
        try? FileManager.default.createDirectory(at: Self.localRoot, withIntermediateDirectories: true)
        openChosenFolder()
        moveOldSession()
        reload()
    }

    func info(_ id: UUID) -> ProjectInfo? { projects.first { $0.id == id } }

    /// Reads the projects again, e.g. after iCloud brought changes from elsewhere.
    func refresh() { reload() }

    private func reload() {
        let files = FileManager.default
        let names = (try? files.contentsOfDirectory(atPath: root.path)) ?? []
        var waiting = 0
        projects = names.filter { $0.hasSuffix(".ctproj") }.compactMap { name in
            let folder = root.appending(path: name, directoryHint: .isDirectory)
            let url = folder.appending(path: "project.json")
            if !files.fileExists(atPath: url.path) {  // in iCloud, not on this iPad yet
                if Self.startDownload(url) { waiting += 1 }
                return nil
            }
            return (try? Data(contentsOf: url)).flatMap { try? JSONDecoder().decode(ProjectInfo.self, from: $0) }
        }
        .sorted { $0.modified > $1.modified }
        for p in projects {
            let url = thumbnailURL(p.id)
            if !files.fileExists(atPath: url.path) {
                Self.startDownload(url)
            } else if thumbnails[p.id] == nil {
                thumbnails[p.id] = UIImage(contentsOfFile: url.path)
            }
        }
        downloading = waiting
        if waiting > 0 {  // look again once iCloud has had a moment
            DispatchQueue.main.asyncAfter(deadline: .now() + 2) { [weak self] in self?.reload() }
        }
    }

    // MARK: where the projects are kept

    /// Opens the folder chosen before, if it can still be reached; otherwise the iPad's.
    private func openChosenFolder() {
        guard let bookmark = UserDefaults.standard.data(forKey: Self.bookmarkKey) else { return }
        var stale = false
        guard let url = try? URL(resolvingBookmarkData: bookmark, bookmarkDataIsStale: &stale),
              url.startAccessingSecurityScopedResource()  // kept for as long as the app runs
        else {
            storageProblem = "Couldn't reach your projects folder, so projects on this \(Theme.device) are shown. Choose the folder again."
            projectLog.error("Couldn't open the chosen projects folder")
            return
        }
        if stale, let fresh = try? url.bookmarkData() {
            UserDefaults.standard.set(fresh, forKey: Self.bookmarkKey)
        }
        root = url
        folderName = url.lastPathComponent
    }

    /// Keeps projects in `url` (a folder picked in Files) from now on. With
    /// `moving`, the projects on this iPad are moved into it, after any saves.
    func useFolder(_ url: URL, moving: Bool) throws {
        guard url.startAccessingSecurityScopedResource() else { throw CocoaError(.fileReadNoPermission) }
        let bookmark = try url.bookmarkData()
        UserDefaults.standard.set(bookmark, forKey: Self.bookmarkKey)
        let local = Self.localRoot
        root = url
        folderName = url.lastPathComponent
        storageProblem = nil
        thumbnails = [:]
        if moving {
            SessionStore.afterSaves { [weak self] in
                Self.move(from: local, to: url)
                DispatchQueue.main.async { self?.reload() }
            }
        }
        reload()
    }

    /// Back to keeping projects on this iPad. The folder's projects stay where they are.
    func useThisIPad() {
        UserDefaults.standard.removeObject(forKey: Self.bookmarkKey)
        root = Self.localRoot
        folderName = nil
        storageProblem = nil
        thumbnails = [:]
        reload()
    }

    /// How many projects are on this iPad, for "Move them?"
    var localProjectCount: Int {
        ((try? FileManager.default.contentsOfDirectory(atPath: Self.localRoot.path)) ?? [])
            .filter { $0.hasSuffix(".ctproj") }.count
    }

    /// Each project folder from `from` into `to`, removed from `from` once copied.
    /// One already in `to` (the same id) is left alone, and so is the iPad's copy.
    private static func move(from: URL, to: URL) {
        let files = FileManager.default
        for name in ((try? files.contentsOfDirectory(atPath: from.path)) ?? []) where name.hasSuffix(".ctproj") {
            let source = from.appending(path: name), target = to.appending(path: name)
            guard !files.fileExists(atPath: target.path) else { continue }
            do {
                try files.copyItem(at: source, to: target)
                try files.removeItem(at: source)
            } catch {
                projectLog.error("Couldn't move \(name): \(error)")
            }
        }
    }

    /// Asks iCloud for a file that's only in the cloud so far. False if it isn't an iCloud file.
    @discardableResult
    private static func startDownload(_ url: URL) -> Bool {
        (try? FileManager.default.startDownloadingUbiquitousItem(at: url)) != nil
    }

    /// Waits until every file of a project is on this iPad (iCloud may have
    /// only placeholders, named ".<name>.icloud"), for up to `timeout` seconds.
    /// True when they're all here.
    func download(_ id: UUID, timeout: TimeInterval = 60) async -> Bool {
        let folder = folder(id), files = FileManager.default
        let deadline = Date().addingTimeInterval(timeout)
        while Date() < deadline {
            let names = (try? files.contentsOfDirectory(atPath: folder.path)) ?? []
            // Not here yet: a placeholder, or a file iCloud lists but hasn't downloaded.
            let missing = names.compactMap { name -> URL? in
                if name.hasPrefix(".") && name.hasSuffix(".icloud") {
                    return folder.appending(path: String(name.dropFirst().dropLast(".icloud".count)))
                }
                let url = folder.appending(path: name)
                let status = try? url.resourceValues(forKeys: [.ubiquitousItemDownloadingStatusKey]).ubiquitousItemDownloadingStatus
                return status == nil || status == .current ? nil : url
            }
            if missing.isEmpty && files.fileExists(atPath: folder.appending(path: "session.json").path) { return true }
            missing.forEach { Self.startDownload($0) }
            try? await Task.sleep(for: .milliseconds(500))
        }
        return false
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
    func create(name: String, canvasSize: CGSize, background: CanvasBackground) -> ProjectInfo {
        let info = ProjectInfo(id: UUID(), name: name, created: Date(), modified: Date(), canvasSize: canvasSize)
        write(info)
        let session = TransferSession()
        session.canvasSize = canvasSize
        session.background = background
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
        let renderer = ImageRenderer(content: CanvasContent(layers: session.layers, size: size,
                                                            background: session.background.color))
        renderer.scale = 2
        guard let image = renderer.uiImage else { return }
        thumbnails[id] = image
        try? image.jpegData(compressionQuality: 0.8)?.write(to: thumbnailURL(id), options: .atomic)
    }
}

// MARK: - sizes

/// How sizes are shown and typed. Sizes are kept in inches.
enum SizeUnit: String, CaseIterable, Codable, Identifiable {
    case inches, centimeters

    var id: String { rawValue }
    var title: String { self == .inches ? "Inches" : "Centimeters" }
    var symbol: String { self == .inches ? "in" : "cm" }
    var perInch: Double { self == .inches ? 1 : 2.54 }

    /// "16 x 20 in"
    func text(_ inches: CGSize) -> String {
        "\(Self.number(inches.width * perInch)) x \(Self.number(inches.height * perInch)) \(symbol)"
    }

    static func number(_ value: Double) -> String { value.formatted(.number.precision(.fractionLength(0...1))) }
}

/// A canvas size to start from: a standard one, one you saved, or a recent project's.
struct CanvasSizeChoice: Codable, Identifiable, Equatable {
    var id = UUID()
    var name: String
    var size: CGSize  // inches, as it should be (portrait or landscape)
    var unit = SizeUnit.inches
}

/// The sizes saved with "Save this size", kept on this iPad.
@Observable
final class SavedSizes {
    static let shared = SavedSizes()
    private static let key = "savedCanvasSizes"

    private(set) var sizes: [CanvasSizeChoice] = []

    /// The standard canvases, portrait.
    static let standard = TransferSession.canvasSizes.map {
        CanvasSizeChoice(name: "Canvas", size: $0)
    }

    private init() {
        if let data = UserDefaults.standard.data(forKey: Self.key),
           let saved = try? JSONDecoder().decode([CanvasSizeChoice].self, from: data) {
            sizes = saved
        }
    }

    func add(_ choice: CanvasSizeChoice) {
        sizes.insert(choice, at: 0)
        persist()
    }

    func rename(_ id: UUID, to name: String) {
        let name = name.trimmingCharacters(in: .whitespaces)
        guard !name.isEmpty, let i = sizes.firstIndex(where: { $0.id == id }) else { return }
        sizes[i].name = name
        persist()
    }

    func delete(_ id: UUID) {
        sizes.removeAll { $0.id == id }
        persist()
    }

    private func persist() {
        if let data = try? JSONEncoder().encode(sizes) { UserDefaults.standard.set(data, forKey: Self.key) }
    }
}

// MARK: - Gallery

/// The Gallery, laid out like a new-document screen: at the top, sizes to
/// start a painting from (Recent or Saved, and Custom size); tap one and the
/// New project panel opens on the right. Below, your paintings, the most
/// recent first; long-press one to rename, duplicate or delete it.
struct GalleryView: View {
    @Bindable var store: ProjectStore
    var onOpen: (UUID) -> Void

    enum Tab: String, CaseIterable, Identifiable {
        case recent = "Recent", saved = "Saved"
        var id: String { rawValue }
    }

    @State private var saved = SavedSizes.shared
    @State private var tab = Tab.saved
    @State private var draft: ProjectDraft? = nil
    @State private var renaming: ProjectInfo? = nil
    @State private var renamingSize: CanvasSizeChoice? = nil
    @State private var newName = ""
    @State private var deleting: ProjectInfo? = nil
    @State private var choosingFolder = false
    @State private var pickedFolder: URL? = nil  // asking whether to move the iPad's projects into it
    @State private var folderError: String? = nil

    private let columns = Theme.isPhone ? [GridItem(.adaptive(minimum: 150), spacing: 14)]  // two across
                                        : [GridItem(.adaptive(minimum: 200, maximum: 240), spacing: 24)]

    /// The sizes of your recent paintings, each once, newest first.
    private var recent: [CanvasSizeChoice] {
        var seen = Set<String>(), result: [CanvasSizeChoice] = []
        for p in store.projects {
            let key = "\(p.canvasSize.width)x\(p.canvasSize.height)"
            guard seen.insert(key).inserted else { continue }
            result.append(CanvasSizeChoice(id: p.id, name: p.name, size: p.canvasSize))
            if result.count == 8 { break }
        }
        return result
    }

    var body: some View {
        HStack(spacing: 0) {
            ScrollView {
                VStack(alignment: .leading, spacing: 36) {
                    header
                    sizesSection
                    projectsSection
                }
                .padding(.horizontal, Theme.isPhone ? 16 : 40)
                .padding(.vertical, Theme.isPhone ? 16 : 32)
            }
            if let current = draft, !Theme.isPhone {  // on the phone it's a sheet
                NewProjectPanel(draft: Binding(get: { draft ?? current }, set: { draft = $0 }),
                                onCreate: create, onClose: { withAnimation { draft = nil } })
                    .frame(width: 380)
                    .padding([.vertical, .trailing], 16)
                    .transition(.move(edge: .trailing))
            }
        }
        .background(Theme.background.ignoresSafeArea())
        .themed()
        .sheet(isPresented: Binding(get: { Theme.isPhone && draft != nil }, set: { if !$0 { draft = nil } })) {
            if let current = draft {
                NewProjectPanel(draft: Binding(get: { draft ?? current }, set: { draft = $0 }),
                                onCreate: create, onClose: { draft = nil })
                    .themed()
                    .presentationBackground(Theme.surface)
            }
        }
        .alert("Rename", isPresented: Binding(get: { renaming != nil }, set: { if !$0 { renaming = nil } })) {
            TextField("Name", text: $newName)
            Button("Cancel", role: .cancel) {}
            Button("Rename") { if let r = renaming { store.rename(r.id, to: newName) } }
        }
        .alert("Rename size", isPresented: Binding(get: { renamingSize != nil }, set: { if !$0 { renamingSize = nil } })) {
            TextField("Name", text: $newName)
            Button("Cancel", role: .cancel) {}
            Button("Rename") { if let r = renamingSize { saved.rename(r.id, to: newName) } }
        }
        .confirmationDialog("Delete \(deleting?.name ?? "this project")?",
                            isPresented: Binding(get: { deleting != nil }, set: { if !$0 { deleting = nil } }),
                            titleVisibility: .visible) {
            Button("Delete", role: .destructive) { if let d = deleting { store.delete(d.id) } }
        } message: {
            Text(store.folderName == nil ? "Its layers and swatches are deleted from this \(Theme.device)."
                                         : "Its layers and swatches are deleted from \(store.folderName ?? "the folder"), everywhere it syncs.")
        }
        .fileImporter(isPresented: $choosingFolder, allowedContentTypes: [.folder]) { result in
            guard case .success(let url) = result else { return }
            if store.folderName == nil && store.localProjectCount > 0 {
                pickedFolder = url  // ask first
            } else {
                use(url, moving: false)
            }
        }
        .confirmationDialog("Move your \(store.localProjectCount) projects to \(pickedFolder?.lastPathComponent ?? "the folder")?",
                            isPresented: Binding(get: { pickedFolder != nil }, set: { if !$0 { pickedFolder = nil } }),
                            titleVisibility: .visible) {
            Button("Move them") { if let url = pickedFolder { use(url, moving: true) } }
            Button("Leave them on this \(Theme.device)") { if let url = pickedFolder { use(url, moving: false) } }
        } message: {
            Text("Projects in an iCloud Drive folder sync through iCloud and show in Finder on your Mac.")
        }
        .alert("Couldn't use that folder", isPresented: Binding(get: { folderError != nil }, set: { if !$0 { folderError = nil } })) {
            Button("OK", role: .cancel) {}
        } message: { Text(folderError ?? "") }
        .onAppear { store.refresh() }
    }

    private func use(_ url: URL, moving: Bool) {
        do {
            try store.useFolder(url, moving: moving)
        } catch {
            folderError = error.localizedDescription
        }
    }

    private var header: some View {
        HStack(alignment: .top) {
            VStack(alignment: .leading, spacing: 6) {
                Text("Gallery").font(.largeTitle.weight(.bold))
                Text(store.projects.isEmpty ? "Let's start a painting" : "Pick up a painting, or start a new one")
                    .font(.callout).foregroundStyle(.secondary)
                if let problem = store.storageProblem {
                    Label(problem, systemImage: "exclamationmark.triangle").font(.callout).foregroundStyle(.orange)
                }
            }
            Spacer()
            storageMenu
        }
        .padding(.top, 8)
    }

    /// Where projects are kept: on this iPad, or a folder you chose (iCloud Drive syncs it).
    private var storageMenu: some View {
        Menu {
            Section(store.folderName.map { "Projects are in “\($0)”" } ?? "Projects are on this \(Theme.device)") {
                Button("Choose a folder…", systemImage: "folder") { choosingFolder = true }
                if store.folderName != nil {
                    Button("Keep projects on this \(Theme.device)", systemImage: Theme.isPhone ? "iphone" : "ipad") {
                        store.useThisIPad()
                    }
                }
                Button("Refresh", systemImage: "arrow.clockwise") { store.refresh() }
            }
        } label: {
            HStack(spacing: 8) {
                if store.downloading > 0 { ProgressView().controlSize(.small) }
                Image(systemName: store.folderName == nil ? (Theme.isPhone ? "iphone" : "ipad") : "folder")
                Text(store.folderName ?? "On this \(Theme.device)").lineLimit(1)
                Image(systemName: "chevron.down").font(.caption.weight(.semibold))
            }
            .padding(.horizontal, 14)
            .frame(height: 40)
            .background(Capsule().fill(Theme.surface))
        }
        .tint(.white)
        .accessibilityLabel("Where projects are kept")
    }

    // MARK: sizes

    private var sizesSection: some View {
        VStack(alignment: .leading, spacing: 18) {
            Text("New project").font(.title2.weight(.semibold))
            Picker("Sizes", selection: $tab) {
                ForEach(Tab.allCases) { Text($0.rawValue).tag($0) }
            }
            .pickerStyle(.segmented)
            .frame(width: 220)
            ScrollView(.horizontal, showsIndicators: false) {
                HStack(alignment: .top, spacing: 16) {
                    customCard
                    switch tab {
                    case .recent:
                        if recent.isEmpty {
                            Text("Sizes of the paintings you make show here.")
                                .font(.callout).foregroundStyle(.secondary)
                                .frame(height: Self.cardSize.height)
                        }
                        ForEach(recent) { choice in
                            sizeCard(choice) {
                                Button("Save this size", systemImage: "square.and.arrow.down") {
                                    saved.add(CanvasSizeChoice(name: choice.name, size: choice.size))
                                }
                            }
                        }
                    case .saved:
                        ForEach(saved.sizes) { choice in
                            sizeCard(choice) {
                                Button("Rename", systemImage: "pencil") { newName = choice.name; renamingSize = choice }
                                Button("Delete", systemImage: "trash", role: .destructive) { saved.delete(choice.id) }
                            }
                        }
                        ForEach(SavedSizes.standard) { choice in
                            sizeCard(choice) {
                                Button("Landscape", systemImage: "rectangle") {
                                    start(CanvasSizeChoice(name: choice.name,
                                                           size: CGSize(width: choice.size.height, height: choice.size.width)))
                                }
                            }
                        }
                    }
                }
                .padding(.vertical, 2)
            }
        }
    }

    private static let cardSize = CGSize(width: 168, height: 150)

    /// Custom size: a round sky-blue +, like the screenshots' add button.
    private var customCard: some View {
        let on = selected(nil)
        return Button { start(nil) } label: {
            VStack(alignment: .leading, spacing: 0) {
                Image(systemName: "plus")
                    .font(.system(size: 22, weight: .semibold))
                    .foregroundStyle(on ? Theme.accent : Theme.onAccent)
                    .frame(width: 48, height: 48)
                    .background(Circle().fill(on ? Color.white : Theme.accent))
                Spacer()
                Text("Custom size").font(.headline)
                Text("Any width and height").font(.caption).opacity(0.7)
            }
            .sizeCardStyle(selected: on)
        }
        .buttonStyle(.plain)
    }

    /// A size card: its shape in a tile, its name with a ⌄ menu, and its
    /// dimensions. The chosen one is filled sky blue.
    private func sizeCard<Items: View>(_ choice: CanvasSizeChoice, @ViewBuilder menu: () -> Items) -> some View {
        let on = selected(choice.id)
        let fit = fitRect(choice.size, in: CGSize(width: 26, height: 26))
        return VStack(alignment: .leading, spacing: 0) {
            HStack(alignment: .top) {
                RoundedRectangle(cornerRadius: 3)
                    .fill(on ? Theme.accent : Color(white: 0.9))
                    .frame(width: fit.width, height: fit.height)
                    .frame(width: 48, height: 48)
                    .background(RoundedRectangle(cornerRadius: Theme.controlRadius, style: .continuous)
                        .fill(on ? Color.white : Theme.raised))
                Spacer()
                Menu {
                    menu()
                } label: {
                    Image(systemName: "chevron.down")
                        .font(.footnote.weight(.semibold))
                        .frame(width: 32, height: 32)
                        .contentShape(Rectangle())
                }
                .tint(on ? Theme.onAccent : Color.white)
                .accessibilityLabel("\(choice.name) options")
            }
            Spacer()
            Text(choice.name).font(.headline).lineLimit(1)
            Text(choice.unit.text(choice.size)).font(.caption).opacity(0.7)
        }
        .sizeCardStyle(selected: on)
        .contentShape(RoundedRectangle(cornerRadius: Theme.cardRadius))
        .onTapGesture { start(choice) }
        .accessibilityAddTraits(.isButton)
    }

    private func selected(_ id: UUID?) -> Bool {
        guard let draft else { return false }
        return draft.sourceID == id
    }

    /// Opens New project with a size, or (Custom size) the last one used.
    private func start(_ choice: CanvasSizeChoice?) {
        let size = choice?.size ?? store.projects.first?.canvasSize ?? CGSize(width: 16, height: 20)
        withAnimation {
            draft = ProjectDraft(size: size, unit: choice?.unit ?? draft?.unit ?? .inches, sourceID: choice?.id)
        }
    }

    private func create() {
        guard let draft, draft.isValid else { return }
        let name = draft.name.trimmingCharacters(in: .whitespaces)
        if draft.saveSize {
            saved.add(CanvasSizeChoice(name: "Saved \(saved.sizes.count + 1)", size: draft.inches, unit: draft.unit))
        }
        let info = store.create(name: name.isEmpty ? ProjectDraft.defaultName() : name,
                                canvasSize: draft.inches, background: draft.background)
        self.draft = nil
        onOpen(info.id)
    }

    // MARK: projects

    private var projectsSection: some View {
        VStack(alignment: .leading, spacing: 14) {
            Text("Your paintings").font(.title2.weight(.semibold))
            if store.projects.isEmpty {
                Text("None yet. Pick a size above to start one.").font(.callout).foregroundStyle(.secondary)
            }
            LazyVGrid(columns: columns, alignment: .leading, spacing: 24) {
                ForEach(store.projects) { project in card(project) }
            }
        }
    }

    /// A painting: its picture on a navy card, then its name, size and date.
    private func card(_ project: ProjectInfo) -> some View {
        Button { onOpen(project.id) } label: {
            VStack(alignment: .leading, spacing: 4) {
                ZStack {
                    if let thumb = store.thumbnails[project.id] {
                        Image(uiImage: thumb).resizable().scaledToFit()
                            .clipShape(RoundedRectangle(cornerRadius: 4))
                            .shadow(color: .black.opacity(0.4), radius: 6, y: 3)
                    } else {
                        let fit = fitRect(project.canvasSize, in: CGSize(width: 160, height: 170))
                        RoundedRectangle(cornerRadius: 4).fill(Color.white).frame(width: fit.width, height: fit.height)
                    }
                }
                .frame(maxWidth: .infinity)
                .frame(height: Theme.isPhone ? 140 : 180)
                .padding(.bottom, 10)
                Text(project.name).font(.headline).lineLimit(1)
                Text("\(SizeUnit.inches.text(project.canvasSize)) · "
                     + project.modified.formatted(date: .abbreviated, time: .omitted))
                    .font(.caption).foregroundStyle(.secondary)
            }
            .padding(16)
            .background(RoundedRectangle(cornerRadius: Theme.cardRadius, style: .continuous).fill(Theme.surface))
            .contentShape(RoundedRectangle(cornerRadius: Theme.cardRadius))
        }
        .buttonStyle(.plain)
        .contextMenu {
            Button("Rename", systemImage: "pencil") { newName = project.name; renaming = project }
            Button("Duplicate", systemImage: "plus.square.on.square") { store.duplicate(project.id) }
            Button("Delete", systemImage: "trash", role: .destructive) { deleting = project }
        }
    }
}

/// What New project will make. Width and height are in `unit`.
struct ProjectDraft: Equatable {
    var name = ProjectDraft.defaultName()
    var unit: SizeUnit
    var width: Double
    var height: Double
    var locked = false
    var background = CanvasBackground.white
    var saveSize = false
    var sourceID: UUID?  // the size card it came from; nil = Custom size

    static let maxInches = 120.0

    init(size: CGSize, unit: SizeUnit, sourceID: UUID?) {
        self.unit = unit
        width = Self.rounded(size.width * unit.perInch)
        height = Self.rounded(size.height * unit.perInch)
        self.sourceID = sourceID
    }

    static func defaultName() -> String { "Untitled - " + Date().formatted(date: .abbreviated, time: .shortened) }
    static func rounded(_ v: Double) -> Double { (v * 10).rounded() / 10 }

    var inches: CGSize { CGSize(width: width / unit.perInch, height: height / unit.perInch) }
    var landscape: Bool { width > height }
    var isValid: Bool {
        width > 0 && height > 0 && max(inches.width, inches.height) <= Self.maxInches
    }
}

/// The New project panel: name, unit, width and height (lockable),
/// orientation, background, and Save this size.
struct NewProjectPanel: View {
    @Binding var draft: ProjectDraft
    var onCreate: () -> Void
    var onClose: () -> Void

    var body: some View {
        VStack(alignment: .leading, spacing: 20) {
            HStack {
                Text("New project").font(.title3.weight(.semibold))
                Spacer()
                Button("Close", systemImage: "xmark", action: onClose)
                    .labelStyle(.iconOnly)
                    .font(.body.weight(.semibold))
                    .foregroundStyle(.white)
                    .frame(width: 36, height: 36)
                    .background(RoundedRectangle(cornerRadius: Theme.controlRadius, style: .continuous).fill(Theme.raised))
            }
            field("Name") {
                HStack(spacing: 8) {
                    TextField("Name", text: $draft.name, prompt: Text("Untitled"))
                    if !draft.name.isEmpty {
                        Button { draft.name = "" } label: {
                            Image(systemName: "xmark.circle.fill").foregroundStyle(.secondary)
                        }
                        .buttonStyle(.plain)
                        .accessibilityLabel("Clear name")
                    }
                }
                .boxed()
            }
            field("Unit") {
                Picker("Unit", selection: unit) {
                    ForEach(SizeUnit.allCases) { Text($0.title).tag($0) }
                }
                .pickerStyle(.menu)
                .frame(maxWidth: .infinity, alignment: .leading)
                .padding(.vertical, 3)
                .background(RoundedRectangle(cornerRadius: Theme.controlRadius, style: .continuous).fill(Theme.raised))
            }
            HStack(alignment: .bottom, spacing: 10) {
                field("Width") { number(width) }
                Button(draft.locked ? "Unlock proportions" : "Lock proportions",
                       systemImage: draft.locked ? "lock.fill" : "lock.open") { draft.locked.toggle() }
                    .labelStyle(.iconOnly)
                    .foregroundStyle(draft.locked ? Theme.accent : Color.secondary)
                    .frame(width: 30, height: 44)
                field("Height") { number(height) }
            }
            field("Orientation") {
                HStack(spacing: 12) {
                    orientation(landscape: false, icon: "rectangle.portrait")
                    orientation(landscape: true, icon: "rectangle")
                }
            }
            field("Background") {
                HStack {
                    Circle().fill(draft.background.color)
                        .overlay(Circle().strokeBorder(Color.gray, lineWidth: 1))
                        .frame(width: 20, height: 20)
                    Picker("Background", selection: $draft.background) {
                        ForEach(CanvasBackground.allCases) { Text($0.label).tag($0) }
                    }
                    .pickerStyle(.menu)
                    Spacer()
                }
                .padding(.leading, 12)
                .padding(.vertical, 3)
                .background(RoundedRectangle(cornerRadius: Theme.controlRadius, style: .continuous).fill(Theme.raised))
            }
            Toggle("Save this size", isOn: $draft.saveSize)
            if !draft.isValid {
                Text("Width and height must be more than 0 and at most \(SizeUnit.number(ProjectDraft.maxInches * draft.unit.perInch)) \(draft.unit.symbol).")
                    .font(.caption).foregroundStyle(.orange)
            }
            Spacer()
            Button(action: onCreate) {
                Text("Create project").font(.headline).frame(maxWidth: .infinity).padding(.vertical, 8)
            }
            .buttonStyle(.accent)
            .disabled(!draft.isValid)
        }
        .padding(24)
        .background(RoundedRectangle(cornerRadius: Theme.cardRadius, style: .continuous).fill(Theme.surface))
    }

    private func field<Content: View>(_ title: String, @ViewBuilder content: () -> Content) -> some View {
        VStack(alignment: .leading, spacing: 6) {
            Text(title).font(.caption).foregroundStyle(.secondary)
            content()
        }
    }

    private func number(_ value: Binding<Double>) -> some View {
        TextField("", value: value, format: .number.precision(.fractionLength(0...1)))
            .keyboardType(.decimalPad)
            .monospacedDigit()
            .boxed()
    }

    private func orientation(landscape: Bool, icon: String) -> some View {
        let on = draft.landscape == landscape
        return Button {
            if !on { (draft.width, draft.height) = (draft.height, draft.width) }
        } label: {
            Image(systemName: icon)
                .font(.title2)
                .foregroundStyle(on ? Theme.onAccent : Color.white)
                .frame(width: 64, height: 48)
                .background(RoundedRectangle(cornerRadius: Theme.controlRadius, style: .continuous)
                    .fill(on ? Theme.accent : Theme.raised))
        }
        .buttonStyle(.plain)
        .accessibilityLabel(landscape ? "Landscape" : "Portrait")
    }

    // Changing the unit converts the numbers; with the lock on, one side follows the other.

    private var unit: Binding<SizeUnit> {
        Binding(get: { draft.unit }, set: { new in
            let scale = new.perInch / draft.unit.perInch
            draft.width = ProjectDraft.rounded(draft.width * scale)
            draft.height = ProjectDraft.rounded(draft.height * scale)
            draft.unit = new
        })
    }

    private var width: Binding<Double> {
        Binding(get: { draft.width }, set: { new in
            if draft.locked, draft.width > 0 { draft.height = ProjectDraft.rounded(new * draft.height / draft.width) }
            draft.width = new
        })
    }

    private var height: Binding<Double> {
        Binding(get: { draft.height }, set: { new in
            if draft.locked, draft.height > 0 { draft.width = ProjectDraft.rounded(new * draft.width / draft.height) }
            draft.height = new
        })
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
    @State private var opening: UUID? = nil  // waiting for iCloud to bring its files down
    @State private var openFailed: String? = nil

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
                    .overlay {
                        if let opening, store.folderName != nil {  // on the iPad it opens at once
                            VStack(spacing: 12) {
                                ProgressView()
                                Text("Downloading \(store.info(opening)?.name ?? "the project") from iCloud…")
                            }
                            .padding(28)
                            .themedBar()
                            .themed()
                        }
                    }
                    .disabled(opening != nil)
            }
        }
        .onAppear {
            if open == nil, let id = UUID(uuidString: lastProject), store.info(id) != nil { openProject(id) }
        }
        .onChange(of: scenePhase) { _, phase in
            // The Gallery's picture stays current even if the app is closed from here.
            if phase == .background, let open { store.saveThumbnail(open.id, session: open.session) }
            if phase == .active, open == nil { store.refresh() }  // changes made elsewhere
        }
        .alert("Couldn't open the project", isPresented: Binding(get: { openFailed != nil }, set: { if !$0 { openFailed = nil } })) {
            Button("OK", role: .cancel) {}
        } message: { Text(openFailed ?? "") }
    }

    /// Opens a project once all its files are here; in an iCloud folder that
    /// may mean waiting for them to download.
    private func openProject(_ id: UUID) {
        guard opening == nil else { return }
        opening = id
        Task { @MainActor in
            let ready = await store.download(id)
            opening = nil
            guard ready else {
                openFailed = "Its files didn't arrive from iCloud. Check the connection and try again."
                return
            }
            let session = SessionStore.load(from: store.folder(id))
            open = OpenProject(id: id, session: session, history: History(session))
            lastProject = id.uuidString
        }
    }

    private func close() {
        if let open { store.saveThumbnail(open.id, session: open.session) }
        open = nil
        lastProject = ""
    }
}

