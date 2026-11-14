import ARKit
import RoomPlan
import SwiftUI

/// A finished capture: the RoomPlan export as JSON (CapturedRoom for one room, CapturedStructure for several) and
/// where the phone was when it ended.
struct CaptureResult {
  var export: Data
  var geo: ScanGeo?
  var rooms: Int
}

/// Apple's RoomCaptureView, full screen. Scan a room, then add another or finish; several rooms are merged into one
/// CapturedStructure by StructureBuilder, in the same coordinates because they share one AR session.
struct RoomScanView: View {
  var location: LocationSensor
  var onFinish: (CaptureResult) -> Void
  @Environment(\.dismiss) private var dismiss
  @State private var host = CaptureHost()
  @State private var working = false
  @State private var error: String?

  var body: some View {
    ZStack(alignment: .bottom) {
      CaptureViewRepresentable(host: host).ignoresSafeArea()
      VStack(spacing: 12) {
        if let error { Text(error).font(.callout).padding(10).background(.regularMaterial, in: .rect(cornerRadius: 10)) }
        HStack(spacing: 12) {
          Button("Cancel", role: .cancel) { host.view?.captureSession.stop(); dismiss() }
            .buttonStyle(.bordered)
          Spacer()
          if host.scanning {
            Button("Room done") { host.finishRoom(location: location) }
              .buttonStyle(.borderedProminent)
          } else if !host.rooms.isEmpty {
            Button("Add a room") { host.startRoom() }.buttonStyle(.bordered)
            Button(working ? "Saving…" : "Finish") { Task { await finish() } }
              .buttonStyle(.borderedProminent).disabled(working)
          }
        }
        .controlSize(.large)
        Text(host.rooms.isEmpty ? "Walk slowly round the room, pointing at walls and floor." : "\(host.rooms.count) room\(host.rooms.count == 1 ? "" : "s") scanned")
          .font(.footnote).foregroundStyle(.secondary)
      }
      .padding()
    }
    .onAppear { location.start(); host.startRoom() }
  }

  private func finish() async {
    working = true
    defer { working = false }
    do {
      let encoder = JSONEncoder()
      let data: Data
      if host.rooms.count == 1 {
        data = try encoder.encode(host.rooms[0])
      } else {
        let structure = try await StructureBuilder(options: [.beautifyObjects]).capturedStructure(from: host.rooms)
        data = try encoder.encode(structure)
      }
      onFinish(CaptureResult(export: data, geo: host.geo, rooms: host.rooms.count))
      dismiss()
    } catch {
      self.error = "Could not save the scan: \(error.localizedDescription)"
    }
  }
}

@Observable
final class CaptureHost {
  var rooms: [CapturedRoom] = []
  var scanning = false
  var geo: ScanGeo?
  @ObservationIgnored weak var view: RoomCaptureView?
  @ObservationIgnored lazy var delegate = CaptureDelegate { [weak self] room in
    self?.rooms.append(room)
  }

  func startRoom() {
    view?.captureSession.run(configuration: RoomCaptureSession.Configuration())
    scanning = true
  }

  /// Stop this room (keeping the AR session so the next room lines up) and note the phone's GPS and compass with
  /// the camera's direction at the same moment, which is what turns the scan onto the map.
  func finishRoom(location: LocationSensor) {
    if let session = view?.captureSession, let frame = session.arSession.currentFrame, let fix = location.location {
      let t = frame.camera.transform
      geo = ScanGeo(lat: fix.coordinate.latitude, lon: fix.coordinate.longitude, altitude: fix.altitude,
                    accuracy_m: fix.horizontalAccuracy, heading_deg: location.headingDegrees,
                    heading_accuracy_deg: location.headingAccuracy,
                    camera_forward: [Double(-t.columns.2.x), Double(-t.columns.2.z)],
                    camera_position: [Double(t.columns.3.x), Double(t.columns.3.z)])
    }
    view?.captureSession.stop(pauseARSession: false)
    scanning = false
  }
}

/// RoomCaptureViewDelegate must also be NSCoding; it is called on the main thread.
nonisolated final class CaptureDelegate: NSObject, RoomCaptureViewDelegate {
  private let onRoom: @MainActor (CapturedRoom) -> Void

  init(onRoom: @escaping @MainActor (CapturedRoom) -> Void) {
    self.onRoom = onRoom
  }

  required init?(coder: NSCoder) { nil }
  func encode(with coder: NSCoder) {}

  func captureView(shouldPresent roomDataForProcessing: CapturedRoomData, error: (any Error)?) -> Bool { true }

  func captureView(didPresent processedResult: CapturedRoom, error: (any Error)?) {
    guard error == nil else { return }
    let onRoom = self.onRoom  // a @MainActor closure is Sendable; self is not
    MainActor.assumeIsolated { onRoom(processedResult) }
  }
}

struct CaptureViewRepresentable: UIViewRepresentable {
  var host: CaptureHost

  func makeUIView(context: Context) -> RoomCaptureView {
    let view = RoomCaptureView(frame: .zero)
    view.delegate = host.delegate
    host.view = view
    return view
  }

  func updateUIView(_ view: RoomCaptureView, context: Context) {}
}
