"""Minimal local web UI: enter a season start year, generate a roster save."""
from fastapi import FastAPI, Form
from fastapi.responses import HTMLResponse

app = FastAPI(title="ncaa-roster-gen")

INDEX = """<!doctype html>
<html><head><meta charset="utf-8"><title>ncaa-roster-gen</title></head>
<body>
  <h1>NCAA Roster Generator</h1>
  <form action="/generate" method="post">
    <label>Season start year (e.g. 2026): <input name="year" type="number" value="2026"></label>
    <button type="submit">Generate</button>
  </form>
  {status}
</body></html>"""


@app.get("/", response_class=HTMLResponse)
def index():
    return INDEX.format(status="")


@app.post("/generate", response_class=HTMLResponse)
def generate(year: int = Form(...)):
    return INDEX.format(status=f"<p>Season {year} selected. Generation pipeline not yet wired up in this build.</p>")
