"""Configuration, text processing and request safety; no desktop side effects."""

from copy import deepcopy
import json
import os
from pathlib import Path
import re
import tempfile
import threading
from urllib.parse import urlsplit
import urllib.request

VERSION = "0.2.3"
DEFAULT_CONFIG = {
    "hotkeys": {"ptt": "Key.ctrl_r + Key.shift_r", "toggle": "Key.f8", "cancel": "Key.esc"},
    "model_size": "small", "compute_device": "auto", "language": "de",
    "sound_feedback": True, "smart_cleanup": True, "auto_paste": True, "autostart": True,
    "max_recording_seconds": 120, "input_device": None,
    "llm_polish": {
        "mode": "off", "ollama_url": "http://localhost:11434/v1/chat/completions",
        "ollama_model": "qwen2.5:3b",
        "cloud_url": "https://api.groq.com/openai/v1/chat/completions",
        "cloud_model": "llama-3.3-70b-versatile",
    },
    "prompt_terms": ["Projektbesprechung", "Angebotsnummer", "Kundendienst"],
    "replacements": {"neuer Absatz": "\n\n", "neue Zeile": "\n", "Stichpunkt": "\n• ", "Anführungszeichen auf": "„", "Anführungszeichen zu": "“"},
}


class ConfigError(ValueError):
    pass


def validate_url(url, local=False):
    if not isinstance(url, str) or any(c.isspace() for c in url):
        raise ConfigError("Die API-Adresse ist ungültig.")
    try:
        parsed = urlsplit(url)
        port = parsed.port
    except ValueError as exc:
        raise ConfigError("Die API-Adresse ist ungültig.") from exc
    if not parsed.hostname or parsed.username or parsed.password or parsed.fragment:
        raise ConfigError("API-Adresse ohne Zugangsdaten oder Fragment angeben.")
    if parsed.query:
        raise ConfigError("API-Adresse ohne Query-Parameter angeben.")
    if local:
        if parsed.scheme not in ("http", "https") or parsed.hostname not in ("localhost", "127.0.0.1", "::1"):
            raise ConfigError("Ollama muss auf localhost, 127.0.0.1 oder ::1 laufen.")
    elif parsed.scheme != "https":
        raise ConfigError("Cloud-Verbindungen benötigen HTTPS.")
    return url


def canonical_hotkey(value):
    if not isinstance(value, str) or not value.strip():
        raise ConfigError("Hotkeys dürfen nicht leer sein.")
    # '+' itself is deliberately unsupported; named keys and single characters suffice.
    parts = [p.strip() for p in value.split("+")]
    if any(not re.fullmatch(r"Key\.[a-z0-9_]+|VK_[0-9]+|'[^'+]'", p) for p in parts):
        raise ConfigError("Ungültige Tastenkombination.")
    return " + ".join(sorted(set(parts)))


def validate_config(data):
    if not isinstance(data, dict):
        raise ConfigError("Die Konfiguration muss ein JSON-Objekt sein.")
    result = deepcopy(DEFAULT_CONFIG)
    # Only known fields are retained. Legacy credentials and obsolete options never persist.
    for name, default in DEFAULT_CONFIG.items():
        if name not in data:
            continue
        value = data[name]
        if name in ("hotkeys", "llm_polish"):
            if not isinstance(value, dict):
                raise ConfigError(f"{name} muss ein Objekt sein.")
            result[name].update({k: v for k, v in value.items() if k in default})
        else:
            result[name] = deepcopy(value)
    for key in ("sound_feedback", "smart_cleanup", "auto_paste", "autostart"):
        if type(result[key]) is not bool:
            raise ConfigError(f"{key} muss true oder false sein.")
    if result["model_size"] not in ("tiny", "base", "small", "medium", "large-v3-turbo"):
        raise ConfigError("Unbekannte Modellgröße.")
    if result["compute_device"] not in ("auto", "cpu", "cuda"):
        raise ConfigError("Unbekannter Hardware-Modus.")
    if result["language"] not in ("de", "en", "auto", None):
        raise ConfigError("Unbekannte Sprache.")
    seconds = result["max_recording_seconds"]
    if type(seconds) is not int or not 5 <= seconds <= 600:
        raise ConfigError("Aufnahmelimit: 5 bis 600 Sekunden.")
    device = result["input_device"]
    if device is not None and (type(device) is not int or device < 0):
        raise ConfigError("Ungültiges Mikrofon.")
    result["hotkeys"] = {k: canonical_hotkey(v) for k, v in result["hotkeys"].items()}
    if len(set(result["hotkeys"].values())) != 3:
        raise ConfigError("Die drei Hotkeys müssen unterschiedlich sein.")
    terms = result["prompt_terms"]
    if not isinstance(terms, list) or any(not isinstance(t, str) for t in terms):
        raise ConfigError("Fachbegriffe müssen eine Liste von Texten sein.")
    replacements = result["replacements"]
    if not isinstance(replacements, dict) or any(
        not isinstance(k, str) or not k.strip() or not isinstance(v, str)
        for k, v in replacements.items()
    ):
        raise ConfigError("Ersetzungen benötigen einen nichtleeren Suchbegriff und Textwert.")
    llm = result["llm_polish"]
    if llm["mode"] not in ("off", "ollama", "cloud"):
        raise ConfigError("Unbekannter Politur-Modus.")
    for field in ("ollama_model", "cloud_model"):
        if not isinstance(llm[field], str) or not llm[field].strip():
            raise ConfigError("Modellname darf nicht leer sein.")
    validate_url(llm["cloud_url"])
    validate_url(llm["ollama_url"], local=True)
    return result


def config_path():
    base = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local"))
    return base / "AmberFlow" / "config.json"


class ConfigStore:
    def __init__(self, path=None):
        self.path = Path(path) if path is not None else config_path()
        self.previous_path = self.path.parent.parent / "ArgonFlow" / "config.json" if path is None else None
        self.lock = threading.RLock()

    def load(self, legacy=None):
        """Read without creating or rewriting files. Legacy import requires explicit saving."""
        with self.lock:
            source = self.path
            migrated = False
            if not source.exists() and self.previous_path is not None and self.previous_path.is_file():
                source, migrated = self.previous_path, True
            if not source.exists():
                if legacy is None or not Path(legacy).is_file():
                    return deepcopy(DEFAULT_CONFIG), ""
                source, migrated = Path(legacy), True
            try:
                raw = json.loads(source.read_text(encoding="utf-8-sig"))
                clean = validate_config(raw)
            except (OSError, ValueError, TypeError) as exc:
                raise ConfigError("Konfiguration nicht lesbar oder ungültig. Die Datei bleibt unverändert.") from exc
            warning = ""
            if migrated:
                clean["llm_polish"]["mode"] = "off"
                warning = "Alte Einstellungen übernommen. Cloud ist zunächst aus. Speichern legt die neue Benutzerkonfiguration an."
            if isinstance(raw.get("llm_polish"), dict) and raw["llm_polish"].get("cloud_key"):
                warning += " Ein alter Klartext-Schlüssel wird nicht übernommen. Nach sicherer Einrichtung aus der alten Datei entfernen."
            return clean, warning.strip()

    def save(self, data):
        clean = validate_config(data)
        with self.lock:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            name = None
            try:
                with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=self.path.parent,
                                                 prefix="config-", suffix=".tmp", delete=False) as f:
                    name = f.name
                    json.dump(clean, f, indent=2, ensure_ascii=False)
                    f.write("\n")
                    f.flush()
                    os.fsync(f.fileno())
                os.replace(name, self.path)
            finally:
                if name is not None and os.path.exists(name):
                    os.unlink(name)
        return clean


def text_for_paste(text):
    """Separate successive dictations, preserving explicit whitespace/newlines."""
    return text + " " if text and not text[-1].isspace() else text


def clean_text(text, config):
    if config["smart_cleanup"]:
        text = re.sub(r"\b(ähm|äh|öhm|hm|uhm|uh)\b[, \t]*", "", text, flags=re.IGNORECASE)
        text = re.sub(r"[ \t]{2,}", " ", text).strip()
    for wrong, right in config["replacements"].items():
        command = r"(?<!\w)" + re.escape(wrong) + r"(?!\w)"
        if right in ("„", "“"):
            if right == "„":
                # Keep punctuation before the opening quote (e.g. a colon).
                pattern = command + r"[ \t]*[,;:]?[ \t]*"
            else:
                # Whisper often treats the spoken closing command as a clause.
                pattern = r"[ \t]*,?[ \t]*" + command
                # A trailing comma at the end is a command artefact. A comma
                # before a following clause can be grammatical and stays intact.
                pattern += r"(?:[ \t]*,(?=[ \t]*(?:$|[.!?\n])))?"
            text = re.sub(pattern, lambda match, replacement=right: replacement, text, flags=re.IGNORECASE)
        elif right.startswith("\n"):
            # Legacy dictionary entries omitted the space after the bullet.
            if re.fullmatch(r"\n+•[ \t]*", right):
                right = right.rstrip(" \t") + " "
            # Remove command separators, but retain sentence-ending punctuation.
            pattern = r"[ \t]*,?[ \t]*" + command + r"[ \t]*,?[ \t]*"
            text = re.sub(pattern, lambda match, replacement=right: replacement, text, flags=re.IGNORECASE)
        else:
            text = re.sub(re.escape(wrong), lambda match, replacement=right: replacement,
                          text, flags=re.IGNORECASE)
    return text


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        # Never forward a transcript or bearer credential to a redirect destination.
        return None


def polish_text(text, config, api_key="", cancelled=None):
    llm = config["llm_polish"]
    mode = llm["mode"]
    if not text or mode == "off" or (cancelled is not None and cancelled.is_set()):
        return text
    if mode == "cloud" and not api_key:
        raise ConfigError("Cloud-Schlüssel fehlt.")
    local = mode == "ollama"
    url = validate_url(llm["ollama_url" if local else "cloud_url"], local=local)
    payload = json.dumps({
        "model": llm["ollama_model" if local else "cloud_model"],
        "messages": [
            {"role": "system", "content": "Glätte das Diktat, ohne Fakten, Sprache oder Tonfall zu ändern. Antworte nur mit dem bereinigten Text."},
            {"role": "user", "content": text},
        ], "temperature": 0.1,
    }).encode("utf-8")
    req = urllib.request.Request(url, data=payload, headers={
        "Content-Type": "application/json", "Authorization": "Bearer " + ("ollama" if local else api_key),
    })
    # Local traffic must not traverse an environment-configured proxy.
    handlers = [NoRedirect()]
    if local:
        handlers.append(urllib.request.ProxyHandler({}))
    opener = urllib.request.build_opener(*handlers)
    with opener.open(req, timeout=15) as response:
        body = response.read(1_048_577)
    if len(body) > 1_048_576:
        raise ValueError("API-Antwort zu groß.")
    result = json.loads(body)["choices"][0]["message"]["content"]
    if not isinstance(result, str) or not result.strip():
        raise ValueError("API-Antwort enthält keinen Text.")
    return result.strip()
