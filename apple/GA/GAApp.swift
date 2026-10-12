import SwiftUI

@main
struct GAApp: App {
    @State private var readingStore = ReadingStore()
    @State private var accessStore = AccessStore()
    @Environment(\.scenePhase) private var scenePhase

    var body: some Scene {
        WindowGroup {
            LibraryScreen()
                .environment(readingStore)
                .environment(accessStore)
                .task { await accessStore.start() }
                .task { await readingStore.start() }
                .onChange(of: scenePhase) { _, phase in
                    if phase == .active {
                        Task { await readingStore.sync()
                        await accessStore.refresh() }
                    } else {
                        readingStore.flush()
                    }
                }
        }
        #if os(macOS)
        .defaultSize(width: 1280, height: 800)
        .commands {
            SidebarCommands()
        }
        #endif
    }
}
