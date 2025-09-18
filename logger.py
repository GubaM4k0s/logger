import os, sys, subprocess, time, threading, getpass, socket, json, ctypes
from datetime import datetime, timedelta
from http.server import HTTPServer, BaseHTTPRequestHandler
import tkinter as tk
from tkinter import messagebox
from ctypes import wintypes

# -------- optional: psutil ----------
try:
    import psutil
    PSUTIL = True
except Exception:
    PSUTIL = False

# -------- encryption ----------
from cryptography.fernet import Fernet
FERNET = Fernet(b"xVtjZaeSuP65U8U213SodWIw0v8tOZCBtnk_TuUOYP8=")  # replace with your key if needed

# -------- background re-spawn ----------
def ensure_background():
    if "--daemon" not in sys.argv:
        creationflags = 0
        if os.name == "nt":
            creationflags = getattr(subprocess, "DETACHED_PROCESS", 0) | getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
        subprocess.Popen(
            [sys.executable, sys.argv[0], "--daemon"],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, stdin=subprocess.DEVNULL,
            creationflags=creationflags
        )
        print("Logging started in background..")
        sys.exit(0)

ensure_background()

# -------- settings ----------
USER = getpass.getuser()
HOST = socket.gethostname()
LOG_DIR = "logs"
os.makedirs(LOG_DIR, exist_ok=True)

ENC_ACTIVITY   = os.path.join(LOG_DIR, "activity.enc")
ENC_TRANSCRIPT = os.path.join(LOG_DIR, "transcript.enc")
TRANSCRIPT_TXT = os.path.join(LOG_DIR, "log01.txt")  # written by PowerShell Start-Transcript

HTTP_BIND = ("127.0.0.1", 8765)
FOREGROUND_POLL_MS = 500
CLIPBOARD_POLL_MS  = 800

TIMER_SECONDS = 450
VS_CANDIDATES = [s.lower() for s in [
    "devenv.exe", "code.exe", "visualstudio.exe", "visualstudiocode.exe"
]]

# -------- utils ----------
def enc_append(path_enc: str, plaintext_line: str):
    token = FERNET.encrypt(plaintext_line.encode("utf-8", errors="ignore"))
    with open(path_enc, "ab") as f:
        f.write(token + b"\n")

def now(): return datetime.now().strftime("%Y-%m-%d %H:%M:%S")
def activity_line(text: str) -> str: return f"{now()} | {text}"

def detect_encoding(path: str) -> str:
    # detect BOM: utf-16 (LE/BE), utf-8-sig, else utf-8
    try:
        with open(path, "rb") as f:
            head = f.read(4)
        if head.startswith(b"\xff\xfe") or head.startswith(b"\xfe\xff"):
            return "utf-16"
        if head.startswith(b"\xef\xbb\xbf"):
            return "utf-8-sig"
    except Exception:
        pass
    return "utf-8"

# -------- GUI ----------
root = tk.Tk()
root.title("LOGGER")

controls = tk.Frame(root); controls.pack(fill='x', padx=6, pady=6)
btn_start = tk.Button(controls, text="I started the exam", width=22)
btn_stop  = tk.Button(controls, text="I finished the exam", width=22)
btn_start.pack(side='left', padx=4); btn_stop.pack(side='left', padx=4)

timer_var = tk.StringVar(value="Timer: --:--")
tk.Label(controls, textvariable=timer_var, font=("Segoe UI", 11, "bold")).pack(side='right')

tk.Label(root, text=f"User: {USER} @ {HOST} — Encrypted log: {ENC_ACTIVITY}").pack(anchor='w', padx=6)
top_text = tk.Text(root, width=120, height=15, state='disabled', wrap='none');     top_text.pack(padx=6, pady=(0,6))
tk.Label(root, text="PowerShell transcript (live view from log01.txt)").pack(anchor='w', padx=6)
bottom_text = tk.Text(root, width=120, height=12, state='disabled', wrap='none');  bottom_text.pack(padx=6, pady=(0,6))

def _ui_append(widget, line: str):
    widget.configure(state='normal'); widget.insert('end', line + "\n"); widget.see('end'); widget.configure(state='disabled')

def ui_append_top(line: str):
    root.after(0, lambda: _ui_append(top_text, line))

def ui_append_bottom(line: str):
    root.after(0, lambda: _ui_append(bottom_text, line))

def log_activity(text: str):
    line = activity_line(text); ui_append_top(line); enc_append(ENC_ACTIVITY, line)

# -------- foreground window tracking (Windows) ----------
user32 = ctypes.WinDLL('user32', use_last_error=True)
GetForegroundWindow = user32.GetForegroundWindow
GetWindowTextLengthW = user32.GetWindowTextLengthW
GetWindowTextW = user32.GetWindowTextW
GetWindowThreadProcessId = user32.GetWindowThreadProcessId

def get_foreground_info():
    hwnd = GetForegroundWindow()
    if not hwnd: return None, None, None
    length = GetWindowTextLengthW(hwnd); buf = ctypes.create_unicode_buffer(length + 1)
    GetWindowTextW(hwnd, buf, length + 1); title = buf.value
    pid = wintypes.DWORD(); GetWindowThreadProcessId(hwnd, ctypes.byref(pid)); pid = pid.value
    proc_name = str(pid)
    if PSUTIL:
        try: proc_name = psutil.Process(pid).name()
        except: pass
    return hwnd, proc_name, title

_last_foreground = (None, None)
def poll_foreground():
    global _last_foreground
    hwnd, proc, title = get_foreground_info()
    if proc:
        key = ((proc or "").lower(), title or "")
        if key != _last_foreground:
            pretty = title if title else "<no-title>"
            log_activity(f"FOREGROUND | app={proc} | title={pretty}")
            _last_foreground = key
    root.after(FOREGROUND_POLL_MS, poll_foreground)

# -------- clipboard tracking ----------
_last_clip = None
def poll_clipboard():
    global _last_clip
    try: clip = root.clipboard_get()
    except: clip = None
    if clip is not None and clip != _last_clip:
        _last_clip = clip
        preview = clip if len(clip) <= 300 else clip[:300] + "..."
        log_activity(f"CLIPBOARD_CHANGED | preview={preview}")
    root.after(CLIPBOARD_POLL_MS, poll_clipboard)

# -------- HTTP (optional URL logging) ----------
class URLHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == "/shutdown":
            self.send_response(200); self.end_headers(); self.wfile.write(b"bye")
            root.after(0, lambda: stop_everything(do_close_editors=False))
        else:
            self.send_response(404); self.end_headers()

    def do_POST(self):
        length = int(self.headers.get('content-length', 0))
        body = self.rfile.read(length).decode('utf-8', errors='ignore')
        try: data = json.loads(body)
        except: data = {}
        url = data.get('url', ''); title = data.get('title', '')
        line = activity_line(f"BROWSER_URL | title={title} | url={url}")
        ui_append_top(line); enc_append(ENC_ACTIVITY, line)
        self.send_response(200); self.end_headers(); self.wfile.write(b"ok")

http_server = None
def start_http_server():
    global http_server
    try:
        http_server = HTTPServer(HTTP_BIND, URLHandler)
        log_activity(f"HTTP URL receiver listening on http://{HTTP_BIND[0]}:{HTTP_BIND[1]}")
        http_server.serve_forever()
    except Exception as e:
        log_activity(f"HTTP server error: {e}")

def stop_http_server():
    global http_server
    if http_server:
        try:
            http_server.shutdown(); http_server.server_close(); log_activity("HTTP server stopped.")
        except: pass
        http_server = None

# -------- transcript tail + archive ----------
_tail_running = True
_tail_pos = 0
_current_encoding = None

def tail_transcript_file():
    """Live read logs/log01.txt (auto-encoding) into bottom pane."""
    global _tail_pos, _current_encoding
    while _tail_running:
        try:
            if os.path.exists(TRANSCRIPT_TXT):
                size = os.path.getsize(TRANSCRIPT_TXT)
                if _tail_pos > size or size == 0:
                    _tail_pos = 0
                    _current_encoding = None
                if _current_encoding is None:
                    _current_encoding = detect_encoding(TRANSCRIPT_TXT)
                with open(TRANSCRIPT_TXT, "r", encoding=_current_encoding, errors="ignore") as f:
                    f.seek(_tail_pos)
                    for line in f:
                        ui_append_bottom(line.rstrip("\r\n"))
                    _tail_pos = f.tell()
        except Exception as e:
            ui_append_bottom(f"[tail error] {e}")
        time.sleep(0.8)

def archive_and_purge_transcript():
    """On exit: copy TXT -> ENC and remove TXT."""
    try:
        if os.path.exists(TRANSCRIPT_TXT):
            enc = detect_encoding(TRANSCRIPT_TXT)
            line_count = 0; byte_count = os.path.getsize(TRANSCRIPT_TXT)
            with open(TRANSCRIPT_TXT, "r", encoding=enc, errors="ignore") as f:
                for line in f:
                    enc_append(ENC_TRANSCRIPT, line.rstrip("\r\n")); line_count += 1
            try: os.remove(TRANSCRIPT_TXT)
            except Exception as del_err: log_activity(f"Transcript TXT delete error: {del_err}")
            log_activity(f"TRANSCRIPT_ARCHIVED | lines={line_count} | bytes={byte_count} | target={ENC_TRANSCRIPT}")
            log_activity("TRANSCRIPT_TXT_PURGED")
        else:
            log_activity("Transcript TXT not found, nothing to archive.")
    except Exception as e:
        log_activity(f"Transcript archive error: {e}")

# -------- timer ----------
timer_running = False; timer_end = None; prewarn_shown = False

def start_timer(seconds=TIMER_SECONDS):
    global timer_running, timer_end, prewarn_shown
    timer_end = datetime.now() + timedelta(seconds=seconds); prewarn_shown = False; timer_running = True
    log_activity(f"TIMER_STARTED | duration={seconds}s"); update_timer()

def stop_timer():
    global timer_running
    timer_running = False; timer_var.set("Timer: --:--"); log_activity("TIMER_STOPPED")

def update_timer():
    global prewarn_shown
    if not timer_running or timer_end is None: return
    remaining = (timer_end - datetime.now()).total_seconds()
    if remaining <= 0:
        timer_var.set("Timer: 00:00"); log_activity("TIMER_EXPIRED")
        try: messagebox.showinfo("Time is up", "Please finish your work and push to Git.")
        except: pass
        stop_everything(do_close_editors=True); return
    if remaining <= 300 and not prewarn_shown:
        prewarn_shown = True; log_activity("TIMER_PREWARN_5MIN")
        try: messagebox.showwarning("5 minutes left", "Please wrap up and prepare your Git push.")
        except: pass
    m = int(remaining) // 60; s = int(remaining) % 60
    timer_var.set(f"Timer: {m:02d}:{s:02d}"); root.after(500, update_timer)

# -------- buttons ----------
def btn_start_clicked():
    log_activity("BUTTON: started exam")
    start_timer(TIMER_SECONDS)

def btn_stop_clicked():
    log_activity("BUTTON: finished exam")
    stop_timer()
    stop_everything(do_close_editors=False)

btn_start.config(command=btn_start_clicked)
btn_stop.config(command=btn_stop_clicked)

# -------- stop & cleanup ----------
def kill_editors():
    if not PSUTIL: return
    for p in psutil.process_iter(['pid','name']):
        try:
            n = (p.info['name'] or "").lower()
            if n in VS_CANDIDATES:
                p.terminate(); log_activity(f"Editor closed: {n}")
        except: pass

def stop_everything(do_close_editors=False):
    global _tail_running
    stop_http_server()
    if do_close_editors:
        try: kill_editors()
        except: pass
    _tail_running = False
    try: root.quit()
    except: pass
    archive_and_purge_transcript()

# -------- start threads and mainloop ----------
log_activity(f"--- Monitor started (user={USER}, host={HOST}) ---")
threading.Thread(target=start_http_server, daemon=True).start()
threading.Thread(target=tail_transcript_file, daemon=True).start()

root.after(FOREGROUND_POLL_MS, poll_foreground)
root.after(CLIPBOARD_POLL_MS,  poll_clipboard)

try:
    root.mainloop()
finally:
    stop_timer()
    stop_everything(do_close_editors=False)
    log_activity("--- Monitor stopped ---")
