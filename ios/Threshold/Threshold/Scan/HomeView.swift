import RoomPlan
import SwiftUI

/// Scans of your own home: make one with LiDAR (or send the sample home where RoomPlan cannot run), then open it.
struct HomeView: View {
  @Environment(AppModel.self) private var app
  @State private var location = LocationSensor()
  @State private var scanning = false
  @State private var uploading = false
  @State private var path: [String] = []
  @State private var name = "My home"
  @State private var kind = "house"

  private let canScan = RoomCaptureSession.isSupported

  var body: some View {
    NavigationStack(path: $path) {
      List {
        Section {
          TextField("Name", text: $name)
          Picker("Building", selection: $kind) {
            Text("House").tag("house")
            Text("Apartment").tag("apartment_unit")
            Text("Office").tag("office")
          }
          if canScan {
            Button { scanning = true } label: { Label("Scan rooms with LiDAR", systemImage: "camera.metering.matrix") }
          }
          Button { Task { await sendSample() } } label: {
            Label(uploading ? "Sending…" : "Send the sample home", systemImage: "house")
          }
          .disabled(uploading)
        } header: {
          Text("New scan")
        } footer: {
          Text(canScan
               ? "RoomPlan measures walls, doors, windows and furniture. Every room you scan in one go lines up in one plan."
               : "This device has no LiDAR, so scanning is off. The sample is a RoomPlan export of a made-up home in the same format the phone sends.")
        }

        Section("Sent from this phone") {
          if let error = app.lastError {
            Label(error, systemImage: "exclamationmark.triangle").foregroundStyle(.secondary)
          } else if app.scans.isEmpty {
            Text("No scans yet.").foregroundStyle(.secondary)
          }
          ForEach(app.scans) { scan in
            NavigationLink(value: scan.sid) {
              VStack(alignment: .leading, spacing: 2) {
                Text(scan.name ?? scan.sid)
                Text(scan.created.map { String($0.prefix(16)).replacingOccurrences(of: "T", with: " ") } ?? scan.sid)
                  .font(.footnote).foregroundStyle(.secondary).monospacedDigit()
              }
            }
          }
        }
      }
      .navigationTitle("Your home")
      .navigationDestination(for: String.self) { ScanDetailView(sid: $0) }
      .refreshable { await app.refreshScans() }
      .task { await app.refreshScans() }
      .fullScreenCover(isPresented: $scanning) {
        RoomScanView(location: location) { result in Task { await upload(result.export, geo: result.geo) } }
      }
    }
  }

  private func sendSample() async {
    guard let url = Bundle.main.url(forResource: "DemoHome", withExtension: "json"), let data = try? Data(contentsOf: url) else { return }
    await upload(data, geo: nil, name: name == "My home" ? "Sample home" : name)
  }

  private func upload(_ export: Data, geo: ScanGeo?, name: String? = nil) async {
    uploading = true
    defer { uploading = false }
    do {
      let result = try await app.api.uploadScan(export: export, name: name ?? self.name, kind: kind, address: nil, geo: geo,
                                                workspace: nil)
      if app.workspace != nil { try? await app.capture.place(result.sid) }  // the scan joins the linked workspace's buildings
      await app.refreshScans()
      path = [result.sid]
    } catch {
      app.lastError = error.localizedDescription
    }
  }
}
