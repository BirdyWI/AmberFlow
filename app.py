"""AmberFlow Windows desktop application. Run with Python 3.11+."""

from copy import deepcopy
import ast
import ctypes
import os
from pathlib import Path
import queue
import sys
import threading
import time
import tkinter as tk
from tkinter import messagebox, ttk

from amber_core import (ConfigError, ConfigStore, DEFAULT_CONFIG, VERSION,
                        clean_text, polish_text, validate_config, text_for_paste)
from dictionary_editor import DictionaryEditor
from autostart import set_autostart, migrate_legacy_autostart
from windows_desktop import prepare_hud, show_hud, modifiers_down, paste_shortcut, acquire_instance, release_instance

# Keep the handles alive while native libraries are in use.
DLL_HANDLES = []
if sys.platform == "win32":
    for name in ("cublas", "cudnn", "cuda_nvrtc"):
        directory = Path(sys.prefix) / "Lib" / "site-packages" / "nvidia" / name / "bin"
        if directory.is_dir():
            # CTranslate2 also loads CUDA DLLs through the ordinary Windows search
            # path; add_dll_directory alone does not cover that code path.
            os.environ["PATH"] = str(directory) + os.pathsep + os.environ.get("PATH", "")
            DLL_HANDLES.append(os.add_dll_directory(str(directory)))

import ctranslate2
from faster_whisper import WhisperModel
import numpy as np
from PIL import Image, ImageDraw
from pynput import keyboard
import pyperclip
import pystray
import sounddevice as sd

SAMPLE_RATE = 16000


def foreground_window():
    if sys.platform != "win32":
        return None
    fn = ctypes.windll.user32.GetForegroundWindow
    fn.restype = ctypes.c_void_p
    return fn()


class AmberFlowApp:
    def __init__(self, root, login_start=False):
        self.root = root
        self.events = queue.Queue()
        self.audio_lock = threading.Lock()
        self.frames = []
        self.samples = 0
        self.current_rms = 0.0
        self.hud_cue_until = 0.0
        self.recording = False
        self.busy = False
        self.loading = False
        self.closing = False
        self.mode = None
        self.stream = None
        self.model = None
        self.job_id = 0
        self.cancelled = threading.Event()
        self.pressed = set()
        self.capture = None
        self.settings = None
        self.result_window = None
        self.pending_delivery = None
        self.processing_job = None
        self.reload_requested = False
        self.hud_hide_timer = None
        self.backend = "Noch nicht geladen"
        self.api_key = os.environ.get("AMBERFLOW_API_KEY", os.environ.get("ARGONFLOW_API_KEY", ""))
        self.controller = keyboard.Controller()
        self.store = ConfigStore()
        warning = ""
        try:
            self.config, warning = self.store.load(Path(__file__).with_name("dictionary.json"))
            self.validate_hotkeys(self.config)
        except ConfigError:
            self.config = deepcopy(DEFAULT_CONFIG)
            warning = "Konfiguration ungültig. Sichere Standardwerte sind aktiv; die Datei wurde nicht verändert. Prüfe die Einstellungen vor dem Speichern."
        # Cloud requires confirmation in this running session, even for edited JSON files.
        if self.config["llm_polish"]["mode"] == "cloud":
            self.config["llm_polish"]["mode"] = "off"
            warning += " Cloud-Politur bitte in den Einstellungen erneut bestätigen."
        try:
            set_autostart(self.config["autostart"])
            migrate_legacy_autostart()
        except OSError:
            warning += " Windows-Autostart konnte nicht eingerichtet werden. Bitte in den Einstellungen erneut speichern."
        self.root.title(f"AmberFlow {VERSION}")
        self.root.withdraw()
        self.root.overrideredirect(True)
        width, height = 220, 42
        self.root.geometry(f"{width}x{height}+{(root.winfo_screenwidth()-width)//2}+{root.winfo_screenheight()-height-85}")
        self.root.resizable(False, False)
        self.root.attributes("-topmost", True)
        self.root.configure(bg="#121212")
        self.root.attributes("-alpha", .94)
        self.status = tk.StringVar(value="Lade Modell …")
        self.engine_status = tk.StringVar(value="Engine wird geladen …")
        self.canvas = tk.Canvas(root, width=width, height=height, bg="#121212",
                                highlightthickness=1, highlightbackground="#3b82f6")
        self.canvas.pack(fill="both", expand=True)
        self.dot = self.canvas.create_oval(14, 15, 26, 27, fill="#f59e0b", outline="")
        self.label = self.canvas.create_text(36, 21, anchor="w", fill="white",
                                             font=("Segoe UI", 9, "bold"), text="Aufnahme …")
        self.bars = [self.canvas.create_rectangle(170+i*7, 20, 174+i*7, 22,
                                                  fill="#f59e0b", outline="") for i in range(5)]
        root.update_idletasks()
        prepare_hud(root)
        root.protocol("WM_DELETE_WINDOW", root.withdraw)
        self.listener = None
        self.last_listener_restart = 0.0
        self.start_listener()
        self.tray = pystray.Icon("AmberFlow", self.icon(), "AmberFlow", pystray.Menu(
            pystray.MenuItem("Einstellungen", lambda: self.events.put(("settings", None)), default=True),
            pystray.MenuItem("Tastenkürzel neu verbinden", lambda: self.events.put(("reconnect", None))),
            pystray.MenuItem("Modell erneut laden", lambda: self.events.put(("reload", None))),
            pystray.MenuItem("Status anzeigen", lambda: self.events.put(("show", None))),
            pystray.MenuItem("Beenden", lambda: self.events.put(("quit", None))),
        ))
        threading.Thread(target=self.tray.run, daemon=True).start()
        self.root.after(30, self.poll)
        self.load_model()
        if not login_start:
            self.open_settings()
        if warning:
            self.root.after(150, lambda: messagebox.showinfo("Konfiguration", warning, parent=root))

    @staticmethod
    def icon():
        # Original geometric fallback: no external logo or unknown asset rights.
        image = Image.new("RGB", (64, 64), "#121212")
        draw = ImageDraw.Draw(image)
        draw.ellipse((10, 10, 54, 54), fill="#3b82f6")
        draw.ellipse((23, 23, 41, 41), fill="white")
        return image

    def show_status(self, message, visible=True):
        self.status.set(message)
        if hasattr(self, "tray"):
            self.tray.title = ("AmberFlow – " + message)[:120]
        if visible and (self.recording or (self.busy and not self.cancelled.is_set())):
            if self.hud_hide_timer is not None:
                self.root.after_cancel(self.hud_hide_timer)
                self.hud_hide_timer = None
            self.paint_hud("Aufnahme …" if self.recording else "Transkribiere …",
                           "#ef4444" if self.recording else "#f59e0b")
            show_hud(self.root)
        elif time.monotonic() >= self.hud_cue_until:
            self.root.withdraw()

    def paint_hud(self, text, color):
        self.canvas.itemconfig(self.dot, fill=color)
        self.canvas.itemconfig(self.label, text=text)
        for bar in self.bars:
            self.canvas.itemconfig(bar, fill=color)

    def update_meter(self):
        level = self.current_rms if self.recording else 0.0
        for i, (bar, factor) in enumerate(zip(self.bars, (.5, .85, 1., .75, .4))):
            height = max(2, int(level * 16 * factor))
            x = 170 + i * 7
            self.canvas.coords(bar, x, 21-height, x+4, 21+height)

    def hide_hud_later(self, delay=1600):
        if self.hud_hide_timer is not None:
            self.root.after_cancel(self.hud_hide_timer)
        def hide():
            self.hud_hide_timer = None
            if not self.recording and not self.busy:
                self.root.withdraw()
        self.hud_hide_timer = self.root.after(delay, hide)

    @staticmethod
    def key_string(key):
        if isinstance(key, keyboard.Key):
            return f"Key.{key.name}"
        if key.char:
            char = key.char.lower()
            if len(char) == 1 and 1 <= ord(char) <= 26:
                char = chr(ord(char) + 96)
            return repr(char)
        return f"VK_{key.vk}"

    @staticmethod
    def validate_hotkeys(config):
        for combo in config["hotkeys"].values():
            for part in combo.split(" + "):
                if part.startswith("Key.") and part[4:] not in keyboard.Key.__members__:
                    raise ConfigError("Unbekannte Taste im Hotkey.")

    def handle_key(self, pressed, key):
        if key is None:
            return
        name = self.key_string(key)
        if pressed:
            if name in self.pressed:
                return
            self.pressed.add(name)
        if self.capture:
            variable, collected = self.capture
            if pressed:
                collected.add(name)
                variable.set(" + ".join(sorted(collected)))
            else:
                self.capture = None
                self.pressed.clear()
            return
        hotkeys = self.config["hotkeys"]
        combo = " + ".join(sorted(self.pressed))
        if pressed:
            if combo == hotkeys["cancel"]:
                self.cancel()
            elif self.settings is None:
                if combo == hotkeys["ptt"]:
                    self.start_recording("ptt")
                elif combo == hotkeys["toggle"]:
                    if self.recording and self.mode == "toggle":
                        self.stop_recording()
                    else:
                        self.start_recording("toggle")
        else:
            self.pressed.discard(name)
            if self.recording and self.mode == "ptt" and name in hotkeys["ptt"].split(" + "):
                self.stop_recording()

    def start_listener(self):
        previous = self.listener
        if previous is not None:
            previous.stop()
        self.listener = keyboard.Listener(
            on_press=lambda key: self.events.put(("key", (True, key))),
            on_release=lambda key: self.events.put(("key", (False, key))),
        )
        self.listener.start()
        self.last_listener_restart = time.monotonic()

    @staticmethod
    def physical_key(name):
        if name.startswith("Key."):
            key = keyboard.Key[name[4:]]
            vk = key.value.vk
        elif name.startswith("VK_"):
            vk = int(name[3:])
            key = keyboard.KeyCode.from_vk(vk)
        else:
            key = keyboard.KeyCode.from_char(ast.literal_eval(name))
            api = ctypes.windll.user32
            api.VkKeyScanW.argtypes = [ctypes.c_wchar]
            api.VkKeyScanW.restype = ctypes.c_short
            mapped = api.VkKeyScanW(key.char)
            if mapped == -1:
                return key, False
            vk = mapped & 0xff
        api = ctypes.windll.user32
        api.GetAsyncKeyState.argtypes = [ctypes.c_int]
        api.GetAsyncKeyState.restype = ctypes.c_short
        return key, bool(api.GetAsyncKeyState(vk) & 0x8000)

    def reconcile_hotkeys(self):
        # Hooks can disappear without their thread dying. Independently sample
        # only configured hotkeys and keys already held, never typed text.
        if getattr(self, "capture", None):
            return
        names = set(self.pressed)
        for combo in self.config["hotkeys"].values():
            names.update(combo.split(" + "))
        states = {name: self.physical_key(name) for name in names}
        missing = any(down and name not in self.pressed for name, (_, down) in states.items())
        for name, (key, down) in states.items():
            if not down and name in self.pressed:
                self.handle_key(False, key)
        for name, (key, down) in states.items():
            if down and name not in self.pressed:
                self.handle_key(True, key)
        listener = getattr(self, "listener", None)
        if listener is not None and (missing or not listener.is_alive()):
            if time.monotonic() - self.last_listener_restart >= 5:
                self.start_listener()

    def load_model(self):
        if self.recording or self.busy or self.loading:
            return
        self.loading = True
        self.model = None
        config = deepcopy(self.config)
        self.engine_status.set("Engine wird geladen …")
        self.show_status("Lade Modell – beim ersten Start mit Download …", visible=False)
        def worker():
            try:
                pref = config["compute_device"]
                try:
                    gpu = pref == "cuda" or (pref == "auto" and ctranslate2.get_cuda_device_count() > 0)
                except Exception:
                    gpu = pref == "cuda"
                device = "cuda" if gpu else "cpu"
                threads = max(1, min(8, os.cpu_count() or 1))
                try:
                    model = WhisperModel(config["model_size"], device=device,
                                         compute_type="float16" if gpu else "int8", cpu_threads=threads)
                    # Validate actual inference, including lazily loaded GPU libraries.
                    list(model.transcribe(np.zeros(SAMPLE_RATE, dtype=np.float32), beam_size=1)[0])
                except Exception:
                    if not gpu:
                        raise
                    model = WhisperModel(config["model_size"], device="cpu", compute_type="int8", cpu_threads=threads)
                    list(model.transcribe(np.zeros(SAMPLE_RATE, dtype=np.float32), beam_size=1)[0])
                    device = "CPU (GPU-Fallback)"
                self.events.put(("model", (model, f"{config['model_size']} / {device}")))
            except Exception:
                self.events.put(("model_error", None))
        threading.Thread(target=worker, daemon=True).start()

    def audio_callback(self, data, frames, timing, status):
        with self.audio_lock:
            if not self.recording:
                return
            if status:
                self.events.put(("audio_error", self.job_id))
                self.recording = False
                return
            remaining = self.max_samples - self.samples
            chunk = data[:remaining].copy()
            if len(chunk):
                self.current_rms = min(1.0, float(np.sqrt(np.mean(chunk**2))) * 18)
            self.frames.append(chunk)
            self.samples += len(chunk)
            if self.samples >= self.max_samples:
                self.recording = False
                self.events.put(("limit", self.job_id))

    def feedback(self, start):
        if not self.config["sound_feedback"]:
            return
        def tone():
            try:
                import winsound
                winsound.Beep(660 if start else 440, 45)
            except (ImportError, RuntimeError):
                pass
        threading.Thread(target=tone, daemon=True).start()

    def start_recording(self, mode):
        if self.recording or self.busy or self.loading or self.stream is not None or self.model is None:
            return
        self.job_id += 1
        self.cancelled = threading.Event()
        self.target_window = foreground_window()
        self.mode = mode
        self.max_samples = self.config["max_recording_seconds"] * SAMPLE_RATE
        with self.audio_lock:
            self.frames = []
            self.samples = 0
            self.current_rms = 0.0
            self.recording = True
        try:
            self.stream = sd.InputStream(device=self.config["input_device"], samplerate=SAMPLE_RATE,
                                         channels=1, dtype="float32", callback=self.audio_callback)
            self.stream.start()
        except Exception:
            with self.audio_lock:
                self.recording = False
                self.frames.clear()
            self.close_stream()
            self.show_status("Mikrofon nicht verfügbar. Gerät und Windows-Berechtigung prüfen.")
            return
        self.feedback(True)
        self.show_status("Aufnahme … Escape bricht ab")

    def close_stream(self):
        stream, self.stream = self.stream, None
        if stream is not None:
            try:
                try:
                    stream.stop()
                finally:
                    stream.close()
            except Exception:
                self.show_status("Mikrofon konnte nicht sauber geschlossen werden. Gerät prüfen und App neu starten.")
                return False
        return True

    def stop_recording(self):
        if self.stream is None:
            return
        with self.audio_lock:
            self.recording = False
            frames, self.frames = self.frames, []
            samples = self.samples
        self.current_rms = 0.0
        if not self.close_stream():
            frames.clear()
            return
        self.feedback(False)
        if samples < int(SAMPLE_RATE * .35):
            self.show_status("Aufnahme zu kurz.")
            self.hide_hud_later()
            return
        self.busy = True
        self.processing_job = self.job_id
        config, model = deepcopy(self.config), self.model
        job, cancelled, target = self.job_id, self.cancelled, self.target_window
        key = self.api_key
        self.show_status("Verarbeite … Escape verwirft die Ausgabe")
        threading.Thread(target=self.transcribe, args=(frames, config, model, job, cancelled, target, key), daemon=True).start()

    def transcribe(self, frames, config, model, job, cancelled, target, key):
        audio = None
        try:
            audio = np.concatenate(frames, axis=0).flatten()
            frames.clear()
            if cancelled.is_set():
                return
            language = config["language"] if config["language"] != "auto" else None
            segments, _ = model.transcribe(audio, language=language,
                initial_prompt=", ".join(config["prompt_terms"]) or None, vad_filter=True,
                vad_parameters={"min_silence_duration_ms": 300}, beam_size=1, without_timestamps=True)
            parts = []
            for segment in segments:
                if cancelled.is_set():
                    return
                parts.append(segment.text.strip())
            text = clean_text(" ".join(parts).strip(), config)
            warning = ""
            if cancelled.is_set():
                return
            try:
                text = polish_text(text, config, key, cancelled)
            except Exception:
                warning = "KI-Politur fehlgeschlagen; lokales Transkript wird angezeigt."
            if not cancelled.is_set():
                self.events.put(("result", (job, text, target, config["auto_paste"], warning)))
        except Exception:
            if not cancelled.is_set():
                self.events.put(("job_error", job))
        finally:
            frames.clear()
            if audio is not None:
                audio.fill(0)
            self.events.put(("done", job))

    def cancel(self):
        self.cancelled.set()
        self.hud_cue_until = 0.0
        self.root.withdraw()
        self.pending_delivery = None
        self.busy = self.processing_job is not None
        with self.audio_lock:
            self.recording = False
            self.frames.clear()
        self.close_stream()
        self.show_status("Abgebrochen.")
        self.hide_hud_later()

    def deliver(self, job, text, target, auto_paste, warning):
        if job != self.job_id or self.cancelled.is_set() or self.closing:
            return
        if not text:
            self.show_status("Keine Sprache erkannt.")
            self.hide_hud_later()
            return
        if not auto_paste:
            self.root.withdraw()
            self.show_result(text, warning)
            return
        payload = (job, text_for_paste(text), target, warning)
        self.pending_delivery = payload
        self.busy = True
        self.attempt_delivery(payload, time.monotonic() + 4.0)

    def attempt_delivery(self, payload, deadline, clipboard_ready=False):
        job, text, target, warning = payload
        if self.closing or self.cancelled.is_set() or job != self.job_id or self.pending_delivery is not payload:
            return
        if modifiers_down():
            if time.monotonic() < deadline:
                self.show_status("Zum Einfügen bitte die Steuertasten loslassen …")
                self.root.after(40, lambda: self.attempt_delivery(payload, deadline, clipboard_ready))
                return
            reason = "Steuertaste noch gedrückt"
        elif not target or foreground_window() != target:
            reason = "Zielfenster gewechselt"
        else:
            try:
                if not clipboard_ready:
                    pyperclip.copy(text)
                    # Clipboard writes are synchronous; yield without an artificial delay.
                    self.root.after(0, lambda: self.attempt_delivery(payload, deadline, True))
                    return
                if pyperclip.paste() != text:
                    self.finish_delivery("Zwischenablage geändert – Text nicht eingefügt.")
                    return
                paste_shortcut()
                self.finish_delivery("Eingefügt." if not warning else "Eingefügt (ohne KI-Politur).")
                return
            except Exception:
                reason = "Windows hat das Einfügen blockiert"
        # Exceptional focus/permission failure: no disruptive review window in direct mode.
        try:
            pyperclip.copy(text)
            self.finish_delivery(f"{reason}. Text kopiert – mit Strg+V einfügen.")
        except Exception:
            self.finish_delivery("Einfügen und Kopieren fehlgeschlagen.")
            self.show_result(text, "Windows-Zwischenablage nicht verfügbar.")

    def finish_delivery(self, message):
        self.pending_delivery = None
        self.busy = self.processing_job is not None
        self.show_status(message, visible=False)
        self.hide_hud_later(2500)

    def show_result(self, text, warning=""):
        if self.result_window is not None:
            self.result_window.destroy()
        win = tk.Toplevel(self.root)
        self.result_window = win
        win.title("AmberFlow – Diktat prüfen")
        win.geometry("650x350")
        ttk.Label(win, text=warning or "Prüfe den Text vor dem Kopieren. Es wurde nichts automatisch eingefügt.", wraplength=620).pack(padx=12, pady=8)
        content = tk.Text(win, wrap="word", undo=True)
        content.insert("1.0", text)
        content.pack(fill="both", expand=True, padx=12)
        def copy():
            try:
                pyperclip.copy(text_for_paste(content.get("1.0", "end-1c")))
                self.show_status("Kopiert. Mit Strg+V einfügen; der Text bleibt in der Zwischenablage.", visible=False)
            except Exception:
                messagebox.showerror("Zwischenablage", "Text konnte nicht kopiert werden.", parent=win)
        def close():
            self.result_window = None
            win.destroy()
        bar = ttk.Frame(win)
        bar.pack(pady=8)
        ttk.Button(bar, text="Text kopieren", command=copy).pack(side="left", padx=6)
        ttk.Button(bar, text="Schließen", command=close).pack(side="left", padx=6)
        win.protocol("WM_DELETE_WINDOW", close)

    def open_settings(self):
        if self.settings is not None:
            self.settings.lift()
            return
        if self.recording or self.busy:
            self.show_status("Bitte Aufnahme oder Verarbeitung zuerst beenden.")
            return
        win = tk.Toplevel(self.root)
        self.settings = win
        win.title(f"AmberFlow {VERSION} – Cockpit")
        win.geometry("720x710")
        win.minsize(700, 690)
        win.configure(bg="#18181b")
        self.root.withdraw()
        self.style_settings(win)
        header = ttk.Frame(win, padding=(20, 16, 20, 4))
        header.pack(fill="x")
        ttk.Label(header, text="AMBER FLOW", style="Brand.TLabel").pack(anchor="w")
        ttk.Label(header, text="Deine Stimme. Direkt im Textfeld.", style="Muted.TLabel").pack(anchor="w", pady=(3, 0))
        book = ttk.Notebook(win)
        book.pack(fill="both", expand=True, padx=12, pady=12)
        general, dictionary, cloud = (ttk.Frame(book, padding=12) for _ in range(3))
        for frame, title in ((general, "Allgemein"), (dictionary, "Wörterbuch"), (cloud, "KI-Politur")):
            book.add(frame, text=title)
            frame.columnconfigure(1, weight=1)
        variables = {}
        def field(frame, row, label, name, value, choices=None, masked=False):
            ttk.Label(frame, text=label).grid(row=row, column=0, sticky="w", pady=6, padx=(0, 10))
            variable = tk.StringVar(value=value)
            variables[name] = variable
            widget = (ttk.Combobox(frame, textvariable=variable, values=choices, state="readonly") if choices
                      else ttk.Entry(frame, textvariable=variable, show="*" if masked else ""))
            widget.grid(row=row, column=1, sticky="ew", pady=6)
            return variable
        ttk.Label(general, textvariable=self.engine_status).grid(row=0, column=0, columnspan=3, sticky="w")
        for row, (name, label) in enumerate((("ptt", "Halten & sprechen"), ("toggle", "Start / Stopp"), ("cancel", "Abbrechen")), 1):
            var = field(general, row, label, name, self.config["hotkeys"][name])
            def capture(variable=var):
                self.pressed.clear()
                self.capture = (variable, set())
                variable.set("Tasten drücken …")
            ttk.Button(general, text="Aufnehmen", command=capture).grid(row=row, column=2, padx=4)
        field(general, 4, "Whisper-Modell", "model_size", self.config["model_size"], ("tiny", "base", "small", "medium", "large-v3-turbo"))
        field(general, 5, "Hardware", "compute_device", self.config["compute_device"], ("auto", "cpu", "cuda"))
        field(general, 6, "Sprache", "language", self.config["language"] or "auto", ("de", "en", "auto"))
        devices = {"Windows-Standard": None}
        try:
            devices.update({f"{i}: {d['name']}": i for i, d in enumerate(sd.query_devices()) if d["max_input_channels"] > 0})
        except Exception:
            pass
        selected = next((k for k, v in devices.items() if v == self.config["input_device"]), "Windows-Standard")
        field(general, 7, "Mikrofon", "input_device", selected, tuple(devices))
        field(general, 8, "Limit in Sekunden", "max_recording_seconds", self.config["max_recording_seconds"])
        for row, (name, label) in enumerate((("sound_feedback", "Akustische Rückmeldung"), ("smart_cleanup", "Füllwörter entfernen"), ("auto_paste", "Direkt ins Textfeld einfügen (aus = Vorschau)"), ("autostart", "Bei der Windows-Anmeldung automatisch starten")), 9):
            variable = tk.BooleanVar(value=self.config[name])
            variables[name] = variable
            ttk.Checkbutton(general, text=label, variable=variable).grid(row=row, column=0, columnspan=3, sticky="w", pady=6)
        ttk.Label(general, textvariable=self.status, wraplength=590).grid(row=13, column=0, columnspan=3, sticky="w", pady=8)
        dictionary_editor = DictionaryEditor(dictionary, self.config["prompt_terms"], self.config["replacements"])
        dictionary_editor.pack(fill="both", expand=True)
        llm = self.config["llm_polish"]
        field(cloud, 0, "Modus", "mode", llm["mode"], ("off", "ollama", "cloud"))
        field(cloud, 1, "Ollama-Modell", "ollama_model", llm["ollama_model"])
        field(cloud, 2, "Ollama-Adresse", "ollama_url", llm["ollama_url"])
        field(cloud, 3, "Cloud-Adresse (HTTPS)", "cloud_url", llm["cloud_url"])
        field(cloud, 4, "Cloud-Modell", "cloud_model", llm["cloud_model"])
        field(cloud, 5, "API-Key (nur diese Sitzung)", "api_key", self.api_key, masked=True)
        ttk.Label(cloud, text="Cloud überträgt den vollständigen Text an den gewählten Anbieter.\nAudio bleibt lokal. Schlüssel werden nicht in der Konfiguration gespeichert.\nOllama ist auf dieses Gerät beschränkt.\nKI kann Inhalte verändern: Ergebnisse vor Verwendung prüfen.", wraplength=590).grid(row=6, column=0, columnspan=2, sticky="w", pady=15)
        def close():
            self.capture = None
            self.settings = None
            win.destroy()
            self.root.withdraw()
        def save():
            try:
                candidate = deepcopy(self.config)
                for name in ("model_size", "compute_device", "language", "sound_feedback", "smart_cleanup", "auto_paste", "autostart"):
                    candidate[name] = variables[name].get()
                candidate["hotkeys"] = {k: variables[k].get() for k in candidate["hotkeys"]}
                try:
                    candidate["max_recording_seconds"] = int(variables["max_recording_seconds"].get())
                except ValueError:
                    raise ConfigError("Aufnahmelimit: Bitte eine ganze Zahl von 5 bis 600 eingeben.")
                candidate["input_device"] = devices[variables["input_device"].get()]
                candidate["prompt_terms"], candidate["replacements"] = dictionary_editor.get()
                candidate["llm_polish"] = {k: variables[k].get().strip() for k in llm}
                candidate = validate_config(candidate)
                self.validate_hotkeys(candidate)
                new_key = variables["api_key"].get().strip()
                new_llm = candidate["llm_polish"]
                if new_llm["mode"] == "cloud":
                    if not new_key:
                        raise ConfigError("Bitte einen API-Key für diese Sitzung angeben.")
                    if not messagebox.askyesno("Cloud-Übertragung", f"Künftige Diktate als Text an diese Adresse senden?\n\n{new_llm['cloud_url']}\n\nEs gelten die Bedingungen des Anbieters.", parent=win):
                        return
                reload = any(candidate[k] != self.config[k] for k in ("model_size", "compute_device"))
                saved = self.store.save(candidate)
                try:
                    set_autostart(saved["autostart"])
                except OSError:
                    self.store.save(self.config)
                    raise
            except ConfigError as exc:
                messagebox.showerror("Einstellungen", str(exc), parent=win)
                return
            except (ValueError, KeyError):
                messagebox.showerror("Einstellungen", "Bitte die Tastenkombinationen und ausgewählten Einstellungen prüfen.", parent=win)
                return
            except OSError:
                messagebox.showerror("Einstellungen", "Einstellungen oder Windows-Autostart konnten nicht gespeichert werden. Bitte Schreibrechte prüfen.", parent=win)
                return
            self.config, self.api_key = saved, new_key
            close()
            if reload:
                if self.loading:
                    self.reload_requested = True
                else:
                    self.load_model()
        footer = ttk.Frame(win, padding=(12, 0, 12, 12))
        footer.pack(fill="x")
        ttk.Button(footer, text="Schließen", command=close).pack(side="right", padx=(8, 0))
        ttk.Button(footer, text="Einstellungen speichern", command=save, style="Accent.TButton").pack(side="right")
        win.protocol("WM_DELETE_WINDOW", close)
        win.update_idletasks()
        needed = max(710, win.winfo_reqheight() + 12)
        win.geometry(f"720x{min(needed, win.winfo_screenheight() - 90)}")

    def style_settings(self, window):
        style = ttk.Style(self.root)
        style.theme_use("clam")
        style.configure(".", background="#18181b", foreground="#e4e4e7", font=("Segoe UI", 10))
        style.configure("TFrame", background="#18181b")
        style.configure("TLabel", background="#18181b", foreground="#e4e4e7")
        style.configure("Brand.TLabel", foreground="#60a5fa", font=("Segoe UI", 19, "bold"))
        style.configure("Muted.TLabel", foreground="#a1a1aa")
        style.configure("TNotebook", background="#18181b", borderwidth=0)
        style.configure("TNotebook.Tab", background="#27272a", foreground="#a1a1aa", padding=(18, 10))
        style.map("TNotebook.Tab", background=[("selected", "#2563eb")], foreground=[("selected", "white")])
        style.configure("Treeview", background="#27272a", fieldbackground="#27272a", foreground="#f4f4f5", rowheight=27)
        style.configure("Treeview.Heading", background="#3f3f46", foreground="#f4f4f5")
        style.map("Treeview", background=[("selected", "#2563eb")], foreground=[("selected", "white")])
        style.configure("TButton", background="#27272a", foreground="#f4f4f5", borderwidth=0, padding=(12, 8))
        style.map("TButton", background=[("active", "#3f3f46"), ("pressed", "#52525b")])
        style.configure("Accent.TButton", background="#2563eb", foreground="white")
        style.map("Accent.TButton", background=[("active", "#3b82f6"), ("pressed", "#1d4ed8")])
        for widget in ("TEntry", "TCombobox"):
            style.configure(widget, fieldbackground="#27272a", background="#27272a",
                            foreground="#f4f4f5", insertcolor="white", arrowcolor="#d4d4d8",
                            bordercolor="#3f3f46", lightcolor="#3f3f46", darkcolor="#3f3f46", padding=6)
            style.map(widget, fieldbackground=[("readonly", "#27272a")],
                      foreground=[("readonly", "#f4f4f5")], selectbackground=[("readonly", "#2563eb")])
        style.configure("TCheckbutton", background="#18181b", foreground="#e4e4e7",
                        indicatorbackground="#27272a", indicatorforeground="#60a5fa")
        style.map("TCheckbutton", background=[("active", "#18181b")],
                  indicatorbackground=[("selected", "#2563eb")])
        window.option_add("*TCombobox*Listbox.background", "#27272a")
        window.option_add("*TCombobox*Listbox.foreground", "#f4f4f5")
        window.option_add("*TCombobox*Listbox.selectBackground", "#2563eb")

    def poll(self):
        if self.closing:
            return
        try:
            self.process_events()
        except Exception as exc:
            # Never include event payloads (dictation/API data) in diagnostics.
            self.status.set(f"Bedienfehler ({type(exc).__name__}); Verarbeitung wird fortgesetzt.")
        finally:
            if not self.closing:
                self.root.after(30, self.poll)

    def process_events(self):
        for _ in range(200):
            try:
                event, value = self.events.get_nowait()
            except queue.Empty:
                break
            if event == "key":
                self.handle_key(*value)
            elif event == "model":
                self.model, self.backend = value
                self.loading = False
                self.engine_status.set(f"Engine: {self.backend}")
                if self.reload_requested:
                    self.reload_requested = False
                    self.load_model()
                    continue
                self.show_status(f"Bereit – {self.backend}", visible=False)
            elif event == "model_error":
                self.loading = False
                self.engine_status.set("Engine konnte nicht geladen werden")
                if self.reload_requested:
                    self.reload_requested = False
                    self.load_model()
                    continue
                self.show_status("Modell konnte nicht geladen werden. Internet, Speicher und Installation prüfen; über das Tray erneut laden.")
            elif event == "result":
                self.deliver(*value)
            elif event == "done" and value == self.job_id:
                self.processing_job = None
                self.busy = self.pending_delivery is not None
                if not self.busy:
                    self.root.withdraw()
            elif event == "job_error" and value == self.job_id and not self.cancelled.is_set():
                self.show_status("Transkription fehlgeschlagen. Modell erneut laden oder CPU wählen.")
            elif event == "limit" and value == self.job_id:
                self.stop_recording()
            elif event == "audio_error" and value == self.job_id:
                self.cancel()
                self.show_status("Audiofehler: Aufnahme verworfen. Mikrofon prüfen.")
            elif event == "settings":
                self.open_settings()
            elif event == "reconnect":
                self.start_listener()
                self.pressed.clear()
                self.show_status("Tastenkürzel neu verbunden.", visible=False)
            elif event == "reload":
                self.load_model()
            elif event == "show":
                self.show_status(self.status.get())
            elif event == "quit":
                self.shutdown()
                return
        if not self.closing:
            self.reconcile_hotkeys()
            self.update_meter()

    def shutdown(self):
        self.closing = True
        self.cancelled.set()
        with self.audio_lock:
            self.recording = False
            self.frames.clear()
        self.close_stream()
        self.listener.stop()
        self.tray.stop()
        self.api_key = ""
        for timer in self.root.tk.call("after", "info"):
            self.root.after_cancel(timer)
        self.root.destroy()


def main():
    if sys.platform != "win32":
        raise SystemExit("This release supports Windows only. macOS/Linux have not been validated.")
    instance = acquire_instance()
    if instance is None:
        return  # Already running: settings remain accessible through the tray.
    try:
        root = tk.Tk()
        app = AmberFlowApp(root, login_start="--autostart" in sys.argv)
        try:
            root.mainloop()
        finally:
            if not app.closing:
                app.shutdown()
    finally:
        release_instance(instance)


if __name__ == "__main__":
    main()
