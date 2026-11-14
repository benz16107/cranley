import SwiftUI

@main
struct ThresholdApp: App {
  @State private var app = AppModel()

  var body: some Scene {
    WindowGroup {
      TabView {
        Tab("Home", systemImage: "house") { HomeView() }
        Tab("Measure", systemImage: "ruler") { MeasureView() }
        Tab("Workspace", systemImage: "link") { WorkspaceView() }
      }
      .environment(app)
      .onOpenURL { app.link($0.absoluteString) }
    }
  }
}
