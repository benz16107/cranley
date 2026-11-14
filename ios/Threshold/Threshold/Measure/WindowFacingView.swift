import SwiftUI

/// Which way a window faces: stand at the window and point the back camera straight out through it.
struct WindowFacingView: View {
  var task: CaptureClient.Task?
  @Environment(AppModel.self) private var app
  @State private var location = LocationSensor()
  @State private var status: String?

  var body: some View {
    List {
      Section {
        if let deg = location.headingDegrees {
          VStack(spacing: 4) {
            Text(Compass.word(deg)).font(.system(size: 56, weight: .semibold, design: .rounded))
            Text(String(format: "%.0f°  ± %.0f°", deg, location.headingAccuracy ?? 0)).monospacedDigit()
              .foregroundStyle(.secondary)
          }
          .frame(maxWidth: .infinity).padding(.vertical)
          .accessibilityElement(children: .combine)
          Button("Send this window's facing") { Task { await send(deg) } }
          if let status { Text(status).font(.footnote).foregroundStyle(.secondary) }
        } else {
          Label("Waiting for the compass. Move the phone in a figure eight if it stays empty.", systemImage: "safari")
        }
      } footer: {
        Text("Hold the phone upright with the back camera pointing straight out of the window. Metal frames and radiators pull the compass; step back half a metre if the number jumps.")
      }
    }
    .navigationTitle("Window facing")
    .onAppear { location.start() }
    .onDisappear { location.stop() }
  }

  private func send(_ deg: Double) async {
    let fix = location.location
    do {
      let reply = try await app.capture.send(.init(task: task?.id, finding: task?.finding, sid: task?.sid,
                                       kind: .windowFacing, value: deg.rounded(), unit: "deg", method: "compass",
                                       accuracy: location.headingAccuracy,
                                       location: fix.map { .init(lat: $0.coordinate.latitude, lon: $0.coordinate.longitude,
                                                                 accuracy_m: $0.horizontalAccuracy) }))
      status = reply.says ?? "Sent: faces \(Compass.word(deg))"
    } catch {
      status = "Not sent: \(error.localizedDescription)"
    }
  }
}
