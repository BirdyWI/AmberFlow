"""Isolated clipboard candidate. Never retries a possibly submitted paste."""
def submit(text, target, current_target, modifiers_down, copy, read, paste, sleep, active):
    if not active() or not target or current_target() != target or modifiers_down():
        raise RuntimeError('Ziel oder Aufnahmestatus geändert; nicht eingefügt')
    copy(text)
    sleep(0.14)
    if not active() or current_target() != target or modifiers_down():
        raise RuntimeError('Ziel oder Aufnahmestatus geändert; Text liegt in der Zwischenablage')
    if read() != text:
        raise RuntimeError('Zwischenablage geändert; nicht eingefügt')
    paste()
