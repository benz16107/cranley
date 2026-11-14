import QuickLook
import SwiftUI

/// One visit: the tools running on the server with a determinate progress bar, then the report to open and hand
/// over. Below, what can still be added on site (field tasks, ceiling photos), after which the report is printed again.
struct VisitView: View {
  var visit: VisitRecord
  @Environment(AppModel.self) private var app
  @State private var status: ThresholdAPI.VisitStatus?
  @State private var plan: ScanPlan?
  @State private var tasks: [CaptureClient.Task] = []
  @State private var error: String?
  @State private var preview: URL?
  @State private var pdf: URL?
  @State private var opening = false
  @State private var photoRoom: ScanPlan.Room?
  @State private var sentPhotos: [String: String] = [:]  // room id -> what the server said

  private var finished: Int { status?.tools.filter { ["done", "error", "skipped"].contains($0.status) }.count ?? 0 }

  var body: some View {
    List {
      Section {
        VStack(alignment: .leading, spacing: 10) {
          Label(visit.kind.title, systemImage: visit.kind.symbol).font(.headline)
          if let status {
            ProgressView(value: Double(finished), total: Double(max(status.tools.count, 1))) {
              Text(status.done ? "All \(status.tools.count) checks finished" : "Running \(running ?? "checks")…")
                .font(.subheadline)
            }
          } else if error == nil {
            ProgressView(value: 0) { Text("Sending…").font(.subheadline) }
          }
        }
        .padding(.vertical, 4)

        Button { Task { await openReport() } } label: {
          HStack {
            Label(opening ? "Printing the report…" : "Open report", systemImage: "doc.richtext")
            Spacer()
            if opening { ProgressView() }
          }
        }
        .disabled(!(status?.done ?? false) || opening)
        .fontWeight(.semibold)

        if let pdf {
          ShareLink(item: pdf) { Label("Send the report", systemImage: "square.and.arrow.up") }
        }
      } header: {
        Text(visit.place.isEmpty ? visit.started.formatted(date: .abbreviated, time: .shortened) : visit.place)
      } footer: {
        if let error { Text(error).foregroundStyle(.red) }
      }

      if let status {
        Section("Checks") {
          ForEach(status.tools) { t in
            VisitToolRow(tool: t)
          }
        }
      }

      if !tasks.isEmpty {
        Section {
          ForEach(tasks) { task in
            if let kind = task.kind {
              NavigationLink { TaskMeasureView(task: task, kind: kind) } label: { TaskLabel(task: task) }
            } else {
              TaskLabel(task: task)
            }
          }
        } header: {
          Text("Measure on site")
        } footer: {
          Text("Each one settles something the scan could not. Open the report again afterwards to include it.")
        }
      }

      if visit.kind == .fire, let plan {
        Section {
          ForEach(plan.rooms.filter { !["Bathroom", "Hallway", "Laundry"].contains($0.label ?? "") }) { room in
            Button { photoRoom = room } label: {
              HStack {
                Label(room.label ?? "Room", systemImage: sentPhotos[room.id] == nil ? "camera" : "checkmark.circle.fill")
                Spacer()
                if let said = sentPhotos[room.id] { Text(said).font(.footnote).foregroundStyle(.secondary).lineLimit(1) }
              }
            }
          }
        } header: {
          Text("Smoke alarms")
        } footer: {
          Text("Photograph each room's ceiling. The report says where an alarm shows and where none was seen.")
        }
      }
    }
    .navigationTitle(visit.name)
    .navigationBarTitleDisplayMode(.inline)
    .quickLookPreview($preview)
    .sheet(item: $photoRoom) { room in
      CameraPicker { image in
        photoRoom = nil
        if let image { Task { await sendCeiling(image, room: room) } }
      }
      .ignoresSafeArea()
    }
    .task { await follow() }
    .refreshable { await refresh() }
  }

  private var running: String? { status?.tools.first { $0.status == "running" || $0.status == "waiting" }?.title }

  /// Read the visit's status until every check has finished, then the plan and the field tasks.
  private func follow() async {
    if app.workspace != visit.token { app.workspace = visit.token }  // this phone's captures go to the visit on screen
    while !Task.isCancelled {
      await refresh()
      if status?.done ?? false { break }
      try? await Task.sleep(for: .seconds(1))
    }
  }

  private func refresh() async {
    do {
      status = try await app.api.visitStatus(visit.workspace)
      error = nil
    } catch {
      self.error = error.localizedDescription
    }
    guard status?.done ?? false else { return }
    if plan == nil { plan = try? await app.api.plan(visit.sid) }
    tasks = (try? await app.capture.tasks()) ?? []
  }

  private func openReport() async {
    opening = true
    defer { opening = false }
    do {
      let url = try await app.api.reportPDF(visit.workspace, name: "\(visit.name) \(visit.kind.title)")
      pdf = url
      preview = url
    } catch {
      self.error = error.localizedDescription
    }
  }

  private func sendCeiling(_ image: UIImage, room: ScanPlan.Room) async {
    guard let jpeg = image.jpegData(compressionQuality: 0.8) else { return }
    sentPhotos[room.id] = "Sending…"
    do {
      try await app.capture.sendCeilingPhoto(jpeg, sid: visit.sid, room: room.id, roomName: room.label ?? "a room")
      sentPhotos[room.id] = "Sent"
    } catch {
      sentPhotos[room.id] = "Not sent: \(error.localizedDescription)"
    }
  }
}

struct VisitToolRow: View {
  var tool: ThresholdAPI.VisitStatus.Tool

  var body: some View {
    VStack(alignment: .leading, spacing: 4) {
      HStack {
        Text(tool.title).font(.headline)
        Spacer()
        switch tool.status {
        case "done": StatusBadge(status: tool.verdict?.status ?? "unknown")
        case "error", "skipped": StatusBadge(status: "unknown")
        default: ProgressView()
        }
      }
      if let text = tool.verdict?.text ?? tool.error {
        Text(text).font(.subheadline).foregroundStyle(.secondary)
      }
    }
    .accessibilityElement(children: .combine)
  }
}

struct TaskLabel: View {
  var task: CaptureClient.Task

  var body: some View {
    Label {
      VStack(alignment: .leading, spacing: 2) {
        Text(task.title)
        if let d = task.detail { Text(d).font(.footnote).foregroundStyle(.secondary) }
      }
    } icon: { Image(systemName: task.kind?.symbol ?? "safari") }
  }
}

/// The camera where there is one (the simulator has none: it falls back to the photo library).
struct CameraPicker: UIViewControllerRepresentable {
  var onPick: (UIImage?) -> Void

  func makeUIViewController(context: Context) -> UIImagePickerController {
    let picker = UIImagePickerController()
    picker.sourceType = UIImagePickerController.isSourceTypeAvailable(.camera) ? .camera : .photoLibrary
    picker.delegate = context.coordinator
    return picker
  }

  func updateUIViewController(_ picker: UIImagePickerController, context: Context) {}

  func makeCoordinator() -> Coordinator { Coordinator(onPick: onPick) }

  final class Coordinator: NSObject, UIImagePickerControllerDelegate, UINavigationControllerDelegate {
    let onPick: (UIImage?) -> Void
    init(onPick: @escaping (UIImage?) -> Void) { self.onPick = onPick }

    func imagePickerController(_ picker: UIImagePickerController, didFinishPickingMediaWithInfo info: [UIImagePickerController.InfoKey: Any]) {
      onPick(info[.originalImage] as? UIImage)
    }

    func imagePickerControllerDidCancel(_ picker: UIImagePickerController) { onPick(nil) }
  }
}
