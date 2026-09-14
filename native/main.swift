import AppKit
import WebKit


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


final class BorgNetAppDelegate: NSObject, NSApplicationDelegate, NSWindowDelegate, WKNavigationDelegate {
    private var window: NSWindow!
    private var webView: WKWebView!
    private var glassView: NSView?
    private var focusFrostView: NSVisualEffectView?
    private var focusShadeView: NSView?
    private var appearanceObservation: NSKeyValueObservation?
    private var darkAppearance: Bool?
    private var nativeMaterial = "visual-effect"

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

        let configuration = WKWebViewConfiguration()
        configuration.websiteDataStore = .default()
        configuration.userContentController.addUserScript(WKUserScript(
            source: nativeAppearanceScript(material: nativeMaterial),
            injectionTime: .atDocumentStart,
            forMainFrameOnly: true
        ))
        webView = WKWebView(frame: container.bounds, configuration: configuration)
        webView.autoresizingMask = [.width, .height]
        webView.navigationDelegate = self
        webView.setValue(false, forKey: "drawsBackground")
        webView.underPageBackgroundColor = .clear
        webView.wantsLayer = true
        webView.layer?.backgroundColor = NSColor.clear.cgColor

        if #available(macOS 26.0, *), nativeMaterial == "liquid-glass" {
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
            frost.blendingMode = .withinWindow
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
        guard let url = URL(string: configuredURL) else {
            fatalError("BORGNET_URL is not a valid URL")
        }
        webView.load(URLRequest(url: url, cachePolicy: .reloadIgnoringLocalCacheData))

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
        let alpha = focusFrostAlpha(isKeyWindow: window.isKeyWindow)
        NSAnimationContext.runAnimationGroup { context in
            context.duration = animated && !NSWorkspace.shared.accessibilityDisplayShouldReduceMotion ? 0.16 : 0
            frost.animator().alphaValue = alpha
            // A two-percent dark backing improves contrast without fading the text.
            focusShadeView?.animator().alphaValue = window.isKeyWindow ? 0.02 : 0
        }
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

    @objc private func reloadWorkspace(_ sender: Any?) {
        webView.reloadFromOrigin()
    }

    func webView(_ webView: WKWebView, decidePolicyFor navigationAction: WKNavigationAction,
                 decisionHandler: @escaping (WKNavigationActionPolicy) -> Void) {
        guard let url = navigationAction.request.url,
              ["127.0.0.1", "localhost", "::1"].contains(url.host ?? ""),
              ["http", "https"].contains(url.scheme ?? "") else {
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
