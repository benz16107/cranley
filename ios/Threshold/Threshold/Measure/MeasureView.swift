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
        ContentUnavailableView("Needs LiDAR", systemImage: "camera.metering.unknown",
                               description: Text("Open this task on the iPhone to measure it."))
      }
    }
  }
}
