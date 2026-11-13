"""Local web UI: pick base save + output folder via browser, generate roster, watch progress."""
import os
import threading
from fastapi import FastAPI
from fastapi.responses import HTMLResponse, JSONResponse

app = FastAPI(title="NCAA Football 14 Roster Generator")

DEFAULT_BASE = "/home/lakerh8r/Downloads/NCAA14RosterPack/13-14 Release Year NCAA14/PS3 end of season 2013-14 Roster posted by majesty95/PS3 end of season 2013-14 Roster posted by majesty95/PS3/SAVEDATA/BLUS31159-ROSTER-JHASLEY10"
DEFAULT_OUT = "/home/lakerh8r/Downloads/NCAA14RosterPack"

STATE = {"running": False, "lines": [], "done": False, "output": "", "error": ""}


def _run(year, base_dir, out_dir, keepname):
    global STATE
    STATE = {"running": True, "lines": [], "done": False, "output": "", "error": ""}

    def log(msg):
        STATE["lines"].append(str(msg))
        if len(STATE["lines"]) > 300:
            STATE["lines"] = STATE["lines"][-300:]

    try:
        from roster_gen.pipeline import run
        out = run(year, base_dir, out_dir, log=log, rename=not keepname)
        STATE["output"] = out
    except Exception as e:
        import traceback
        STATE["error"] = f"{e}\n{traceback.format_exc()}"
        log(f"ERROR: {e}")
    finally:
        STATE["done"] = True
        STATE["running"] = False


INDEX = r"""<!doctype html>
<html><head><meta charset="utf-8"><title>NCAA Football 14 Roster Generator</title>
<style>
  body { font-family: monospace; max-width: 900px; margin: 2em auto; }
  #log { background:#111; color:#0f0; padding:1em; height:400px; overflow:auto; white-space:pre-wrap; border-radius:6px; }
  button { padding:0.5em 1em; cursor:pointer; }
  input { padding:0.3em; }
  label { display:block; margin:0.5em 0; }
  .row { display:flex; gap:0.5em; align-items:center; }
  .row input { flex:1; }
  /* modal */
  #modal { display:none; position:fixed; top:0; left:0; width:100%; height:100%; background:rgba(0,0,0,0.6); }
  #modalbox { background:#fff; color:#000; max-width:600px; margin:5% auto; padding:1em; border-radius:8px; max-height:80%; overflow:auto; }
  #modalbox ul { list-style:none; padding:0; }
  #modalbox li { padding:0.3em; cursor:pointer; border-bottom:1px solid #eee; }
  #modalbox li:hover { background:#eee; }
  #modalbox .dir { color:#0066cc; }
  #modalbox .file { color:#555; }
  #breadcrumb { font-size:0.85em; color:#333; margin-bottom:0.5em; word-break:break-all; }
</style>
<script>
  let activeField = null;
  async function openBrowse(fieldId) {
    activeField = fieldId;
    const cur = document.getElementById(fieldId).value || '/home/lakerh8r';
    document.getElementById('modal').style.display = 'block';
    await loadDir(cur);
  }
  async function loadDir(path) {
    const r = await fetch('/browse?path=' + encodeURIComponent(path));
    const d = await r.json();
    document.getElementById('breadcrumb').textContent = d.path;
    document.getElementById('selectBtn').onclick = () => { document.getElementById(activeField).value = d.path; closeModal(); };
    const ul = document.getElementById('dirlist');
    ul.innerHTML = '';
    if (d.parent) {
      const li = document.createElement('li');
      li.textContent = '.. (parent)';
      li.className = 'dir';
      li.onclick = () => loadDir(d.parent);
      ul.appendChild(li);
    }
    for (const dir of d.dirs) {
      const li = document.createElement('li');
      li.textContent = '\uD83D\uDCC1 ' + dir;
      li.className = 'dir';
      li.onclick = () => loadDir(d.path + '/' + dir);
      ul.appendChild(li);
    }
    for (const f of d.files) {
      const li = document.createElement('li');
      li.textContent = '\uD83D\uDCC4 ' + f;
      li.className = 'file';
      ul.appendChild(li);
    }
  }
  function closeModal() { document.getElementById('modal').style.display = 'none'; }
  async function poll() {
    const r = await fetch('/status');
    const s = await r.json();
    const log = document.getElementById('log');
    log.textContent = s.lines.join('\n');
    log.scrollTop = log.scrollHeight;
    if (s.done) {
      document.getElementById('status').textContent = s.error ? ('ERROR: ' + s.error) : ('Done! Output: ' + s.output + '  --  Copy the PS3 folder to your USB root (or upload BLUS31159-ROSTER-* to /dev_hdd0/home/00000001/savedata/ via FTP).');
      return;
    }
    setTimeout(poll, 1000);
  }
  function start() {
    const y = document.getElementById('year').value;
    const o = document.getElementById('out').value;
    const b = document.getElementById('base').value;
    const k = document.getElementById('keepname').checked ? 1 : 0;
    fetch('/generate?year='+y+'&out='+encodeURIComponent(o)+'&base='+encodeURIComponent(b)+'&keepname='+k, {method:'POST'});
    document.getElementById('status').textContent = 'Running...';
    setTimeout(poll, 500);
  }
</script>
</head>
<body>
  <h1>NCAA Football 14 Roster Generator</h1>
  <label>Base save folder (your own PS3 save, or leave default):
    <div class="row">
      <input id="base" type="text" value="__DEFAULT_BASE__">
      <button onclick="openBrowse('base')">Browse...</button>
    </div>
  </label>
  <label>Output folder:
    <div class="row">
      <input id="out" type="text" value="__DEFAULT_OUT__">
      <button onclick="openBrowse('out')">Browse...</button>
    </div>
  </label>
  <label>Season start year (e.g. 2026): <input id="year" type="number" value="2026"></label>
  <label><input id="keepname" type="checkbox" checked> Keep original save name (safer for PS3)</label>
  <p><button onclick="start()">Generate</button></p>
  <p id="status"></p>
  <div id="log"></div>

  <!-- folder browser modal -->
  <div id="modal">
    <div id="modalbox">
      <h3>Select folder</h3>
      <div id="breadcrumb"></div>
      <ul id="dirlist"></ul>
      <p>
        <button id="selectBtn">Select this folder</button>
        <button onclick="closeModal()">Cancel</button>
      </p>
    </div>
  </div>
</body></html>""".replace("__DEFAULT_OUT__", DEFAULT_OUT).replace("__DEFAULT_BASE__", DEFAULT_BASE)


@app.get("/", response_class=HTMLResponse)
def index():
    return INDEX


@app.post("/generate")
def generate(year: int, out: str, base: str, keepname: int = 0):
    if STATE["running"]:
        return JSONResponse({"ok": False, "msg": "already running"})
    threading.Thread(target=_run, args=(year, base, out, bool(keepname)), daemon=True).start()
    return JSONResponse({"ok": True})


@app.get("/browse")
def browse(path: str = "/home/lakerh8r"):
    # normalize
    path = os.path.abspath(os.path.expanduser(path))
    if not os.path.isdir(path):
        path = os.path.dirname(path) or "/"
    if not os.path.isdir(path):
        path = "/"
    try:
        entries = sorted(os.listdir(path))
    except PermissionError:
        entries = []
    dirs = []
    files = []
    for e in entries:
        full = os.path.join(path, e)
        if os.path.isdir(full):
            dirs.append(e)
        else:
            files.append(e)
    parent = os.path.dirname(path) if path != "/" else None
    return JSONResponse({"path": path, "parent": parent, "dirs": dirs, "files": files})


@app.get("/status", response_class=JSONResponse)
def status():
    return STATE