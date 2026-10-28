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
}

/// Pan (one or two fingers), pinch and twist, all at once, with UIKit's
/// recognizers. SwiftUI's combined Drag + Magnify + Rotate gesture hung after
/// a pinch with the fingers close together (its rotation came back NaN, then
/// it stopped sending anything), and the canvas no longer answered touches.
/// UIKit's recognizers always report when they end or are cancelled.
struct CanvasGestureView: UIViewRepresentable {
    var handlers: CanvasGestureHandlers

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
        c.continuous = Set([pan, pinch, rotate].map(ObjectIdentifier.init))
        for recognizer in [pan, pinch, rotate, doubleTap, undoTap, redoTap] {
            recognizer.delegate = c
            view.addGestureRecognizer(recognizer)
        }
        return view
    }

    func updateUIView(_ view: UIView, context: Context) {
        context.coordinator.handlers = handlers
    }

    final class Coordinator: NSObject, UIGestureRecognizerDelegate {
        var handlers: CanvasGestureHandlers
        var continuous: Set<ObjectIdentifier> = []  // pan, pinch and twist
        private var active: Set<ObjectIdentifier> = []  // recognizers between began and ended

        init(handlers: CanvasGestureHandlers) { self.handlers = handlers }

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
            continuous.contains(ObjectIdentifier(g)) && continuous.contains(ObjectIdentifier(other))
        }
    }
}
