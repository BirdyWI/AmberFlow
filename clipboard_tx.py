"""Experimental Windows paste transaction. No transcript/audio persistence.

Inspired by Handy's receipt-sequenced approach; independent Python implementation.
Delayed rendering observes the FIRST materialization, not successful insertion.
No automatic retry and no fallback that discards unsupported clipboard formats.
"""
import ctypes as C
from ctypes import wintypes as W
import threading
import time
from contextlib import contextmanager

U = C.WinDLL('user32', use_last_error=True)
K = C.WinDLL('kernel32', use_last_error=True)
G = C.WinDLL('gdi32', use_last_error=True)
PTR = C.c_void_p
PROC = C.WINFUNCTYPE(C.c_ssize_t, W.HWND, W.UINT, W.WPARAM, W.LPARAM)

def api(lib, name, result, *args):
    f = getattr(lib, name)
    f.restype, f.argtypes = result, list(args)
    return f

api(U, 'OpenClipboard', W.BOOL, W.HWND)
api(U, 'CloseClipboard', W.BOOL)
api(U, 'EmptyClipboard', W.BOOL)
api(U, 'GetClipboardData', PTR, W.UINT)
api(U, 'SetClipboardData', PTR, W.UINT, PTR)
api(U, 'EnumClipboardFormats', W.UINT, W.UINT)
api(U, 'GetClipboardOwner', W.HWND)
api(U, 'GetClipboardSequenceNumber', W.DWORD)
api(U, 'RegisterClipboardFormatW', W.UINT, W.LPCWSTR)
api(U, 'GetClipboardFormatNameW', C.c_int, W.UINT, W.LPWSTR, C.c_int)
api(U, 'CopyImage', PTR, PTR, W.UINT, C.c_int, C.c_int, W.UINT)
api(G, 'DeleteObject', W.BOOL, PTR)
api(K, 'GlobalAlloc', PTR, W.UINT, C.c_size_t)
api(K, 'GlobalLock', PTR, PTR)
api(K, 'GlobalUnlock', W.BOOL, PTR)
api(K, 'GlobalSize', C.c_size_t, PTR)
api(K, 'GlobalFree', PTR, PTR)
api(K, 'GetProcessHeap', PTR)
api(K, 'HeapFree', W.BOOL, PTR, W.DWORD, PTR)
api(K, 'GetModuleHandleW', W.HMODULE, W.LPCWSTR)
api(U, 'DefWindowProcW', C.c_ssize_t, W.HWND, W.UINT, W.WPARAM, W.LPARAM)
api(U, 'CreateWindowExW', W.HWND, W.DWORD, W.LPCWSTR, W.LPCWSTR, W.DWORD,
    C.c_int, C.c_int, C.c_int, C.c_int, W.HWND, W.HMENU, W.HINSTANCE, PTR)
api(U, 'DestroyWindow', W.BOOL, W.HWND)
api(U, 'PeekMessageW', W.BOOL, C.POINTER(W.MSG), W.HWND, W.UINT, W.UINT, W.UINT)
api(U, 'TranslateMessage', W.BOOL, C.POINTER(W.MSG))
api(U, 'DispatchMessageW', C.c_ssize_t, C.POINTER(W.MSG))
api(U, 'GetForegroundWindow', W.HWND)

class WNDCLASS(C.Structure):
    _fields_ = [('style', W.UINT), ('proc', PROC), ('extra', C.c_int),
                ('window_extra', C.c_int), ('instance', W.HINSTANCE),
                ('icon', W.HICON), ('cursor', W.HANDLE), ('background', W.HBRUSH),
                ('menu', W.LPCWSTR), ('name', W.LPCWSTR)]

api(U, 'RegisterClassW', W.ATOM, C.POINTER(WNDCLASS))
api(U, 'UnregisterClassW', W.BOOL, W.LPCWSTR, W.HINSTANCE)

class ClipboardError(RuntimeError):
    pass

def empty_enterprise_marker(fmt):
    """Only omit an unreadable WIP marker if Windows confirms no identity.

    A registered format ID is session-specific. Never whitelist a numeric ID,
    drop unknown unreadable formats, or infer an empty identity from NULL data.
    EdpGetEnterpriseIdForClipboard documents success + NULL as non-enterprise.
    https://learn.microsoft.com/windows/win32/devnotes/edpgetenterpriseidforclipboard-function
    """
    name = C.create_unicode_buffer(256)
    if not U.GetClipboardFormatNameW(fmt, name, len(name)) or name.value != 'EnterpriseDataProtectionId':
        return False
    identity = PTR()
    try:
        edp = C.WinDLL('edputil', use_last_error=True)
        get_identity = api(edp, 'EdpGetEnterpriseIdForClipboard', C.c_long, C.POINTER(PTR))
        result = get_identity(C.byref(identity))
        return result == 0 and not identity.value
    except (OSError, AttributeError):
        return False
    finally:
        if identity.value:
            K.HeapFree(K.GetProcessHeap(), 0, identity)

@contextmanager
def opened(hwnd=None, timeout=.4):
    end = time.monotonic() + timeout
    while not U.OpenClipboard(hwnd):
        if time.monotonic() >= end:
            raise ClipboardError('Zwischenablage belegt; unverändert lassen')
        time.sleep(.01)
    try:
        yield
    finally:
        U.CloseClipboard()

def put_bytes(fmt, data):
    h = K.GlobalAlloc(2, max(1, len(data)))
    if not h:
        raise ClipboardError('Speicher nicht verfügbar')
    p = K.GlobalLock(h)
    if not p:
        K.GlobalFree(h)
        raise ClipboardError('Speicher nicht lesbar')
    C.memmove(p, data, len(data))
    K.GlobalUnlock(h)
    if not U.SetClipboardData(fmt, h):
        K.GlobalFree(h)
        raise ClipboardError('Zwischenablage konnte nicht geschrieben werden')

class Snapshot:
    """Must be captured under the SAME lock as publication. Never log payloads."""
    def __init__(self):
        self.items = []

    @classmethod
    def capture(cls):
        result = cls()
        fmt, total = 0, 0
        try:
            while True:
                C.set_last_error(0)
                fmt = U.EnumClipboardFormats(fmt)
                if not fmt:
                    if C.get_last_error():
                        raise ClipboardError('Formate konnten nicht vollständig gelesen werden')
                    return result
                # GDI/private/owner-display formats need individual serializers.
                if fmt in (3, 9, 14, 0x80, 0x81, 0x82, 0x83, 0x8e) or 0x200 <= fmt <= 0x3ff:
                    raise ClipboardError('Sonderformat: sichere Sicherung nicht unterstützt; nichts geändert')
                C.set_last_error(0)
                h = U.GetClipboardData(fmt)
                if not h:
                    error = C.get_last_error()
                    if error == 0 and empty_enterprise_marker(fmt):
                        continue
                    raise ClipboardError(f'Zwischenablageformat {fmt} nicht lesbar (Windows {error}); nichts geändert')
                if fmt == 2:
                    duplicate = U.CopyImage(h, 0, 0, 0, 0x2000)
                    if not duplicate:
                        raise ClipboardError('Bild nicht sicher kopierbar; nichts geändert')
                    result.items.append((fmt, duplicate))
                    continue
                size = K.GlobalSize(h)
                total += size
                if not size or size > 16 * 1024 * 1024 or total > 64 * 1024 * 1024:
                    raise ClipboardError('Format nicht sicher kopierbar oder zu groß; nichts geändert')
                p = K.GlobalLock(h)
                if not p:
                    raise ClipboardError('Format nicht lesbar; nichts geändert')
                try:
                    result.items.append((fmt, C.string_at(p, size)))
                finally:
                    K.GlobalUnlock(h)
        except BaseException:
            result.close()
            raise

    def restore(self):
        if not U.EmptyClipboard():
            raise ClipboardError('Wiederherstellung blockiert')
        for fmt, value in self.items:
            if fmt == 2:
                duplicate = U.CopyImage(value, 0, 0, 0, 0x2000)
                if not duplicate or not U.SetClipboardData(fmt, duplicate):
                    if duplicate:
                        G.DeleteObject(duplicate)
                    raise ClipboardError('Bild-Wiederherstellung fehlgeschlagen')
            else:
                put_bytes(fmt, value)

    def close(self):
        for fmt, value in self.items:
            if fmt == 2:
                G.DeleteObject(value)
        self.items.clear()

class PasteTransaction:
    _serial = threading.Lock()

    def __init__(self, text, valid, inject, *, timeout=8.0, grace=.5):
        self.text = text.replace('\r\n', '\n').replace('\r', '\n').replace('\n', '\r\n')
        self.valid, self.inject = valid, inject
        self.timeout, self.grace = timeout, grace
        self.done = threading.Event()
        self.status, self.error = 'pending', None
        self.read_at = self.injected_at = None
        self.lost = False
        self.hwnd = self.snapshot = None
        self.sequence = None
        self.rendered = False
        self.offered = False
        self.ms = None

    def start(self):
        self.thread = threading.Thread(target=self._run, daemon=False)
        self.thread.start()
        return self

    def _render(self):
        if not self.rendered:
            put_bytes(13, (self.text + '\0').encode('utf-16-le'))
            self.rendered = True

    def _message(self, hwnd, msg, wp, lp):
        try:
            if msg == 0x305 and wp == 13 and self.offered:  # first materialization only
                self._render()
                self.read_at = time.monotonic()
                return 0
            if msg == 0x307:
                self.lost = True
                return 0
            if msg == 0x306 and self.offered and U.GetClipboardOwner() == hwnd:
                with opened(hwnd):
                    self._render()
                return 0
        except Exception as exc:
            self.error = type(exc).__name__
        return U.DefWindowProcW(hwnd, msg, wp, lp)

    def _pump(self):
        msg = W.MSG()
        while U.PeekMessageW(C.byref(msg), None, 0, 0, 1):
            U.TranslateMessage(C.byref(msg))
            U.DispatchMessageW(C.byref(msg))

    def _restore(self):
        # Compare ownership AND sequence while holding the clipboard lock.
        # A user's newer copy always wins, even if its text is identical.
        with opened(self.hwnd, timeout=1):
            if self.lost or U.GetClipboardOwner() != self.hwnd or U.GetClipboardSequenceNumber() != self.sequence:
                return False
            self.offered = False
            self.snapshot.restore()
            return True

    def _run(self):
        start = time.monotonic()
        name = 'AmberFlowClipboardPrototype_' + str(id(self))
        instance = K.GetModuleHandleW(None)
        proc = PROC(self._message)
        registered = False
        published = False
        try:
            with self._serial:
                if not self.valid():
                    self.status = 'cancelled_before_publish'
                    return
                wc = WNDCLASS(0, proc, 0, 0, instance, None, None, None, None, name)
                if not U.RegisterClassW(C.byref(wc)):
                    raise ClipboardError('Nachrichtenfenster nicht registrierbar')
                registered = True
                self.hwnd = U.CreateWindowExW(0, name, '', 0, 0, 0, 0, 0, W.HWND(-3), None, instance, None)
                if not self.hwnd:
                    raise ClipboardError('Nachrichtenfenster nicht verfügbar')
                with opened(self.hwnd):
                    self.snapshot = Snapshot.capture()
                    if not self.valid():
                        self.status = 'cancelled_before_publish'
                        return
                    if not U.EmptyClipboard():
                        raise ClipboardError('Zwischenablage nicht verfügbar')
                    published = True
                    try:
                        for key, value in [('CanIncludeInClipboardHistory', 0), ('CanUploadToCloudClipboard', 0), ('ExcludeClipboardContentFromMonitorProcessing', 1)]:
                            fmt = U.RegisterClipboardFormatW(key)
                            if not fmt:
                                raise ClipboardError('Historienmarkierung nicht verfügbar')
                            put_bytes(fmt, value.to_bytes(4, 'little'))
                        C.set_last_error(0)
                        U.SetClipboardData(13, None)
                        if C.get_last_error():
                            raise ClipboardError('Textbereitstellung fehlgeschlagen')
                        self.offered = True
                    except BaseException:
                        self.snapshot.restore()
                        published = False
                        raise
                self.sequence = U.GetClipboardSequenceNumber()
                injection_error = None
                try:
                    if not self.valid():
                        raise ClipboardError('Ziel gewechselt; kein Einfügen ausgelöst')
                    if U.GetClipboardOwner() != self.hwnd or U.GetClipboardSequenceNumber() != self.sequence:
                        raise ClipboardError('Zwischenablage vor Einfügen geändert; kein Einfügen ausgelöst')
                    self.injected_at = time.monotonic()
                    self.inject()
                except Exception as exc:
                    injection_error = type(exc).__name__
                deadline = time.monotonic() + (.5 if injection_error else self.timeout)
                while time.monotonic() < deadline:
                    self._pump()
                    if self.lost:
                        break
                    # The first reader may be a clipboard manager; no success claim.
                    if self.read_at and self.read_at >= self.injected_at and time.monotonic() - self.read_at >= self.grace:
                        break
                    time.sleep(.01)
                restored = self._restore()
                published = False
                self.error = injection_error or self.error
                self.status = ('newer_clipboard_preserved' if not restored else
                               'injection_failed_restored' if injection_error else
                               'read_observed_restored' if self.read_at else 'unconfirmed_timeout_restored')
        except Exception as exc:
            self.status = 'error'
            self.error = str(exc)
            if published and self.snapshot:
                try:
                    self._restore()
                except Exception:
                    self.status = 'restore_failed'
        finally:
            if self.hwnd:
                U.DestroyWindow(self.hwnd)
            if registered:
                U.UnregisterClassW(name, instance)
            if self.snapshot:
                self.snapshot.close()
            self.text = ''
            self.ms = round((time.monotonic() - start) * 1000)
            self.done.set()
