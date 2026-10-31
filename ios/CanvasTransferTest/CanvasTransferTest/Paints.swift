import Foundation
import Observation

/// A paint from the prototype's library (Paint in canvastransfer/paints.py),
/// read from its paints.json. Only what mixing needs is kept.
struct Paint: Codable, Identifiable, Equatable {
    var id: String
    var medium: String
    var brand: String
    var name: String
    var pigments: [String] = []
    var lab: [Double]? = nil  // CIELAB D50 of the masstone; nil = no color data
    var strength: Double = 1  // tinting strength: 3 = one part does what three parts of an average paint do
    var favorite: Bool = false
    var enabled: Bool = true  // offered in matches and mixes
    var standIn: String? = nil  // nil: automatic, "": none, else a paint id

    enum CodingKeys: String, CodingKey {
        case id, medium, brand, name, pigments, lab, strength, favorite, enabled
        case standIn = "stand_in"
    }

    init(id: String, medium: String, brand: String, name: String, lab: [Double]?) {
        self.id = id; self.medium = medium; self.brand = brand; self.name = name; self.lab = lab
    }

    // Tolerant: the prototype's file has more fields, and older ones fewer.
    init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        id = try c.decode(String.self, forKey: .id)
        medium = (try? c.decode(String.self, forKey: .medium)) ?? ""
        brand = (try? c.decode(String.self, forKey: .brand)) ?? ""
        name = (try? c.decode(String.self, forKey: .name)) ?? id
        pigments = (try? c.decode([String].self, forKey: .pigments)) ?? []
        lab = (try? c.decodeIfPresent([Double].self, forKey: .lab)).flatMap { $0?.count == 3 ? $0 : nil }
        strength = (try? c.decode(Double.self, forKey: .strength)) ?? 1
        favorite = (try? c.decode(Bool.self, forKey: .favorite)) ?? false
        enabled = (try? c.decode(Bool.self, forKey: .enabled)) ?? true
        standIn = try? c.decodeIfPresent(String.self, forKey: .standIn)
    }

    /// Every pigment a white (PW…).
    var isWhite: Bool { !pigments.isEmpty && pigments.allSatisfy { $0.uppercased().hasPrefix("PW") } }
    var pigmentSet: Set<String> { Set(pigments.map { $0.uppercased() }) }
}

struct Palette: Codable, Identifiable, Equatable {
    var id: String
    var name: String
    var medium: String
    var paintIDs: [String]

    enum CodingKeys: String, CodingKey {
        case id, name, medium
        case paintIDs = "paint_ids"
    }
}

/// Your paints and palettes. The prototype's paints.json comes with the app;
/// Import paints… replaces it with a newer one, kept in Application Support.
@Observable
final class PaintLibrary {
    static let shared = PaintLibrary()

    private(set) var paints: [Paint] = []
    private(set) var palettes: [Palette] = []
    private(set) var origin = ""  // where they came from, for the panel
    @ObservationIgnored private var colors: [String: [Double]] = [:]  // own or stand-in Lab, by paint id
    @ObservationIgnored private var standIns: [String: Paint] = [:]

    private struct File: Codable {
        var paints: [Paint]
        var palettes: [Palette]?
    }

    private static var importedURL: URL {
        URL.applicationSupportDirectory.appending(path: "paints.json")
    }

    private init() {
        if let data = try? Data(contentsOf: Self.importedURL), load(data) {
            origin = "Imported"
        } else if let url = Bundle.main.url(forResource: "paints", withExtension: "json"),
                  let data = try? Data(contentsOf: url), load(data) {
            origin = "From the prototype (Oct 30)"
        }
    }

    /// Reads a prototype paints.json; keeps it for next time. Throws if it isn't one.
    func importFile(at url: URL) throws {
        let access = url.startAccessingSecurityScopedResource()
        defer { if access { url.stopAccessingSecurityScopedResource() } }
        let data = try Data(contentsOf: url)
        guard load(data) else { throw CocoaError(.fileReadCorruptFile) }
        try FileManager.default.createDirectory(at: URL.applicationSupportDirectory, withIntermediateDirectories: true)
        try data.write(to: Self.importedURL, options: .atomic)
        origin = "Imported \(Date().formatted(date: .abbreviated, time: .shortened))"
    }

    @discardableResult
    private func load(_ data: Data) -> Bool {
        guard let file = try? JSONDecoder().decode(File.self, from: data), !file.paints.isEmpty else { return false }
        paints = file.paints
        palettes = file.palettes ?? []
        standIns = [:]
        colors = [:]
        for paint in paints {
            if let lab = paint.lab {
                colors[paint.id] = lab
            } else if let stand = standIn(for: paint), let lab = stand.lab {
                standIns[paint.id] = stand
                colors[paint.id] = lab
            }
        }
        return true
    }

    func paint(_ id: String) -> Paint? { paints.first { $0.id == id } }

    /// The paint's own Lab (D50), or its stand-in's; nil if it has neither.
    func color(of paint: Paint) -> [Double]? { colors[paint.id] }

    /// The paint whose color a paint without color data borrows.
    func standInUsed(for paint: Paint) -> Paint? { standIns[paint.id] }

    var media: [String] {
        let order = ["oil", "watercolor", "acrylic", "gouache"]
        return Set(paints.map(\.medium)).sorted { (order.firstIndex(of: $0) ?? 9, $0) < (order.firstIndex(of: $1) ?? 9, $1) }
    }

    func paints(of palette: Palette) -> [Paint] { palette.paintIDs.compactMap(paint) }

    /// Whites to lighten with, in the prototype's order: the selection's own
    /// first, then favorites, then titanium, then by name.
    func whites(medium: String, selection: [Paint]) -> [Paint] {
        let chosen = Set(selection.map(\.id))
        return paints.filter { $0.medium == medium && $0.isWhite && color(of: $0) != nil }
            .sorted { a, b in
                func key(_ p: Paint) -> (Int, Int, Int, String) {
                    (chosen.contains(p.id) ? 0 : 1, p.favorite ? 0 : 1, p.name.lowercased().contains("titanium") ? 0 : 1, p.name)
                }
                return key(a) < key(b)
            }
    }

    // MARK: what to mix from (the prototype's Mix from and Lighten with)

    /// One Mix from choice: your palettes, all your paints of a medium, or a
    /// classic palette filled from your paints.
    struct MixSource: Identifiable {
        var key: String  // "palette:<id>", "medium:<m>" or "template:<key>:<m>"
        var title: String
        var medium: String
        var paints: [Paint]
        var note = ""  // what a classic palette is, and what filled it
        var id: String { key }
    }

    func mixSources(favoritesOnly: Bool) -> [MixSource] {
        let mine = palettes.map {
            MixSource(key: "palette:\($0.id)", title: "\($0.name) (\($0.medium), \($0.paintIDs.count))", medium: $0.medium,
                      paints: paints(of: $0))
        }
        let all = media.map { m -> MixSource in
            let list = paints.filter { $0.medium == m && $0.enabled && ($0.favorite || !favoritesOnly) }
            let withColor = list.filter { color(of: $0) != nil }.count
            return MixSource(key: "medium:\(m)", title: "All \(m) paints\(favoritesOnly ? ", favorites" : "") (\(withColor) with color)",
                             medium: m, paints: list)
        }
        // Classic palettes need at least two roles filled to be worth offering.
        let classics = media.flatMap { m in
            ClassicPalettes.templates.compactMap { t -> MixSource? in
                let filled = ClassicPalettes.fill(t, library: self, medium: m)
                guard filled.filter({ $0.paint != nil }).count >= 2 else { return nil }
                let parts = filled.compactMap { f in f.paint.map { "\($0.name)\(f.substitute ? " (for \(f.role.name.lowercased()))" : "")" } }
                let empty = filled.filter { $0.paint == nil }.map { $0.role.name.lowercased() }
                var note = t.note + "\nYours: " + parts.joined(separator: ", ") + "."
                if !empty.isEmpty { note += " None of your paints fits: " + empty.joined(separator: ", ") + "." }
                return MixSource(key: "template:\(t.id):\(m)", title: "\(t.name) (classic, \(m))", medium: m,
                                 paints: filled.compactMap(\.paint), note: note)
            }
        }
        return mine + all + classics
    }

    /// The choice for `key`, or the first if it's gone.
    func mixSource(_ key: String, favoritesOnly: Bool) -> MixSource? {
        let all = mixSources(favoritesOnly: favoritesOnly)
        return all.first { $0.key == key } ?? all.first
    }

    /// What lightens the mixes: `choice` is a white's id, "water" or "none";
    /// otherwise a white (the selection's own first), or water for watercolor.
    func lightener(_ choice: String, for source: MixSource?) -> Paint? {
        guard let source else { return nil }
        let whites = whites(medium: source.medium, selection: source.paints)
        switch choice {
        case "none": return nil
        case "water": return Mixing.water
        default:
            if let chosen = whites.first(where: { $0.id == choice }) { return chosen }
            return source.medium == "watercolor" || whites.isEmpty ? Mixing.water : whites.first
        }
    }

    // MARK: stand-ins (stand_in_for and auto_stand_in in paints.py)

    private func standIn(for paint: Paint) -> Paint? {
        if paint.lab != nil || paint.standIn == "" { return nil }
        if let id = paint.standIn {  // chosen by hand: any medium
            return self.paint(id).flatMap { $0.lab != nil ? $0 : nil }
        }
        // Automatic, within the medium: the same pigments (closest name wins),
        // then a near-identical name, then a similar name sharing a pigment.
        let candidates = paints.filter { $0.medium == paint.medium && $0.lab != nil && $0.id != paint.id }
        guard !candidates.isEmpty else { return nil }
        let pigments = paint.pigmentSet
        let same = candidates.filter { !pigments.isEmpty && $0.pigmentSet == pigments }
        if !same.isEmpty {
            return same.max { Self.nameSimilarity(paint.name, $0.name) < Self.nameSimilarity(paint.name, $1.name) }
        }
        let scored = candidates.map { ($0, Self.nameSimilarity(paint.name, $0.name), pigments.intersection($0.pigmentSet).count) }
        let good = scored.filter { $0.1 >= 0.8 || ($0.1 >= 0.6 && $0.2 > 0) }
        return good.max { ($0.1, $0.2) < ($1.1, $1.2) }?.0
    }

    private static let nameNoise: Set<String> = ["de", "extra", "genuine", "of", "the", "no", "hue", "mars"]

    /// 0...1: the share of words two names have in common, allowing small
    /// spelling differences ("Caput Mortum" ~ "Caput Mortuum").
    static func nameSimilarity(_ a: String, _ b: String) -> Double {
        let ta = tokens(a), tb = tokens(b)
        guard !ta.isEmpty, !tb.isEmpty else { return 0 }
        var unmatched = tb, matched = 0
        for w in ta {
            guard let best = unmatched.indices.max(by: { ratio(w, unmatched[$0]) < ratio(w, unmatched[$1]) }) else { continue }
            if ratio(w, unmatched[best]) >= 0.8 {
                matched += 1
                unmatched.remove(at: best)
            }
        }
        return 2 * Double(matched) / Double(ta.count + tb.count)
    }

    private static func tokens(_ name: String) -> [String] {
        var words: [String] = [], word = ""
        for ch in name.lowercased() {
            if ("a"..."z").contains(ch) || ("à"..."ÿ").contains(ch) { word.append(ch) } else if !word.isEmpty {
                words.append(word); word = ""
            }
        }
        if !word.isEmpty { words.append(word) }
        return words.filter { !nameNoise.contains($0) }
    }

    /// difflib.SequenceMatcher(None, a, b).ratio(): 2 × matching characters / total.
    static func ratio(_ a: String, _ b: String) -> Double {
        let x = Array(a), y = Array(b)
        guard !x.isEmpty || !y.isEmpty else { return 1 }
        return 2 * Double(matches(x, 0, x.count, y, 0, y.count)) / Double(x.count + y.count)
    }

    /// Characters in the longest common block, then recursively left and right of it (Ratcliff/Obershelp).
    private static func matches(_ a: [Character], _ alo: Int, _ ahi: Int, _ b: [Character], _ blo: Int, _ bhi: Int) -> Int {
        var bestI = alo, bestJ = blo, bestSize = 0
        var lengths = [Int](repeating: 0, count: bhi - blo + 1)
        for i in alo..<ahi {
            var next = [Int](repeating: 0, count: bhi - blo + 1)
            for j in blo..<bhi where a[i] == b[j] {
                let k = lengths[j - blo] + 1
                next[j - blo + 1] = k
                if k > bestSize { bestI = i - k + 1; bestJ = j - k + 1; bestSize = k }
            }
            lengths = next
        }
        guard bestSize > 0 else { return 0 }
        return bestSize + matches(a, alo, bestI, b, blo, bestJ) + matches(a, bestI + bestSize, ahi, b, bestJ + bestSize, bhi)
    }
}
