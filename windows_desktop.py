"""Small Win32 boundary for nonactivating HUD and native paste input."""
import ctypes
from ctypes import wintypes


def user32():
    return ctypes.windll.user32


# Shared with the previous name to prevent concurrent old/new instances.
def acquire_instance(name="Local\\ArgonFlow"):
    api = ctypes.WinDLL("kernel32", use_last_error=True)
    api.CreateMutexW.argtypes = [ctypes.c_void_p, wintypes.BOOL, wintypes.LPCWSTR]
    api.CreateMutexW.restype = wintypes.HANDLE
    api.CloseHandle.argtypes = [wintypes.HANDLE]
    handle = api.CreateMutexW(None, False, name)
    if not handle:
        raise ctypes.WinError(ctypes.get_last_error())
    if ctypes.get_last_error() == 183:
        api.CloseHandle(handle)
        return None
    return handle


def release_instance(handle):
    api = ctypes.windll.kernel32
    api.CloseHandle.argtypes = [wintypes.HANDLE]
    api.CloseHandle(handle)


def window_handle(widget):
    api = user32()
    api.GetParent.argtypes = [wintypes.HWND]
    api.GetParent.restype = wintypes.HWND
    child = widget.winfo_id()
    return api.GetParent(child) or child


def prepare_hud(widget):
    api = user32()
    hwnd = window_handle(widget)
    api.GetWindowLongW.argtypes = [wintypes.HWND, ctypes.c_int]
    api.GetWindowLongW.restype = wintypes.LONG
    api.SetWindowLongW.argtypes = [wintypes.HWND, ctypes.c_int, wintypes.LONG]
    # WS_EX_NOACTIVATE | WS_EX_TOOLWINDOW. Apply before making the HUD visible.
    style = api.GetWindowLongW(hwnd, -20)
    api.SetWindowLongW(hwnd, -20, style | 0x08000000 | 0x00000080)
    return hwnd


def show_hud(widget):
    hwnd = prepare_hud(widget)
    widget.deiconify()
    api = user32()
    api.ShowWindow.argtypes = [wintypes.HWND, ctypes.c_int]
    api.SetWindowPos.argtypes = [wintypes.HWND, wintypes.HWND, ctypes.c_int,
                                ctypes.c_int, ctypes.c_int, ctypes.c_int, wintypes.UINT]
    api.ShowWindow(hwnd, 4)  # SW_SHOWNOACTIVATE
    api.SetWindowPos(hwnd, -1, 0, 0, 0, 0, 0x0001 | 0x0002 | 0x0010 | 0x0040)


def modifiers_down():
    # Physical state avoids delayed/lost listener releases and ignores ordinary typing.
    return any(user32().GetAsyncKeyState(vk) & 0x8000
               for vk in (0x10, 0x11, 0x12, 0x5B, 0x5C))


class MOUSEINPUT(ctypes.Structure):
    _fields_ = [("dx", wintypes.LONG), ("dy", wintypes.LONG),
                ("mouseData", wintypes.DWORD), ("dwFlags", wintypes.DWORD),
                ("time", wintypes.DWORD), ("dwExtraInfo", ctypes.c_size_t)]


class KEYBDINPUT(ctypes.Structure):
    _fields_ = [("wVk", wintypes.WORD), ("wScan", wintypes.WORD),
                ("dwFlags", wintypes.DWORD), ("time", wintypes.DWORD),
                ("dwExtraInfo", ctypes.c_size_t)]


class INPUTUNION(ctypes.Union):
    _fields_ = [("mi", MOUSEINPUT), ("ki", KEYBDINPUT)]


class INPUT(ctypes.Structure):
    _anonymous_ = ("data",)
    _fields_ = [("type", wintypes.DWORD), ("data", INPUTUNION)]


def paste_shortcut():
    events = (INPUT * 4)()
    for event, (vk, flags) in zip(events, ((0x11, 0), (0x56, 0), (0x56, 2), (0x11, 2))):
        event.type = 1
        event.ki = KEYBDINPUT(vk, 0, flags, 0, 0)
    api = user32()
    api.SendInput.argtypes = [wintypes.UINT, ctypes.POINTER(INPUT), ctypes.c_int]
    api.SendInput.restype = wintypes.UINT
    if api.SendInput(4, events, ctypes.sizeof(INPUT)) != 4:
        # Release injected keys even if Windows accepted only part of the sequence.
        api.SendInput(2, ctypes.cast(ctypes.byref(events, 2 * ctypes.sizeof(INPUT)),
                                    ctypes.POINTER(INPUT)), ctypes.sizeof(INPUT))
        raise OSError("Windows hat die Texteingabe blockiert.")


TEXT_INPUT_MARKER = 0x414D4246


class GUITHREADINFO(ctypes.Structure):
    _fields_ = [("cbSize", wintypes.DWORD), ("flags", wintypes.DWORD),
                ("hwndActive", wintypes.HWND), ("hwndFocus", wintypes.HWND),
                ("hwndCapture", wintypes.HWND), ("hwndMenuOwner", wintypes.HWND),
                ("hwndMoveSize", wintypes.HWND), ("hwndCaret", wintypes.HWND),
                ("rcCaret", wintypes.RECT)]


def insert_native_editor(text):
    """Use RichEdit's selection API, bypassing Notepad's broken VK_PACKET path.

    EM_REPLACESEL preserves selection, undo, current formatting and the clipboard.
    Only the focused standard RichEdit control in the foreground window qualifies.
    A timeout is ambiguous: report failure rather than inserting the text twice.
    """
    api = user32()
    api.GetForegroundWindow.restype = wintypes.HWND
    api.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.c_void_p]
    api.GetGUIThreadInfo.argtypes = [wintypes.DWORD, ctypes.POINTER(GUITHREADINFO)]
    api.GetClassNameW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
    api.GetAncestor.argtypes = [wintypes.HWND, wintypes.UINT]
    api.GetAncestor.restype = wintypes.HWND
    target = api.GetForegroundWindow()
    thread = api.GetWindowThreadProcessId(target, None)
    info = GUITHREADINFO()
    info.cbSize = ctypes.sizeof(info)
    if not thread or not api.GetGUIThreadInfo(thread, ctypes.byref(info)) or not info.hwndFocus:
        return False
    name = ctypes.create_unicode_buffer(256)
    api.GetClassNameW(info.hwndFocus, name, len(name))
    if name.value.lower() not in ("richeditd2dpt", "richedit50w", "richedit20w"):
        return False
    if api.GetAncestor(info.hwndFocus, 2) != target or api.GetForegroundWindow() != target:
        raise OSError("Zielfenster gewechselt; keine Texteingabe gesendet.")
    api.SendMessageTimeoutW.argtypes = [wintypes.HWND, wintypes.UINT, ctypes.c_size_t,
                                        ctypes.c_void_p, wintypes.UINT, wintypes.UINT,
                                        ctypes.POINTER(ctypes.c_size_t)]
    api.SendMessageTimeoutW.restype = ctypes.c_ssize_t
    content = ctypes.create_unicode_buffer(text.replace('\n', '\r\n'))
    result = ctypes.c_size_t()
    if not api.SendMessageTimeoutW(info.hwndFocus, 0x00C2, 1, ctypes.cast(content, ctypes.c_void_p),
                                  0x0002, 2000, ctypes.byref(result)):
        raise OSError("Editor antwortet nicht; Zielfeld vor erneutem Einfügen prüfen.")
    return True


def type_unicode(text):
    """Submit Unicode text without reading or writing any clipboard format."""
    # Normalize line endings and send line feeds as text, not Enter shortcuts.
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    if not text:
        return
    if insert_native_editor(text):
        return
    encoded = text.encode("utf-16-le")
    units = [int.from_bytes(encoded[i:i + 2], "little") for i in range(0, len(encoded), 2)]
    if not units:
        return
    events = (INPUT * (2 * len(units)))()
    for i, unit in enumerate(units):
        for offset, flags in ((0, 0x0004), (1, 0x0004 | 0x0002)):
            events[2 * i + offset].type = 1
            events[2 * i + offset].ki = KEYBDINPUT(0, unit, flags, 0, TEXT_INPUT_MARKER)
    api = user32()
    api.SendInput.argtypes = [wintypes.UINT, ctypes.POINTER(INPUT), ctypes.c_int]
    api.SendInput.restype = wintypes.UINT
    if api.SendInput(len(events), events, ctypes.sizeof(INPUT)) != len(events):
        # Do not retry: some characters may already have arrived.
        raise OSError("Texteingabe möglicherweise unvollständig. Zielfeld prüfen.")
