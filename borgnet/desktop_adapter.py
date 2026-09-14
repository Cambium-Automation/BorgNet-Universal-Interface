"""Current-desktop controls. macOS requires TCC consent; Linux requires X11."""
import ctypes
import io
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time

from PIL import Image


def status():
    if sys.platform == 'darwin':
        try:
            import Quartz
            service = ctypes.CDLL('/System/Library/Frameworks/ApplicationServices.framework/ApplicationServices')
            service.AXIsProcessTrusted.restype = ctypes.c_bool
            accessibility = bool(service.AXIsProcessTrusted())
            recording = bool(Quartz.CGPreflightScreenCaptureAccess())
            return {'supported': True, 'ready': accessibility and recording,
                    'accessibility': accessibility, 'screen_recording': recording,
                    'message': 'macOS: grant Accessibility and Screen Recording to the launching terminal/Python app in System Settings, then restart it.'}
        except (ImportError, OSError):
            return {'supported': False, 'ready': False, 'message': 'Install the bundled Quartz dependencies.'}
    if sys.platform == 'linux':
        ready = bool(os.environ.get('DISPLAY')) and not bool(os.environ.get('WAYLAND_DISPLAY'))
        return {'supported': ready, 'ready': ready, 'message': 'Desktop control requires an X11 session; Wayland is not supported.'}
    return {'supported': False, 'ready': False, 'message': 'Desktop control supports macOS and Linux X11.'}


class Desktop:
    def __init__(self):
        self.observed = 0
        self.width = self.height = 0
        self.scale_x = self.scale_y = 1.0
        self.origin_x = self.origin_y = 0

    def check(self, observed=False):
        if not status()['ready']:
            raise ValueError(status()['message'])
        if observed and (not self.observed or time.monotonic() - self.observed > 60):
            raise ValueError('Take a fresh desktop screenshot before acting (valid for 60 seconds).')

    def screenshot(self):
        self.check()
        if sys.platform == 'darwin':
            import Quartz
            with tempfile.TemporaryDirectory(prefix='borgnet-screen-') as directory:
                path = Path(directory) / 'screen.png'
                subprocess.run(['/usr/sbin/screencapture', '-x', '-D', '1', '-t', 'png', str(path)],
                               check=True, capture_output=True, timeout=15)
                if path.stat().st_size > 64_000_000:
                    raise ValueError('Screenshot exceeds size limit')
                image = Image.open(path).convert('RGB')
            bounds = Quartz.CGDisplayBounds(Quartz.CGMainDisplayID())
            native_width, native_height = bounds.size.width, bounds.size.height
        else:
            import mss
            with mss.mss() as capture:
                monitor=capture.monitors[1]
                self.origin_x,self.origin_y=monitor["left"],monitor["top"]
                screen = capture.grab(monitor)
                image = Image.frombytes('RGB', screen.size, screen.rgb)
                native_width, native_height = image.size
        image.thumbnail((1600, 1000))
        self.width, self.height = image.size
        self.scale_x, self.scale_y = native_width / self.width, native_height / self.height
        self.observed = time.monotonic()
        output = io.BytesIO()
        image.save(output, format='PNG')
        return output.getvalue(), {'width': self.width, 'height': self.height,
                                   'coordinates': 'Use coordinates in this screenshot. Primary display only.'}

    def click(self, x, y, button='left'):
        self.check(observed=True)
        if not 0 <= x < self.width or not 0 <= y < self.height or button not in {'left','right'}:
            raise ValueError('Click must be within the last screenshot')
        x, y = self.origin_x + round(x * self.scale_x), self.origin_y + round(y * self.scale_y)
        if sys.platform == 'darwin':
            import Quartz as q
            btn = q.kCGMouseButtonLeft if button == 'left' else q.kCGMouseButtonRight
            events = (q.kCGEventLeftMouseDown, q.kCGEventLeftMouseUp) if button == 'left' else (q.kCGEventRightMouseDown, q.kCGEventRightMouseUp)
            for kind in events:
                q.CGEventPost(q.kCGHIDEventTap, q.CGEventCreateMouseEvent(None, kind, (x,y), btn))
        else:
            from Xlib import X, display
            from Xlib.ext import xtest
            connection = display.Display()
            try:
                xtest.fake_input(connection, X.MotionNotify, x=x, y=y)
                for kind in (X.ButtonPress, X.ButtonRelease):
                    xtest.fake_input(connection, kind, 1 if button == 'left' else 3)
                connection.sync()
            finally:
                connection.close()
        self.observed = 0

    def key(self, key):
        self.check(observed=True)
        names = {'Enter':36,'Tab':48,'Escape':53,'Backspace':51,'Left':123,'Right':124,'Down':125,'Up':126,'Space':49}
        if key not in names:
            raise ValueError('Supported keys: '+', '.join(names))
        if sys.platform == 'darwin':
            import Quartz as q
            for down in (True,False):
                q.CGEventPost(q.kCGHIDEventTap, q.CGEventCreateKeyboardEvent(None, names[key], down))
        else:
            from Xlib import X, XK, display
            from Xlib.ext import xtest
            connection=display.Display()
            try:
                symbol={'Enter':'Return','Backspace':'BackSpace','Space':'space'}.get(key,key)
                code=connection.keysym_to_keycode(XK.string_to_keysym(symbol))
                for kind in (X.KeyPress,X.KeyRelease): xtest.fake_input(connection,kind,code)
                connection.sync()
            finally: connection.close()
        self.observed=0

    def type_text(self, text):
        self.check(observed=True)
        if not text or len(text)>2000 or any(ord(c)<32 for c in text):
            raise ValueError('Enter 1–2,000 printable characters; use the key tool for Enter.')
        if sys.platform == 'darwin':
            import Quartz as q
            for chunk in [text[i:i+20] for i in range(0,len(text),20)]:
                for down in (True,False):
                    event=q.CGEventCreateKeyboardEvent(None,0,down)
                    q.CGEventKeyboardSetUnicodeString(event,len(chunk.encode('utf-16-le'))//2,chunk)
                    q.CGEventPost(q.kCGHIDEventTap,event)
        else:
            from Xlib import X, display
            from Xlib.ext import xtest
            connection=display.Display()
            try:
                # Respect the active keyboard layout; refuse characters needing unsupported modifiers.
                strokes=[]
                for char in text:
                    keys=connection.keysym_to_keycodes(ord(char))
                    usable=next(((code,level) for code,level in keys if level in (0,1)),None)
                    if usable is None: raise ValueError('Text contains a character unavailable in the current X11 keyboard layout')
                    strokes.append(usable)
                shift=connection.keysym_to_keycode(0xffe1)
                for code,level in strokes:
                    if level: xtest.fake_input(connection,X.KeyPress,shift)
                    xtest.fake_input(connection,X.KeyPress,code)
                    xtest.fake_input(connection,X.KeyRelease,code)
                    if level: xtest.fake_input(connection,X.KeyRelease,shift)
                connection.sync()
            finally: connection.close()
        self.observed=0

    def scroll(self, lines):
        self.check(observed=True)
        if not -20 <= lines <= 20 or not lines: raise ValueError('Scroll between -20 and 20 lines')
        if sys.platform == 'darwin':
            import Quartz as q
            q.CGEventPost(q.kCGHIDEventTap,q.CGEventCreateScrollWheelEvent(None,q.kCGScrollEventUnitLine,1,-lines))
        else:
            from Xlib import X, display
            from Xlib.ext import xtest
            connection=display.Display()
            try:
                for _ in range(abs(lines)):
                    for kind in (X.ButtonPress,X.ButtonRelease):xtest.fake_input(connection,kind,5 if lines>0 else 4)
                connection.sync()
            finally:connection.close()
        self.observed=0
