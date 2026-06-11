from __future__ import annotations

import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote, urlparse

import yaml

from agentloop.core.engine import DryRunResult, execute_loop
from agentloop.core.rendering import RenderError
from agentloop.security.redaction import redact_mapping, secret_names
from agentloop.storage.configs import ConfigError, copy_template, create_template, default_template_data, find_config, list_configs, load_loop, write_template
from agentloop.storage.runs import find_run, list_runs, request_stop


INDEX_HTML = """<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>AgentLoop</title>
  <style>
    :root {
      color-scheme: light;
      --bg:#ffffff;
      --surface:#ffffff;
      --panel:#f7f9fc;
      --ink:#17202a;
      --muted:#667085;
      --line:#d8dee8;
      --accent:#176b87;
      --accent-ink:#ffffff;
      --ok:#1d7f45;
      --bad:#b42318;
      --code-bg:#101828;
      --code-ink:#f2f4f7;
    }
    :root[data-theme="dark"] {
      color-scheme: dark;
      --bg:#111418;
      --surface:#191e24;
      --panel:#151a20;
      --ink:#eef2f6;
      --muted:#aab4c0;
      --line:#313945;
      --accent:#59a6c0;
      --accent-ink:#071116;
      --ok:#6fcf97;
      --bad:#ff8a80;
      --code-bg:#090c10;
      --code-ink:#eef2f6;
    }
    * { box-sizing: border-box; }
    body { margin:0; font-family: ui-sans-serif, system-ui, -apple-system, Segoe UI, sans-serif; color:var(--ink); background:var(--bg); }
    header { border-bottom:1px solid var(--line); padding:12px 18px; display:flex; justify-content:space-between; align-items:center; gap:12px; background:var(--surface); position:sticky; top:0; z-index:10; }
    h1 { font-size:20px; margin:0; letter-spacing:0; }
    h2 { font-size:18px; margin:0 0 12px; }
    h3 { font-size:15px; margin:16px 0 8px; }
    main { min-height:calc(100vh - 57px); }
    .brand { display:flex; align-items:center; gap:10px; min-width:0; }
    .workspace { overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }
    .menu-button { width:38px; height:34px; display:grid; place-content:center; gap:4px; padding:0; }
    .menu-button span { display:block; width:18px; height:2px; background:currentColor; border-radius:2px; }
    .shell { display:grid; grid-template-columns: 260px 1fr; min-height:calc(100vh - 57px); }
    .shell.menu-collapsed { grid-template-columns: 0 1fr; }
    nav { overflow:hidden; border-right:1px solid var(--line); background:var(--panel); transition:width .15s ease; }
    .nav-inner { width:260px; padding:14px; }
    .nav-item { width:100%; display:flex; justify-content:space-between; align-items:center; border:1px solid transparent; background:transparent; color:var(--ink); text-align:left; }
    .nav-item.active { background:var(--surface); border-color:var(--line); }
    .page { display:none; padding:20px 24px; min-width:0; }
    .page.active { display:grid; gap:16px; }
    button, input, select, textarea { font:inherit; }
    button { border:1px solid var(--line); background:var(--surface); color:var(--ink); border-radius:6px; padding:8px 10px; cursor:pointer; }
    button.primary { background:var(--accent); border-color:var(--accent); color:var(--accent-ink); }
    button.danger { color:var(--bad); }
    .row { display:flex; gap:8px; align-items:center; flex-wrap:wrap; }
    .stack { display:grid; gap:10px; }
    .list button { width:100%; text-align:left; margin:3px 0; overflow:hidden; text-overflow:ellipsis; }
    .grid { display:grid; grid-template-columns: repeat(3, minmax(160px, 1fr)); gap:12px; }
    label { display:grid; gap:4px; color:var(--muted); font-size:13px; }
    input, textarea, select { width:100%; border:1px solid var(--line); border-radius:6px; padding:8px; background:var(--surface); color:var(--ink); }
    textarea { min-height:92px; resize:vertical; }
    pre { background:var(--code-bg); color:var(--code-ink); padding:12px; border-radius:6px; overflow:auto; white-space:pre-wrap; }
    .split { display:grid; grid-template-columns: minmax(260px, 380px) 1fr; gap:16px; align-items:start; }
    .panel { border:1px solid var(--line); border-radius:8px; padding:14px; background:var(--surface); }
    .muted { color:var(--muted); }
    .status { font-weight:600; }
    .theme-toggle { min-width:92px; }
    @media (max-width: 900px) {
      .shell, .shell.menu-collapsed { grid-template-columns:1fr; }
      nav { border-right:0; border-bottom:1px solid var(--line); }
      .shell.menu-collapsed nav { display:none; }
      .nav-inner { width:100%; }
      .split, .grid { grid-template-columns:1fr; }
      .page { padding:16px; }
    }
  </style>
</head>
<body>
  <header>
    <div class="brand">
      <button class="menu-button" id="menuToggle" aria-label="Menu" aria-expanded="true"><span></span><span></span><span></span></button>
      <h1>AgentLoop</h1>
    </div>
    <div class="row">
      <button class="theme-toggle" id="themeToggle" title="Toggle theme">System</button>
      <div class="muted workspace" id="workspace"></div>
    </div>
  </header>
  <main class="shell" id="shell">
    <nav>
      <div class="nav-inner stack">
        <button class="nav-item active" data-page-target="dashboardPage">Home Dashboard</button>
        <button class="nav-item" data-page-target="runPage">Run</button>
        <button class="nav-item" data-page-target="loopsPage">Loops</button>
        <button class="nav-item" data-page-target="templatesPage">Templates</button>
        <button class="nav-item" data-page-target="settingsPage">Settings</button>
      </div>
    </nav>
    <section>
      <div class="page active" id="dashboardPage">
        <h2>Home Dashboard</h2>
        <div class="grid">
          <div class="panel"><strong id="loopCount">0</strong><div class="muted">loops</div></div>
          <div class="panel"><strong id="templateCount">0</strong><div class="muted">templates</div></div>
          <div class="panel"><strong id="runCount">0</strong><div class="muted">runs</div></div>
        </div>
        <div class="panel">
          <strong>Recent Runs</strong>
          <div class="list" id="dashboardRuns"></div>
        </div>
      </div>
      <div class="page" id="runPage">
        <h2>Run</h2>
        <div class="split">
          <div class="panel stack">
            <label>Loop or template<select id="runConfigSelect"></select></label>
            <div><strong id="selectedName">Select a loop or template</strong><div class="muted" id="selectedKind"></div></div>
            <div id="variables" class="stack"></div>
            <label>Max iterations<input id="maxIterations" type="number" min="1" placeholder="config default"></label>
            <div class="row">
              <button class="primary" id="dryRun">Dry-run</button>
              <button id="startRun">Start</button>
            </div>
            <div class="status" id="message"></div>
          </div>
          <div class="panel">
            <strong>Rendered Output</strong>
            <pre id="output">No dry-run yet.</pre>
          </div>
        </div>
      </div>
      <div class="page" id="loopsPage">
        <h2>Loops</h2>
        <div class="panel list" id="loops"></div>
      </div>
      <div class="page" id="templatesPage">
        <h2>Templates</h2>
        <div class="split">
          <div class="panel">
            <div class="list" id="templates"></div>
          </div>
          <div class="panel stack">
            <div class="row">
              <input id="templateName" placeholder="template-name">
              <button id="newTemplate">New</button>
              <button id="copyTemplate">Copy</button>
              <button class="primary" id="saveTemplate">Save</button>
            </div>
            <textarea id="templateYaml" spellcheck="false" style="min-height:420px; font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;"></textarea>
          </div>
        </div>
      </div>
      <div class="page" id="settingsPage">
        <h2>Settings</h2>
        <div class="split">
          <div class="panel stack">
            <label>Theme
              <select id="themeMode">
                <option value="system">System</option>
                <option value="light">Light</option>
                <option value="dark">Dark</option>
              </select>
            </label>
            <label>Workspace<input id="workspaceSetting" readonly></label>
            <label>Run storage<input value=".agentloop-runs/" readonly></label>
            <label>Config directory<input value=".agentloop/" readonly></label>
          </div>
          <div class="panel">
            <strong>Run Details</strong>
            <pre id="runDetails">No run selected.</pre>
            <div class="row">
              <button class="danger" id="stopRun">Stop selected run</button>
            </div>
          </div>
        </div>
      </div>
    </section>
  </main>
<script>
const state = { selected: null, selectedRun: null, configs: { loops: [], templates: [] }, runs: [] };
const $ = id => document.getElementById(id);
const prefersDark = window.matchMedia('(prefers-color-scheme: dark)');
function storedTheme() { return localStorage.getItem('agentloop-theme') || 'system'; }
function effectiveTheme(mode) { return mode === 'system' ? (prefersDark.matches ? 'dark' : 'light') : mode; }
function applyTheme(mode=storedTheme()) {
  const theme = effectiveTheme(mode);
  document.documentElement.dataset.theme = theme;
  $('themeToggle').textContent = mode[0].toUpperCase() + mode.slice(1);
  $('themeMode').value = mode;
}
async function api(path, options={}) {
  const response = await fetch(path, { headers: {'content-type':'application/json'}, ...options });
  const text = await response.text();
  const data = text ? JSON.parse(text) : {};
  if (!response.ok) throw new Error(data.error || response.statusText);
  return data;
}
function setMessage(text) { $('message').textContent = text; }
function showPage(pageId) {
  document.querySelectorAll('.page').forEach(page => page.classList.toggle('active', page.id === pageId));
  document.querySelectorAll('[data-page-target]').forEach(button => button.classList.toggle('active', button.dataset.pageTarget === pageId));
}
function collectValues() {
  const values = {};
  document.querySelectorAll('[data-var]').forEach(input => { if (input.value) values[input.dataset.var] = input.value; });
  return values;
}
function renderVariables(item) {
  $('variables').innerHTML = '';
  (item.variables || []).forEach(variable => {
    const label = document.createElement('label');
    label.textContent = variable.name + (variable.required ? ' *' : '');
    const input = document.createElement(variable.secret ? 'input' : 'textarea');
    if (variable.secret) input.type = 'password';
    input.dataset.var = variable.name;
    if (variable.default !== null && variable.default !== undefined) input.value = variable.default;
    label.appendChild(input);
    $('variables').appendChild(label);
  });
}
function selectConfig(item) {
  state.selected = item;
  $('selectedName').textContent = item.name;
  $('selectedKind').textContent = item.kind;
  $('runConfigSelect').value = `${item.kind}:${item.name}`;
  renderVariables(item);
  if (item.kind === 'templates') loadTemplateYaml(item.name);
}
function configByKey(key) {
  const [kind, name] = key.split(':');
  return (state.configs[kind] || []).find(item => item.name === name);
}
async function loadConfigs() {
  const data = await api('/api/configs');
  state.configs = { loops: data.loops, templates: data.templates };
  $('workspace').textContent = data.workspace;
  $('workspaceSetting').value = data.workspace;
  $('loopCount').textContent = data.loops.length;
  $('templateCount').textContent = data.templates.length;
  $('runConfigSelect').innerHTML = '';
  for (const kind of ['loops','templates']) {
    $(kind).innerHTML = '';
    data[kind].forEach(item => {
      const button = document.createElement('button');
      button.textContent = item.name;
      button.onclick = () => { selectConfig(item); showPage(kind === 'loops' ? 'runPage' : 'templatesPage'); };
      $(kind).appendChild(button);
      const option = document.createElement('option');
      option.value = `${kind}:${item.name}`;
      option.textContent = `${item.name} (${kind.slice(0, -1)})`;
      $('runConfigSelect').appendChild(option);
    });
  }
  if (!state.selected && $('runConfigSelect').value) selectConfig(configByKey($('runConfigSelect').value));
}
async function loadRuns() {
  const data = await api('/api/runs');
  state.runs = data.runs;
  $('runCount').textContent = data.runs.length;
  $('dashboardRuns').innerHTML = '';
  data.runs.slice(0, 8).forEach(run => {
    const button = document.createElement('button');
    button.textContent = `${run.run_id} ${run.status || ''}`;
    button.onclick = async () => {
      state.selectedRun = run.run_id;
      const detail = await api(`/api/runs/${run.run_id}`);
      $('runDetails').textContent = JSON.stringify(detail, null, 2);
      showPage('settingsPage');
    };
    $('dashboardRuns').appendChild(button);
  });
}
async function dryRun() {
  if (!state.selected) return setMessage('Select a loop or template.');
  const data = await api('/api/dry-run', { method:'POST', body: JSON.stringify({ ...state.selected, values: collectValues() }) });
  $('output').textContent = '# Rendered Prompt\\n' + data.prompt + '\\n\\n# Commands\\n' + data.commands.join('\\n');
  setMessage('Dry-run complete.');
}
async function startRun() {
  if (!state.selected) return setMessage('Select a loop or template.');
  const max = $('maxIterations').value;
  const payload = { ...state.selected, values: collectValues(), max_iterations: max ? Number(max) : null };
  const data = await api('/api/run', { method:'POST', body: JSON.stringify(payload) });
  setMessage(`Started ${data.run_id}`);
  setTimeout(loadRuns, 1000);
}
async function stopRun() {
  if (!state.selectedRun) return setMessage('Select a run.');
  await api(`/api/runs/${state.selectedRun}/stop`, { method:'POST', body:'{}' });
  setMessage('Stop requested.');
  await loadRuns();
}
async function loadTemplateYaml(name) {
  const data = await api(`/api/templates/${encodeURIComponent(name)}`);
  $('templateName').value = data.name;
  $('templateYaml').value = data.yaml;
}
async function newTemplate() {
  const name = $('templateName').value.trim();
  if (!name) return setMessage('Enter a template name.');
  const data = await api('/api/templates', { method:'POST', body: JSON.stringify({ name }) });
  $('templateName').value = data.name;
  $('templateYaml').value = data.yaml;
  await loadConfigs();
  setMessage(`Created ${data.name}.`);
}
async function copyTemplate() {
  if (!state.selected || state.selected.kind !== 'templates') return setMessage('Select a template to copy.');
  const name = $('templateName').value.trim();
  if (!name) return setMessage('Enter the new template name.');
  const data = await api(`/api/templates/${encodeURIComponent(state.selected.name)}/copy`, { method:'POST', body: JSON.stringify({ name }) });
  $('templateName').value = data.name;
  $('templateYaml').value = data.yaml;
  await loadConfigs();
  setMessage(`Copied to ${data.name}.`);
}
async function saveTemplate() {
  const name = $('templateName').value.trim();
  if (!name) return setMessage('Enter a template name.');
  const data = await api(`/api/templates/${encodeURIComponent(name)}`, { method:'PUT', body: JSON.stringify({ yaml: $('templateYaml').value }) });
  $('templateYaml').value = data.yaml;
  await loadConfigs();
  setMessage(`Saved ${data.name}.`);
}
$('dryRun').onclick = dryRun;
$('startRun').onclick = startRun;
$('stopRun').onclick = stopRun;
$('newTemplate').onclick = newTemplate;
$('copyTemplate').onclick = copyTemplate;
$('saveTemplate').onclick = saveTemplate;
$('runConfigSelect').onchange = event => {
  const item = configByKey(event.target.value);
  if (item) selectConfig(item);
};
$('menuToggle').onclick = () => {
  const shell = $('shell');
  shell.classList.toggle('menu-collapsed');
  $('menuToggle').setAttribute('aria-expanded', String(!shell.classList.contains('menu-collapsed')));
};
document.querySelectorAll('[data-page-target]').forEach(button => {
  button.onclick = () => showPage(button.dataset.pageTarget);
});
$('themeToggle').onclick = () => {
  const modes = ['system', 'light', 'dark'];
  const next = modes[(modes.indexOf(storedTheme()) + 1) % modes.length];
  localStorage.setItem('agentloop-theme', next);
  applyTheme(next);
};
$('themeMode').onchange = event => {
  localStorage.setItem('agentloop-theme', event.target.value);
  applyTheme(event.target.value);
};
prefersDark.addEventListener('change', () => { if (storedTheme() === 'system') applyTheme('system'); });
applyTheme();
loadConfigs().then(loadRuns).catch(err => setMessage(err.message));
setInterval(loadRuns, 5000);
</script>
</body>
</html>
"""


class AgentLoopHandler(BaseHTTPRequestHandler):
    workspace: Path = Path.cwd()

    def log_message(self, format: str, *args) -> None:
        return

    def _json(self, payload: object, status: int = 200) -> None:
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("content-type", "application/json")
        self.send_header("content-length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _error(self, exc: Exception, status: int = 400) -> None:
        self._json({"error": str(exc)}, status)

    def _body(self) -> dict:
        length = int(self.headers.get("content-length") or 0)
        if not length:
            return {}
        return json.loads(self.rfile.read(length).decode("utf-8"))

    def do_GET(self) -> None:
        try:
            parsed = urlparse(self.path)
            if parsed.path == "/":
                body = INDEX_HTML.encode("utf-8")
                self.send_response(200)
                self.send_header("content-type", "text/html; charset=utf-8")
                self.send_header("content-length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
            elif parsed.path == "/api/configs":
                self._json(self._configs())
            elif parsed.path == "/api/runs":
                self._json({"runs": self._runs()})
            elif parsed.path.startswith("/api/templates/"):
                template_name = unquote(parsed.path.split("/")[3])
                self._json(self._template_detail(template_name))
            elif parsed.path.startswith("/api/runs/"):
                run_id = parsed.path.split("/")[3]
                self._json(self._run_detail(run_id))
            else:
                self._json({"error": "not found"}, 404)
        except Exception as exc:
            self._error(exc)

    def do_POST(self) -> None:
        try:
            parsed = urlparse(self.path)
            payload = self._body()
            if parsed.path == "/api/dry-run":
                self._json(self._dry_run(payload))
            elif parsed.path == "/api/run":
                self._json(self._start_run(payload))
            elif parsed.path == "/api/templates":
                self._json(self._create_template(payload))
            elif parsed.path.startswith("/api/templates/") and parsed.path.endswith("/copy"):
                template_name = unquote(parsed.path.split("/")[3])
                self._json(self._copy_template(template_name, payload))
            elif parsed.path.startswith("/api/runs/") and parsed.path.endswith("/stop"):
                run_id = parsed.path.split("/")[3]
                request_stop(run_id, self.workspace)
                self._json({"ok": True})
            else:
                self._json({"error": "not found"}, 404)
        except Exception as exc:
            self._error(exc)

    def do_PUT(self) -> None:
        try:
            parsed = urlparse(self.path)
            payload = self._body()
            if parsed.path.startswith("/api/templates/"):
                template_name = unquote(parsed.path.split("/")[3])
                self._json(self._save_template(template_name, payload))
            else:
                self._json({"error": "not found"}, 404)
        except Exception as exc:
            self._error(exc)

    def _config_item(self, path: Path, kind: str) -> dict:
        loop = load_loop(path, self.workspace)
        return {
            "name": loop.name,
            "kind": kind,
            "path": str(path),
            "description": loop.description,
            "variables": [
                {
                    "name": variable.name,
                    "required": variable.required,
                    "default": None if variable.secret else variable.default,
                    "secret": variable.secret,
                    "description": variable.description,
                }
                for variable in loop.variables
            ],
        }

    def _configs(self) -> dict:
        return {
            "workspace": str(self.workspace),
            "loops": [self._config_item(path, "loops") for path in list_configs("loops", self.workspace)],
            "templates": [self._config_item(path, "templates") for path in list_configs("templates", self.workspace)],
        }

    def _template_payload(self, path: Path) -> dict:
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        return {"name": data.get("name") or path.stem, "path": str(path), "yaml": path.read_text(encoding="utf-8")}

    def _template_detail(self, template_name: str) -> dict:
        return self._template_payload(find_config(template_name, "templates", self.workspace))

    def _create_template(self, payload: dict) -> dict:
        name = str(payload.get("name") or "")
        data = payload.get("data") or default_template_data(name)
        path = create_template(name, self.workspace, data=data, overwrite=bool(payload.get("force", False)))
        return self._template_payload(path)

    def _copy_template(self, template_name: str, payload: dict) -> dict:
        target_name = str(payload.get("name") or "")
        path = copy_template(template_name, target_name, self.workspace, overwrite=bool(payload.get("force", False)))
        return self._template_payload(path)

    def _save_template(self, template_name: str, payload: dict) -> dict:
        if "yaml" not in payload:
            raise ConfigError("Missing yaml")
        data = yaml.safe_load(str(payload["yaml"])) or {}
        data["name"] = template_name
        path = write_template(template_name, data, self.workspace, overwrite=True)
        return self._template_payload(path)

    def _load_payload_loop(self, payload: dict):
        kind = payload.get("kind") or "loops"
        name = payload.get("name")
        path = payload.get("path")
        if path:
            return load_loop(Path(path), self.workspace)
        return load_loop(find_config(name, kind, self.workspace), self.workspace)

    def _dry_run(self, payload: dict) -> dict:
        loop = self._load_payload_loop(payload)
        result = execute_loop(loop, payload.get("values") or {}, dry=True)
        assert isinstance(result, DryRunResult)
        safe_values = redact_mapping(result.values, secret_names(loop.variables))
        return {"prompt": result.prompt, "commands": result.commands, "values": safe_values}

    def _start_run(self, payload: dict) -> dict:
        loop = self._load_payload_loop(payload)
        values = payload.get("values") or {}
        max_iterations = payload.get("max_iterations")
        holder: dict[str, str] = {}

        def target() -> None:
            result = execute_loop(loop, values, max_iterations=max_iterations)
            if not isinstance(result, DryRunResult):
                holder["run_id"] = result.run_id

        thread = threading.Thread(target=target, daemon=True)
        thread.start()
        thread.join(0.05)
        return {"started": True, "run_id": holder.get("run_id", "pending")}

    def _runs(self) -> list[dict]:
        runs = []
        for path in list_runs(self.workspace):
            summary = path / "summary.json"
            if summary.exists():
                data = json.loads(summary.read_text(encoding="utf-8"))
            else:
                run_yaml = path / "run.yaml"
                data = yaml.safe_load(run_yaml.read_text(encoding="utf-8")) if run_yaml.exists() else {}
            runs.append({"run_id": path.name, "status": data.get("status"), "reason": data.get("reason")})
        return runs

    def _run_detail(self, run_id: str) -> dict:
        path = find_run(run_id, self.workspace)
        detail = {"run_id": run_id, "files": sorted(item.name for item in path.iterdir() if not item.name.startswith("."))}
        summary = path / "summary.json"
        if summary.exists():
            detail["summary"] = json.loads(summary.read_text(encoding="utf-8"))
        report = path / "final_report.md"
        if report.exists():
            detail["report"] = report.read_text(encoding="utf-8")
        return detail


def serve(host: str = "127.0.0.1", port: int = 8765, workspace: str | Path | None = None) -> None:
    handler = type("ConfiguredAgentLoopHandler", (AgentLoopHandler,), {"workspace": Path(workspace or Path.cwd()).resolve()})
    server = ThreadingHTTPServer((host, port), handler)
    print(f"AgentLoop serving on http://{host}:{port}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
