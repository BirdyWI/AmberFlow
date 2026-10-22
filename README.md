# AmberFlow

Local speech-to-text for Windows, with global push-to-talk, a tray menu,
German voice commands and optional text polishing through Ollama or a cloud API.

**Version: 0.2.5 — formatted dictation with clipboard restoration.** This is a Python source distribution, not an
installer or signed EXE. Windows desktop acceptance checks are listed in
[RELEASE_CHECKLIST.md](RELEASE_CHECKLIST.md). No macOS, Linux or Apple Neural
Engine support is claimed for this release.

### Text-field compatibility (0.2.5)

Automatic dictation temporarily provides prepared text through the Windows clipboard
and sends Ctrl+V. Previous supported clipboard formats are saved in memory and
restored after an observed text request plus a safety interval, or a bounded timeout.
A newer user copy takes precedence. There is no automatic retry.

Unreadable, unsupported or oversized formats cause a safe abort before replacing
the clipboard. An unreadable EnterpriseDataProtectionId marker is omitted only
when the documented Windows API confirms that no enterprise identity exists.
This fixes the abort observed after fresh Ctrl+C in Windows Notepad.

The owner accepted real dictation and clipboard preservation in Notepad and browser
fields with the separate candidate, then accepted the upgraded normal installation
and reported that the earlier insertion pause had disappeared. LinkedIn may display paragraph breaks as single line breaks;
compatibility with every application is not guaranteed.

## Install on Windows

Use Windows 10/11 x64 and **Python 3.11 x64 with Tcl/Tk**. The pinned environment
targets Python 3.11. Other Python versions have not been validated.

Download and extract the repository ZIP, or clone it using its actual GitHub
Clone URL. Open PowerShell in the extracted AmberFlow directory, then run:

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip setuptools
.\.venv\Scripts\python.exe -m pip install -r requirements-win-py311.lock.txt
.\.venv\Scripts\python.exe -m pip check
.\.venv\Scripts\python.exe app.py
```

Create the virtual environment inside this AmberFlow checkout; do not reuse an
ArgonFlow environment. Desktop shortcuts and autostart must point to this checkout
and its own Python executable. The installed system Python and user model cache
remain separate dependencies. Environment activation is unnecessary. Installation needs internet access.
On first use, faster-whisper downloads the selected model from Hugging Face
into its user cache. A different model may trigger another download. Allow
several GB of free disk space for larger models and sufficient RAM/VRAM;
performance depends on the selected model and hardware. Start with `small`, or
`tiny`/`base` on constrained machines. CPU INT8 inference is supported.

If native libraries cannot load, install the current Microsoft Visual C++ x64
Redistributable and verify the 64-bit Python installation.

### Optional NVIDIA acceleration

The CPU install does not install NVIDIA runtimes. The pinned CTranslate2 version
uses CUDA 12 / cuDNN 9. Install a compatible NVIDIA driver and runtimes according
to the [faster-whisper instructions](https://github.com/SYSTRAN/faster-whisper#gpu)
and [CTranslate2 installation guide](https://opennmt.net/CTranslate2/installation.html).
The application also discovers NVIDIA runtime DLL directories inside its own
virtual environment and registers them in both the Windows DLL search path and PATH
so CTranslate2 can actually load cuBLAS/cuDNN. GPU initialization includes a short inference check and
falls back to CPU if it fails. The active engine is displayed in settings.

CUDA packages are deliberately separate from the CPU lock file. GPU operation
requires its own hardware acceptance test; an import check alone is insufficient.

## Use

- Hold **right Ctrl + right Shift**, speak, then release either key.
- Press **F8** to start/stop hands-free recording.
- Press **Escape** to cancel recording or discard pending processing output.
- Right-click the tray icon for settings, status, hotkey reconnection, model retry or exit.
- The microphone opens only for a recording and closes at stop/cancel.
- Recordings stop after 120 seconds by default; settings allow 5–600 seconds.
- Only one recording/processing job runs at once. Wait for it to finish.

On manual launch the dark Cockpit opens, including while the model loads.
Close it to return to your work. The compact nonactivating HUD shows five live
level bars in **red during recording** and switches to **orange during transcription
and pending insertion**. It disappears when insertion finishes or you cancel.
It stays hidden while idle. Engine readiness appears in settings; operation status is available through the tray.

### Windows autostart

**Enabled by default.** The checkbox **Bei der Windows-Anmeldung automatisch
starten** in General settings enables/disables startup for your Windows account.
Save settings to apply it. The app uses only its own `AmberFlow` value under
`HKEY_CURRENT_USER\Software\Microsoft\Windows\CurrentVersion\Run`; no admin
rights or service installation are needed. Windows starts it after login, not
before a user has signed in. Windows Startup Apps policy can independently block it.

Login startup uses the virtual environment's `pythonw.exe` and opens in the tray
without a settings window. Manual launch opens settings. A second launch does
not create a duplicate microphone/keyboard listener; use the existing tray icon.
Moving or removing the project requires updating/disabling its startup entry.

**Automatic clipboard insertion is the default.** On completion AmberFlow waits
briefly for held modifier keys to be released, checks the original foreground
window, copies the prepared text and sends Ctrl+V. A trailing space separates
consecutive dictations; existing trailing whitespace and line breaks are preserved.
The previous supported clipboard contents are restored; copying something new
during the transaction takes precedence. Windows history/cloud opt-out markers
are set, but third-party clipboard managers may still retain the transcript.
The first clipboard read is not proof of successful insertion into the intended
field. A safety interval and an eight-second timeout bound the restore; an
exceptionally delayed target or a hard process termination remains a limitation.

The preview remains hidden unless you enable **Diktat vor dem Einfügen prüfen**
or explicitly choose **Letztes Diktat anzeigen** in the tray. The latter retains
only the latest dictation in process memory, not a saved transcript log.

If the target changed, modifiers remain held, or insertion fails, a tray notice
offers the explicit recovery action; no preview opens automatically. There is
no automatic retry after a possibly partial paste. Check the destination before
reusing the retained text to avoid duplicates. AmberFlow does not force focus back
to a window you have left. Clipboard changes and focus are rechecked before Ctrl+V;
the clipboard can still change after that check. A different field inside the same
top-level window cannot be detected. Elevated or paste-blocking apps may reject
input, and single-line fields cannot preserve multiline formatting.

Transcription and optional polishing may change words or meaning. Review
important text before sending or relying on it.

## Upgrading from ArgonFlow

AmberFlow is the new name of this Windows dictation app. The Cockpit, tray and
windows use AmberFlow. For independent installations, keep the previous directory
as a backup and install AmberFlow with its own environment using the steps above.
Do not move an existing virtual environment: recreate it in the new directory.
Update shortcuts and startup entries, and close the old app before starting the new
one. Downloaded models can remain in the user cache.

If AmberFlow settings do not yet exist, the app reads the previous
`%LOCALAPPDATA%\ArgonFlow\config.json`. Saving writes to the new AmberFlow
location and preserves the old file. An existing AmberFlow configuration takes
priority. `ARGONFLOW_API_KEY` remains a fallback for the new `AMBERFLOW_API_KEY`.
The old autostart entry is removed only when it points to this exact installation.
Old and new app versions share an instance lock to avoid double recording.

## Hotkey recovery

The app reconciles configured shortcuts and held keys with the current Windows
key state every UI cycle. This provides a fallback if the keyboard hook loses
press/release events or is silently removed. Missing events can trigger a listener
restart, with a five-second retry limit. The tray action **Tastenkürzel neu verbinden**
reconnects the listener without reloading the speech model. Individual event-handler
errors no longer permanently stop UI event processing.

This fix covers simulated hook loss, lost releases and event-handler failures.
It does not claim to reproduce every cause of long-running unresponsiveness.

## Settings and personal dictionary

Settings are stored in `%LOCALAPPDATA%\AmberFlow\config.json`, independent of the
working directory. Missing settings use safe defaults without creating a file;
the **Speichern** button writes them atomically. Invalid files are left intact
and the app starts with safe defaults and a warning. Saving then replaces the
invalid user configuration with the corrected settings.

An existing `dictionary.json` next to `app.py` is read once as a legacy source
when the new user configuration does not exist. It is not modified. Recognized
preferences and dictionary entries are retained; obsolete fields and API keys
are discarded. Cloud is initially disabled on migration. Direct insertion is enabled unless an explicit
review preference was saved in the configuration.
Saving creates the new user configuration. The old file remains private and
excluded from Git; remove obsolete plaintext credentials there yourself after
migration if it contains any.

Use the settings tabs to select the microphone, hardware, model and language,
record hotkeys, and edit terminology and replacements. The dictionary editor provides a list with spoken and written text. Add, edit or remove entries without configuration syntax. Enter inserts a real line break in the replacement field. Terms are entered one per line. Saving also applies the entry currently being edited.

### Spoken formatting commands

| Say | Result |
| --- | --- |
| neuer Absatz | A blank line between paragraphs |
| neue Zeile | A line break |
| Stichpunkt | A new bullet with a space before the first word |
| Anführungszeichen auf | German opening quote: „ |
| Anführungszeichen zu | German closing quote: “ |

Example: `Das ist Anführungszeichen auf eine gute Idee Anführungszeichen zu`
becomes `Das ist „eine gute Idee“`. Command-adjacent commas are cleaned up;
commas within the dictated text are retained. Recognition examples are general
terms such as Projektbesprechung, Angebotsnummer and Kundendienst.

## Optional AI polishing

Polishing is **off by default**. Speech recognition always runs locally.

- **Ollama:** install Ollama separately and download a model such as `qwen2.5:3b`.
  The endpoint must use `localhost`, `127.0.0.1` or `::1`. After model setup it can
  operate locally without cloud inference. Proxy settings are bypassed for this
  local connection.
- **Cloud:** choose an OpenAI-compatible HTTPS endpoint and model. The complete
  transcript is sent to that provider; its pricing, terms and retention rules
  apply. Enabling cloud requires confirmation in every application session.
  HTTP redirects are refused so the app does not forward credentials or text to
  a redirected destination.
- Enter a key in the masked field for the current session, or provide the
  `AMBERFLOW_API_KEY` environment variable before launch. Keys are never written
  to the application configuration. An environment variable is not a credential
  vault; set it only in an appropriately protected session. Do not put real keys
  into source files, screenshots, issue reports or shell scripts.

If polishing fails or times out, the local transcript is used with the selected
insertion mode; the status reports that polishing was skipped.
Cancelling suppresses output and subsequent requests where possible; it cannot
recall text already sent to an API or forcibly stop native inference immediately.

See [PRIVACY.md](PRIVACY.md) for the complete data flow and limitations.

## Verify and contribute

```powershell
.\.venv\Scripts\python.exe -B -m unittest discover -s tests -v
.\.venv\Scripts\python.exe -m pip check
```

Default tests use simulated audio, model responses, clipboard and keyboard operations;
they do not record speech or call a provider. CI runs them on Windows/Python 3.11
and audits dependencies. Three additional opt-in desktop tests verify settings startup, HUD focus and
actual paste into their own isolated Tk text field. Enable them with
`$env:AMBERFLOW_DESKTOP_TEST="1"` before running the tests on an interactive desktop.
They briefly activate their own window and place synthetic test text on the clipboard.
Real speech and target-app behavior were accepted by the owner on their Windows computer. Other hardware and applications can behave differently. Live Ollama/cloud integration has not been verified.

Eleven additional native clipboard tests are opt-in: set
`$env:AMBERFLOW_CLIPBOARD_TEST="1"` on an interactive Windows desktop and rerun
the suite while not copying or dictating. They use synthetic clipboard fixtures
and restore the original supported contents; a detected newer copy takes priority.
Unsupported originals abort setup rather than being discarded. These are separate
from the three desktop tests and are not enabled in hosted CI.

The code is split into `amber_core.py` (configuration, cleanup and HTTP safety),
`app.py` (UI and recording coordination), `dictionary_editor.py` (dictionary UI),
`autostart.py` (Windows login startup), and `windows_desktop.py` (nonactivating HUD and native paste).
No packaging step is needed to run this source release. Do not distribute a
virtual environment or an unreviewed standalone executable.

## License

AmberFlow source is licensed under the [MIT License](LICENSE). Dependencies and
downloaded models retain their own licenses; see [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).
The tray icon is drawn by the application. Legacy local logo files are not
included in this distribution.

Dictionary rows show real line breaks as ↵. Use Enter once for a line break or
twice for a blank line; a literal `\n` is flagged as text, not silently converted.
