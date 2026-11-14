import SwiftUI

/// The part of a ScanPlan (Contract 1) the phone draws: metres, x and y on the floor.
nonisolated struct ScanPlan: Decodable, Sendable {
  struct Floor: Decodable, Sendable, Identifiable { var id: String; var label: String? }
  struct Wall: Decodable, Sendable { var id: String; var floor: String; var a: [Double]; var b: [Double] }
  struct Opening: Decodable, Sendable, Identifiable {
    var id: String; var floor: String; var type: String; var width: Double?; var center: [Double]; var wall: String?
  }
  struct Room: Decodable, Sendable, Identifiable {
    var id: String; var floor: String; var label: String?; var polygon: [[Double]]; var area: Double?
    var center: [Double]?
  }
  struct Object: Decodable, Sendable, Identifiable {
    var id: String; var floor: String; var label: String?; var center: [Double]; var size: [Double]; var yaw_deg: Double
  }
  struct Quality: Decodable, Sendable { var notes: [String] }
  var sid: String
  var name: String?
  var floors: [Floor]
  var walls: [Wall]
  var openings: [Opening]
  var rooms: [Room]
  var objects: [Object]?
  var quality: Quality?
}

/// A floor plan drawn from the plan's own numbers: rooms, walls, door and window gaps, and the objects RoomPlan found.
struct PlanView: View {
  var plan: ScanPlan
  var floor: String

  var body: some View {
    Canvas { ctx, size in
      let walls = plan.walls.filter { $0.floor == floor }
      let xs = walls.flatMap { [$0.a[0], $0.b[0]] }, ys = walls.flatMap { [$0.a[1], $0.b[1]] }
      guard let minX = xs.min(), let maxX = xs.max(), let minY = ys.min(), let maxY = ys.max() else { return }
      let scale = min((size.width - 24) / max(maxX - minX, 0.1), (size.height - 24) / max(maxY - minY, 0.1))
      let ox = (size.width - (maxX - minX) * scale) / 2, oy = (size.height - (maxY - minY) * scale) / 2
      func pt(_ x: Double, _ y: Double) -> CGPoint { CGPoint(x: ox + (x - minX) * scale, y: oy + (maxY - y) * scale) }

      for room in plan.rooms where room.floor == floor && room.polygon.count >= 3 {
        var path = Path()
        path.addLines(room.polygon.map { pt($0[0], $0[1]) })
        path.closeSubpath()
        ctx.fill(path, with: .color(.accentColor.opacity(0.08)))
      }
      for o in plan.objects ?? [] where o.floor == floor {
        let c = pt(o.center[0], o.center[1])
        let rect = CGRect(x: -o.size[0] * scale / 2, y: -o.size[1] * scale / 2, width: o.size[0] * scale, height: o.size[1] * scale)
        let shape = Path(roundedRect: rect, cornerRadius: 2)
          .applying(CGAffineTransform(rotationAngle: -o.yaw_deg * .pi / 180).concatenating(.init(translationX: c.x, y: c.y)))
        ctx.stroke(shape, with: .color(.secondary), lineWidth: 1)
      }
      for w in walls {
        var path = Path()
        path.move(to: pt(w.a[0], w.a[1]))
        path.addLine(to: pt(w.b[0], w.b[1]))
        ctx.stroke(path, with: .color(.primary), style: StrokeStyle(lineWidth: 3, lineCap: .square))
      }
      let wallByID = Dictionary(uniqueKeysWithValues: walls.map { ($0.id, $0) })
      for o in plan.openings where o.floor == floor {
        guard let w = o.wall.flatMap({ wallByID[$0] }), let width = o.width else { continue }
        let dx = w.b[0] - w.a[0], dy = w.b[1] - w.a[1], len = max(hypot(dx, dy), 1e-6)
        let ux = dx / len * width / 2, uy = dy / len * width / 2
        var gap = Path()
        gap.move(to: pt(o.center[0] - ux, o.center[1] - uy))
        gap.addLine(to: pt(o.center[0] + ux, o.center[1] + uy))
        let window = o.type == "window"
        ctx.stroke(gap, with: .color(window ? .cyan : Color(uiColor: .systemBackground)), lineWidth: window ? 2 : 5)
      }
      for room in plan.rooms where room.floor == floor {
        guard let c = room.center, let label = room.label else { continue }
        ctx.draw(Text(label).font(.caption2).foregroundStyle(.secondary), at: pt(c[0], c[1]))
      }
    }
    .accessibilityElement()
    .accessibilityLabel("Floor plan with \(plan.rooms.filter { $0.floor == floor }.count) rooms")
  }
}
