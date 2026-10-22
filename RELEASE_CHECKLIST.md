# AmberFlow 0.2.4 release checklist

- 89 tests passed locally on Windows/Python 3.11, including all three interactive
  desktop tests. Clipboard delivery, focus/clipboard races, cancellation, no
  duplicate paste, explicit-only preview and dictionary hints are covered.
- The owner accepted the isolated clipboard speech test and the installed 0.2.4
  build in Notepad and browser fields. Chrome and Firefox were included in the
  requested acceptance workflow. LinkedIn's paragraph-to-line-break behavior is
  accepted as a remaining limitation; Google Docs is not separately certified here.
- A separate AmberFlow environment passed pip check and all 89 tests; cached
  large-v3-turbo performed synthetic-silence inference on CUDA. No imports from
  the previous ArgonFlow directory were observed. Desktop shortcut and autostart
  were verified against the new environment; a Windows login/reboot was not tested.
- Publication retains the existing public Pillow 13.0.0 lock, rather than copying
  the local installation's older dependency manifest. GitHub CI validates the
  public lock separately; interactive desktop checks are not run in hosted CI.
- Only source, regression tests and documentation are included. No runtime,
  personal configuration, test transcripts or local installation scripts are shipped.

This is a source update, not a signed installer. Live cloud/Ollama acceptance
and compatibility with every Windows text field are not claimed.

---

# AmberFlow 0.2.3 release checklist

- [x] Clipboard-free direct input and the Notepad compatibility fix tested locally.
- [x] 83 local tests passed, including three interactive Windows tests.
- [x] Notepad long-text readback, paragraphs, word wrapping, scrolling and undo checked.
- [x] Owner confirmed everyday Windows acceptance before publication.
- [x] Only reviewed source, tests and documentation included; no private settings,
  installation paths, recordings, models or runtime environments.

GitHub Actions results are linked from the release pull request. The interactive
desktop tests are opt-in and are not claimed to run on GitHub's hosted runner.

## Previous 0.2.0 release checklist

- [x] Product name updated in Cockpit, tray, windows and documentation.
- [x] Existing settings retained through tested migration.
- [x] 68 tests passed, including isolated desktop integration checks.
- [x] Installed dependencies pass `pip check`.
- [x] All 32 locked runtime versions checked against OSV; no findings.
- [x] Owner accepted dictation and formatting behavior on Windows.
- [x] Public repository name and visibility explicitly approved by the owner.
- [x] MIT license, dependency notices, privacy and security documentation included.
- [x] Release contains no personal dictionary, credentials, audio, models or venv.

See VALIDATION.md for the evidence and limitations. Optional live Ollama/cloud
checks and a reboot/login check are outstanding; they are not represented as passed.
GitHub CI results must be checked after the initial publication.
