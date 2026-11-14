import RoomPlan
import SwiftUI

/// Site visits: scan a space with LiDAR (or send the test cafe where RoomPlan cannot run), name the place and the
/// business, choose the report, and follow it to a PDF. Earlier visits and scans stay listed.
struct HomeView: View {
  enum Route: Hashable { case scan(String), visit(VisitRecord) }

  @Environment(AppModel.self) private var app
  @State private var location = LocationSensor()
  @State private var scanning = false
  @State private var setup: Setup?
  @State private var captured: Setup?  // shown once the scanner has gone: a sheet cannot open while a cover closes
  @State private var path: [Route] = []

  /// What the report form is for: a capture not sent yet, or a scan already on the server.
  struct Setup: Identifiable {
    let id = UUID()
    var source: VisitSetupView.Source
  }

  private let canScan = RoomCaptureSession.isSupported

  var body: some View {
    NavigationStack(path: $path) {
      List {
        Section {
          if canScan {
            Button { scanning = true } label: { Label("Scan a space", systemImage: "camera.metering.matrix") }
              .fontWeight(.semibold)
          }
          Button { useSample("DemoCafe", rooms: 4) } label: { Label("Use the test cafe", systemImage: "cup.and.saucer") }
          Button { useSample("DemoHome", rooms: 6) } label: { Label("Use the test home", systemImage: "house") }
        } header: {
          Text("New visit")
        } footer: {
          Text(canScan
               ? "Walk each room slowly with the phone up. Then name the business and pick a report; it is ready in under a minute."
               : "This device has no LiDAR, so scanning is off. The test cafe and home are hand-made RoomPlan exports, not real places.")
        }

        Section("Reports") {
          if app.visits.isEmpty {
            Text("No visits yet.").foregroundStyle(.secondary)
          }
          ForEach(app.visits) { v in
            NavigationLink(value: Route.visit(v)) {
              Label {
                VStack(alignment: .leading, spacing: 2) {
                  Text(v.name)
                  Text("\(v.kind.title) · \(v.started.formatted(date: .abbreviated, time: .shortened))")
                    .font(.footnote).foregroundStyle(.secondary)
                }
              } icon: { Image(systemName: v.kind.symbol) }
            }
          }
          .onDelete { app.visits.remove(atOffsets: $0) }
        }

        Section("Scans sent from this phone") {
          if let error = app.lastError {
            Label(error, systemImage: "exclamationmark.triangle").foregroundStyle(.secondary)
          } else if app.scans.isEmpty {
            Text("No scans yet.").foregroundStyle(.secondary)
          }
          ForEach(app.scans) { scan in
            NavigationLink(value: Route.scan(scan.sid)) {
              VStack(alignment: .leading, spacing: 2) {
                Text(scan.name ?? scan.sid)
                Text(scan.created.flatMap { try? Date($0, strategy: .iso8601) }?.formatted(date: .abbreviated, time: .shortened) ?? scan.sid)
                  .font(.footnote).foregroundStyle(.secondary).monospacedDigit()
              }
            }
          }
        }
      }
      .navigationTitle("Site visits")
      .navigationDestination(for: Route.self) { route in
        switch route {
        case .scan(let sid): ScanDetailView(sid: sid) { name in setup = Setup(source: .scan(sid: sid, name: name)) }
        case .visit(let v): VisitView(visit: v)
        }
      }
      .refreshable { await app.refreshScans() }
      .task { await app.refreshScans() }
      .fullScreenCover(isPresented: $scanning, onDismiss: { setup = captured; captured = nil }) {
        RoomScanView(location: location) { result in
          captured = Setup(source: .export(result.export, result.geo, rooms: result.rooms))
        }
      }
      .sheet(item: $setup) { s in
        VisitSetupView(source: s.source) { visit in
          path = [.visit(visit)]
          Task { await app.refreshScans() }
        }
      }
    }
  }

  private func useSample(_ name: String, rooms: Int) {
    guard let url = Bundle.main.url(forResource: name, withExtension: "json"), let data = try? Data(contentsOf: url) else { return }
    setup = Setup(source: .export(data, nil, rooms: rooms))
  }
}
