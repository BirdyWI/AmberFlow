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
