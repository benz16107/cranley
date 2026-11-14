import SwiftUI

/// After a scan: name the place and the business, pick the report, send. Sending uploads the scan (when it has not
/// been sent yet) and starts the visit on the server, whose tools then run while the next screen shows progress.
struct VisitSetupView: View {
  enum Source {
    case export(Data, ScanGeo?, rooms: Int)  // a scan just made, not uploaded yet
    case scan(sid: String, name: String)      // a scan already on the server
  }

  var source: Source
  var onStarted: (VisitRecord) -> Void
  @Environment(AppModel.self) private var app
  @Environment(\.dismiss) private var dismiss
  @AppStorage("lastKind") private var kindRaw = ThresholdAPI.ReportKind.accessibility.rawValue
  @AppStorage("lastSpace") private var space = "storefront"
  @State private var business = ""
  @State private var place = ""
  @State private var address = ""
  @State private var sending = false
  @State private var error: String?
  @FocusState private var focus: Field?
  enum Field { case business, place, address }

  private var kind: ThresholdAPI.ReportKind { .init(rawValue: kindRaw) ?? .accessibility }

  var body: some View {
    NavigationStack {
      Form {
        Section {
          TextField("Business", text: $business, prompt: Text("Business name, e.g. Small World Coffee"))
            .textContentType(.organizationName).focused($focus, equals: .business).accessibilityIdentifier("business").submitLabel(.next)
            .onSubmit { focus = .place }
          TextField("Space", text: $place, prompt: Text("Space, e.g. Ground floor shop"))
            .focused($focus, equals: .place).accessibilityIdentifier("place").submitLabel(.next).onSubmit { focus = .address }
          TextField("Address", text: $address, prompt: Text("Address (optional)"))
            .textContentType(.fullStreetAddress).focused($focus, equals: .address).submitLabel(.done)
          if case .export = source {
            Picker("Kind of space", selection: $space) {
              Text("Shop or cafe").tag("storefront")
              Text("Office").tag("office")
              Text("Home").tag("house")
              Text("Apartment").tag("apartment_unit")
            }
          }
        } header: {
          Text("Where")
        } footer: {
          switch source {
          case .export(_, _, let rooms): Text("\(rooms) room\(rooms == 1 ? "" : "s") scanned. The business name goes on the report's cover.")
          case .scan(_, let name): Text("Scan: \(name)")
          }
        }

        Section("Report") {
          ForEach(ThresholdAPI.ReportKind.allCases) { k in
            Button { kindRaw = k.rawValue } label: {
              HStack(alignment: .firstTextBaseline, spacing: 12) {
                Image(systemName: k.symbol).frame(width: 22).foregroundStyle(Color.accentColor)
                VStack(alignment: .leading, spacing: 2) {
                  Text(k.title).foregroundStyle(.primary)
                  Text(k.detail).font(.footnote).foregroundStyle(.secondary)
                }
                Spacer()
                if k == kind { Image(systemName: "checkmark").foregroundStyle(Color.accentColor).fontWeight(.semibold) }
              }
            }
            .tint(.primary)  // a list of choices, not a column of links
            .accessibilityAddTraits(k == kind ? .isSelected : [])
          }
        }

        if let error {
          Section { Label(error, systemImage: "exclamationmark.triangle").foregroundStyle(.red) }
        }
      }
      .navigationTitle("New report")
      .navigationBarTitleDisplayMode(.inline)
      .toolbar {
        ToolbarItem(placement: .cancellationAction) { Button("Cancel") { dismiss() }.disabled(sending) }
        ToolbarItem(placement: .confirmationAction) {
          Button { Task { await send() } } label: { if sending { ProgressView() } else { Text("Send") } }
            .disabled(sending || (business.isEmpty && place.isEmpty))
        }
      }
      .onAppear {
        if case .scan(_, let name) = source, place.isEmpty { place = name }
        focus = .business
      }
      .interactiveDismissDisabled(sending)
    }
  }

  private func send() async {
    sending = true
    error = nil
    defer { sending = false }
    let title = place.isEmpty ? business : place
    do {
      let sid: String
      switch source {
      case .export(let data, let geo, _):
        let up = try await app.api.uploadScan(export: data, name: title, kind: space, address: address.isEmpty ? nil : address,
                                              geo: geo, workspace: nil)
        app.mine.append(up.sid)
        sid = up.sid
      case .scan(let s, _):
        sid = s
      }
      let v = try await app.api.startVisit(sid: sid, kind: kind, business: business, place: place, address: address)
      let rec = VisitRecord(workspace: v.workspace, token: v.token, sid: sid, kind: kind, business: business, place: place,
                            started: .now)
      app.visits.insert(rec, at: 0)
      app.workspace = v.token  // measurements and photos from this phone now go to this visit
      dismiss()
      onStarted(rec)
    } catch {
      self.error = error.localizedDescription
    }
  }
}
