# AmberFlow 0.2.3 validation — 2026-10-21

83 tests passed locally, including three isolated interactive Windows tests.
The owner subsequently confirmed successful everyday testing of the Windows fix.

Publication checks identified eight advisories affecting the previous Pillow
12.3.0 pin. Both dependency manifests now pin Pillow 13.0.0, the fixed version
reported by pip-audit. This finding concerns the dependency and is not evidence
of an exploit in AmberFlow. The application's generated tray icon and full local
test suite are also checked with Pillow 13.0.0 before publication.

- Windows 11 Notepad reproduced invisible text and missing paragraphs with the
  Unicode keyboard-input path introduced in local 0.2.2.
- Native RichEdit insertion now preserves text, paragraphs, formatting and undo.
  A real Notepad test read back 12,459 characters plus the trailing dictation
  space exactly. Word wrapping, scrolling and one-step undo were checked visually.
- The clipboard sequence number stayed unchanged during insertion. Automated
  tests cover Unicode/surrogate input, unchanged clipboard behavior, foreground
  changes and RichEdit timeouts without duplicate fallback insertion.
- Other target controls keep the existing Unicode input behavior. Insertion into
  a different field within the same top-level window remains a known limitation.
- The public 0.2.1 release used clipboard paste; this release includes both the
  locally accepted clipboard-free change and its Notepad compatibility fix.

The automated tests use defined transcription text and simulated hardware/network
responses, not live speech or cloud calls. The owner's everyday acceptance is
separate from those automated results. See the earlier limits below.

---

# AmberFlow 0.2.1 validation — 2026-10-19

74 tests passed locally, including three isolated interactive Windows tests.
New tests cover silent hook loss, missed releases, no duplicate shortcut triggers,
settings/capture behavior, idle stability and recovery after event-handler errors.
The reported multi-minute idle failure has not been reproduced directly; these
checks simulate the specific failure modes addressed by the fix. The owner subsequently
confirmed that shortcuts remained responsive after idle periods in everyday use.
All 74 local tests passed again before publication. No real speech
or cloud calls were used for these tests.

---

# AmberFlow 0.2.0 validation — 2026-10-18

## Current release

- 68 tests passed on Windows / Python 3.11, including three interactive desktop tests.
- The desktop tests verify settings startup, HUD behavior and native insertion
  into an isolated text field. They restore the clipboard and use no microphone or cloud.
- Dictionary editing, spoken quotes, paragraph/line commands, comma cleanup and
  bullet spacing are covered by regression tests.
- Rename tests verify old settings migration, new settings precedence and narrowly
  scoped cleanup of the old autostart entry.
- `pip check` passed in the installed environment.
- OSV checked all 32 pinned runtime packages on 2026-10-18: no advisories returned.
  This is a point-in-time dependency check, not a security guarantee.
- The owner accepted real dictation, insertion, HUD and formatting behavior on
  their computer before the rename. The rename was checked with the tests above.

## Earlier environment checks (same runtime dependency lock)

A fresh Windows/Python 3.11 environment installed all 32 pinned runtime packages
and passed `pip check`. GPU testing on the owner's computer verified cached
large-v3-turbo loading and synthetic-silence inference after repairing NVIDIA
DLL discovery. No model was downloaded for that probe; it is not a speech
accuracy or latency benchmark. The CPU fallback is also covered with mocked errors.

## Limits

Live Ollama/cloud calls have not been tested; HTTP handling uses simulated responses
in tests. No Windows reboot was performed to validate login startup. This is a
source release, not a signed executable or installer. Other Windows versions,
hardware, elevated applications and target fields may behave differently.

Only source, general example settings, documentation and tests are distributed.
Private settings, API credentials, recordings, models, local logos and Python
environments are excluded.
