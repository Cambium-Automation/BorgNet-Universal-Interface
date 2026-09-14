import AppKit

// The same connected B mark used by the interface, drawn at every Dock size.
let destination = CommandLine.arguments[1]
try FileManager.default.createDirectory(atPath: destination, withIntermediateDirectories: true)
func render(_ size: Int, _ filename: String) throws {
    let bitmap = NSBitmapImageRep(bitmapDataPlanes: nil, pixelsWide: size, pixelsHigh: size,
        bitsPerSample: 8, samplesPerPixel: 4, hasAlpha: true, isPlanar: false,
        colorSpaceName: .deviceRGB, bytesPerRow: 0, bitsPerPixel: 0)!
    NSGraphicsContext.saveGraphicsState()
    NSGraphicsContext.current = NSGraphicsContext(bitmapImageRep: bitmap)
    let scale = CGFloat(size) / 1024
    let transform = NSAffineTransform(); transform.scale(by: scale); transform.concat()
    let tile = NSBezierPath(roundedRect: NSRect(x: 70, y: 70, width: 884, height: 884), xRadius: 190, yRadius: 190)
    NSGraphicsContext.saveGraphicsState()
    let shadow = NSShadow(); shadow.shadowColor = NSColor.black.withAlphaComponent(0.35)
    shadow.shadowBlurRadius = 28; shadow.shadowOffset = NSSize(width: 0, height: -12); shadow.set()
    NSColor(srgbRed: 0.10, green: 0.17, blue: 0.19, alpha: 1).setFill(); tile.fill()
    NSGraphicsContext.restoreGraphicsState()
    NSGradient(starting: NSColor(srgbRed: 0.24, green: 0.40, blue: 0.43, alpha: 1),
               ending: NSColor(srgbRed: 0.06, green: 0.12, blue: 0.16, alpha: 1))!.draw(in: tile, angle: -70)
    NSColor.white.withAlphaComponent(0.22).setStroke(); tile.lineWidth = 5; tile.stroke()
    let mark = NSBezierPath(); mark.move(to: NSPoint(x: 290, y: 735))
    mark.line(to: NSPoint(x: 590, y: 735)); mark.line(to: NSPoint(x: 755, y: 512))
    mark.line(to: NSPoint(x: 590, y: 289)); mark.line(to: NSPoint(x: 290, y: 289)); mark.close()
    mark.move(to: NSPoint(x: 290, y: 512)); mark.line(to: NSPoint(x: 755, y: 512))
    mark.move(to: NSPoint(x: 443, y: 735)); mark.line(to: NSPoint(x: 443, y: 289))
    mark.lineWidth = 33; mark.lineJoinStyle = .round; mark.lineCapStyle = .round
    NSColor(srgbRed: 0.72, green: 0.88, blue: 0.83, alpha: 1).setStroke(); mark.stroke()
    let node = NSBezierPath(ovalIn: NSRect(x: 708, y: 465, width: 94, height: 94))
    NSColor(srgbRed: 0.82, green: 0.98, blue: 0.90, alpha: 1).setFill(); node.fill()
    NSGraphicsContext.restoreGraphicsState()
    try bitmap.representation(using: .png, properties: [:])!.write(to: URL(fileURLWithPath: destination).appendingPathComponent(filename))
}
for size in [16, 32, 128, 256, 512] {
    try render(size, "icon_\(size)x\(size).png")
    try render(size * 2, "icon_\(size)x\(size)@2x.png")
}
