from __future__ import annotations

import subprocess
import tempfile
import threading
import time
import unittest
import inspect
import base64
import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import yaml

from agentloop.adapters.codex.adapter import CodexAdapter
from agentloop.adapters.base import AdapterResult
from agentloop.core.processes import run_interruptible
from agentloop.core.engine import DryRunResult, execute_loop
from agentloop.core.models import CheckConfig, LoopConfig, RenderedLoop
from agentloop.core.rendering import RenderError, render_loop
from agentloop.storage.configs import ConfigError, load_loop
from agentloop.storage.runs import find_run, list_runs, request_stop
from agentloop.web.server import AgentLoopHandler, DICE_HTML, INDEX_HTML


class AgentLoopTests(unittest.TestCase):
    def planner_json(self) -> str:
        return json.dumps(
            [
                {
                    "field": "feature_details",
                    "question": "When the coffee simulator starts brewing, should the player control grind, water, heat, timing, or only watch the animation?",
                },
                {
                    "field": "testing_plan",
                    "question": "What specific behavior should tests verify for a successful brew cycle?",
                },
                {
                    "field": "library_preferences",
                    "question": "Should this be plain HTML canvas, React, or another rendering stack?",
                },
            ]
        )

    def make_workspace(self) -> tempfile.TemporaryDirectory[str]:
        temp = tempfile.TemporaryDirectory()
        root = Path(temp.name)
        (root / ".agentloop" / "loops").mkdir(parents=True)
        (root / ".agentloop" / "prompts").mkdir(parents=True)
        return temp

    def write_loop(self, root: Path, name: str, data: dict, prompt: str = "Task {{ task_description }}") -> Path:
        (root / ".agentloop" / "prompts" / f"{name}.md").write_text(prompt, encoding="utf-8")
        config = {
            "name": name,
            "adapter": "shell",
            "prompt": f"{name}.md",
            "variables": [{"name": "task_description", "required": True}],
            "checks": [{"name": "ok", "command": "true"}],
        }
        config.update(data)
        path = root / ".agentloop" / "loops" / f"{name}.yaml"
        path.write_text(yaml.safe_dump(config, sort_keys=False), encoding="utf-8")
        return path

    def test_render_loop_requires_variables(self) -> None:
        with self.make_workspace() as temp:
            root = Path(temp)
            path = self.write_loop(root, "required", {})
            loop = load_loop(path, root)
            with self.assertRaises(RenderError):
                render_loop(loop, {})

    def test_dice_rng_page_contains_three_js_app(self) -> None:
        self.assertIn("3D Dice RNG", DICE_HTML)
        self.assertIn("three@0.165.0", DICE_HTML)
        self.assertIn("cannon-es@0.20.0", DICE_HTML)
        self.assertIn("RoundedBoxGeometry", DICE_HTML)
        self.assertIn("OrbitControls", DICE_HTML)
        self.assertIn("controls.enablePan = true", DICE_HTML)
        self.assertIn("controls.enableZoom = true", DICE_HTML)
        self.assertIn('id="diceCanvas"', DICE_HTML)
        self.assertIn('id="sidesInput"', DICE_HTML)
        self.assertIn('id="diceInput"', DICE_HTML)
        self.assertIn('data-step="sides:-1"', DICE_HTML)
        self.assertIn('data-step="dice:1"', DICE_HTML)
        self.assertIn("window.diceRng", DICE_HTML)
        self.assertIn("document.body.dataset.diceCount", DICE_HTML)
        self.assertIn("document.body.dataset.modelSideCount", DICE_HTML)
        self.assertIn("document.body.dataset.values", DICE_HTML)
        self.assertIn("document.body.dataset.probability100", DICE_HTML)
        self.assertIn("world.step(1 / 60, dt, 5)", DICE_HTML)
        self.assertIn("function convexFromNormals", DICE_HTML)
        self.assertIn("new CANNON.ConvexPolyhedron", DICE_HTML)
        self.assertIn("geometryFromPolyhedron(polyhedron)", DICE_HTML)
        self.assertIn("const maxVertexLength = Math.max", DICE_HTML)
        self.assertIn("point.multiplyScalar(scale)", DICE_HTML)
        self.assertIn("function expectedDistribution", DICE_HTML)
        self.assertIn("function expectedCounts", DICE_HTML)
        self.assertIn("dice:settled", DICE_HTML)
        self.assertNotIn('href="/dice"', INDEX_HTML)
        self.assertIn('data-page-target="appsPage"', INDEX_HTML)

    def test_dice_rng_probability_model_covers_required_100_roll_cases(self) -> None:
        def expected_counts(sides: int, count: int, rolls: int = 100) -> list[tuple[int, float]]:
            distribution = {0: 1}
            for _ in range(count):
                next_distribution: dict[int, int] = {}
                for subtotal, ways in distribution.items():
                    for face in range(1, sides + 1):
                        next_distribution[subtotal + face] = next_distribution.get(subtotal + face, 0) + ways
                distribution = next_distribution
            total_ways = sides**count
            return [(total, round(ways / total_ways * rolls, 6)) for total, ways in sorted(distribution.items())]

        self.assertEqual(expected_counts(6, 1), [(1, 16.666667), (2, 16.666667), (3, 16.666667), (4, 16.666667), (5, 16.666667), (6, 16.666667)])
        self.assertEqual(
            expected_counts(10, 1),
            [(1, 10.0), (2, 10.0), (3, 10.0), (4, 10.0), (5, 10.0), (6, 10.0), (7, 10.0), (8, 10.0), (9, 10.0), (10, 10.0)],
        )
        self.assertEqual(
            expected_counts(6, 2),
            [(2, 2.777778), (3, 5.555556), (4, 8.333333), (5, 11.111111), (6, 13.888889), (7, 16.666667), (8, 13.888889), (9, 11.111111), (10, 8.333333), (11, 5.555556), (12, 2.777778)],
        )

    def test_server_routes_dice_rng_page(self) -> None:
        source = inspect.getsource(AgentLoopHandler.do_GET)
        self.assertIn('parsed.path == "/dice"', source)
        self.assertIn("DICE_HTML.encode", source)

    def test_dry_run_renders_prompt_and_commands(self) -> None:
        with self.make_workspace() as temp:
            root = Path(temp)
            path = self.write_loop(
                root,
                "dry",
                {"checks": [{"name": "echo", "command": "echo {{ task_description }}"}]},
            )
            loop = load_loop(path, root)
            result = execute_loop(loop, {"task_description": "ship it"}, dry=True)
            self.assertIsInstance(result, DryRunResult)
            assert isinstance(result, DryRunResult)
            self.assertIn("ship it", result.prompt)
            self.assertEqual(result.commands, ["echo ship it"])

    def test_run_interruptible_streams_output_before_process_exits(self) -> None:
        chunks: list[str] = []
        completed = run_interruptible(
            "python3 -c \"print('first', flush=True); print('second', flush=True)\"",
            cwd=Path.cwd(),
            shell=True,
            output_callback=chunks.append,
        )

        self.assertEqual(completed.returncode, 0)
        self.assertIn("first", "".join(chunks))
        self.assertIn("second", completed.stdout)

    def test_run_interruptible_emits_heartbeat_for_quiet_process(self) -> None:
        heartbeats: list[float] = []
        completed = run_interruptible(
            "python3 -c \"import time; time.sleep(.35)\"",
            cwd=Path.cwd(),
            shell=True,
            heartbeat_interval=0.1,
            heartbeat_callback=heartbeats.append,
        )

        self.assertEqual(completed.returncode, 0)
        self.assertGreaterEqual(len(heartbeats), 1)

    def test_dry_run_renders_long_inline_prompt_as_prompt_text(self) -> None:
        with self.make_workspace() as temp:
            root = Path(temp)
            long_prompt = "Do this work:\n{{ task_description }}\n" + ("test and scan. " * 40)
            path = self.write_loop(root, "long-inline", {"prompt": long_prompt})
            loop = load_loop(path, root)

            result = execute_loop(loop, {"task_description": "ship it"}, dry=True)

            self.assertIsInstance(result, DryRunResult)
            assert isinstance(result, DryRunResult)
            self.assertIn("Do this work:", result.prompt)
            self.assertIn("ship it", result.prompt)

    def test_execute_loop_writes_required_artifacts(self) -> None:
        with self.make_workspace() as temp:
            root = Path(temp)
            path = self.write_loop(root, "pass", {"prompt": "echo working"})
            loop = load_loop(path, root)
            result = execute_loop(loop, {"task_description": "x"})
            assert not isinstance(result, DryRunResult)
            self.assertEqual(result.status, "passed")
            for name in [
                "run.yaml",
                "variables.yaml",
                "run.log",
                "prompt_iteration_001.txt",
                "adapter_iteration_001.log",
                "checks_iteration_001.log",
                "summary.json",
                "final_report.md",
            ]:
                self.assertTrue((result.run_dir / name).exists(), name)
            run_log = (result.run_dir / "run.log").read_text(encoding="utf-8")
            self.assertIn("run created:", run_log)
            self.assertIn("starting adapter", run_log)
            self.assertIn("run finished: passed", run_log)
            live_log = result.run_dir / "adapter_iteration_001.live.log"
            self.assertTrue(live_log.exists())
            self.assertIn("working", live_log.read_text(encoding="utf-8"))

    def test_repeated_failure_stops_run(self) -> None:
        with self.make_workspace() as temp:
            root = Path(temp)
            path = self.write_loop(
                root,
                "repeat",
                {"prompt": "true", "checks": [{"name": "fail", "command": "false"}], "max_iterations": 5},
            )
            loop = load_loop(path, root)
            result = execute_loop(loop, {"task_description": "x"})
            assert not isinstance(result, DryRunResult)
            self.assertEqual(result.status, "failed")
            self.assertEqual(result.reason, "same failure repeated")
            self.assertEqual(result.iterations, 2)

    def test_failed_check_output_is_included_in_next_iteration_prompt(self) -> None:
        with self.make_workspace() as temp:
            root = Path(temp)
            path = self.write_loop(
                root,
                "check-feedback",
                {
                    "prompt": "true",
                    "checks": [{"name": "acceptance", "command": "printf 'expected total missing\\n'; exit 1"}],
                    "max_iterations": 2,
                },
            )
            loop = load_loop(path, root)

            result = execute_loop(loop, {"task_description": "x"})

            assert not isinstance(result, DryRunResult)
            second_prompt = (result.run_dir / "prompt_iteration_002.txt").read_text(encoding="utf-8")
            self.assertIn("Previous checks failed", second_prompt)
            self.assertIn("acceptance exited 1", second_prompt)
            self.assertIn("expected total missing", second_prompt)

    def test_blocked_output_stops_run(self) -> None:
        with self.make_workspace() as temp:
            root = Path(temp)
            path = self.write_loop(root, "blocked", {"prompt": "echo 'BLOCKED: missing data'"})
            loop = load_loop(path, root)
            result = execute_loop(loop, {"task_description": "x"})
            assert not isinstance(result, DryRunResult)
            self.assertEqual(result.status, "blocked")

    def test_blocked_text_in_prompt_echo_does_not_stop_run(self) -> None:
        with self.make_workspace() as temp:
            root = Path(temp)
            path = self.write_loop(
                root,
                "prompt-mentions-blocked",
                {"prompt": "printf 'Task says BLOCKED: is an instruction\\nwork complete\\n'"},
            )
            loop = load_loop(path, root)
            result = execute_loop(loop, {"task_description": "x"})
            assert not isinstance(result, DryRunResult)
            self.assertEqual(result.status, "passed")

    def test_codex_adapter_uses_full_access_sandbox_to_avoid_nested_bwrap(self) -> None:
        rendered = RenderedLoop(
            loop=LoopConfig(
                name="codex-loop",
                description="",
                adapter="codex",
                prompt="do work",
                checks=[CheckConfig(name="ok", command="true")],
                workspace=Path.cwd(),
            ),
            values={},
            prompt="do work",
            commands=["true"],
        )

        with patch("agentloop.adapters.codex.adapter.run_interruptible") as run:
            run.return_value = SimpleNamespace(returncode=0, stdout="done\n")
            result = CodexAdapter().run_iteration(rendered, 1)

        command = result.command
        exec_index = command.index("exec")
        self.assertTrue(command[0].endswith(("codex", "codex.js")) or "@openai/codex" in command[:exec_index])
        self.assertEqual(command[exec_index : exec_index + 3], ["exec", "--sandbox", "danger-full-access"])
        self.assertIn('approval_policy="never"', command)
        self.assertFalse(result.blocked)

    def test_codex_adapter_falls_back_to_user_npm_global_codex_path(self) -> None:
        rendered = RenderedLoop(
            loop=LoopConfig(
                name="codex-loop",
                description="",
                adapter="codex",
                prompt="do work",
                checks=[CheckConfig(name="ok", command="true")],
                workspace=Path.cwd(),
            ),
            values={},
            prompt="do work",
            commands=["true"],
        )

        with (
            patch("agentloop.adapters.codex.adapter.shutil.which", return_value=None),
            patch("agentloop.adapters.codex.adapter.Path.exists", return_value=True),
            patch("agentloop.adapters.codex.adapter.os.access", return_value=True),
            patch("agentloop.adapters.codex.adapter.run_interruptible") as run,
        ):
            run.return_value = SimpleNamespace(returncode=0, stdout="done\n")
            result = CodexAdapter().run_iteration(rendered, 1)

        self.assertEqual(result.command[0], str(Path.home() / ".npm-global" / "bin" / "codex"))

    def test_codex_adapter_allows_explicit_binary_override(self) -> None:
        rendered = RenderedLoop(
            loop=LoopConfig(
                name="codex-loop",
                description="",
                adapter="codex",
                prompt="do work",
                checks=[CheckConfig(name="ok", command="true")],
                workspace=Path.cwd(),
            ),
            values={},
            prompt="do work",
            commands=["true"],
        )

        with (
            patch.dict("os.environ", {"AGENTLOOP_CODEX_BIN": "/tmp/custom-codex"}),
            patch("agentloop.adapters.codex.adapter.Path.exists", return_value=True),
            patch("agentloop.adapters.codex.adapter.os.access", return_value=True),
            patch("agentloop.adapters.codex.adapter.run_interruptible") as run,
        ):
            run.return_value = SimpleNamespace(returncode=0, stdout="done\n")
            result = CodexAdapter().run_iteration(rendered, 1)

        self.assertEqual(result.command[0], "/tmp/custom-codex")

    def test_codex_adapter_falls_back_to_npx_when_direct_binary_is_missing(self) -> None:
        rendered = RenderedLoop(
            loop=LoopConfig(
                name="codex-loop",
                description="",
                adapter="codex",
                prompt="do work",
                checks=[CheckConfig(name="ok", command="true")],
                workspace=Path.cwd(),
            ),
            values={},
            prompt="do work",
            commands=["true"],
        )

        def fake_which(name: str) -> str | None:
            return "/usr/bin/npx" if name == "npx" else None

        with (
            patch("agentloop.adapters.codex.adapter.shutil.which", side_effect=fake_which),
            patch("agentloop.adapters.codex.adapter.Path.exists", return_value=False),
            patch("agentloop.adapters.codex.adapter.run_interruptible") as run,
        ):
            run.return_value = SimpleNamespace(returncode=0, stdout="done\n")
            result = CodexAdapter().run_iteration(rendered, 1)

        self.assertEqual(result.command[:3], ["/usr/bin/npx", "--yes", "@openai/codex"])

    def test_codex_adapter_reports_missing_binary_clearly(self) -> None:
        with (
            patch.dict("os.environ", {}, clear=True),
            patch("agentloop.adapters.codex.adapter.shutil.which", return_value=None),
            patch("agentloop.adapters.codex.adapter.Path.exists", return_value=False),
        ):
            with self.assertRaisesRegex(FileNotFoundError, "Codex binary not found"):
                CodexAdapter()._codex_binary()

    def test_codex_adapter_only_marks_recent_final_blocked_lines(self) -> None:
        rendered = RenderedLoop(
            loop=LoopConfig(
                name="codex-loop",
                description="",
                adapter="codex",
                prompt="do work",
                checks=[CheckConfig(name="ok", command="true")],
                workspace=Path.cwd(),
            ),
            values={},
            prompt="do work",
            commands=["true"],
        )

        with patch("agentloop.adapters.codex.adapter.run_interruptible") as run:
            run.return_value = SimpleNamespace(returncode=0, stdout="user prompt says BLOCKED:\nwork completed\n")
            result = CodexAdapter().run_iteration(rendered, 1)
        self.assertFalse(result.blocked)

        with patch("agentloop.adapters.codex.adapter.run_interruptible") as run:
            run.return_value = SimpleNamespace(returncode=0, stdout="attempted work\nBLOCKED: missing dependency\n")
            result = CodexAdapter().run_iteration(rendered, 1)
        self.assertTrue(result.blocked)

    def test_invalid_max_iterations_reports_config_error(self) -> None:
        with self.make_workspace() as temp:
            root = Path(temp)
            path = self.write_loop(root, "bad-max", {"max_iterations": "3 - bad instruction text"})

            with self.assertRaisesRegex(ConfigError, "max_iterations must be an integer"):
                load_loop(path, root)

    def test_execute_loop_finalizes_run_when_adapter_raises(self) -> None:
        class RaisingAdapter:
            name = "raising"

            def run_iteration(self, rendered: RenderedLoop, iteration: int, stop_file=None) -> AdapterResult:
                raise FileNotFoundError("missing adapter binary")

        with self.make_workspace() as temp:
            root = Path(temp)
            path = self.write_loop(root, "adapter-raises", {})
            loop = load_loop(path, root)

            with patch("agentloop.core.engine.get_adapter", return_value=RaisingAdapter()):
                result = execute_loop(loop, {"task_description": "x"})

            assert not isinstance(result, DryRunResult)
            self.assertEqual(result.status, "failed")
            self.assertIn("FileNotFoundError", result.reason)
            self.assertTrue((result.run_dir / "summary.json").exists())
            self.assertTrue((result.run_dir / "final_report.md").exists())
            self.assertTrue((result.run_dir / "error.log").exists())
            run_yaml = yaml.safe_load((result.run_dir / "run.yaml").read_text(encoding="utf-8"))
            self.assertEqual(run_yaml["status"], "failed")

    def test_stop_request_interrupts_running_adapter_process(self) -> None:
        with self.make_workspace() as temp:
            root = Path(temp)
            path = self.write_loop(
                root,
                "slow",
                {"prompt": "python3 -c 'import time; time.sleep(30)'", "checks": [{"name": "ok", "command": "true"}]},
            )
            loop = load_loop(path, root)
            result_holder = {}

            thread = threading.Thread(
                target=lambda: result_holder.setdefault("result", execute_loop(loop, {"task_description": "x"}))
            )
            thread.start()

            deadline = time.time() + 5
            run_id = None
            while time.time() < deadline:
                runs = list_runs(root)
                if runs:
                    run_id = runs[0].name
                    break
                time.sleep(0.05)

            self.assertIsNotNone(run_id)
            assert run_id is not None
            request_stop(run_id, root)
            thread.join(timeout=5)

            self.assertFalse(thread.is_alive(), "run thread did not stop after STOP was requested")
            result = result_holder["result"]
            assert not isinstance(result, DryRunResult)
            self.assertEqual(result.status, "stopped")
            self.assertEqual(result.reason, "stop requested")

    def test_cli_dry_run(self) -> None:
        with self.make_workspace() as temp:
            root = Path(temp)
            self.write_loop(root, "cli", {"checks": [{"name": "echo", "command": "echo {{ task_description }}"}]})
            completed = subprocess.run(
                [
                    "python3",
                    "-m",
                    "agentloop.cli.main",
                    "dry-run",
                    "cli",
                    "--workspace",
                    str(root),
                    "--var",
                    "task_description=from-cli",
                ],
                cwd=Path(__file__).resolve().parents[1],
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                check=False,
            )
            self.assertEqual(completed.returncode, 0, completed.stderr)
            self.assertIn("from-cli", completed.stdout)

    def test_cli_template_create_copy_edit(self) -> None:
        with self.make_workspace() as temp:
            root = Path(temp)
            commands = [
                [
                    "python3",
                    "-m",
                    "agentloop.cli.main",
                    "templates",
                    "create",
                    "starter",
                    "--workspace",
                    str(root),
                ],
                [
                    "python3",
                    "-m",
                    "agentloop.cli.main",
                    "templates",
                    "copy",
                    "starter",
                    "starter-copy",
                    "--workspace",
                    str(root),
                ],
                [
                    "python3",
                    "-m",
                    "agentloop.cli.main",
                    "templates",
                    "edit",
                    "starter-copy",
                    "--workspace",
                    str(root),
                    "--description",
                    "Edited template",
                    "--check",
                    "unit=python3 -m unittest discover",
                    "--variable",
                    "task_description:required",
                    "--variable",
                    "api_token:secret",
                ],
            ]
            for command in commands:
                completed = subprocess.run(
                    command,
                    cwd=Path(__file__).resolve().parents[1],
                    text=True,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    check=False,
                )
                self.assertEqual(completed.returncode, 0, completed.stderr)

            copied = root / ".agentloop" / "templates" / "starter-copy.yaml"
            data = yaml.safe_load(copied.read_text(encoding="utf-8"))
            self.assertEqual(data["description"], "Edited template")
            self.assertEqual(data["checks"][0]["command"], "python3 -m unittest discover")
            self.assertTrue(data["variables"][1]["secret"])

    def test_web_ui_has_pages_and_theme_controls(self) -> None:
        for text in ["Home Dashboard", "Run", "Chat", "Apps", "Loops", "Templates", "Settings", "themeMode", "prefers-color-scheme"]:
            self.assertIn(text, INDEX_HTML)
        for text in ["appsPage", "loadApps", "/api/apps"]:
            self.assertIn(text, INDEX_HTML)
        for text in ["Loop Configuration", "Loop Runs", "loopRunsPage", "showLoopRuns", "editLoopConfig", "saveLoopConfig"]:
            self.assertIn(text, INDEX_HTML)
        for text in ["Dry-run failed:", "try {", "catch (err)"]:
            self.assertIn(text, INDEX_HTML)
        for text in ["Rolling Log", "downloadRunLog", "runLogArtifacts", "runAttachments", "renderLogArtifacts"]:
            self.assertIn(text, INDEX_HTML)
        for text in ["Final Output", "runFinalArtifacts", "wasNearBottom", "detail.status === 'running'"]:
            self.assertIn(text, INDEX_HTML)
        for text in ["chatPage", "chatTranscript", "chatMessage", "sendChat", "/api/chat"]:
            self.assertIn(text, INDEX_HTML)
        for text in ["chatMode", "Edit existing", "chatEditControls", "chatTargetKind", "chatTarget", "chatAction", "updateChatMode"]:
            self.assertIn(text, INDEX_HTML)
        for text in ["chatFileInput", "attachChatFile", "chatAttachments", "collectChatAttachments"]:
            self.assertIn(text, INDEX_HTML)
        for text in ["chatDraftActions", "createChatTemplate", "createChatLoop", "startChatRun", "resetChatDraft"]:
            self.assertIn(text, INDEX_HTML)
        for text in ["action: 'conversation'", "conversation_create", "setChatDraft", "createFromChat"]:
            self.assertIn(text, INDEX_HTML)
        for text in ["Rerun selected run", "rerunRun", "state.selectedRun = null", "button.dataset.runId"]:
            self.assertIn(text, INDEX_HTML)
        for text in ["refreshSelectedRun", "setInterval(refreshSelectedRun, 2000)"]:
            self.assertIn(text, INDEX_HTML)
        self.assertNotIn("showPage('settingsPage')", INDEX_HTML)

    def test_web_loop_config_detail_and_save(self) -> None:
        with self.make_workspace() as temp:
            root = Path(temp)
            self.write_loop(root, "editable", {"description": "Before"})
            handler = AgentLoopHandler.__new__(AgentLoopHandler)
            handler.workspace = root

            detail = AgentLoopHandler._loop_detail(handler, "editable")
            self.assertIn("description: Before", detail["yaml"])

            updated_yaml = detail["yaml"].replace("description: Before", "description: After")
            saved = AgentLoopHandler._save_loop(handler, "editable", {"yaml": updated_yaml})
            self.assertIn("description: After", saved["yaml"])

            loop = load_loop(root / ".agentloop" / "loops" / "editable.yaml", root)
            self.assertEqual(loop.description, "After")

    def test_web_configs_keeps_valid_items_when_one_config_is_invalid(self) -> None:
        with self.make_workspace() as temp:
            root = Path(temp)
            self.write_loop(root, "valid", {})
            self.write_loop(root, "invalid", {"max_iterations": "3 - bad instruction text"})
            handler = AgentLoopHandler.__new__(AgentLoopHandler)
            handler.workspace = root

            configs = AgentLoopHandler._configs(handler)

            self.assertEqual([item["name"] for item in configs["loops"]], ["invalid", "valid"])
            invalid = configs["loops"][0]
            self.assertIn("max_iterations must be an integer", invalid["error"])
            self.assertNotIn("error", configs["loops"][1])

    def test_web_loop_runs_filter_and_detail_logs(self) -> None:
        with self.make_workspace() as temp:
            root = Path(temp)
            first = load_loop(self.write_loop(root, "first", {"prompt": "echo first"}), root)
            second = load_loop(self.write_loop(root, "second", {"prompt": "echo second"}), root)
            first_result = execute_loop(first, {"task_description": "x"})
            second_result = execute_loop(second, {"task_description": "x"})
            assert not isinstance(first_result, DryRunResult)
            assert not isinstance(second_result, DryRunResult)
            handler = AgentLoopHandler.__new__(AgentLoopHandler)
            handler.workspace = root

            first_runs = AgentLoopHandler._runs(handler, loop_name="first")
            second_runs = AgentLoopHandler._runs(handler, loop_name="second")
            self.assertEqual([run["run_id"] for run in first_runs], [first_result.run_id])
            self.assertEqual([run["run_id"] for run in second_runs], [second_result.run_id])
            self.assertEqual(first_runs[0]["loop"], "first")

            detail = AgentLoopHandler._run_detail(handler, first_result.run_id)
            self.assertEqual(detail["loop"], "first")
            log_names = [log["name"] for log in detail["logs"]]
            self.assertIn("run.log", log_names)
            self.assertIn("adapter_iteration_001.live.log", log_names)
            self.assertIn("adapter_iteration_001.log", log_names)
            self.assertIn("checks_iteration_001.log", log_names)
            self.assertEqual(log_names.count("adapter_iteration_001.live.log"), 1)
            self.assertTrue(detail["run_log_url"].endswith("/files/run.log"))
            self.assertIn("run created:", detail["event_log"])
            self.assertIn("latest adapter output: adapter_iteration_001.live.log", detail["event_log"])
            self.assertIn("Final report", [item["name"] for item in detail["final_artifacts"]])

            screenshot = first_result.run_dir / "screenshot.png"
            screenshot.write_bytes(b"fake image")
            detail_with_attachment = AgentLoopHandler._run_detail(handler, first_result.run_id)
            self.assertEqual(detail_with_attachment["attachments"][0]["name"], "screenshot.png")
            self.assertTrue(detail_with_attachment["attachments"][0]["download_url"].endswith("screenshot.png?download=1"))

    def test_web_run_detail_surfaces_final_urls_and_app_route_artifacts(self) -> None:
        with self.make_workspace() as temp:
            root = Path(temp)
            loop = load_loop(
                self.write_loop(
                    root,
                    "artifact-links",
                    {
                        "prompt": "echo 'Open http://127.0.0.1:8765/apps/coffee-sim/ or /apps/coffee-sim/'",
                        "variables": [
                            {"name": "task_description", "required": True},
                            {"name": "app_slug", "required": False, "default": "coffee-sim"},
                            {"name": "app_endpoint", "required": False, "default": "/apps/coffee-sim/"},
                        ],
                    },
                ),
                root,
            )
            result = execute_loop(loop, {"task_description": "x", "app_slug": "coffee-sim", "app_endpoint": "/apps/coffee-sim/"})
            assert not isinstance(result, DryRunResult)
            handler = AgentLoopHandler.__new__(AgentLoopHandler)
            handler.workspace = root

            detail = AgentLoopHandler._run_detail(handler, result.run_id)

            artifacts = {item["name"]: item["url"] for item in detail["final_artifacts"]}
            self.assertEqual(artifacts["Final report"], f"/api/runs/{result.run_id}/files/final_report.md")
            self.assertEqual(artifacts["coffee-sim"], "/apps/coffee-sim/")
            self.assertEqual(artifacts["http://127.0.0.1:8765/apps/coffee-sim/"], "http://127.0.0.1:8765/apps/coffee-sim/")

    def test_web_apps_lists_and_serves_named_app_endpoints(self) -> None:
        with self.make_workspace() as temp:
            root = Path(temp)
            app_dir = root / ".agentloop" / "apps" / "coffee-sim"
            app_dir.mkdir(parents=True)
            (app_dir / "index.html").write_text("<!doctype html><title>Coffee Sim</title>", encoding="utf-8")
            handler = AgentLoopHandler.__new__(AgentLoopHandler)
            handler.workspace = root

            apps = AgentLoopHandler._apps(handler)

            self.assertEqual(apps, [{"name": "coffee-sim", "path": str(app_dir), "url": "/apps/coffee-sim/"}])

    def test_chat_updates_loop_acceptance_criteria(self) -> None:
        with self.make_workspace() as temp:
            root = Path(temp)
            self.write_loop(
                root,
                "chat-loop",
                {
                    "prompt": "Task: {{ task_description }}",
                    "variables": [{"name": "task_description", "required": True}],
                    "checks": [{"name": "ok", "command": "true"}],
                },
            )
            handler = AgentLoopHandler.__new__(AgentLoopHandler)
            handler.workspace = root

            response = AgentLoopHandler._chat(
                handler,
                {
                    "message": "Support exporting the result as CSV.",
                    "target": {"kind": "loops", "name": "chat-loop"},
                    "action": "update",
                },
            )

            self.assertIn("Added requirement", response["message"])
            updated = yaml.safe_load((root / ".agentloop" / "loops" / "chat-loop.yaml").read_text(encoding="utf-8"))
            acceptance = next(item for item in updated["variables"] if item["name"] == "acceptance_criteria")
            self.assertIn("Support exporting the result as CSV.", acceptance["default"])
            self.assertIn("{{ acceptance_criteria }}", updated["prompt"])

    def test_chat_app_idea_creates_template_with_followup_questions(self) -> None:
        with self.make_workspace() as temp:
            root = Path(temp)
            handler = AgentLoopHandler.__new__(AgentLoopHandler)
            handler.workspace = root

            with patch.object(AgentLoopHandler, "_run_question_planner", return_value=self.planner_json()):
                response = AgentLoopHandler._chat(
                    handler,
                    {
                        "message": "A meal planning app for families that builds weekly grocery lists.",
                        "target": {"kind": "new", "name": ""},
                        "action": "idea",
                        "create": "template",
                    },
                )

            self.assertIn("Created template", response["message"])
            self.assertEqual(response["target"]["kind"], "templates")
            template_path = root / ".agentloop" / "templates" / f"{response['name']}.yaml"
            self.assertTrue(template_path.exists())
            data = yaml.safe_load(template_path.read_text(encoding="utf-8"))
            variable_defaults = {item["name"]: item.get("default") for item in data["variables"]}
            self.assertIn("meal planning app", variable_defaults["app_idea"])
            self.assertTrue(variable_defaults["app_endpoint"].startswith("/apps/"))
            self.assertIn("successful brew cycle", variable_defaults["followup_questions"])
            self.assertIn("followup_question_plan", variable_defaults)
            self.assertIn(".agentloop/apps/{{ app_slug }}/index.html", data["prompt"])
            self.assertIn("Do not reuse /dice", data["prompt"])
            self.assertIn("{{ followup_questions }}", data["prompt"])

    def test_chat_conversation_builds_requirements_one_turn_at_a_time(self) -> None:
        with self.make_workspace() as temp:
            root = Path(temp)
            handler = AgentLoopHandler.__new__(AgentLoopHandler)
            handler.workspace = root

            with patch.object(AgentLoopHandler, "_run_question_planner", return_value=self.planner_json()):
                first = AgentLoopHandler._chat(
                    handler,
                    {
                        "message": "I want a 2D coffee simulator where you start a pot and watch it brew.",
                        "action": "conversation",
                    },
                )
            self.assertIn("grind, water, heat", first["message"])
            self.assertIn("draft", first)

            second = AgentLoopHandler._chat(
                handler,
                {
                    "message": "Show a kettle, filter basket, rising steam, a timer, and a strength meter.",
                    "action": "conversation",
                    "draft": first["draft"],
                },
            )

            self.assertIn("successful brew cycle", second["message"])
            data = second["draft"]["data"]
            variable_defaults = {item["name"]: item.get("default") for item in data["variables"]}
            self.assertIn("rising steam", variable_defaults["feature_details"])

            created = AgentLoopHandler._chat(
                handler,
                {
                    "message": "create",
                    "action": "conversation_create",
                    "create": "template",
                    "draft": second["draft"],
                },
            )

            self.assertIn("Created template", created["message"])
            self.assertTrue((root / ".agentloop" / "templates" / f"{created['name']}.yaml").exists())

    def test_chat_image_upload_is_saved_and_included_in_draft(self) -> None:
        with self.make_workspace() as temp:
            root = Path(temp)
            handler = AgentLoopHandler.__new__(AgentLoopHandler)
            handler.workspace = root

            with patch.object(AgentLoopHandler, "_run_question_planner", return_value=self.planner_json()):
                response = AgentLoopHandler._chat(
                    handler,
                    {
                        "message": "Use this screenshot to fix the coffee app spacing.",
                        "action": "conversation",
                        "attachments": [
                            {
                                "name": "spacing.png",
                                "type": "image/png",
                                "data": base64.b64encode(b"\x89PNG\r\n\x1a\nfake").decode("ascii"),
                            }
                        ],
                    },
                )

            upload_paths = list((root / ".agentloop" / "uploads").glob("*.png"))
            self.assertEqual(len(upload_paths), 1)
            data = response["draft"]["data"]
            variable_defaults = {item["name"]: item.get("default") for item in data["variables"]}
            self.assertIn("Attached images for the AI to inspect", variable_defaults["app_idea"])
            self.assertIn(str(upload_paths[0]), variable_defaults["app_idea"])

    def test_chat_app_idea_can_create_loop_and_start_run(self) -> None:
        with self.make_workspace() as temp:
            root = Path(temp)
            handler = AgentLoopHandler.__new__(AgentLoopHandler)
            handler.workspace = root

            with patch.object(AgentLoopHandler, "_run_question_planner", return_value=self.planner_json()):
                base_name, data, _values = AgentLoopHandler._app_idea_config(
                    handler,
                    "Build a tiny status page. Test command: true",
                )
            data["adapter"] = "shell"
            data["prompt"] = "printf '%s\\n' '{{ app_idea }} {{ followup_questions }}'"
            values = {item["name"]: item.get("default", "") for item in data["variables"]}
            with patch.object(AgentLoopHandler, "_app_idea_config", return_value=(base_name, data, values)):
                response = AgentLoopHandler._chat(
                    handler,
                    {
                        "message": "Build a tiny status page. Test command: true",
                        "target": {"kind": "new", "name": ""},
                        "action": "idea",
                        "create": "run",
                    },
                )

            self.assertIn("Created loop", response["message"])
            self.assertNotEqual(response["run_id"], "pending")
            loop_path = root / ".agentloop" / "loops" / f"{response['loop']}.yaml"
            self.assertTrue(loop_path.exists())
            deadline = time.time() + 5
            detail = {}
            while time.time() < deadline:
                detail = AgentLoopHandler._run_detail(handler, response["run_id"])
                if detail["status"] == "passed":
                    break
                time.sleep(0.05)
            self.assertEqual(detail["status"], "passed")
            adapter_log = next(log for log in detail["logs"] if log["name"] == "adapter_iteration_001.log")
            self.assertIn("Build a tiny status page", adapter_log["content"])

    def test_chat_reruns_past_run_with_added_requirement(self) -> None:
        with self.make_workspace() as temp:
            root = Path(temp)
            loop = load_loop(
                self.write_loop(
                    root,
                    "chat-rerun",
                    {
                        "prompt": "printf '%s\\n' '{{ task_description }} {{ acceptance_criteria }}'",
                        "variables": [
                            {"name": "task_description", "required": True},
                            {"name": "acceptance_criteria", "required": False, "default": ""},
                        ],
                        "checks": [{"name": "ok", "command": "true"}],
                    },
                ),
                root,
            )
            first = execute_loop(loop, {"task_description": "build page", "acceptance_criteria": "initial"})
            assert not isinstance(first, DryRunResult)
            handler = AgentLoopHandler.__new__(AgentLoopHandler)
            handler.workspace = root

            response = AgentLoopHandler._chat(
                handler,
                {
                    "message": "Add keyboard controls.",
                    "target": {"kind": "runs", "name": first.run_id},
                    "action": "rerun",
                },
            )

            self.assertIn("Started", response["message"])
            self.assertNotEqual(response["run_id"], "pending")
            deadline = time.time() + 5
            detail = {}
            while time.time() < deadline:
                detail = AgentLoopHandler._run_detail(handler, response["run_id"])
                if detail["status"] == "passed":
                    break
                time.sleep(0.05)
            self.assertEqual(detail["status"], "passed")
            adapter_log = next(log for log in detail["logs"] if log["name"] == "adapter_iteration_001.log")
            self.assertIn("Add keyboard controls.", adapter_log["content"])

    def test_web_moves_plain_english_check_command_to_acceptance_criteria(self) -> None:
        with self.make_workspace() as temp:
            root = Path(temp)
            self.write_loop(
                root,
                "quality",
                {
                    "prompt": "Task: {{ task_description }}\nCriteria: {{ acceptance_criteria }}",
                    "variables": [
                        {"name": "task_description", "required": True},
                        {"name": "acceptance_criteria", "required": False, "default": ""},
                        {"name": "check_command", "required": False, "default": "true"},
                    ],
                    "checks": [{"name": "objective", "command": "{{ check_command }}"}],
                },
            )
            handler = AgentLoopHandler.__new__(AgentLoopHandler)
            handler.workspace = root

            result = AgentLoopHandler._dry_run(
                handler,
                {
                    "kind": "loops",
                    "name": "quality",
                    "values": {
                        "task_description": "build dice",
                        "check_command": "100 rolls should produce likely totals",
                    },
                },
            )

            self.assertEqual(result["commands"], ["true"])
            self.assertIn("100 rolls should produce likely totals", result["prompt"])

    def test_web_rerun_uses_original_loop_and_values(self) -> None:
        with self.make_workspace() as temp:
            root = Path(temp)
            first = load_loop(self.write_loop(root, "first", {"prompt": "echo {{ task_description }}"}), root)
            first_result = execute_loop(first, {"task_description": "again"})
            assert not isinstance(first_result, DryRunResult)
            handler = AgentLoopHandler.__new__(AgentLoopHandler)
            handler.workspace = root

            response = AgentLoopHandler._rerun(handler, first_result.run_id, {})

            self.assertEqual(response["loop"], "first")
            deadline = time.time() + 5
            reruns = []
            while time.time() < deadline:
                reruns = [run for run in AgentLoopHandler._runs(handler, loop_name="first") if run["run_id"] != first_result.run_id]
                if reruns and reruns[0]["status"] == "passed":
                    break
                time.sleep(0.05)
            self.assertTrue(reruns)
            rerun_detail = AgentLoopHandler._run_detail(handler, reruns[0]["run_id"])
            adapter_log = next(log for log in rerun_detail["logs"] if log["name"] == "adapter_iteration_001.log")
            self.assertIn("again", adapter_log["content"])

    def test_web_start_long_run_returns_real_run_id_for_stop(self) -> None:
        with self.make_workspace() as temp:
            root = Path(temp)
            self.write_loop(root, "slow-web", {"prompt": "python3 -c 'import time; time.sleep(30)'"})
            handler = AgentLoopHandler.__new__(AgentLoopHandler)
            handler.workspace = root

            response = AgentLoopHandler._start_run(
                handler,
                {"kind": "loops", "name": "slow-web", "values": {"task_description": "x"}},
            )

            self.assertNotEqual(response["run_id"], "pending")
            request_stop(response["run_id"], root)
            deadline = time.time() + 5
            metadata = {}
            while time.time() < deadline:
                metadata = AgentLoopHandler._run_metadata(handler, find_run(response["run_id"], root))
                if metadata["status"] == "stopped":
                    break
                time.sleep(0.05)
            self.assertEqual(metadata["status"], "stopped")

    def test_web_run_metadata_marks_stale_stop_requested_run_stopped(self) -> None:
        with self.make_workspace() as temp:
            root = Path(temp)
            run_dir = root / ".agentloop-runs" / "manual-run"
            run_dir.mkdir(parents=True)
            (run_dir / "run.yaml").write_text("run_id: manual-run\nloop: Test\nstatus: running\n", encoding="utf-8")
            (run_dir / "STOP").write_text("stop requested\n", encoding="utf-8")
            handler = AgentLoopHandler.__new__(AgentLoopHandler)
            handler.workspace = root

            metadata = AgentLoopHandler._run_metadata(handler, run_dir)

            self.assertEqual(metadata["status"], "stopped")
            self.assertEqual(metadata["reason"], "stop requested")

    def test_web_template_run_materializes_loop_config(self) -> None:
        with self.make_workspace() as temp:
            root = Path(temp)
            (root / ".agentloop" / "templates").mkdir(parents=True)
            template_path = root / ".agentloop" / "templates" / "starter.yaml"
            template_path.write_text(
                yaml.safe_dump(
                    {
                        "name": "starter",
                        "adapter": "shell",
                        "prompt": "true",
                        "variables": [{"name": "task_description", "required": True}],
                        "checks": [{"name": "ok", "command": "true"}],
                    },
                    sort_keys=False,
                ),
                encoding="utf-8",
            )
            handler = AgentLoopHandler.__new__(AgentLoopHandler)
            handler.workspace = root

            response = AgentLoopHandler._start_run(
                handler,
                {
                    "kind": "templates",
                    "name": "starter",
                    "path": str(template_path),
                    "values": {"task_description": "from template"},
                },
            )

            self.assertEqual(response["loop"], "starter")
            loop_path = root / ".agentloop" / "loops" / "starter.yaml"
            self.assertTrue(loop_path.exists())
            data = yaml.safe_load(loop_path.read_text(encoding="utf-8"))
            self.assertEqual(data["template_source"], "starter")


if __name__ == "__main__":
    unittest.main()
