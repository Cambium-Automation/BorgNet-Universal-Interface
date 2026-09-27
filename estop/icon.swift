import AppKit
import Foundation

// Draw the Dock icon from source so the signed app and SHA-256 manifest cover it.
let output = URL(fileURLWithPath: CommandLine.arguments[1])
let size = 1024
guard let bitmap = NSBitmapImageRep(bitmapDataPlanes: nil, pixelsWide: size,
                                   pixelsHigh: size, bitsPerSample: 8,
                                   samplesPerPixel: 4, hasAlpha: true, isPlanar: false,
                                   colorSpaceName: .deviceRGB, bytesPerRow: 0,
                                   bitsPerPixel: 0),
      let context = NSGraphicsContext(bitmapImageRep: bitmap) else {
    fatalError("Could not create E-stop icon")
}
NSGraphicsContext.saveGraphicsState()
NSGraphicsContext.current = context
context.imageInterpolation = .high

let tile = NSRect(x: 46, y: 46, width: 932, height: 932)
let frame = NSBezierPath(roundedRect: tile, xRadius: 202, yRadius: 202)
let tileShadow = NSShadow()
tileShadow.shadowColor = NSColor.black.withAlphaComponent(0.55)
tileShadow.shadowOffset = NSSize(width: 0, height: -15)
tileShadow.shadowBlurRadius = 24
NSGraphicsContext.saveGraphicsState()
tileShadow.set()
NSColor(white: 0.05, alpha: 1).setFill()
frame.fill()
NSGraphicsContext.restoreGraphicsState()

let inner = NSBezierPath(roundedRect: tile.insetBy(dx: 25, dy: 25),
                         xRadius: 178, yRadius: 178)
NSGraphicsContext.saveGraphicsState()
inner.addClip()
NSColor(srgbRed: 0.99, green: 0.79, blue: 0.06, alpha: 1).setFill()
inner.fill()
NSColor(white: 0.045, alpha: 1).setFill()
let stripeWidth: CGFloat = 93
var x: CGFloat = -size.cgFloat - stripeWidth
while x < size.cgFloat + stripeWidth {
    let stripe = NSBezierPath()
    stripe.move(to: NSPoint(x: x, y: 0))
    stripe.line(to: NSPoint(x: x + stripeWidth, y: 0))
    stripe.line(to: NSPoint(x: x + stripeWidth + size.cgFloat, y: size.cgFloat))
    stripe.line(to: NSPoint(x: x + size.cgFloat, y: size.cgFloat))
    stripe.close()
    stripe.fill()
    x += stripeWidth * 2
}
NSGraphicsContext.restoreGraphicsState()

let bezel = NSBezierPath(ovalIn: NSRect(x: 191, y: 174, width: 642, height: 642))
let buttonShadow = NSShadow()
buttonShadow.shadowColor = NSColor.black.withAlphaComponent(0.85)
buttonShadow.shadowOffset = NSSize(width: 0, height: -19)
buttonShadow.shadowBlurRadius = 27
NSGraphicsContext.saveGraphicsState()
buttonShadow.set()
NSColor(white: 0.07, alpha: 1).setFill()
bezel.fill()
NSGraphicsContext.restoreGraphicsState()

let button = NSBezierPath(ovalIn: NSRect(x: 231, y: 216, width: 562, height: 562))
NSGradient(starting: NSColor(srgbRed: 1, green: 0.15, blue: 0.13, alpha: 1),
           ending: NSColor(srgbRed: 0.58, green: 0.01, blue: 0.03, alpha: 1))!
    .draw(in: button, angle: -70)
NSColor.white.withAlphaComponent(0.85).setStroke()
bezel.lineWidth = 11
bezel.stroke()
NSColor.black.withAlphaComponent(0.5).setStroke()
button.lineWidth = 9
button.stroke()

let style = NSMutableParagraphStyle()
style.alignment = .center
("STOP" as NSString).draw(in: NSRect(x: 275, y: 420, width: 474, height: 150),
                           withAttributes: [
                            .font: NSFont.systemFont(ofSize: 150, weight: .black),
                            .foregroundColor: NSColor.white,
                            .paragraphStyle: style
                           ])

context.flushGraphics()
NSGraphicsContext.restoreGraphicsState()
guard let data = bitmap.representation(using: .png, properties: [:]) else {
    fatalError("Could not encode E-stop icon")
}
try data.write(to: output)

private extension Int {
    var cgFloat: CGFloat { CGFloat(self) }
}
