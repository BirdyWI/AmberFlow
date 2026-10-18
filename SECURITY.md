# Security

Do not include real API keys, private dictionaries, transcripts or audio in
public reports. For sensitive issues, use the repository's private vulnerability
reporting feature if enabled; otherwise ask the maintainer for a private channel
without disclosing exploit details or private data publicly.

This project is an early source release. Dependency audits and automated tests do
not constitute a security certification. The supported target is Windows x64
with the documented Python environment.

Before release, audit the exact pinned environment, inspect all staged files,
enable appropriate GitHub security features, and complete the desktop checks.
Never commit `.env`, personal `dictionary.json`, the user configuration or venvs.
