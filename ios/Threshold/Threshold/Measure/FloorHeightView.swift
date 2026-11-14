import SwiftUI

/// How high the front door sits above the street, from the barometer: hold the phone at the street, then at the
/// door threshold. Air pressure changes about 12 Pa per metre, which the barometer resolves; holding still for a few
/// seconds at each end averages out the noise. The flood tools use the result as their floor height.
struct FloorHeightView: View {
  var task: CaptureClient.Task?
  @Environment(AppModel.self) private var app
  @State private var baro = Barometer()
  @State private var street: (metres: Double, spread: Double)?
  @State private var door: (metres: Double, spread: Double)?
  @State private var status: String?

  private var height: Double? { street.flatMap { s in door.map { $0.metres - s.metres } } }
  private var spread: Double { (street?.spread ?? 0) + (door?.spread ?? 0) }

  var body: some View {
    List {
      if !baro.available {
        ContentUnavailableView("No barometer", systemImage: "barometer",
                               description: Text("This device cannot measure air pressure. Use the iPhone."))
      } else {
        Section {
          Step(number: 1, text: "Stand at the street or the ground outside, hold the phone at waist height and keep it still.",
               done: street != nil) { street = baro.settled(); door = nil }
          Step(number: 2, text: "Walk to the front door, hold the phone at the same height over the threshold and keep it still.",
               done: door != nil) { door = baro.settled() }
            .disabled(street == nil)
        } footer: {
          Text(baro.latest.map { String(format: "Barometer: %+.2f m since you opened this screen", $0) } ?? "Waiting for the barometer…")
            .monospacedDigit()
        }
        if let height {
          Section("Floor above the street") {
            LabeledContent("Height") {
              Text(String(format: "%.2f m  ± %.2f", height, max(spread, 0.05))).monospacedDigit()
            }
            Button("Send and use for flood tools") { Task { await send(height) } }
            if let status { Text(status).font(.footnote).foregroundStyle(.secondary) }
          }
        }
      }
    }
    .navigationTitle("Floor above street")
    .onAppear { baro.start() }
    .onDisappear { baro.stop() }
  }

  private func send(_ height: Double) async {
    do {
      // with a flood task this settles it and the flood rehearsal runs again on the desktop
      let reply = try await app.capture.send(.init(task: task?.id, finding: task?.finding, sid: task?.sid, kind: .floorHeight,
                                                   value: height, unit: "m", method: "barometer", accuracy: max(spread, 0.05)))
      status = reply.says ?? "Sent to the workspace"
    } catch {
      status = "Not sent: \(error.localizedDescription)"
    }
  }
}

private struct Step: View {
  var number: Int
  var text: String
  var done: Bool
  var action: () -> Void

  var body: some View {
    VStack(alignment: .leading, spacing: 8) {
      Label(text, systemImage: done ? "checkmark.circle.fill" : "\(number).circle")
      Button(done ? "Read again" : "Read here", action: action).buttonStyle(.bordered)
    }
    .padding(.vertical, 4)
  }
}
