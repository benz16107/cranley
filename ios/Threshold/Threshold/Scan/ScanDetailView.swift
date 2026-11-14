import SwiftUI

/// One phone scan as the server sees it: the plan drawn from its numbers, its rooms, and the geometry tools run on it.
struct ScanDetailView: View {
  var sid: String
  var onReport: ((String) -> Void)? = nil  // open the report form for this scan, with its name
  @Environment(AppModel.self) private var app
  @State private var plan: ScanPlan?
  @State private var floor: String?
  @State private var results: [String: Result<ToolOutcome, any Error>] = [:]
  @State private var error: String?

  /// Geometry tools that need nothing but the plan, with the inputs a phone scan wants.
  static let tools: [(id: String, title: String, inputs: [String: any Sendable])] = [
    ("door_widths", "Door widths", ["min_width_m": 0.813]),
    ("step_free_route", "Wheelchair route", ["read_panoramas": false]),
    ("turning_space", "Turning space", [:]),
    ("bathroom_clearance", "Bathroom clearance", ["read_panoramas": false]),
    ("furniture_fit", "Sofa fits", ["object": "sofa"]),
    ("stretcher_route", "Stretcher route", [:]),
    ("egress_routes", "Ways out", [:]),
    ("robot_fit", "Robot fit", [:]),
    ("takeoff_bid", "Cleaning bid", ["trade": "cleaning"]),
  ]

  var body: some View {
    List {
      if let plan {
        Section {
          PlanView(plan: plan, floor: floor ?? plan.floors.first?.id ?? "")
            .frame(height: 280)
            .listRowInsets(EdgeInsets(top: 8, leading: 8, bottom: 8, trailing: 8))
          if plan.floors.count > 1 {
            Picker("Floor", selection: Binding(get: { floor ?? plan.floors[0].id }, set: { floor = $0 })) {
              ForEach(plan.floors) { Text($0.label ?? $0.id).tag($0.id) }
            }
            .pickerStyle(.segmented)
          }
        } footer: {
          Text("\(plan.rooms.count) rooms, \(plan.openings.count) doors and windows, \(plan.objects?.count ?? 0) objects")
        }

        Section("Rooms") {
          ForEach(plan.rooms) { room in
            LabeledContent(room.label ?? "Room") {
              Text(room.area.map { String(format: "%.1f m²", $0) } ?? "–").monospacedDigit()
            }
          }
        }

        Section("Tools on this scan") {
          ForEach(Self.tools, id: \.id) { tool in
            ToolRow(title: tool.title, result: results[tool.id])
          }
        }

        if let notes = plan.quality?.notes, !notes.isEmpty {
          Section("What the scan cannot tell") {
            ForEach(notes, id: \.self) { Text($0).font(.footnote).foregroundStyle(.secondary) }
          }
        }
      } else if let error {
        ContentUnavailableView("Could not load the scan", systemImage: "wifi.exclamationmark", description: Text(error))
      } else {
        ProgressView().frame(maxWidth: .infinity)
      }
    }
    .navigationTitle(plan?.name ?? "Scan")
    .navigationBarTitleDisplayMode(.inline)
    .toolbar {
      if let onReport {
        Button { onReport(plan?.name ?? "") } label: { Label("Make a report", systemImage: "doc.richtext") }
          .disabled(plan == nil)
      }
    }
    .task { await load() }
    .refreshable { await load() }
  }

  private func load() async {
    do {
      plan = try await app.api.plan(sid)
      error = nil
    } catch {
      self.error = error.localizedDescription
      return
    }
    await withTaskGroup(of: (String, Result<ToolOutcome, any Error>).self) { group in
      for tool in Self.tools {
        let api = app.api
        var inputs = tool.inputs
        inputs["scan"] = sid
        let sending = inputs
        group.addTask {
          do { return (tool.id, .success(try await api.runTool(tool.id, inputs: sending))) }
          catch { return (tool.id, .failure(error)) }
        }
      }
      for await (id, result) in group { results[id] = result }
    }
  }
}

struct ToolRow: View {
  var title: String
  var result: Result<ToolOutcome, any Error>?

  var body: some View {
    VStack(alignment: .leading, spacing: 4) {
      HStack {
        Text(title).font(.headline)
        Spacer()
        switch result {
        case .success(let r): StatusBadge(status: r.verdict.status)
        case .failure: StatusBadge(status: "unknown")
        case nil: ProgressView()
        }
      }
      switch result {
      case .success(let r): Text(r.verdict.text).font(.subheadline).foregroundStyle(.secondary)
      case .failure(let e): Text(e.localizedDescription).font(.subheadline).foregroundStyle(.secondary)
      case nil: EmptyView()
      }
    }
    .accessibilityElement(children: .combine)
  }
}

struct StatusBadge: View {
  var status: String

  var body: some View {
    let (word, color): (String, Color) = switch status {
    case "pass": ("Pass", .green)
    case "warn": ("Check", .orange)
    case "fail": ("Fail", .red)
    default: ("Unknown", .gray)
    }
    Text(word)
      .font(.caption.weight(.semibold))
      .padding(.horizontal, 8).padding(.vertical, 3)
      .foregroundStyle(color)
      .background(color.opacity(0.15), in: .capsule)
  }
}
