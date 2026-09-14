import AppKit
import WebKit
import Darwin


// Optional WindowServer API: isolates undocumented desktop blur support.
// No screen capture, tint manipulation, or foreground filtering is involved.
final class WindowBackdropBlur {
    typealias Connection = @convention(c) () -> Int32
    typealias SetRadius = @convention(c) (Int32, Int, Int32) -> Int32
    private let library: UnsafeMutableRawPointer?
    private let connection: Connection?
    private let setRadius: SetRadius?
    init() {
        library = dlopen("/System/Library/PrivateFrameworks/SkyLight.framework/SkyLight", RTLD_LAZY | RTLD_LOCAL)
        if let library,
           let get = dlsym(library, "CGSMainConnectionID"),
           let set = dlsym(library, "CGSSetWindowBackgroundBlurRadius") {
            connection = unsafeBitCast(get, to: Connection.self)
            setRadius = unsafeBitCast(set, to: SetRadius.self)
        } else { connection = nil; setRadius = nil }
    }
    func apply(window: NSWindow, radius: Double) -> Bool {
        guard radius.isFinite, (0...100).contains(radius), window.windowNumber > 0,
              let connection, let setRadius else { return false }
        return setRadius(connection(), window.windowNumber, Int32(radius.rounded())) == 0
    }
}

func nativeAppearanceScript(material: String, appearance: String? = nil) -> String {
    let state: [String: Any] = ["version": 1, "material": material, "tintPolicy": "system-theme-fixed"]
    let data = try! JSONSerialization.data(withJSONObject: state, options: [.sortedKeys])
    let json = String(data: data, encoding: .utf8)!
    let theme = appearance == nil
        ? "(window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light')"
        : (appearance == "dark" ? "'dark'" : "'light'")
    return """
    (() => {
      const state = Object.freeze({...\(json), appearance: \(theme)});
      window.borgnetNativeAppearance = state;
      document.documentElement?.setAttribute('data-native-material', state.material);
      document.documentElement?.setAttribute('data-native-appearance', state.appearance);
      window.dispatchEvent(new CustomEvent('borgnet-native-appearance', {detail: state}));
    })();
    """
}


func focusFrostAlpha(isKeyWindow: Bool) -> CGFloat {
    isKeyWindow ? 0.08 : 0
}


final class BorgNetAppDelegate: NSObject, NSApplicationDelegate, NSWindowDelegate, WKNavigationDelegate, WKScriptMessageHandler {
    private var workspaceURL: URL?
    private var window: NSWindow!
    private var webView: WKWebView!
    private var glassView: NSView?
    private var focusFrostView: NSVisualEffectView?
    private var focusShadeView: NSView?
    private var appearanceObservation: NSKeyValueObservation?
    private var darkAppearance: Bool?
    private var nativeMaterial = "visual-effect"
    private var userBlur: Double?
    private let radiusBlur = WindowBackdropBlur()
    private var fallbackMaterial: NSVisualEffectView?
    private let zoomSteps: [Double] = [0.5, 0.67, 0.75, 0.8, 0.9, 1, 1.1, 1.25, 1.5, 1.75, 2, 2.5, 3]
    private var zoomLabel: NSMenuItem?

    private func applyZoom(_ value: Double) {
        let zoom = min(3, max(0.5, value))
        webView.pageZoom = zoom
        UserDefaults.standard.set(zoom, forKey: "BorgNetPageZoom")
        zoomLabel?.title = "Zoom: \(Int((zoom * 100).rounded()))%"
    }
    @objc private func zoomIn(_ sender: Any?) {
        applyZoom(zoomSteps.first(where: { $0 > webView.pageZoom + 0.001 }) ?? 3)
    }
    @objc private func zoomOut(_ sender: Any?) {
        applyZoom(zoomSteps.last(where: { $0 < webView.pageZoom - 0.001 }) ?? 0.5)
    }
    @objc private func resetZoom(_ sender: Any?) { applyZoom(1) }


    func applicationDidFinishLaunching(_ notification: Notification) {
        configureMenu()

        let frame = NSRect(x: 0, y: 0, width: 1240, height: 840)
        window = NSWindow(
            contentRect: frame,
            styleMask: [.titled, .closable, .miniaturizable, .resizable],
            backing: .buffered,
            defer: false
        )
        window.title = "BorgNet Universal Interface"
        // Keep a visible native drag surface above the transparent glass content.
        window.titleVisibility = .visible
        window.titlebarAppearsTransparent = false
        window.titlebarSeparatorStyle = .line
        window.isOpaque = false
        window.backgroundColor = .clear
        window.hasShadow = true
        window.minSize = NSSize(width: 720, height: 560)
        window.delegate = self

        let container = NSView(frame: frame)
        container.autoresizingMask = [.width, .height]
        container.wantsLayer = true
        container.layer?.backgroundColor = NSColor.clear.cgColor

        if #available(macOS 26.0, *),
           ProcessInfo.processInfo.environment["BORGNET_MATERIAL"] != "visual-effect" {
            nativeMaterial = "liquid-glass"
        }

        if radiusBlur.apply(window: window, radius: 0) {
            nativeMaterial = "radius-blur"
            // WindowServer does not blur fully transparent pixels.
            window.backgroundColor = NSColor.black.withAlphaComponent(0.001)
        }
        let configuration = WKWebViewConfiguration()
        configuration.websiteDataStore = .default()
        configuration.userContentController.add(self, name: "borgnetBlur")
        configuration.userContentController.addUserScript(WKUserScript(
            source: nativeAppearanceScript(material: nativeMaterial),
            injectionTime: .atDocumentStart,
            forMainFrameOnly: true
        ))
        webView = WKWebView(frame: container.bounds, configuration: configuration)
        webView.autoresizingMask = [.width, .height]
        webView.navigationDelegate = self
        let savedZoom = UserDefaults.standard.double(forKey: "BorgNetPageZoom")
        applyZoom(savedZoom > 0 ? savedZoom : 1)
        webView.setValue(false, forKey: "drawsBackground")
        webView.underPageBackgroundColor = .clear
        webView.wantsLayer = true
        webView.layer?.backgroundColor = NSColor.clear.cgColor

        if nativeMaterial == "radius-blur" {
            container.addSubview(webView)
        } else if #available(macOS 26.0, *), nativeMaterial == "liquid-glass" {
            let glass = NSGlassEffectView(frame: container.bounds)
            glass.autoresizingMask = [.width, .height]
            glass.style = .clear
            // The window owns the outer corners; content meets the title bar flush.
            glass.cornerRadius = 0
            glass.alphaValue = 1
            let glassContent = NSView(frame: container.bounds)
            glassContent.translatesAutoresizingMaskIntoConstraints = false
            glassContent.wantsLayer = true
            glassContent.layer?.backgroundColor = NSColor.clear.cgColor
            let frost = NSVisualEffectView(frame: glassContent.bounds)
            frost.translatesAutoresizingMaskIntoConstraints = false
            frost.material = .hudWindow
            frost.blendingMode = .behindWindow
            frost.state = .active
            frost.isEmphasized = false
            frost.alphaValue = focusFrostAlpha(isKeyWindow: false)
            let shade = NSView(frame: glassContent.bounds)
            shade.translatesAutoresizingMaskIntoConstraints = false
            shade.wantsLayer = true
            shade.layer?.backgroundColor = NSColor.black.cgColor
            shade.alphaValue = 0
            webView.translatesAutoresizingMaskIntoConstraints = false
            // Soften only the backdrop, leaving text and controls outside the frost layer.
            glassContent.addSubview(frost)
            glassContent.addSubview(shade)
            glassContent.addSubview(webView)
            for view in [frost, shade, webView] as [NSView] {
                NSLayoutConstraint.activate([
                    view.leadingAnchor.constraint(equalTo: glassContent.leadingAnchor),
                    view.trailingAnchor.constraint(equalTo: glassContent.trailingAnchor),
                    view.topAnchor.constraint(equalTo: glassContent.topAnchor),
                    view.bottomAnchor.constraint(equalTo: glassContent.bottomAnchor),
                ])
            }
            glass.contentView = glassContent
            container.addSubview(glass)
            glassView = glass
            focusFrostView = frost
            focusShadeView = shade
        } else {
            let material = NSVisualEffectView(frame: container.bounds)
            material.autoresizingMask = [.width, .height]
            material.material = .hudWindow
            material.blendingMode = .behindWindow
            material.state = .active
            material.alphaValue = 0.48
            fallbackMaterial = material
            container.addSubview(material)
            container.addSubview(webView)
        }
        window.contentView = container
        synchronizeAppearance()
        appearanceObservation = NSApp.observe(\.effectiveAppearance, options: [.new]) { [weak self] _, _ in
            DispatchQueue.main.async {
                self?.synchronizeAppearance()
            }
        }

        let configuredURL = ProcessInfo.processInfo.environment["BORGNET_URL"]
            ?? "http://127.0.0.1:7337/?native=1"
        guard let url = URL(string: configuredURL), ["127.0.0.1", "localhost", "::1"].contains(url.host ?? ""), ["http", "https"].contains(url.scheme ?? ""), url.user == nil, url.password == nil else {
            fatalError("BORGNET_URL is not a valid URL")
        }
        workspaceURL = url
        loadAuthenticatedWorkspace()

        window.center()
        window.makeKeyAndOrderFront(nil)
        NSApp.activate(ignoringOtherApps: true)
        synchronizeFocusFrost(animated: false)
    }

    func applicationShouldTerminateAfterLastWindowClosed(_ sender: NSApplication) -> Bool {
        true
    }

    func windowDidBecomeKey(_ notification: Notification) {
        synchronizeFocusFrost(animated: true)
    }

    func windowDidResignKey(_ notification: Notification) {
        synchronizeFocusFrost(animated: true)
    }

    private func synchronizeFocusFrost(animated: Bool) {
        guard let frost = focusFrostView else { return }
        let alpha = userBlur.map { CGFloat($0 / 100) } ?? focusFrostAlpha(isKeyWindow: window.isKeyWindow)
        NSAnimationContext.runAnimationGroup { context in
            context.duration = animated && !NSWorkspace.shared.accessibilityDisplayShouldReduceMotion ? 0.16 : 0
            frost.animator().alphaValue = alpha
            // A two-percent dark backing improves contrast without fading the text.
            focusShadeView?.animator().alphaValue = window.isKeyWindow ? 0.02 : 0
        }
    }

    func userContentController(_ userContentController: WKUserContentController, didReceive message: WKScriptMessage) {
        guard message.name == "borgnetBlur", message.frameInfo.isMainFrame,
              let url = message.frameInfo.request.url,
              url.host == workspaceURL?.host, url.port == workspaceURL?.port, url.scheme == workspaceURL?.scheme,
              let body = message.body as? [String: Any] else { return }
        let radius: Double
        if body["reset"] as? Bool == true { radius = 0 }
        else if let value = body["radius"] as? Double, value.isFinite, (0...100).contains(value) { radius = value }
        else { return }
        let applied = nativeMaterial == "radius-blur" && radiusBlur.apply(window: window, radius: radius)
        webView.evaluateJavaScript("window.dispatchEvent(new CustomEvent('borgnet-blur-status',{detail:{available:\(applied),radius:\(radius)}}))")
    }

    private func synchronizeAppearance() {
        let dark = NSApp.effectiveAppearance.bestMatch(from: [.darkAqua, .aqua]) == .darkAqua
        guard darkAppearance != dark else { return }
        darkAppearance = dark
        let appearance = NSAppearance(named: dark ? .darkAqua : .aqua)
        window.appearance = appearance
        webView.appearance = appearance
        if #available(macOS 26.0, *), let glass = glassView as? NSGlassEffectView {
            glass.appearance = appearance
            // The assigned tint is focus-independent; AppKit still owns glass rendering.
            glass.tintColor = dark
                ? NSColor(srgbRed: 0.16, green: 0.17, blue: 0.18, alpha: 0.18)
                : NSColor(srgbRed: 0.96, green: 0.97, blue: 0.98, alpha: 0.12)
        }
        publishNativeAppearance()
    }

    private func publishNativeAppearance() {
        guard let dark = darkAppearance else { return }
        webView.evaluateJavaScript(nativeAppearanceScript(
            material: nativeMaterial,
            appearance: dark ? "dark" : "light"
        ))
    }

    func webView(_ webView: WKWebView, didFinish navigation: WKNavigation!) {
        publishNativeAppearance()
    }

    private func loadAuthenticatedWorkspace() {
        guard let url = workspaceURL else { return }
        var launchURL = URLComponents(url: url, resolvingAgainstBaseURL: false)!
        let home = FileManager.default.homeDirectoryForCurrentUser
        let configuredData = ProcessInfo.processInfo.environment["BORGNET_DATA_DIR"]
        let roots = configuredData.map { [URL(fileURLWithPath: ($0 as NSString).expandingTildeInPath)] }
            ?? [home.appendingPathComponent("Library/Application Support/BorgNet"), home.appendingPathComponent(".borgnet")]
        for root in roots {
            if let data = try? Data(contentsOf: root.appendingPathComponent("browser-session.json")),
               let object = try? JSONSerialization.jsonObject(with: data) as? [String: String],
               let token = object["token"] {
                launchURL.fragment = "session=" + token
                break
            }
        }
        // A changed fragment alone is a same-document navigation in WKWebView.
        launchURL.queryItems = (launchURL.queryItems ?? []).filter { $0.name != "reload" }
            + [URLQueryItem(name: "reload", value: UUID().uuidString)]
        webView.load(URLRequest(url: launchURL.url!, cachePolicy: .reloadIgnoringLocalCacheData))
    }

    @objc private func reloadWorkspace(_ sender: Any?) {
        loadAuthenticatedWorkspace()
    }

    func webView(_ webView: WKWebView, decidePolicyFor navigationAction: WKNavigationAction,
                 decisionHandler: @escaping (WKNavigationActionPolicy) -> Void) {
        guard let url = navigationAction.request.url,
              url.host == workspaceURL?.host, url.port == workspaceURL?.port, url.scheme == workspaceURL?.scheme else {
            decisionHandler(.cancel)
            return
        }
        decisionHandler(.allow)
    }

    func webView(_ webView: WKWebView, didFailProvisionalNavigation navigation: WKNavigation!, withError error: Error) {
        let alert = NSAlert()
        alert.messageText = "Start your BorgNet workspace"
        alert.informativeText = "Run borgnet serve in a terminal, then choose View → Reload. The default local address is http://127.0.0.1:7337."
        alert.addButton(withTitle: "OK")
        alert.beginSheetModal(for: window)
    }

    private func configureMenu() {
        let mainMenu = NSMenu()
        let appItem = NSMenuItem()
        let appMenu = NSMenu()
        appMenu.addItem(withTitle: "Quit BorgNet", action: #selector(NSApplication.terminate(_:)), keyEquivalent: "q")
        appItem.submenu = appMenu
        mainMenu.addItem(appItem)
        let editItem = NSMenuItem()
        let editMenu = NSMenu(title: "Edit")
        for (title, action, key) in [("Undo", "undo:", "z"), ("Cut", "cut:", "x"), ("Copy", "copy:", "c"), ("Paste", "paste:", "v"), ("Select All", "selectAll:", "a")] {
            editMenu.addItem(withTitle: title, action: Selector(action), keyEquivalent: key)
        }
        editItem.submenu = editMenu
        mainMenu.addItem(editItem)
        let viewItem = NSMenuItem()
        let viewMenu = NSMenu(title: "View")
        let reload = NSMenuItem(title: "Reload", action: #selector(reloadWorkspace(_:)), keyEquivalent: "r")
        reload.target = self
        viewMenu.addItem(reload)
        viewMenu.addItem(.separator())
        let scale = NSMenuItem(title: "Zoom: 100%", action: nil, keyEquivalent: "")
        viewMenu.addItem(scale)
        zoomLabel = scale
        for (title, action, key) in [
            ("Zoom In", #selector(zoomIn(_:)), "+"),
            ("Zoom Out", #selector(zoomOut(_:)), "-"),
            ("Actual Size", #selector(resetZoom(_:)), "0")
        ] {
            let item = NSMenuItem(title: title, action: action, keyEquivalent: key)
            item.target = self
            item.keyEquivalentModifierMask = [.command]
            viewMenu.addItem(item)
        }
        // Also accept Command = without requiring Shift on US keyboards.
        let equalZoom = NSMenuItem(title: "Zoom In", action: #selector(zoomIn(_:)), keyEquivalent: "=")
        equalZoom.target = self
        equalZoom.keyEquivalentModifierMask = [.command]
        equalZoom.isHidden = true
        equalZoom.allowsKeyEquivalentWhenHidden = true
        viewMenu.addItem(equalZoom)
        viewItem.submenu = viewMenu
        mainMenu.addItem(viewItem)
        NSApp.mainMenu = mainMenu
    }
}
let application = NSApplication.shared
let delegate = BorgNetAppDelegate()
application.setActivationPolicy(.regular)
application.delegate = delegate
application.run()
