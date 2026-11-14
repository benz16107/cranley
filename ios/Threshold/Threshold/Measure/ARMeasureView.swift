import ARKit
import RealityKit
import SwiftUI

/// Measure with LiDAR, like Apple's Measure app: aim the dot, tap to drop a point, drop a second. Door width is the
/// level distance between the points (jamb to jamb, or jamb to the face of the open door); the heights are the
/// vertical distance (floor to threshold top, tread to tread, floor to ceiling).
struct ARMeasureView: View {
  var kind: CaptureClient.Kind
  var task: CaptureClient.Task?
  @Environment(AppModel.self) private var app
  @State private var session = MeasureSession()
  @State private var sending = false
  @State private var sent: String?

  var body: some View {
    ZStack {
      MeasureARView(session: session).ignoresSafeArea()
      Image(systemName: "plus").font(.title2.weight(.light)).foregroundStyle(.white).shadow(radius: 2)
        .accessibilityHidden(true)
      VStack {
        Text(instruction).font(.callout).multilineTextAlignment(.center)
          .padding(10).background(.regularMaterial, in: .rect(cornerRadius: 12)).padding(.top, 8)
        Spacer()
        if let value = session.value(for: kind) {
          Text(format(value)).font(.system(size: 44, weight: .semibold, design: .rounded)).monospacedDigit()
            .padding(.horizontal, 16).padding(.vertical, 6).background(.regularMaterial, in: .capsule)
            .accessibilityLabel("\(kind.title) \(format(value))")
        }
        if let sent { Text(sent).font(.footnote).padding(6).background(.regularMaterial, in: .capsule) }
        HStack(spacing: 12) {
          Button("Clear") { session.clear(); sent = nil }.buttonStyle(.bordered).disabled(session.points.isEmpty)
          Spacer()
          if session.points.count < 2 {
            Button(session.points.isEmpty ? "Add point" : "Add second point") { session.addPointAtCentre() }
              .buttonStyle(.borderedProminent)
          } else {
            Button(sending ? "Sending…" : "Send") { Task { await send() } }
              .buttonStyle(.borderedProminent).disabled(sending)
          }
        }
        .controlSize(.large).padding()
      }
    }
    .navigationTitle(kind.title)
    .navigationBarTitleDisplayMode(.inline)
    .toolbarBackground(.visible, for: .navigationBar)
  }

  private var instruction: String {
    switch kind {
    case .doorWidth: "Aim at one door jamb at waist height, add a point, then at the other jamb (or the face of the open door)."
    case .thresholdHeight: "Add a point on the floor beside the threshold, then one on the top of the threshold."
    case .stepHeight: "Add a point on the lower tread, then one on the top of the step."
    case .ceilingHeight: "Add a point on the floor, then aim straight up and add one on the ceiling."
    default: ""
    }
  }

  private func format(_ metres: Double) -> String {
    metres < 1 ? String(format: "%.0f cm", metres * 100) : String(format: "%.2f m", metres)
  }

  private func send() async {
    guard let value = session.value(for: kind) else { return }
    sending = true
    defer { sending = false }
    let m = CaptureClient.Measurement(
      task: task?.id, finding: task?.finding, sid: task?.sid, kind: kind, value: value,
      unit: "m", method: "arkit_lidar", accuracy: 0.01,
      points: session.points.map { [Double($0.x), Double($0.y), Double($0.z)] },
      photo: await session.snapshotJPEG())
    do {
      sent = try await app.capture.send(m).says ?? "Sent to the workspace"
    } catch {
      sent = "Not sent: \(error.localizedDescription)"
    }
  }
}

@Observable
final class MeasureSession {
  var points: [SIMD3<Float>] = []
  @ObservationIgnored weak var view: ARView?
  @ObservationIgnored private var markers: [Entity] = []

  func value(for kind: CaptureClient.Kind) -> Double? {
    guard points.count == 2 else { return nil }
    let d = points[1] - points[0]
    return kind == .doorWidth ? Double(simd_length(SIMD2(d.x, d.z))) : Double(abs(d.y))  // ARKit: y is up
  }

  func addPointAtCentre() {
    guard let view, points.count < 2 else { return }
    let centre = CGPoint(x: view.bounds.midX, y: view.bounds.midY)
    guard let hit = view.raycast(from: centre, allowing: .estimatedPlane, alignment: .any).first else { return }
    let p = SIMD3<Float>(hit.worldTransform.columns.3.x, hit.worldTransform.columns.3.y, hit.worldTransform.columns.3.z)
    points.append(p)
    let anchor = AnchorEntity(world: p)
    anchor.addChild(ModelEntity(mesh: .generateSphere(radius: 0.008), materials: [UnlitMaterial(color: .white)]))
    view.scene.addAnchor(anchor)
    markers.append(anchor)
    if points.count == 2 { drawLine() }
    UIImpactFeedbackGenerator(style: .light).impactOccurred()
  }

  private func drawLine() {
    guard let view else { return }
    let a = points[0], b = points[1], length = simd_length(b - a)
    let line = ModelEntity(mesh: .generateBox(size: [0.004, 0.004, length]), materials: [UnlitMaterial(color: .systemYellow)])
    let anchor = AnchorEntity(world: (a + b) / 2)
    line.look(at: b, from: (a + b) / 2, relativeTo: nil)
    anchor.addChild(line)
    view.scene.addAnchor(anchor)
    markers.append(anchor)
  }

  func clear() {
    markers.forEach { $0.removeFromParent() }
    markers = []
    points = []
  }

  func snapshotJPEG() async -> Data? {
    guard let view else { return nil }
    return await withCheckedContinuation { cont in
      view.snapshot(saveToHDR: false) { image in cont.resume(returning: image?.jpegData(compressionQuality: 0.6)) }
    }
  }
}

struct MeasureARView: UIViewRepresentable {
  var session: MeasureSession

  func makeUIView(context: Context) -> ARView {
    let view = ARView(frame: .zero, cameraMode: .ar, automaticallyConfigureSession: false)
    let config = ARWorldTrackingConfiguration()
    config.planeDetection = [.horizontal, .vertical]
    if ARWorldTrackingConfiguration.supportsSceneReconstruction(.mesh) { config.sceneReconstruction = .mesh }
    if ARWorldTrackingConfiguration.supportsFrameSemantics(.sceneDepth) { config.frameSemantics.insert(.sceneDepth) }
    view.session.run(config)
    let coaching = ARCoachingOverlayView()
    coaching.session = view.session
    coaching.goal = .anyPlane
    coaching.autoresizingMask = [.flexibleWidth, .flexibleHeight]
    view.addSubview(coaching)
    session.view = view
    return view
  }

  func updateUIView(_ view: ARView, context: Context) {}

  static func dismantleUIView(_ view: ARView, coordinator: ()) { view.session.pause() }
}

extension CaptureClient.Kind {
  var title: String {
    switch self {
    case .doorWidth: "Door width"
    case .thresholdHeight: "Threshold height"
    case .stepHeight: "Step height"
    case .ceilingHeight: "Ceiling height"
    case .floorHeight: "Floor above street"
    case .windowFacing: "Window facing"
    case .photo: "Photo"
    }
  }

  var symbol: String {
    switch self {
    case .doorWidth: "door.left.hand.open"
    case .thresholdHeight: "rectangle.portrait.bottomhalf.filled"
    case .stepHeight: "stairs"
    case .ceilingHeight: "arrow.up.and.down"
    case .floorHeight: "barometer"
    case .windowFacing: "safari"
    case .photo: "camera"
    }
  }
}
