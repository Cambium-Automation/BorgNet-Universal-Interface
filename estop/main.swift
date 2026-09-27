import AppKit
import CryptoKit
import Darwin

private let expectedHelperSHA256 = "__HELPER_SHA256__"

private final class HazardStripeView: NSView {
    override func draw(_ dirtyRect: NSRect) {
        super.draw(dirtyRect)
        NSColor(srgbRed: 0.98, green: 0.78, blue: 0.09, alpha: 1).setFill()
        bounds.fill()

        NSColor(srgbRed: 0.06, green: 0.06, blue: 0.06, alpha: 1).setFill()
        let stripeWidth: CGFloat = 56
        var x = -bounds.height - stripeWidth
        while x < bounds.width + stripeWidth {
            let stripe = NSBezierPath()
            stripe.move(to: NSPoint(x: x, y: 0))
            stripe.line(to: NSPoint(x: x + stripeWidth, y: 0))
            stripe.line(to: NSPoint(x: x + stripeWidth + bounds.height, y: bounds.height))
            stripe.line(to: NSPoint(x: x + bounds.height, y: bounds.height))
            stripe.close()
            stripe.fill()
            x += stripeWidth * 2
        }
    }
}

private final class EmergencyButton: NSButton {
    override func draw(_ dirtyRect: NSRect) {
        let diameter = min(bounds.width, bounds.height) - 14
        let frame = NSRect(x: bounds.midX - diameter / 2,
                           y: bounds.midY - diameter / 2,
                           width: diameter, height: diameter)
        let rim = NSBezierPath(ovalIn: frame)
        let shadow = NSShadow()
        shadow.shadowColor = NSColor.black.withAlphaComponent(0.85)
        shadow.shadowOffset = NSSize(width: 0, height: -8)
        shadow.shadowBlurRadius = 13
        NSGraphicsContext.saveGraphicsState()
        shadow.set()
        NSColor(white: 0.09, alpha: 1).setFill()
        rim.fill()
        NSGraphicsContext.restoreGraphicsState()

        let faceRect = frame.insetBy(dx: 11, dy: 11)
        let face = NSBezierPath(ovalIn: faceRect)
        let gradient = NSGradient(starting: isEnabled
            ? NSColor(srgbRed: 0.99, green: 0.12, blue: 0.12, alpha: 1)
            : NSColor(srgbRed: 0.70, green: 0.13, blue: 0.13, alpha: 1),
            ending: isEnabled
            ? NSColor(srgbRed: 0.56, green: 0.01, blue: 0.03, alpha: 1)
            : NSColor(srgbRed: 0.38, green: 0.04, blue: 0.05, alpha: 1))!
        gradient.draw(in: face, angle: -70)
        NSColor.white.withAlphaComponent(isEnabled ? 0.78 : 0.43).setStroke()
        rim.lineWidth = 3
        rim.stroke()
        NSColor.black.withAlphaComponent(0.48).setStroke()
        face.lineWidth = 3
        face.stroke()

        let style = NSMutableParagraphStyle()
        style.alignment = .center
        let attributes: [NSAttributedString.Key: Any] = [
            .font: NSFont.systemFont(ofSize: 27, weight: .black),
            .foregroundColor: NSColor.white,
            .paragraphStyle: style
        ]
        ("E-STOP" as NSString).draw(in: NSRect(x: faceRect.minX + 12, y: faceRect.midY - 9,
                                                width: faceRect.width - 24, height: 36),
                                    withAttributes: attributes)
        let subattributes: [NSAttributedString.Key: Any] = [
            .font: NSFont.systemFont(ofSize: 12, weight: .bold),
            .foregroundColor: NSColor.white.withAlphaComponent(0.9),
            .paragraphStyle: style
        ]
        ("SSH + AGENTS" as NSString).draw(in: NSRect(x: faceRect.minX + 12, y: faceRect.midY - 30,
                                                       width: faceRect.width - 24, height: 18),
                                           withAttributes: subattributes)
    }

    override func drawFocusRingMask() {
        NSBezierPath(ovalIn: bounds.insetBy(dx: 7, dy: 7)).fill()
    }
}

final class EStopApp: NSObject, NSApplicationDelegate {
    private var window: NSWindow!
    private var summary: NSTextField!
    private var detail: NSTextView!
    private var stopButton: NSButton!
    private var ownerPID: pid_t?
    private var ownerTimer: Timer?
    private var helperURL: URL {
        Bundle.main.resourceURL!.appendingPathComponent("stop.py")
    }

    private let installedApp = "/Applications/BorgNet E-Stop.app"
    private let manifestPath = "/Library/Application Support/BorgNet E-Stop/SHA256SUMS"

    func applicationDidFinishLaunching(_ notification: Notification) {
        if let ownerFlag = CommandLine.arguments.firstIndex(of: "--borgnet-owner-pid") {
            guard ownerFlag + 1 < CommandLine.arguments.count,
                  let pid = pid_t(CommandLine.arguments[ownerFlag + 1]),
                  pid > 1, getppid() == pid else {
                NSApp.terminate(nil)
                return
            }
            ownerPID = pid
        }
        NSApp.setActivationPolicy(.regular)
        let menu = NSMenu()
        let appItem = NSMenuItem()
        menu.addItem(appItem)
        let appMenu = NSMenu()
        appMenu.addItem(NSMenuItem(title: "Quit BorgNet E-Stop", action: #selector(NSApplication.terminate(_:)), keyEquivalent: "q"))
        appItem.submenu = appMenu
        NSApp.mainMenu = menu
        window = NSWindow(contentRect: NSRect(x: 0, y: 0, width: 740, height: 760),
                          styleMask: [.titled, .closable, .miniaturizable],
                          backing: .buffered, defer: false)
        window.title = "BorgNet E-Stop"
        window.center()
        window.isReleasedWhenClosed = false

        let background = HazardStripeView(frame: window.contentView!.bounds)
        background.autoresizingMask = [.width, .height]
        window.contentView?.addSubview(background)

        let introduction = NSStackView()
        introduction.orientation = .vertical
        introduction.alignment = .leading
        introduction.spacing = 9
        introduction.edgeInsets = NSEdgeInsets(top: 15, left: 16, bottom: 15, right: 16)
        introduction.wantsLayer = true
        introduction.layer?.backgroundColor = NSColor.black.withAlphaComponent(0.91).cgColor
        introduction.layer?.cornerRadius = 14
        introduction.translatesAutoresizingMaskIntoConstraints = false
        window.contentView?.addSubview(introduction)
        NSLayoutConstraint.activate([
            introduction.widthAnchor.constraint(equalToConstant: 680),
            introduction.centerXAnchor.constraint(equalTo: window.contentView!.centerXAnchor),
            introduction.topAnchor.constraint(equalTo: window.contentView!.topAnchor, constant: 20)
        ])

        let title = NSTextField(labelWithString: "Emergency stop")
        title.font = .systemFont(ofSize: 30, weight: .bold)
        title.textColor = .white
        introduction.addArrangedSubview(title)

        let explanation = NSTextField(wrappingLabelWithString:
            "After a fresh Mac account password check, stop BorgNet, active SSH sessions, and AI agent processes on this Mac. Running agent work will be interrupted. Background jobs stay disabled until you re-enable them.")
        explanation.font = .systemFont(ofSize: 13)
        explanation.textColor = .white
        explanation.maximumNumberOfLines = 4
        introduction.addArrangedSubview(explanation)
        explanation.widthAnchor.constraint(equalToConstant: 648).isActive = true

        stopButton = EmergencyButton(title: "E-STOP", target: self, action: #selector(stopAll))
        stopButton.isBordered = false
        stopButton.keyEquivalent = ""
        stopButton.setAccessibilityLabel("Emergency stop: stop all SSH sessions and agent processes")
        stopButton.toolTip = "Requires your current Mac account password before stopping anything"
        stopButton.translatesAutoresizingMaskIntoConstraints = false
        window.contentView?.addSubview(stopButton)
        NSLayoutConstraint.activate([
            stopButton.widthAnchor.constraint(equalToConstant: 204),
            stopButton.heightAnchor.constraint(equalToConstant: 204),
            stopButton.centerXAnchor.constraint(equalTo: window.contentView!.centerXAnchor),
            stopButton.centerYAnchor.constraint(equalTo: window.contentView!.centerYAnchor)
        ])

        let report = NSStackView()
        report.orientation = .vertical
        report.alignment = .leading
        report.spacing = 9
        report.edgeInsets = NSEdgeInsets(top: 14, left: 15, bottom: 14, right: 15)
        report.wantsLayer = true
        report.layer?.backgroundColor = NSColor.black.withAlphaComponent(0.93).cgColor
        report.layer?.cornerRadius = 14
        report.translatesAutoresizingMaskIntoConstraints = false
        window.contentView?.addSubview(report)
        NSLayoutConstraint.activate([
            report.widthAnchor.constraint(equalToConstant: 680),
            report.centerXAnchor.constraint(equalTo: window.contentView!.centerXAnchor),
            report.bottomAnchor.constraint(equalTo: window.contentView!.bottomAnchor, constant: -20)
        ])

        summary = NSTextField(wrappingLabelWithString: "Checking bundled stop program…")
        summary.font = .systemFont(ofSize: 13, weight: .semibold)
        summary.textColor = .white
        summary.widthAnchor.constraint(equalToConstant: 650).isActive = true
        report.addArrangedSubview(summary)

        let buttons = NSStackView()
        buttons.orientation = .horizontal
        let preview = NSButton(title: "Preview targets", target: self, action: #selector(previewTargets))
        preview.bezelStyle = .rounded
        buttons.addArrangedSubview(preview)
        report.addArrangedSubview(buttons)

        let scroll = NSScrollView()
        scroll.hasVerticalScroller = true
        scroll.borderType = .lineBorder
        detail = NSTextView(frame: NSRect(x: 0, y: 0, width: 650, height: 145))
        detail.isEditable = false
        detail.isSelectable = true
        detail.font = .monospacedSystemFont(ofSize: 11, weight: .regular)
        detail.backgroundColor = NSColor(srgbRed: 0.07, green: 0.07, blue: 0.07, alpha: 1)
        detail.textColor = .white
        detail.string = "Preview is read-only. The live stop requires your current macOS password.\n"
        scroll.documentView = detail
        report.addArrangedSubview(scroll)
        scroll.widthAnchor.constraint(equalToConstant: 650).isActive = true
        scroll.heightAnchor.constraint(equalToConstant: 145).isActive = true

        let good = integrityOK()
        stopButton.isEnabled = good
        summary.stringValue = good
            ? "Root-owned app and trusted SHA-256 manifest verified"
            : "NOT PROTECTED — install the verified build with Mac admin authorization."
        summary.textColor = good ? .systemGreen : .systemRed
        if ownerPID == nil {
            window.makeKeyAndOrderFront(nil)
            NSApp.activate(ignoringOtherApps: true)
        } else {
            window.orderFront(nil)
            ownerTimer = Timer.scheduledTimer(withTimeInterval: 0.35, repeats: true) { [weak self] _ in
                guard let self, let owner = self.ownerPID else { return }
                if getppid() != owner { NSApp.terminate(nil) }
            }
        }
    }

    func applicationShouldTerminateAfterLastWindowClosed(_ sender: NSApplication) -> Bool {
        true
    }

    private func helperDigest() -> String? {
        guard let data = try? Data(contentsOf: helperURL) else { return nil }
        return SHA256.hash(data: data).map { String(format: "%02x", $0) }.joined()
    }

    private func rootProtected(_ path: String, immutable: Bool = false) -> Bool {
        var info = stat()
        guard lstat(path, &info) == 0, info.st_uid == 0,
              (info.st_mode & mode_t(S_IFMT)) != mode_t(S_IFLNK),
              (info.st_mode & 0o022) == 0 else { return false }
        if immutable && (info.st_flags & UInt32(UF_IMMUTABLE)) == 0 { return false }
        return true
    }

    private func integrityOK() -> Bool {
        guard Bundle.main.bundleURL.standardizedFileURL.path == installedApp,
              rootProtected(installedApp, immutable: true),
              rootProtected(installedApp + "/Contents", immutable: true),
              rootProtected(installedApp + "/Contents/MacOS", immutable: true),
              rootProtected(installedApp + "/Contents/Resources", immutable: true),
              rootProtected(installedApp + "/Contents/MacOS/BorgNetEStop", immutable: true),
              rootProtected(helperURL.path, immutable: true),
              rootProtected("/Library/Application Support/BorgNet E-Stop"),
              rootProtected(manifestPath, immutable: true),
              helperDigest() == expectedHelperSHA256,
              let manifest = try? String(contentsOfFile: manifestPath, encoding: .utf8) else {
            return false
        }
        let lines = manifest.split(separator: "\n")
        guard lines.count >= 3 else { return false }
        var paths = Set<String>()
        for line in lines {
            guard let gap = line.range(of: "  ") else { return false }
            let expected = String(line[..<gap.lowerBound])
            let relative = String(line[gap.upperBound...])
            guard expected.count == 64,
                  relative.hasPrefix("BorgNet E-Stop.app/"),
                  !relative.contains("..") else { return false }
            let file = "/Applications/" + relative
            guard rootProtected(file, immutable: true),
                  let data = try? Data(contentsOf: URL(fileURLWithPath: file)) else { return false }
            let digest = SHA256.hash(data: data).map { String(format: "%02x", $0) }.joined()
            guard digest == expected else { return false }
            paths.insert(relative)
        }
        return paths.contains("BorgNet E-Stop.app/Contents/MacOS/BorgNetEStop") &&
               paths.contains("BorgNet E-Stop.app/Contents/Resources/stop.py")
    }

    private func runHelper(_ action: String, password: String? = nil) -> (Int32, String) {
        let task = Process()
        task.executableURL = URL(fileURLWithPath: "/usr/bin/python3")
        task.arguments = [helperURL.path, action]
        let output = Pipe()
        task.standardOutput = output
        task.standardError = output
        if let password {
            let input = Pipe()
            task.standardInput = input
            do {
                try task.run()
                input.fileHandleForWriting.write(Data((password + "\n").utf8))
                try? input.fileHandleForWriting.close()
            } catch {
                return (1, "Could not launch stop program: \(error.localizedDescription)")
            }
        } else {
            do { try task.run() }
            catch { return (1, "Could not launch preview: \(error.localizedDescription)") }
        }
        let data = output.fileHandleForReading.readDataToEndOfFile()
        task.waitUntilExit()
        return (task.terminationStatus, String(data: data, encoding: .utf8) ?? "Invalid stop report")
    }

    private func present(_ raw: String, code: Int32, action: String) {
        guard let data = raw.data(using: .utf8),
              let object = try? JSONSerialization.jsonObject(with: data) as? [String: Any] else {
            detail.string = "\(action) failed: \(raw)"
            return
        }
        if let error = object["error"] as? String {
            detail.string = error
            return
        }
        let state = (action == "Preview") ? object : (object["planned"] as? [String: Any] ?? [:])
        let jobs = state["jobs"] as? [String] ?? []
        let processes = state["processes"] as? [[String: Any]] ?? []
        var lines = ["\(action): \(jobs.count) launch jobs, \(processes.count) processes"]
        if !jobs.isEmpty { lines += ["", "Launch jobs:"] + jobs.map { "  \($0)" } }
        if !processes.isEmpty {
            lines.append("\nProcesses:")
            for item in processes {
                let pid = item["pid"] as? Int ?? 0
                let category = item["category"] as? String ?? "?"
                let command = item["command"] as? String ?? "?"
                lines.append("  [\(category)] \(pid)  \(String(command.prefix(120)))")
            }
        }
        if action == "Stop" {
            let errors = object["errors"] as? [String] ?? []
            let remaining = object["remaining"] as? [String: Any] ?? [:]
            let survivors = remaining["processes"] as? [[String: Any]] ?? []
            lines.append("\nStopped PIDs: \((object["killed_pids"] as? [Int] ?? []).count)")
            lines.append("Remaining agent/SSH processes: \(survivors.count)")
            if !errors.isEmpty { lines += ["Errors:"] + errors.map { "  \($0)" } }
            if let path = object["report_path"] as? String { lines.append("Report: \(path)") }
            summary.stringValue = code == 0 ? "E-STOP COMPLETE" : "E-STOP PARTIAL — review the report"
            summary.textColor = code == 0 ? .systemGreen : .systemOrange
        }
        detail.string = lines.joined(separator: "\n")
    }

    @objc private func previewTargets(_ sender: Any?) {
        guard helperDigest() == expectedHelperSHA256 else {
            detail.string = "Bundled stop program SHA-256 mismatch; preview unavailable."
            return
        }
        let (code, raw) = runHelper("--preview")
        present(raw, code: code, action: "Preview")
    }

    @objc private func stopAll(_ sender: Any?) {
        guard integrityOK() else {
            summary.stringValue = "INTEGRITY CHECK FAILED — stop disabled."
            stopButton.isEnabled = false
            return
        }
        let alert = NSAlert()
        alert.messageText = "Stop all SSH and agents on this Mac?"
        alert.informativeText = "This closes active SSH sessions and interrupts BorgNet, Codex, ChatGPT, and other detected agents. Enter your current Mac account password. The password is checked locally by macOS sudo and is not saved."
        alert.alertStyle = .critical
        alert.addButton(withTitle: "STOP NOW")
        alert.addButton(withTitle: "Cancel")
        let field = NSSecureTextField(frame: NSRect(x: 0, y: 0, width: 320, height: 25))
        field.placeholderString = "Mac account password"
        alert.accessoryView = field
        guard alert.runModal() == .alertFirstButtonReturn else { return }
        let password = field.stringValue
        field.stringValue = ""
        guard !password.isEmpty else { detail.string = "Password required; nothing was stopped."; return }
        stopButton.isEnabled = false
        summary.stringValue = "Stopping SSH and agents…"
        let (code, raw) = runHelper("--execute", password: password)
        present(raw, code: code, action: "Stop")
        stopButton.isEnabled = integrityOK()
    }
}

let app = NSApplication.shared
let delegate = EStopApp()
app.delegate = delegate
app.run()
