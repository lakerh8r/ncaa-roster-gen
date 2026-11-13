"""Local web UI: enter a season start year + output folder, generate a roster save, watch progress."""
import threading
from fastapi import FastAPI
from fastapi.responses import HTMLResponse, JSONResponse

app = FastAPI(title="ncaa-roster-gen")

BASE_SAVE = "/home/lakerh8r/Downloads/NCAA14RosterPack/13-14 Release Year NCAA14/PS3 end of season 2013-14 Roster posted by majesty95/PS3 end of season 2013-14 Roster posted by majesty95/PS3/SAVEDATA/BLUS31159-ROSTER-JHASLEY10"
DEFAULT_OUT = "/home/lakerh8r/Downloads/NCAA14RosterPack"

STATE = {"running": False, "lines": [], "done": False, "output": "", "error": ""}


def _run(year, out_dir, keepname=False):
    global STATE
    STATE = {"running": True, "lines": [], "done": False, "output": "", "error": ""}

    def log(msg):
        STATE["lines"].append(str(msg))
        if len(STATE["lines"]) > 200:
            STATE["lines"] = STATE["lines"][-200:]

    try:
        from roster_gen.pipeline import run
        out = run(year, BASE_SAVE, out_dir, log=log, rename=not keepname)
        STATE["output"] = out
    except Exception as e:
        import traceback
        STATE["error"] = f"{e}\n{traceback.format_exc()}"
        log(f"ERROR: {e}")
    finally:
        STATE["done"] = True
        STATE["running"] = False


INDEX = """<!doctype html>
<html><head><meta charset="utf-8"><title>ncaa-roster-gen</title>
<style>
  body { font-family: monospace; max-width: 900px; margin: 2em auto; }
  #log { background:#111; color:#0f0; padding:1em; height:400px; overflow:auto; white-space:pre-wrap; border-radius:6px; }
  button { padding:0.5em 1em; }
  input { padding:0.3em; }
  label { display:block; margin:0.5em 0; }
</style>
<script>
  async function poll() {
    const r = await fetch('/status');
    const s = await r.json();
    const log = document.getElementById('log');
    log.textContent = s.lines.join('\\n');
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
    const k = document.getElementById('keepname').checked ? 1 : 0;
    fetch('/generate?year='+y+'&out='+encodeURIComponent(o)+'&keepname='+k, {method:'POST'});
    document.getElementById('status').textContent = 'Running...';
    setTimeout(poll, 500);
  }
</script>
</head>
<body>
  <h1>NCAA Roster Generator</h1>
  <label>Season start year (e.g. 2026): <input id="year" type="number" value="2026"></label>
  <label>Output folder: <input id="out" type="text" value="__DEFAULT_OUT__" style="width:600px"></label>
  <label><input id="keepname" type="checkbox"> Keep original save name (safer for PS3, recommended if having issues)</label>
  <p><button onclick="start()">Generate</button></p>
  <p id="status"></p>
  <div id="log"></div>
</body></html>""".replace("__DEFAULT_OUT__", DEFAULT_OUT)


@app.get("/", response_class=HTMLResponse)
def index():
    return INDEX


@app.post("/generate")
def generate(year: int, out: str, keepname: int = 0):
    if STATE["running"]:
        return JSONResponse({"ok": False, "msg": "already running"})
    threading.Thread(target=_run, args=(year, out, bool(keepname)), daemon=True).start()
    return JSONResponse({"ok": True})


@app.get("/status", response_class=JSONResponse)
def status():
    return STATE