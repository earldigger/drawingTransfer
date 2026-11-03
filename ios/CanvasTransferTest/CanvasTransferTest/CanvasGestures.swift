import OSLog
import SwiftUI
import UIKit

/// Gesture starts and ends, and rejected values. Shown in Xcode's console.
let gestureLog = Logger(subsystem: "CanvasTransferTest", category: "gestures")

/// What the canvas gestures do. Each call gets the change since the last
/// call, so nothing is remembered from one gesture to the next.
struct CanvasGestureHandlers {
    var pan: (CGSize) -> Void  // points on screen
    var pinch: (CGFloat) -> Void  // scale factor
    var rotate: (Angle) -> Void
    var doubleTap: () -> Void
    var undo: () -> Void  // two-finger tap
    var redo: () -> Void  // three-finger tap
    var began: () -> Void  // the first of pan, pinch and twist started
    var ended: () -> Void  // the last finger lifted, or iPadOS cancelled the gesture
    /// Pick, while `picking`: one finger at a point (in this view), then
    /// `true` when it lifts there, or `false` if it was cancelled (a second
    /// finger came down to pan or zoom).
    var pick: (CGPoint, _ finished: Bool?) -> Void = { _, _ in }
}

/// Pan (one or two fingers), pinch and twist, all at once, with UIKit's
/// recognizers. SwiftUI's combined Drag + Magnify + Rotate gesture hung after
/// a pinch with the fingers close together (its rotation came back NaN, then
/// it stopped sending anything), and the canvas no longer answered touches.
/// UIKit's recognizers always report when they end or are cancelled.
///
/// While `picking`, one finger (or Pencil) picks instead of moving: it takes
/// two fingers to pan.
struct CanvasGestureView: UIViewRepresentable {
    var handlers: CanvasGestureHandlers
    var picking = false

    func makeCoordinator() -> Coordinator { Coordinator(handlers: handlers) }

    func makeUIView(context: Context) -> UIView {
        let view = UIView()
        view.backgroundColor = .clear
        let c = context.coordinator
        let pan = UIPanGestureRecognizer(target: c, action: #selector(Coordinator.pan(_:)))
        pan.maximumNumberOfTouches = 2
        let pinch = UIPinchGestureRecognizer(target: c, action: #selector(Coordinator.pinch(_:)))
        let rotate = UIRotationGestureRecognizer(target: c, action: #selector(Coordinator.rotate(_:)))
        let doubleTap = UITapGestureRecognizer(target: c, action: #selector(Coordinator.doubleTap(_:)))
        doubleTap.numberOfTapsRequired = 2
        // Undo and redo as in Procreate.
        let undoTap = UITapGestureRecognizer(target: c, action: #selector(Coordinator.undoTap(_:)))
        undoTap.numberOfTouchesRequired = 2
        let redoTap = UITapGestureRecognizer(target: c, action: #selector(Coordinator.redoTap(_:)))
        redoTap.numberOfTouchesRequired = 3
        // Pick: a touch tracker for exactly one finger, from the moment it lands.
        let pick = UILongPressGestureRecognizer(target: c, action: #selector(Coordinator.pick(_:)))
        pick.minimumPressDuration = 0
        pick.numberOfTouchesRequired = 1
        pick.allowableMovement = .greatestFiniteMagnitude
        pick.isEnabled = false
        c.continuous = Set([pan, pinch, rotate].map(ObjectIdentifier.init))
        c.panRecognizer = pan
        c.pickRecognizer = pick
        for recognizer in [pan, pinch, rotate, doubleTap, undoTap, redoTap, pick] {
            recognizer.delegate = c
            view.addGestureRecognizer(recognizer)
        }
        return view
    }

    func updateUIView(_ view: UIView, context: Context) {
        let c = context.coordinator
        c.handlers = handlers
        c.pickRecognizer?.isEnabled = picking
        c.panRecognizer?.minimumNumberOfTouches = picking ? 2 : 1  // one finger picks
    }

    final class Coordinator: NSObject, UIGestureRecognizerDelegate {
        var handlers: CanvasGestureHandlers
        var continuous: Set<ObjectIdentifier> = []  // pan, pinch and twist
        weak var panRecognizer: UIPanGestureRecognizer?
        weak var pickRecognizer: UILongPressGestureRecognizer?
        private var active: Set<ObjectIdentifier> = []  // recognizers between began and ended
        private var pickCancelled = false  // a second finger came down during this pick

        init(handlers: CanvasGestureHandlers) { self.handlers = handlers }

        @objc func pick(_ g: UILongPressGestureRecognizer) {
            let p = g.location(in: g.view)
            switch g.state {
            case .began:
                pickCancelled = false
                handlers.pick(p, nil)
            case .changed:
                if g.numberOfTouches > 1 { pickCancelled = true }  // turning into a pan or pinch
                if !pickCancelled { handlers.pick(p, nil) }
            case .ended:
                handlers.pick(p, !pickCancelled)
            case .cancelled, .failed:
                handlers.pick(p, false)
            default:
                break
            }
        }

        @objc func pan(_ g: UIPanGestureRecognizer) {
            let t = g.translation(in: g.view)
            g.setTranslation(.zero, in: g.view)
            if t.x.isFinite && t.y.isFinite {
                handlers.pan(CGSize(width: t.x, height: t.y))
            } else {
                gestureLog.error("Ignored a bad pan: \(t.x), \(t.y)")
            }
            track(g, "pan")
        }

        @objc func pinch(_ g: UIPinchGestureRecognizer) {
            let s = g.scale
            g.scale = 1
            if s.isFinite && s > 0 {
                handlers.pinch(s)
            } else {
                gestureLog.error("Ignored a bad pinch: \(s)")
            }
            track(g, "pinch")
        }

        @objc func rotate(_ g: UIRotationGestureRecognizer) {
            let r = g.rotation
            g.rotation = 0
            if r.isFinite {
                handlers.rotate(.radians(r))
            } else {
                gestureLog.error("Ignored a bad rotation: \(r)")
            }
            track(g, "rotate")
        }

        @objc func doubleTap(_ g: UITapGestureRecognizer) {
            if g.state == .ended { handlers.doubleTap() }
        }

        @objc func undoTap(_ g: UITapGestureRecognizer) {
            if g.state == .ended { handlers.undo() }
        }

        @objc func redoTap(_ g: UITapGestureRecognizer) {
            if g.state == .ended { handlers.redo() }
        }

        private func track(_ g: UIGestureRecognizer, _ name: String) {
            let id = ObjectIdentifier(g)
            switch g.state {
            case .began:
                if active.isEmpty {
                    gestureLog.notice("Gesture began (\(name))")
                    handlers.began()
                }
                active.insert(id)
            case .ended, .cancelled, .failed:
                active.remove(id)
                if g.state != .ended { gestureLog.notice("\(name) was cancelled") }
                if active.isEmpty { handlers.ended() }
            default:
                break
            }
        }

        // Move, pinch and twist together, as in Procreate. Taps don't run
        // alongside them: a pinch that has started can't also end as a
        // two-finger tap and undo itself.
        func gestureRecognizer(_ g: UIGestureRecognizer,
                               shouldRecognizeSimultaneouslyWith other: UIGestureRecognizer) -> Bool {
            // Pick runs alongside everything, and gives way when a second finger lands.
            if g === pickRecognizer || other === pickRecognizer { return true }
            return continuous.contains(ObjectIdentifier(g)) && continuous.contains(ObjectIdentifier(other))
        }

        // A pan, pinch or twist starting means the pick is off.
        func gestureRecognizerShouldBegin(_ g: UIGestureRecognizer) -> Bool {
            if continuous.contains(ObjectIdentifier(g)) { pickCancelled = true }
            return true
        }
    }
}
