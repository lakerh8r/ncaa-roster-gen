"""Local web UI: enter a season start year, generate a roster save, watch progress."""
import threading
import time
from fastapi import FastAPI, Form
from fastapi.responses import HTMLResponse, JSONResponse

app = FastAPI(title="ncaa-roster-gen")

BASE_SAVE = "/home/lakerh8r/Downloads/NCAA14RosterPack/13-14 Release Year NCAA14/PS3 end of season 2013-14 Roster posted by majesty95/PS3 end of season 2013-14 Roster posted by majesty95/PS3/SAVEDATA/BLUS31159-ROSTER-JHASLEY10"

STATE = {"running": False, "lines": [], "done": False, "output": "", "error": ""}


def _run(year):
    global STATE
    STATE = {"running": True, "lines": [], "done": False, "output": "", "error": ""}

    def log(msg):
        STATE["lines"].append(str(msg))
        # keep last 200 lines
        if len(STATE["lines"]) > 200:
            STATE["lines"] = STATE["lines"][-200:]

    try:
        from roster_gen.pipeline import run
        out = run(year, BASE_SAVE, None, log=log)
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
</style>
<script>
  async function poll() {
    const r = await fetch('/status');
    const s = await r.json();
    const log = document.getElementById('log');
    log.textContent = s.lines.join('\\n');
    log.scrollTop = log.scrollHeight;
    if (s.done) {
      document.getElementById('status').textContent = s.error ? ('ERROR: ' + s.error) : ('Done. Output: ' + s.output);
      return;
    }
    setTimeout(poll, 1000);
  }
  function start() {
    const y = document.getElementById('year').value;
    fetch('/generate?year='+y, {method:'POST'});
    document.getElementById('status').textContent = 'Running...';
    setTimeout(poll, 500);
  }
</script>
</head>
<body>
  <h1>NCAA Roster Generator</h1>
  <p>Season start year (e.g. 2026): <input id="year" type="number" value="2026">
  <button onclick="start()">Generate</button></p>
  <p id="status"></p>
  <div id="log"></div>
</body></html>"""


@app.get("/", response_class=HTMLResponse)
def index():
    return INDEX


@app.post("/generate")
def generate(year: int):
    if STATE["running"]:
        return JSONResponse({"ok": False, "msg": "already running"})
    threading.Thread(target=_run, args=(year,), daemon=True).start()
    return JSONResponse({"ok": True})


@app.get("/status", response_class=JSONResponse)
def status():
    return STATE
