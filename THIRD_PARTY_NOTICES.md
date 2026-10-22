# Third-party components

The MIT license covers AmberFlow's own source. It does not relicense dependencies,
model weights, NVIDIA components or third-party binary libraries.

Direct dependencies in the tested environment declare:

| Component | License reported by package metadata |
| --- | --- |
| faster-whisper | MIT |
| CTranslate2 | MIT |
| sounddevice | MIT |
| NumPy | BSD-3-Clause and bundled third-party notices |
| pyperclip | BSD |
| pynput | LGPLv3 |
| pystray | LGPLv3 |
| Pillow | MIT-CMU |

These are inventory labels, not a substitute for the complete license texts
shipped in the respective distributions. Transitive dependencies also carry
their own notices; PyAV wheels include FFmpeg components, for example.

This release ships source and dependency specifications, not copies of those
installed packages or model weights. Before distributing an executable,
installer, environment, NVIDIA libraries or model weights, inventory all bundled
components and include the applicable license texts, attribution and any
required source/relinking materials. In particular, review LGPL obligations for
pynput/pystray and bundled media libraries. Validate each model's own model card
and license before redistributing it.

Useful upstream sources:
- https://github.com/SYSTRAN/faster-whisper
- https://github.com/OpenNMT/CTranslate2
- https://github.com/moses-palmer/pynput
- https://github.com/moses-palmer/pystray
- https://pyav.org/

The application renders its own geometric tray icon. Old personal `logo.ico` or
`logo.png` files are excluded and not loaded by this release.

## Clipboard design reference

The Windows clipboard transaction is an independent Python implementation informed
by the receipt-sequenced paste approach in [Handy](https://github.com/cjpais/Handy/tree/main/src-tauri/src/paste_tx),
an MIT-licensed project (Copyright 2025 CJ Pais). Handy source is not bundled.
Clipboard-format validation and the empty Windows enterprise-identity marker
handling are specific to this implementation.
