import Foundation

/// Classic limited palettes, described by role ("yellow ochre", "a cool red")
/// and filled from the paints you own (the prototype's palettes.py). Each
/// role lists the pigments and name words that fit it, plus fallback pigments
/// for a modern substitute (cadmium or pyrrole red for vermilion, titanium
/// for lead white). A role with no fitting paint stays empty. The palettes
/// are traditions rather than exact historical inventories; see each note.
enum ClassicPalettes {
    struct Role {
        var name: String
        var pigments: Set<String>
        var words: [String] = []
        var fallback: Set<String> = []
        var prefer: [String] = []  // tie-breaking name words, e.g. "scarlet" for a warm red

        init(_ name: String, _ pigments: String, _ words: String = "", _ fallback: String = "", prefer: String = "") {
            func set(_ s: String) -> Set<String> { Set(s.split(separator: ",").map { $0.trimmingCharacters(in: .whitespaces).uppercased() }.filter { !$0.isEmpty }) }
            func list(_ s: String) -> [String] { s.split(separator: ",").map { $0.trimmingCharacters(in: .whitespaces) }.filter { !$0.isEmpty } }
            self.name = name
            self.pigments = set(pigments)
            self.words = list(words)
            self.fallback = set(fallback)
            self.prefer = list(prefer)
        }
    }

    struct Template: Identifiable {
        var id: String  // the prototype's key
        var name: String
        var note: String
        var roles: [Role]
    }

    struct Filled {
        var role: Role
        var paint: Paint?
        var substitute = false  // a fallback pigment, e.g. cadmium red for vermilion
    }

    static let leadWhite = Role("Lead white", "PW1", "lead white, flake white, cremnitz", "PW6, PW4, PW5")
    static let titaniumWhite = Role("White", "PW6", "titanium white", "PW1, PW4, PW5")
    static let yellowOchre = Role("Yellow ochre", "PY43, PY42", "yellow ochre")
    static let vermilion = Role("Vermilion", "PR106", "vermilion, vermillion", "PR108, PR255, PR254")
    static let ivoryBlack = Role("Ivory black", "PBK9", "ivory black, bone black", "PBK8, PBK11, PBK6")
    static let redEarth = Role("Red earth", "PR101, PR102", "english red, light red, venetian red, indian red, red ochre")
    static let alizarin = Role("Alizarin crimson / madder", "PR83", "alizarin, madder, crimson", "PR177, PV19, PR264, PR176")
    static let cadmiumYellow = Role("Cadmium yellow", "PY35, PY37", "cadmium yellow")
    static let viridian = Role("Viridian", "PG18", "viridian")
    static let cobaltBlue = Role("Cobalt blue", "PB28", "cobalt blue")
    static let ultramarine = Role("Ultramarine", "PB29", "ultramarine")
    static let burntUmber = Role("Burnt umber", "PBR7", "burnt umber, raw umber, umber")

    static let templates: [Template] = [
        Template(id: "zorn", name: "Zorn",
                 note: "Anders Zorn's well-known four colors: lead white, yellow ochre, vermilion and ivory black. His surviving palettes show he added other colors at times.",
                 roles: [leadWhite, yellowOchre, vermilion, ivoryBlack]),
        Template(id: "sargent", name: "Sargent (as commonly cited)",
                 note: "The colors usually given for John Singer Sargent. Published lists vary and are poorly sourced; pigment studies of his work confirm vermilion, red lake, ochres, cobalt, ultramarine and lead white.",
                 roles: [leadWhite, ivoryBlack, vermilion, alizarin, redEarth, yellowOchre, cadmiumYellow, viridian, cobaltBlue, ultramarine]),
        Template(id: "classical", name: "Classical four-color",
                 note: "White, yellow ochre, red earth and black: the four-color palette Pliny credits to the ancient Greek painters. Cool notes come from black against the warm earths.",
                 roles: [leadWhite, yellowOchre, redEarth, ivoryBlack]),
        Template(id: "triad", name: "Primary triad", note: "One yellow, one crimson and one blue plus white.",
                 roles: [titaniumWhite, Role("Yellow", "PY35, PY37, PY3, PY74, PY65, PY184", "cadmium yellow, lemon, hansa"),
                         Role("Crimson", "PR83, PR177, PV19, PR122, PR202, PR264", "alizarin, crimson, quinacridone, magenta, rose", "PR108, PR255"),
                         ultramarine]),
        Template(id: "split", name: "Split primary", note: "A warm and a cool version of each primary, plus white.",
                 roles: [titaniumWhite,
                         Role("Cool yellow", "PY35, PY3, PY175, PY184", "lemon, primrose"),
                         Role("Warm yellow", "PY35, PY37, PY65, PY110, PY83", "deep, medium, orange"),
                         Role("Warm red", "PR108, PR255, PR254, PR106", "cadmium red, vermilion, scarlet, pyrrole", prefer: "scarlet, light, medium"),
                         Role("Cool red", "PR83, PR177, PV19, PR122, PR202, PR264", "alizarin, crimson, quinacridone, magenta"),
                         Role("Warm blue", "PB29", "ultramarine"),
                         Role("Cool blue", "PB15, PB15:1, PB15:3, PB15:4, PB27", "phthalo, prussian", "PB35, PB36")]),
        Template(id: "earth", name: "Earth palette", note: "Earths with ultramarine and black: low chroma, very harmonious.",
                 roles: [titaniumWhite, yellowOchre, redEarth, burntUmber, ultramarine, ivoryBlack]),
    ]

    /// (score, is a substitute); 0 means the paint doesn't fit the role.
    private static func score(_ r: Role, _ paint: Paint) -> (Double, Bool) {
        let pig = paint.pigmentSet, name = paint.name.lowercased()
        var score = 0.0
        if !pig.isEmpty && pig.isSubset(of: r.pigments) { score += 3 } else if !pig.isDisjoint(with: r.pigments) { score += 1 }
        if r.words.contains(where: { name.contains($0) }) { score += 3 }
        var substitute = false
        if score < 3 && !pig.isEmpty && pig.isSubset(of: r.fallback) { score = 2; substitute = true }
        if score < 2 { return (0, false) }
        score += r.prefer.contains(where: { name.contains($0) }) ? 1 : 0
        return (score + (paint.lab != nil ? 0.5 : 0) + (paint.favorite ? 0.25 : 0), substitute)
    }

    /// Each role filled with the best-fitting paint you own in `medium` that
    /// has color data and is enabled; no paint is used twice.
    static func fill(_ t: Template, library: PaintLibrary, medium: String) -> [Filled] {
        let candidates = library.paints.filter { $0.medium == medium && $0.enabled && library.color(of: $0) != nil }
        var used = Set<String>()
        return t.roles.map { role in
            var best: (score: Double, sub: Bool, paint: Paint)? = nil
            for p in candidates where !used.contains(p.id) {
                let (s, sub) = score(role, p)
                if s > 0 && s > (best?.score ?? 0) { best = (s, sub, p) }  // the first of equals wins, as in max()
            }
            guard let best else { return Filled(role: role, paint: nil) }
            used.insert(best.paint.id)
            return Filled(role: role, paint: best.paint, substitute: best.sub)
        }
    }
}
