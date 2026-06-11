# AgentLoop

AgentLoop is a lightweight standalone web app and CLI for local-first loop engineering. It runs repeat-until-pass AI workflows that invoke an agent, execute objective checks, and stop when checks pass, a blocker is detected, the same failure repeats, the run is stopped, or the maximum iteration count is reached.

AgentLoop starts with Codex CLI support through `codex exec`, and the core engine is adapter-based so other agents can be added later.

## Install

From this repository:

```bash
python3 -m pip install -e .
```

## CLI

```bash
agentloop serve
agentloop list
agentloop dry-run staging-fix --var task_description="Fix login bug" --var target_url="http://localhost:8000"
agentloop run generic-quality-loop --var task_description="Fix login bug" --var check_command="python3 -m unittest discover"
agentloop stop <run-id>
agentloop logs <run-id>

agentloop templates list
agentloop templates show generic-quality-loop
agentloop templates create bug-fix --check "tests=python3 -m unittest discover"
agentloop templates copy generic-quality-loop bug-fix-copy
agentloop templates edit bug-fix-copy --description "Bug fix loop" --variable task_description:required --variable api_token:secret
agentloop templates dry-run generic-quality-loop --vars-file vars.yaml
agentloop templates run generic-quality-loop --vars-file vars.yaml

agentloop runs list
agentloop runs show <run-id>
agentloop runs report <run-id>
agentloop runs rerun <run-id>
```

Useful options include `--host`, `--port`, `--workspace`, `--var key=value`, `--vars-file vars.yaml`, `--allow-outside-workspace`, and `--max-iterations`.

## Web UI

Start the local interface:

```bash
agentloop serve --host 127.0.0.1 --port 8765
```

Open `http://127.0.0.1:8765` to view loop configs, templates, runs, rendered dry-runs, and run details. The UI can start a loop, fill template variables, and request a stop for a run.

The web UI also includes a template editor. You can create a starter template, copy an existing template, edit the YAML, and save it back to `.agentloop/templates/`.

## Config Layout

Loop configs live under:

```text
.agentloop/
  loops/
    staging-fix.yaml
    model-refresh.yaml
    ui-smoke.yaml
  prompts/
    staging-fix.md
    model-refresh.md
    ui-smoke.md
  templates/
    generic-quality-loop.yaml
  examples/
    ml-model-refresh.yaml
```

Run artifacts are stored under:

```text
.agentloop-runs/<run_id>/
  run.yaml
  variables.yaml
  prompt_iteration_001.txt
  adapter_iteration_001.log
  checks_iteration_001.log
  summary.json
  final_report.md
```

Secret variable values are redacted from user-facing run files and API responses. AgentLoop stores a private `.variables.private.yaml` file with mode `0600` for reruns that need the same values.

## Adapters

The first production adapter is `codex`, which invokes:

```bash
codex exec "<rendered prompt>"
```

A `shell` adapter is included for local testing and non-AI command loops.
