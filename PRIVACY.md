# Data handling

- The global keyboard listener observes key presses/releases to recognize
  shortcuts. It keeps the currently held keys in memory; there is no keystroke
  log. Disable AmberFlow through the tray when it is not needed.
- The microphone is opened only while recording. Float audio samples are held
  in RAM, bounded by the recording limit, then passed to local faster-whisper.
  AmberFlow does not save audio recordings. Native libraries and the operating
  system may hold memory copies; releasing/zeroing Python buffers is not a
  forensic secure-erasure guarantee.
- Transcripts are processed in memory. Only the latest dictation is retained in
  process memory for the explicit tray recovery action; it is cleared at shutdown.
  No transcript log or audio file is written by the app. The preview appears only
  when requested. Native dependencies may emit diagnostics.
- Automatic insertion writes the transcript to the Windows clipboard, reads it
  back to check for intervening changes, and sends Ctrl+V. Previous clipboard
  contents are replaced and are not restored. The last copied text remains on the
  clipboard, including after the app exits. Clipboard history, synchronization and
  other software can retain it. Explicit **Text kopieren** has the same exposure.
  If a target check fails after copying, the text can remain on the clipboard even
  though no paste is sent.
- Text polishing is optional. Ollama sends text to a loopback endpoint on the
  same device. Cloud mode sends the full transcript, model choice and editing
  instruction to the configured HTTPS provider with the supplied API key.
  AmberFlow does not send audio to that provider. Polishing can change meaning.
- Cloud is confirmed per session. A cancellation cannot retract a request
  already received by the provider. No retention promise is made on its behalf.
- Model setup can contact Hugging Face and download weights into the user's
  cache. Dependency installation contacts package services. Offline inference
  requires these downloads to have completed first.
- Preferences and dictionary terms are local plaintext in
  `%LOCALAPPDATA%\AmberFlow\config.json`. They can contain personal information;
  do not upload that file. Protect your Windows account and backups accordingly.
- Keys remain in process memory or come from `AMBERFLOW_API_KEY`; they are not
  persisted by the app. A legacy dictionary containing a key is left untouched
  and produces a warning. Review old private backups separately.

This is a description of application behavior, not a guarantee about third-party
software, Windows, a cloud provider, or compromised machines.
