import ARKit
import SwiftUI

/// The phone's own sensors as evidence: LiDAR distances, the barometer and the compass.
struct MeasureView: View {
  private let hasLiDAR = ARWorldTrackingConfiguration.supportsSceneReconstruction(.mesh)

  var body: some View {
    NavigationStack {
      List {
        if hasLiDAR {
          Section {
            ForEach([CaptureClient.Kind.doorWidth, .thresholdHeight, .stepHeight, .ceilingHeight], id: \.self) { kind in
              NavigationLink { ARMeasureView(kind: kind, task: nil) } label: { Label(kind.title, systemImage: kind.symbol) }
            }
          } header: { Text("LiDAR") } footer: { Text("Points sit on real surfaces, to about a centimetre.") }
        }
        Section {
          NavigationLink { FloorHeightView(task: nil) } label: { Label(CaptureClient.Kind.floorHeight.title, systemImage: "barometer") }
          NavigationLink { WindowFacingView(task: nil) } label: { Label(CaptureClient.Kind.windowFacing.title, systemImage: "safari") }
        } header: { Text("Barometer and compass") } footer: {
          Text(hasLiDAR ? "" : "LiDAR measuring needs an iPhone Pro; it is hidden on this device.")
        }
      }
      .navigationTitle("Measure")
    }
  }
}

/// The screen that answers a field task, by its kind.
struct TaskMeasureView: View {
  var task: CaptureClient.Task
  var kind: CaptureClient.Kind

  var body: some View {
    switch kind {
    case .floorHeight: FloorHeightView(task: task)
    case .windowFacing: WindowFacingView(task: task)
    case .photo, .doorWidth, .thresholdHeight, .stepHeight, .ceilingHeight:
      if ARWorldTrackingConfiguration.supportsSceneReconstruction(.mesh) {
        ARMeasureView(kind: kind == .photo ? .doorWidth : kind, task: task)
      } else {
        TapeEntryView(task: task, kind: kind)
      }
    }
  }
}

/// Without LiDAR, the person measures with a tape and types it, as on the web page.
struct TapeEntryView: View {
  @Environment(AppModel.self) private var app
  var task: CaptureClient.Task
  var kind: CaptureClient.Kind
  @State private var text = ""
  @State private var inches = true
  @State private var sending = false
  @State private var sent: String?
  @FocusState private var typing: Bool

  private var metres: Double? {
    guard let v = Double(text.replacingOccurrences(of: ",", with: ".")), v > 0 else { return nil }
    return inches ? v * 0.0254 : v / 100
  }

  var body: some View {
    Form {
      Section {
        Text(task.title).font(.headline)
        if let d = task.detail { Text(d).foregroundStyle(.secondary) }
      } footer: {
        Text(kind == .doorWidth ? "Open the door to 90 degrees and measure from the face of the door to the stop on the latch side."
                                : "Measure from the floor to the top edge of the step or threshold.")
      }
      Section("With a tape") {
        HStack {
          TextField(kind == .doorWidth ? "32.5" : "0.5", text: $text).keyboardType(.decimalPad).monospacedDigit().focused($typing)
          Picker("Unit", selection: $inches) { Text("in").tag(true); Text("cm").tag(false) }.pickerStyle(.segmented).frame(width: 110)
        }
        Button(sending ? "Sending…" : "Save") { Task { await save() } }.disabled(metres == nil || sending)
      }
      if let sent { Section { Text(sent) } }
    }
    .navigationTitle(kind == .doorWidth ? "Door width" : "Step height")
    .toolbar { ToolbarItemGroup(placement: .keyboard) { Spacer(); Button("Done") { typing = false } } }  // a decimal pad has no return key
  }

  private func save() async {
    guard let m = metres else { return }
    typing = false
    sending = true
    defer { sending = false }
    let reading = CaptureClient.Measurement(task: task.id, finding: task.finding, sid: task.sid, kind: kind, value: m, unit: "m", method: "tape")
    do { sent = try await app.capture.send(reading).says ?? "Sent to the workspace" } catch { sent = "Not sent: \(error.localizedDescription)" }
  }
}
