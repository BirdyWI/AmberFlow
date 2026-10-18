"""Per-user Windows login startup, limited to the AmberFlow Run entry."""
from pathlib import Path
import subprocess
import sys
import winreg

RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
VALUE_NAME = "AmberFlow"


def startup_command(script=None, executable=None):
    script = Path(script) if script is not None else Path(__file__).with_name("app.py")
    python = Path(executable or sys.executable)
    pythonw = python.with_name("pythonw.exe")
    if pythonw.is_file():
        python = pythonw
    return subprocess.list2cmdline([str(python.resolve()), str(script.resolve()), "--autostart"])


def set_autostart(enabled, script=None, executable=None):
    with winreg.CreateKeyEx(winreg.HKEY_CURRENT_USER, RUN_KEY, 0, winreg.KEY_SET_VALUE) as key:
        if enabled:
            winreg.SetValueEx(key, VALUE_NAME, 0, winreg.REG_SZ, startup_command(script, executable))
        else:
            try:
                winreg.DeleteValue(key, VALUE_NAME)
            except FileNotFoundError:
                pass


def migrate_legacy_autostart(script=None, executable=None):
    """Remove the old name only if it launches this exact installation."""
    with winreg.CreateKeyEx(winreg.HKEY_CURRENT_USER, RUN_KEY, 0,
                            winreg.KEY_QUERY_VALUE | winreg.KEY_SET_VALUE) as key:
        try:
            command, _ = winreg.QueryValueEx(key, "ArgonFlow")
        except FileNotFoundError:
            return
        if command == startup_command(script, executable):
            winreg.DeleteValue(key, "ArgonFlow")
