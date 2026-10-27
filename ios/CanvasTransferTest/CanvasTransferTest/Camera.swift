import AVFoundation
import SwiftUI
import UIKit
import Vision

/// Finds the rectangle in live frames, a few times a second, on the camera queue.
final class FrameAnalyzer: NSObject, AVCaptureVideoDataOutputSampleBufferDelegate {
    var onResult: ((VNRectangleObservation?) -> Void)?  // called on the main queue
    private var last = Date.distantPast

    func captureOutput(_ output: AVCaptureOutput, didOutput sampleBuffer: CMSampleBuffer, from connection: AVCaptureConnection) {
        guard Date().timeIntervalSince(last) > 0.15, let buffer = CMSampleBufferGetImageBuffer(sampleBuffer) else { return }
        last = Date()
        let request = ImageOps.rectangleRequest()
        try? VNImageRequestHandler(cvPixelBuffer: buffer, orientation: .up, options: [:]).perform([request])
        let found = request.results?.first
        DispatchQueue.main.async { self.onResult?(found) }
    }
}

/// Receives the full-resolution still.
final class PhotoReceiver: NSObject, AVCapturePhotoCaptureDelegate {
    var onImage: ((UIImage) -> Void)?  // called on the main queue

    func photoOutput(_ output: AVCapturePhotoOutput, didFinishProcessingPhoto photo: AVCapturePhoto, error: Error?) {
        guard let data = photo.fileDataRepresentation(), let image = UIImage(data: data) else { return }
        DispatchQueue.main.async { self.onImage?(image) }
    }
}

/// Live camera with the detected rectangle outlined, and a full-resolution
/// still on request. Detection on the live view is only feedback; the
/// corners come from running detection again on the still photo.
final class CameraController: UIViewController {
    var onRectangleFound: ((Bool) -> Void)?

    private let session = AVCaptureSession()
    private let photoOutput = AVCapturePhotoOutput()
    private let videoOutput = AVCaptureVideoDataOutput()
    private let queue = DispatchQueue(label: "camera")
    private let previewLayer = AVCaptureVideoPreviewLayer()
    private let quadLayer = CAShapeLayer()
    private var rotation: AVCaptureDevice.RotationCoordinator?
    private var rotationObservation: NSKeyValueObservation?
    private let analyzer = FrameAnalyzer()
    private let receiver = PhotoReceiver()

    override func viewDidLoad() {
        super.viewDidLoad()
        view.backgroundColor = .black
        previewLayer.session = session
        previewLayer.videoGravity = .resizeAspectFill
        view.layer.addSublayer(previewLayer)
        quadLayer.strokeColor = UIColor.systemBlue.cgColor
        quadLayer.fillColor = UIColor.systemBlue.withAlphaComponent(0.12).cgColor
        quadLayer.lineWidth = 3
        quadLayer.lineJoin = .round
        view.layer.addSublayer(quadLayer)
        analyzer.onResult = { [weak self] observation in self?.show(observation) }
        AVCaptureDevice.requestAccess(for: .video) { granted in
            guard granted else { return }
            self.queue.async { self.configure() }
        }
    }

    override func viewDidLayoutSubviews() {
        super.viewDidLayoutSubviews()
        previewLayer.frame = view.bounds
        quadLayer.frame = view.bounds
    }

    override func viewWillDisappear(_ animated: Bool) {
        super.viewWillDisappear(animated)
        queue.async { self.session.stopRunning() }
    }

    private func configure() {
        guard let device = AVCaptureDevice.default(.builtInWideAngleCamera, for: .video, position: .back),
              let input = try? AVCaptureDeviceInput(device: device) else { return }
        session.beginConfiguration()
        session.sessionPreset = .photo
        if session.canAddInput(input) { session.addInput(input) }
        if session.canAddOutput(photoOutput) { session.addOutput(photoOutput) }
        videoOutput.alwaysDiscardsLateVideoFrames = true
        videoOutput.setSampleBufferDelegate(analyzer, queue: queue)
        if session.canAddOutput(videoOutput) { session.addOutput(videoOutput) }
        session.commitConfiguration()
        session.startRunning()

        DispatchQueue.main.async {
            // Keeps the preview and the photo level however the iPad is held.
            let coordinator = AVCaptureDevice.RotationCoordinator(device: device, previewLayer: self.previewLayer)
            self.rotation = coordinator
            self.previewLayer.connection?.videoRotationAngle = coordinator.videoRotationAngleForHorizonLevelPreview
            self.rotationObservation = coordinator.observe(\.videoRotationAngleForHorizonLevelPreview, options: [.new]) {
                [weak self] coordinator, _ in
                DispatchQueue.main.async {
                    self?.previewLayer.connection?.videoRotationAngle = coordinator.videoRotationAngleForHorizonLevelPreview
                }
            }
        }
    }

    private func show(_ observation: VNRectangleObservation?) {
        onRectangleFound?(observation != nil)
        guard let r = observation else {
            quadLayer.path = nil
            return
        }
        // Vision counts from the bottom of the sensor image; the capture device
        // counts from the top. The preview layer then handles rotation and fill.
        let points = [r.topLeft, r.topRight, r.bottomRight, r.bottomLeft].map {
            previewLayer.layerPointConverted(fromCaptureDevicePoint: CGPoint(x: $0.x, y: 1 - $0.y))
        }
        let path = UIBezierPath()
        path.move(to: points[0])
        points.dropFirst().forEach { path.addLine(to: $0) }
        path.close()
        quadLayer.path = path.cgPath
    }

    func capture(_ done: @escaping (UIImage) -> Void) {
        receiver.onImage = done
        if let connection = photoOutput.connection(with: .video), let angle = rotation?.videoRotationAngleForHorizonLevelCapture,
           connection.isVideoRotationAngleSupported(angle) {
            connection.videoRotationAngle = angle
        }
        photoOutput.capturePhoto(with: AVCapturePhotoSettings(), delegate: receiver)
    }
}

struct CameraPreview: UIViewControllerRepresentable {
    let controller: CameraController

    func makeUIViewController(context: Context) -> CameraController { controller }
    func updateUIViewController(_ controller: CameraController, context: Context) {}
}

/// Capture: full screen, Canvas | Reference chosen before the shot, shutter on the right.
struct CameraScreen: View {
    @Binding var kind: LayerKind
    var onPhoto: (UIImage) -> Void
    var onCancel: () -> Void

    @State private var controller = CameraController()
    @State private var found = false
    @State private var capturing = false

    var body: some View {
        ZStack {
            CameraPreview(controller: controller).ignoresSafeArea()
            VStack {
                HStack {
                    Button("Cancel", action: onCancel)
                        .buttonStyle(.borderedProminent).tint(Color(white: 0.15))
                    Spacer()
                    if found {
                        Text("Rectangle found · hold steady")
                            .padding(.horizontal, 14).padding(.vertical, 6)
                            .background(Capsule().fill(Color.blue)).foregroundStyle(.white)
                    }
                    Spacer()
                }
                Spacer()
                Picker("Use as", selection: $kind) {
                    ForEach(LayerKind.allCases) { Text($0.rawValue).tag($0) }
                }
                .pickerStyle(.segmented)
                .frame(width: 260)
                .padding(6)
                .background(RoundedRectangle(cornerRadius: 10).fill(Color.black.opacity(0.6)))
            }
            .padding()
            .padding(.trailing, 110)

            HStack {
                Spacer()
                ZStack {
                    Color.black.opacity(0.55).ignoresSafeArea()
                    Button {
                        guard !capturing else { return }
                        capturing = true
                        controller.capture { image in onPhoto(image) }
                    } label: {
                        Circle().fill(Color.white).frame(width: 64, height: 64)
                            .padding(6)
                            .overlay(Circle().stroke(Color.white, lineWidth: 4))
                    }
                    .accessibilityLabel("Take photo")
                }
                .frame(width: 110)
            }
        }
        .onAppear { controller.onRectangleFound = { found = $0 } }
    }
}
