"""Local web UI: pick base save + output folder via browser, generate roster, watch progress."""
import os
import threading
from fastapi import FastAPI
from fastapi.responses import HTMLResponse, JSONResponse

from roster_gen import paths

app = FastAPI(title="NCAA Football 14 Roster Generator")

DEFAULT_BASE = paths.DEFAULT_BASE
DEFAULT_OUT = str(paths.DEFAULT_OUT)
HOME = os.path.expanduser("~")

def _horizon_path():
    try:
        from roster_gen.xbox.horizon import find_horizon
        p = find_horizon()
        return str(p) if p else ""
    except Exception:
        return ""

STATE = {"running": False, "lines": [], "done": False, "output": "", "error": "", "horizon": _horizon_path()}


def _run(year, base_dir, out_dir, keepname, realignment, rankings, skip_stats, resign=False, platform="auto"):
    global STATE
    STATE = {"running": True, "lines": [], "done": False, "output": "", "error": "",
             "horizon": _horizon_path()}

    def log(msg):
        STATE["lines"].append(str(msg))
        if len(STATE["lines"]) > 300:
            STATE["lines"] = STATE["lines"][-300:]

    try:
        from roster_gen.pipeline import run
        out = run(year, base_dir, out_dir, log=log, rename=not keepname, realignment=realignment, rankings=rankings, workers=10, skip_stats=skip_stats, resign=resign, platform=platform)
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
  button.active { background:#0066cc; color:#fff; }
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
  #modalbox .file.pickable:hover { background:#eee; cursor:pointer; }
  #breadcrumb { font-size:0.85em; color:#333; margin-bottom:0.5em; word-break:break-all; }
</style>
<script>
  let activeField = null;
  let allowFiles = false;
  async function openBrowse(fieldId) {
    activeField = fieldId;
    allowFiles = fieldId === 'base';
    document.getElementById('modalTitle').textContent = allowFiles ? 'Select PS3 save folder or Xbox 360 ROSTER-* file' : 'Select folder';
    const cur = document.getElementById(fieldId).value || '__HOME__';
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
      li.className = 'file' + (allowFiles ? ' pickable' : '');
      if (allowFiles) {
        li.onclick = () => {
          document.getElementById(activeField).value = d.path + '/' + f;
          if (activeField === 'base') {
            const isFile = true;
            const lower = f.toLowerCase();
            const xbox = lower.startsWith('roster') || lower.endsWith('.con');
            selectConsole(xbox ? 'xbox360' : 'ps3');
          }
          closeModal();
        };
      }
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
      document.getElementById('status').textContent = s.error ? ('ERROR: ' + s.error) : ('Done! Output: ' + s.output + '  --  See the log below for where to copy the save.');
      return;
    }
    setTimeout(poll, 1000);
  }
  function resignExisting() {
    const f = prompt('Path to ROSTER-* file to re-sign:');
    if (!f) return;
    fetch('/resign?file=' + encodeURIComponent(f), {method:'POST'})
      .then(r=>r.json()).then(d=>{ alert(d.msg); });
  }
  fetch('/horizon').then(r=>r.json()).then(d=>{
    const el = document.getElementById('horizonStatus');
    if (!el) return;
    if (d.found) {
      el.textContent = 'Horizon found: ' + d.path;
    } else {
      el.textContent = 'Horizon not found. Stock consoles will need a manual Rehash & Resign (see README).';
    }
  });
  // restore console selection
  try {
    const saved = localStorage.getItem('ncaa_console');
    if (saved === 'ps3' || saved === 'xbox360') selectConsole(saved);
  } catch(e) {}
    const y = document.getElementById('year').value;
    const o = document.getElementById('out').value;
    const b = document.getElementById('base').value;
    const k = document.getElementById('keepname').checked ? 1 : 0;
    const r = document.getElementById('realignment').checked ? 1 : 0;
    const rk = document.getElementById('rankings').checked ? 1 : 0;
    const ss = document.getElementById('skipstats').checked ? 1 : 0;
    const console = (document.getElementById('btnPS3').classList.contains('active')) ? 'ps3' : 'xbox360';
    const modded = (console === 'xbox360') ? (document.getElementById('moddedYes').checked ? 1 : 0) : 0;
    const keepname = (console === 'ps3') ? (document.getElementById('keepname').checked ? 1 : 0) : 0;
    fetch('/generate?year='+y+'&out='+encodeURIComponent(o)+'&base='+encodeURIComponent(b)+'&keepname='+keepname+'&realignment='+r+'&rankings='+rk+'&skipstats='+ss+'&console='+console+'&modded='+modded, {method:'POST'});
    document.getElementById('status').textContent = 'Running...';
    setTimeout(poll, 500);
  }
</script>
</head>
<body>
  <h1>NCAA Football 14 Roster Generator</h1>

  <p id="consolePrompt" style="font-weight:bold;">What are you building for?</p>
  <div class="row" style="margin-bottom:1em;">
    <button id="btnPS3" onclick="selectConsole('ps3')">PlayStation 3</button>
    <button id="btnXbox" onclick="selectConsole('xbox360')">Xbox 360</button>
  </div>
  <p id="consoleBadge" style="color:#555; font-size:0.9em;"></p>

  <div id="panel" style="display:none;">
    <label>Base save:
      <div class="row">
        <input id="base" type="text" value="__DEFAULT_BASE__" placeholder="">
        <button onclick="openBrowse('base')">Browse...</button>
      </div>
      <span id="baseHint" style="font-size:0.85em; color:#555;"></span>
    </label>

    <label>Output folder:
      <div class="row">
        <input id="out" type="text" value="__DEFAULT_OUT__">
        <button onclick="openBrowse('out')">Browse...</button>
      </div>
    </label>

    <label>Season start year (e.g. 2026): <input id="year" type="number" value="2026"></label>

    <div id="ps3Opts" style="display:none;">
      <label><input id="keepname" type="checkbox" checked> Keep original save name (recommended — PS3 rejects renamed saves)</label>
    </div>

    <div id="xboxOpts" style="display:none;">
      <p style="margin:0.5em 0;">Is your Xbox 360 modded? (DashLaunch with contpatch)</p>
      <label><input type="radio" name="modded" value="1" id="moddedYes"> Yes — modded console (no extra steps)</label><br>
      <label><input type="radio" name="modded" value="0" id="moddedNo" checked> No — stock console</label>
      <p id="horizonStatus" style="font-size:0.85em; color:#555; margin:0.3em 0;"></p>
    </div>

    <details style="margin:0.5em 0;">
      <summary>Advanced options</summary>
      <label><input id="realignment" type="checkbox"> Apply 2026 conference realignment (may cause schedule freeze - experimental)</label><br>
      <label><input id="rankings" type="checkbox" checked> Update Top 25 rankings (AP + Coaches)</label><br>
      <label><input id="skipstats" type="checkbox"> Skip stats (instant, uses priors only)</label>
    </details>

    <p><button onclick="start()">Generate</button>
       <button onclick="resignExisting()">Re-sign existing file...</button></p>
    <p id="status"></p>
    <div id="log"></div>
  </div>

  <!-- folder browser modal -->
  <div id="modal">
    <div id="modalbox">
      <h3 id="modalTitle">Select folder</h3>
      <div id="breadcrumb"></div>
      <ul id="dirlist"></ul>
      <p>
        <button id="selectBtn">Select this folder</button>
        <button onclick="closeModal()">Cancel</button>
      </p>
    </div>
  </div>
</body></html>""".replace("__DEFAULT_OUT__", DEFAULT_OUT).replace("__DEFAULT_BASE__", DEFAULT_BASE).replace("__HOME__", HOME)


@app.get("/", response_class=HTMLResponse)
def index():
    return INDEX


@app.post("/generate")
def generate(year: int, out: str, base: str, keepname: int = 0, realignment: int = 0, rankings: int = 1, skipstats: int = 0, console: str = "auto", modded: int = 0):
    if STATE["running"]:
        return JSONResponse({"ok": False, "msg": "already running"})
    resign = (console == "xbox360" and not bool(modded))
    threading.Thread(target=_run, args=(year, base, out, bool(keepname), bool(realignment), bool(rankings), bool(skipstats), resign), kwargs={"platform": console}, daemon=True).start()
    return JSONResponse({"ok": True})


@app.post("/resign")
def resign_endpoint(file: str):
    try:
        from roster_gen.xbox.resign import resign_with_horizon
        from roster_gen.xbox.horizon import find_horizon
        hr = find_horizon()
        res = resign_with_horizon(file, horizon_path=hr, launch_gui=True)
        return JSONResponse({"ok": res.ok or res.mode == "manual", "mode": res.mode,
                            "msg": res.message, "backup": res.backup_path or ""})
    except Exception as e:
        import traceback
        return JSONResponse({"ok": False, "msg": f"{e}\n{traceback.format_exc()}"})
def browse(path: str = ""):
    # normalize
    if not path:
        path = HOME
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


@app.get("/horizon")
def horizon():
    from roster_gen.xbox.horizon import find_horizon
    p = find_horizon()
    return JSONResponse({"found": bool(p), "path": str(p) if p else ""})


@app.get("/status", response_class=JSONResponse)
def status():
    return STATE