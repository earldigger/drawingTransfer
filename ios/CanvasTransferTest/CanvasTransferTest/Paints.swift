import Foundation
import Observation

/// Any JSON value, kept as it was read: the paint's `site` record.
indirect enum JSONValue: Codable, Equatable {
    case string(String), number(Double), bool(Bool), array([JSONValue]), object([String: JSONValue]), null

    init(from decoder: Decoder) throws {
        let c = try decoder.singleValueContainer()
        if c.decodeNil() { self = .null }
        else if let v = try? c.decode(Bool.self) { self = .bool(v) }
        else if let v = try? c.decode(Double.self) { self = .number(v) }
        else if let v = try? c.decode(String.self) { self = .string(v) }
        else if let v = try? c.decode([JSONValue].self) { self = .array(v) }
        else { self = .object(try c.decode([String: JSONValue].self)) }
    }

    func encode(to encoder: Encoder) throws {
        var c = encoder.singleValueContainer()
        switch self {
        case .string(let v): try c.encode(v)
        case .number(let v): try c.encode(v)
        case .bool(let v): try c.encode(v)
        case .array(let v): try c.encode(v)
        case .object(let v): try c.encode(v)
        case .null: try c.encodeNil()
        }
    }

    var string: String? { if case .string(let v) = self { v } else { nil } }
    var strings: [String]? { if case .array(let v) = self { v.compactMap(\.string) } else { nil } }
    var numbers: [Double]? {
        if case .array(let v) = self { v.compactMap { if case .number(let n) = $0 { n } else { nil } } } else { nil }
    }
}

/// A paint from the prototype's library (Paint in canvastransfer/paints.py),
/// with every field its paints.json has, so editing here keeps them all.
struct Paint: Codable, Identifiable, Equatable {
    var id: String
    var medium: String
    var brand: String
    var name: String
    var code = ""  // the maker's catalog number
    var series = ""  // the maker's price series
    var pigments: [String] = []
    var opacity = ""  // "T", "ST", "SO", "O" or ""
    var lightfastness = ""  // as the site shows it: "ASTM I", "I", or stars "★★★"
    var lab: [Double]? = nil  // CIELAB D50 of the masstone; nil = no color data
    var source = ""  // where the color came from: "Chart", "Entered by hand", …
    var url = ""
    var drying = ""
    var strength: Double = 1  // tinting strength: 3 = one part does what three parts of an average paint do
    var favorite: Bool = false
    var enabled: Bool = true  // offered in matches and mixes
    var standIn: String? = nil  // nil: automatic, "": none, else a paint id
    var edited: [String] = []  // site fields changed by hand
    var site: [String: JSONValue] = [:]  // the site's values at the last import

    /// Fields the editor can change that come from the site (EDITABLE_FIELDS).
    static let siteFields = ["medium", "brand", "name", "series", "pigments", "opacity", "lightfastness", "lab"]
    static let opacityLabels = ["T": "Transparent", "ST": "Semi-Transparent", "SO": "Semi-Opaque", "O": "Opaque"]

    enum CodingKeys: String, CodingKey {
        case id, medium, brand, name, code, series, pigments, opacity, lightfastness, lab, source, url, drying
        case strength, favorite, enabled, edited, site
        case standIn = "stand_in"
    }

    init(id: String, medium: String, brand: String, name: String, lab: [Double]?) {
        self.id = id; self.medium = medium; self.brand = brand; self.name = name; self.lab = lab
    }

    // Tolerant: older files have fewer fields.
    init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        func string(_ k: CodingKeys) -> String { (try? c.decode(String.self, forKey: k)) ?? "" }
        id = try c.decode(String.self, forKey: .id)
        medium = string(.medium); brand = string(.brand); name = (try? c.decode(String.self, forKey: .name)) ?? id
        code = string(.code); series = string(.series); opacity = string(.opacity); lightfastness = string(.lightfastness)
        source = string(.source); url = string(.url); drying = string(.drying)
        pigments = (try? c.decode([String].self, forKey: .pigments)) ?? []
        lab = (try? c.decodeIfPresent([Double].self, forKey: .lab)).flatMap { $0?.count == 3 ? $0 : nil }
        strength = (try? c.decode(Double.self, forKey: .strength)) ?? 1
        favorite = (try? c.decode(Bool.self, forKey: .favorite)) ?? false
        enabled = (try? c.decode(Bool.self, forKey: .enabled)) ?? true
        standIn = try? c.decodeIfPresent(String.self, forKey: .standIn)
        edited = (try? c.decode([String].self, forKey: .edited)) ?? []
        site = (try? c.decode([String: JSONValue].self, forKey: .site)) ?? [:]
    }

    func encode(to encoder: Encoder) throws {
        var c = encoder.container(keyedBy: CodingKeys.self)
        try c.encode(id, forKey: .id); try c.encode(medium, forKey: .medium); try c.encode(brand, forKey: .brand)
        try c.encode(name, forKey: .name); try c.encode(code, forKey: .code); try c.encode(series, forKey: .series)
        try c.encode(pigments, forKey: .pigments); try c.encode(opacity, forKey: .opacity)
        try c.encode(lightfastness, forKey: .lightfastness)
        if let lab { try c.encode(lab, forKey: .lab) } else { try c.encodeNil(forKey: .lab) }
        try c.encode(source, forKey: .source); try c.encode(url, forKey: .url); try c.encode(drying, forKey: .drying)
        try c.encode(strength, forKey: .strength); try c.encode(favorite, forKey: .favorite)
        try c.encode(enabled, forKey: .enabled)
        if let standIn { try c.encode(standIn, forKey: .standIn) } else { try c.encodeNil(forKey: .standIn) }
        try c.encode(edited, forKey: .edited); try c.encode(site, forKey: .site)
    }

    /// Every pigment a white (PW…).
    var isWhite: Bool { !pigments.isEmpty && pigments.allSatisfy { $0.uppercased().hasPrefix("PW") } }
    var pigmentSet: Set<String> { Set(pigments.map { $0.uppercased() }) }
    var isManual: Bool { id.hasPrefix("manual-") }

    /// Notes which site fields now differ from the site's values (for ✎ and Revert).
    mutating func updateEdited() {
        guard !site.isEmpty else { return }
        edited = Self.siteFields.filter { field in
            guard let original = site[field] else { return false }
            switch field {
            case "medium": return original.string != medium
            case "brand": return original.string != brand
            case "name": return original.string != name
            case "series": return original.string != series
            case "opacity": return original.string != opacity
            case "lightfastness": return original.string != lightfastness
            case "pigments": return (original.strings ?? []) != pigments
            case "lab":
                let o = original.numbers, l = lab
                if o == nil || o?.count != 3 { return l != nil }
                guard let l else { return true }
                return zip(o!, l).contains { abs($0 - $1) > 0.0005 }
            default: return false
            }
        }
    }

    /// Back to the site's values for the site fields.
    mutating func revertToSite() {
        if let v = site["medium"]?.string { medium = v }
        if let v = site["brand"]?.string { brand = v }
        if let v = site["name"]?.string { name = v }
        if let v = site["series"]?.string { series = v }
        if let v = site["opacity"]?.string { opacity = v }
        if let v = site["lightfastness"]?.string { lightfastness = v }
        if let v = site["pigments"]?.strings { pigments = v }
        if let v = site["lab"] { lab = v.numbers.flatMap { $0.count == 3 ? $0 : nil } }
        edited = []
    }
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
    /// Strengths measured on the iPad, by paint id. They replace paints.json's
    /// strength in mixes, survive Import paints…, and are listed for copying
    /// into the prototype by hand (its paints.json is never written).
    private(set) var measured: [String: MeasuredStrength] = [:]
    private(set) var revision = 0  // changes whenever paints or strengths do, so mixes are found again
    @ObservationIgnored private var fileStrengths: [String: Double] = [:]  // paints.json's own values
    @ObservationIgnored private var colors: [String: [Double]] = [:]  // own or stand-in Lab, by paint id
    @ObservationIgnored private var standIns: [String: Paint] = [:]

    private struct File: Codable {
        var version: Int? = 1
        var paints: [Paint]
        var palettes: [Palette]?
    }

    /// The library as edited in the Paint library, kept on the iPad in the
    /// prototype's format (so it can go back to the Mac by hand). Strengths
    /// measured here are now part of the paints themselves.
    func replace(paints newPaints: [Paint], palettes newPalettes: [Palette]) throws {
        let encoder = JSONEncoder()
        encoder.outputFormatting = [.prettyPrinted, .sortedKeys]
        let data = try encoder.encode(File(version: 1, paints: newPaints, palettes: newPalettes))
        try FileManager.default.createDirectory(at: URL.applicationSupportDirectory, withIntermediateDirectories: true)
        try data.write(to: Self.importedURL, options: .atomic)
        measured = [:]
        try? FileManager.default.removeItem(at: Self.strengthsURL)
        load(data)
        origin = "Edited on the iPad \(Date().formatted(date: .abbreviated, time: .shortened))"
    }

    private static var importedURL: URL {
        URL.applicationSupportDirectory.appending(path: "paints.json")
    }

    private static var strengthsURL: URL {
        URL.applicationSupportDirectory.appending(path: "measured-strengths.json")
    }

    private init() {
        if let data = try? Data(contentsOf: Self.strengthsURL),
           let saved = try? JSONDecoder().decode([String: MeasuredStrength].self, from: data) {
            measured = saved
        }
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
        fileStrengths = Dictionary(file.paints.map { ($0.id, $0.strength) }, uniquingKeysWith: { a, _ in a })
        paints = file.paints.map { paint in
            var p = paint
            if let m = measured[p.id] { p.strength = m.strength }
            return p
        }
        revision += 1
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

    /// paints.json's strength for a paint, before any measured on the iPad.
    func fileStrength(of paint: Paint) -> Double { fileStrengths[paint.id] ?? 1 }

    /// Uses a strength measured on the iPad for this paint from now on.
    func setMeasured(_ m: MeasuredStrength, for paintID: String) {
        measured[paintID] = m
        applyMeasured()
    }

    /// Back to paints.json's strength.
    func removeMeasured(for paintID: String) {
        measured[paintID] = nil
        applyMeasured()
    }

    private func applyMeasured() {
        paints = paints.map { paint in
            var p = paint
            p.strength = measured[p.id]?.strength ?? fileStrengths[p.id] ?? 1
            return p
        }
        revision += 1
        if let data = try? JSONEncoder().encode(measured) {
            try? FileManager.default.createDirectory(at: URL.applicationSupportDirectory, withIntermediateDirectories: true)
            try? data.write(to: Self.strengthsURL, options: .atomic)
        }
    }

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

    private func standIn(for paint: Paint) -> Paint? { Self.standIn(for: paint, among: paints) }

    /// The paint whose color `paint` borrows, chosen from `paints`: by hand,
    /// or automatically. Works on any list, so the editor can show it live.
    static func standIn(for paint: Paint, among paints: [Paint]) -> Paint? {
        if paint.lab != nil || paint.standIn == "" { return nil }
        if let id = paint.standIn {  // chosen by hand: any medium
            return paints.first { $0.id == id }.flatMap { $0.lab != nil ? $0 : nil }
        }
        return autoStandIn(for: paint, among: paints)
    }

    /// Automatic, within the medium: the same pigments (closest name wins),
    /// then a near-identical name, then a similar name sharing a pigment.
    static func autoStandIn(for paint: Paint, among paints: [Paint]) -> Paint? {
        let candidates = paints.filter { $0.medium == paint.medium && $0.lab != nil && $0.id != paint.id }
        guard !candidates.isEmpty else { return nil }
        let pigments = paint.pigmentSet
        let same = candidates.filter { !pigments.isEmpty && $0.pigmentSet == pigments }
        if !same.isEmpty {
            return same.max { nameSimilarity(paint.name, $0.name) < nameSimilarity(paint.name, $1.name) }
        }
        let scored = candidates.map { ($0, nameSimilarity(paint.name, $0.name), pigments.intersection($0.pigmentSet).count) }
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
