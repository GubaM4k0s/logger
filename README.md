# Logger

A minimal (Windows-focused) GUI-based activity logger intended for short, timed sessions (e.g. exam / assessment environments).  
It records:

- Foreground application/process changes
- Window titles
- Clipboard changes (with truncated preview)
- Optional browser URL events via a local HTTP server
- A live-tailed PowerShell transcript file (`logs/log01.txt`) which is archived (encrypted) on exit
- Start/stop button events and a countdown timer (with 5‑minute pre-warning)
- Optional termination of common editor processes at timer expiry

All sensitive/event data are appended in **encrypted form** (`Fernet`) to `.enc` files inside the `logs/` directory.

> IMPORTANT: This tool touches user activity and clipboard contents. Use only with the user’s informed consent and in compliance with applicable laws, organizational policy, and ethical standards.

---

## Features

| Category                | Details |
|-------------------------|---------|
| GUI (Tkinter)           | Start / Finish buttons, timer display, two live text panes (activity + PowerShell transcript) |
| Auto background spawn   | Re-launches itself in a detached mode with `--daemon` flag |
| Encryption              | Uses a hard-coded Fernet key (replace this!) |
| Foreground tracking     | Polls active window (process + title) via Win32 API (Windows only) |
| Clipboard monitoring    | Polls clipboard every 800 ms and logs changes (truncated to 300 chars) |
| HTTP URL intake         | Local server at `http://127.0.0.1:8765` accepts POST JSON: `{"url": "...", "title": "..."}` |
| PowerShell transcript   | Tails `logs/log01.txt` (e.g. created by `Start-Transcript`) and archives it encrypted on exit |
| Timer / alerts          | Configurable duration, 5‑minute warning, final popup on expiry |
| Optional editor cleanup | On expiry, terminates common VS / VSCode executables (if `psutil` installed) |
| Minimal dependencies    | `cryptography` required; `psutil` optional; Tkinter bundled with most CPython on Windows |

---

## How It Works (Flow)

1. Script starts → if not already running with `--daemon`, it respawns itself and exits the foreground instance.
2. GUI launches; activity log begins.
3. User presses “I started the exam” → timer begins.
4. Foreground window / clipboard / (optional) URL events are logged.
5. If a PowerShell transcript (`logs/log01.txt`) exists, it's live-tailed into the lower pane.
6. At 5 minutes remaining, a warning event + popup are triggered.
7. At timer expiration (or manual Finish):  
   - (Optional) editor processes are terminated.  
   - Transcript file is encrypted line-by-line into `transcript.enc`.  
   - Plain transcript file is deleted (best-effort).
8. Encrypted logs remain in `logs/`.

---

## Repository Layout (current minimal state)

```
logger.py
logs/                # Created automatically on first run
  activity.enc       # Encrypted activity lines
  transcript.enc     # Encrypted transcript lines (appended on exits over time)
  log01.txt          # (Optional) Plaintext live PowerShell transcript while session runs
```

---

## Installation

```bash
# Clone
git clone https://github.com/GubaM4k0s/logger.git
cd logger

# (Recommended) create virtual environment
python -m venv .venv
# Windows activation:
.venv\Scripts\activate

# Install required packages
pip install cryptography

# Optional (process names, nicer app detection, editor termination)
pip install psutil
```

Tkinter: Included in standard Windows CPython installers. If missing, reinstall Python with Tcl/Tk enabled.

---

## Running

```bash
python logger.py
```

You’ll see:
- A console message “Logging started in background..” (initial launcher)
- The GUI window (spawned `--daemon` instance)

If you want to suppress **all** console windows, run from a `.pyw` file or package into an executable (e.g. PyInstaller with `--noconsole`).

### Disabling Auto Respawn

Comment out or remove the call to `ensure_background()` near the top if you prefer a single foreground process.

---

## Timer Configuration

In `logger.py`:

```python
TIMER_SECONDS = 450  # 7.5 minutes (example)
```

Adjust as needed. The 5‑minute pre-warning threshold is currently hard-coded at `remaining <= 300`.

---

## PowerShell Transcript Integration (Optional)

To populate the lower pane:

1. Before (or after) starting the logger, run in PowerShell:
   ```powershell
   New-Item -ItemType Directory -Path .\logs -ErrorAction SilentlyContinue | Out-Null
   Start-Transcript -Path .\logs\log01.txt -Append
   ```
2. Perform your console actions.
3. When the logger session stops, the plaintext transcript is:
   - Read + encrypted line-by-line into `transcript.enc`
   - Deleted (best-effort) afterward.

---

## HTTP URL Logging API (Optional)

Local server binds to: `http://127.0.0.1:8765`

### Record a URL

```bash
curl -X POST http://127.0.0.1:8765 \
  -H "Content-Type: application/json" \
  -d "{\"url\":\"https://example.com\", \"title\":\"Example Domain\"}"
```

### Shutdown via HTTP

```bash
curl http://127.0.0.1:8765/shutdown
```

(Log will note shutdown; cleanup runs.)

---

## Encryption Details

- Uses a single hard-coded **Fernet** key:
  ```python
  FERNET = Fernet(b"xVtjZaeSuP65U8U213SodWIw0v8tOZCBtnk_TuUOYP8=")
  ```
- Each line/event encrypted individually; ciphertext lines separated by `\n`.
- To decrypt later:

```python
from cryptography.fernet import Fernet

KEY = b"xVtjZaeSuP65U8U213SodWIw0v8tOZCBtnk_TuUOYP8="  # replace with actual
fernet = Fernet(KEY)

with open("logs/activity.enc","rb") as f:
    for line in f:
        line = line.strip()
        if not line: continue
        try:
            print(fernet.decrypt(line).decode())
        except Exception as e:
            print("Failed line:", e)
```

### IMPORTANT: Replace the Key
Generate a fresh key for real use:

```python
from cryptography.fernet import Fernet
print(Fernet.generate_key())
```

Store it securely (env var, config file not committed, etc.).

---

## Editor Termination Logic

On timer expiry (only when `do_close_editors=True` in `stop_everything`) the script attempts to terminate processes with names in:

```python
VS_CANDIDATES = ["devenv.exe", "code.exe", "visualstudio.exe", "visualstudiocode.exe"]
```

Modify or clear this list if not desired.

---

## Cross-Platform Notes

| Component              | Windows | macOS | Linux |
|------------------------|---------|-------|-------|
| Tkinter GUI            | Yes     | Yes   | Yes   |
| Foreground window API  | Implemented via Win32 | Not implemented | Not implemented |
| Editor termination     | Via `psutil` | Likely works (process names differ) | Works (names differ) |
| PowerShell transcript  | Native PowerShell | Requires PowerShell Core | Requires PowerShell Core |
| Clipboard polling      | Yes (Tkinter) | Yes | Yes |

Non-Windows systems will fail on the Win32 API imports (`ctypes.WinDLL('user32', ...)`). If portability is needed, guard these sections with OS checks.

---

## Ethical & Legal Considerations

This tool:
- Captures potentially sensitive clipboard contents.
- Monitors active application usage.
- Archives terminal/PowerShell commands (if transcript enabled).

Best practices:
- Obtain explicit informed consent.
- Disclose retention & encryption policies.
- Allow users to inspect exported decrypted logs.
- Never deploy with a public or reused encryption key.

---

## Potential Improvements (Roadmap Ideas)

- Config file / CLI arguments (timer length, polling intervals, port)
- Real-time decryption viewer (admin tool)
- Hash integrity chain per line (tamper detection)
- Secure key management (KMS / DPAPI)
- Optional screenshot capture (with strict consent)
- Structured JSON log mode before encryption
- Packaging as executable (PyInstaller) for easier distribution

---

## Troubleshooting

| Issue | Cause | Fix |
|-------|-------|-----|
| GUI never appears | Spawned daemon terminated early | Run `python logger.py --daemon` directly to test |
| No foreground events | Non-Windows or Win32 API blocked | Run on Windows; ensure not in RDP minimal shell |
| Clipboard errors | OS clipboard locked | These are ignored silently; normal |
| Transcript not archived | `log01.txt` missing | Ensure you started `Start-Transcript` in `logs/` |
| Decryption fails | Wrong key or truncated file | Verify key; avoid manual edits to `.enc` |

---

## Security Notes

- Encryption is only as strong as key handling.
- Clipboard previews truncated to 300 chars but still may contain secrets.
- Consider excluding patterns (passwords, tokens) before logging (not implemented).
- The HTTP server binds only to loopback by default (`127.0.0.1`).

---

## License

Add a license of your choice (e.g. MIT) here. Example:

```
MIT License (placeholder—replace with actual)
```

---

## Disclaimer

Provided “as is” without warranty. The author(s) are not responsible for misuse or violations arising from deployment of this tool.

---

## Quick Start Summary

```bash
git clone https://github.com/GubaM4k0s/logger
cd logger
python -m venv .venv
.venv\Scripts\activate
pip install cryptography psutil
python logger.py
# (Optional in parallel PowerShell:)
# Start-Transcript -Path .\logs\log01.txt -Append
```

Press “I started the exam”, let timer run, finish or wait for expiry, encrypted logs end up in `logs/`.

---

## Contributing

1. Fork repository
2. Create feature branch
3. Make changes (add OS guards, config parsing, etc.)
4. Submit Pull Request with description

---

Feel free to adapt text, branding, or scope for your specific institution / workflow.

---
