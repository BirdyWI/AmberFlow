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
