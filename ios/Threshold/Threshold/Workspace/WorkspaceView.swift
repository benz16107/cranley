import SwiftUI
import VisionKit

/// Link the phone to a desktop workspace (the code under its Phone tab), see the field tasks it asks for, and set
/// the server.
struct WorkspaceView: View {
  @Environment(AppModel.self) private var app
  @State private var scanningCode = false
  @State private var pasted = ""
  @State private var tasks: [CaptureClient.Task] = []
  @State private var taskError: String?
  @State private var serverText = ""

  private var canScanCode: Bool { DataScannerViewController.isSupported }

  var body: some View {
    NavigationStack {
      List {
        Section {
          if app.workspace != nil {
            LabeledContent("Linked to") { Text(app.server.host() ?? app.server.absoluteString) }
            Button("Leave this workspace", role: .destructive) { app.workspace = nil; tasks = [] }
          }
          if canScanCode {
            Button { scanningCode = true } label: { Label("Scan the code on your computer", systemImage: "qrcode.viewfinder") }
          }
          TextField("Or paste the link", text: $pasted)
            .textInputAutocapitalization(.never).autocorrectionDisabled().keyboardType(.URL)
            .onSubmit { attach(pasted) }
        } header: {
          Text("Workspace")
        } footer: {
          Text("On the computer, open the Phone tab at the bottom of the page. Scans and measurements from this phone then show up in that workspace.")
        }

        if app.workspace != nil {
          Section("Field tasks") {
            if tasks.isEmpty {
              Text(taskError ?? "Nothing to measure on site.").foregroundStyle(.secondary)
            }
            ForEach(tasks) { task in
              let row = Label {
                VStack(alignment: .leading, spacing: 2) {
                  Text(task.title)
                  if let d = task.detail { Text(d).font(.footnote).foregroundStyle(.secondary) }
                  if task.kind == nil { Text("Do this one on the web page the code opens.").font(.footnote).foregroundStyle(.secondary) }
                }
              } icon: { Image(systemName: task.kind?.symbol ?? "safari") }
              if let kind = task.kind { NavigationLink { TaskMeasureView(task: task, kind: kind) } label: { row } } else { row }
            }
          }
        }

        Section {
          TextField("Server", text: $serverText)
            .textInputAutocapitalization(.never).autocorrectionDisabled().keyboardType(.URL)
            .onSubmit { if let url = URL(string: serverText), url.host != nil { app.server = url } }
        } header: { Text("Server") } footer: { Text("Your computer and phone need to be on the same Tailscale network.") }
      }
      .navigationTitle("Workspace")
      .onAppear { serverText = app.server.absoluteString }
      .task(id: app.workspace) { await loadTasks() }
      .refreshable { await loadTasks() }
      .sheet(isPresented: $scanningCode) {
        QRScanner { code in
          scanningCode = false
          attach(code)
        }
        .ignoresSafeArea()
      }
    }
  }

  private func attach(_ text: String) {
    if app.link(text) {
      pasted = ""
      serverText = app.server.absoluteString
      taskError = nil
    } else {
      taskError = "That link has no pairing code. Scan the code under the Phone tab on your computer."
    }
  }

  private func loadTasks() async {
    guard app.workspace != nil else { return }
    do {
      tasks = try await app.capture.tasks()
      taskError = nil
    } catch {
      taskError = error.localizedDescription
    }
  }
}

/// VisionKit's live QR reader; returns the first code it sees.
struct QRScanner: UIViewControllerRepresentable {
  var onCode: (String) -> Void

  func makeUIViewController(context: Context) -> DataScannerViewController {
    let vc = DataScannerViewController(recognizedDataTypes: [.barcode(symbologies: [.qr])], qualityLevel: .balanced,
                                       isHighlightingEnabled: true)
    vc.delegate = context.coordinator
    try? vc.startScanning()
    return vc
  }

  func updateUIViewController(_ vc: DataScannerViewController, context: Context) {}

  func makeCoordinator() -> Coordinator { Coordinator(onCode: onCode) }

  final class Coordinator: NSObject, DataScannerViewControllerDelegate {
    let onCode: (String) -> Void
    private var done = false
    init(onCode: @escaping (String) -> Void) { self.onCode = onCode }

    func dataScanner(_ scanner: DataScannerViewController, didAdd items: [RecognizedItem], allItems: [RecognizedItem]) {
      guard !done else { return }
      for case .barcode(let code) in items {
        if let text = code.payloadStringValue {
          done = true
          scanner.stopScanning()
          onCode(text)
          return
        }
      }
    }
  }
}
