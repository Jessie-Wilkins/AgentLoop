from __future__ import annotations

import subprocess
import tempfile
import unittest
from pathlib import Path

import yaml

from agentloop.core.engine import DryRunResult, execute_loop
from agentloop.core.rendering import RenderError, render_loop
from agentloop.storage.configs import load_loop


class AgentLoopTests(unittest.TestCase):
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
                "prompt_iteration_001.txt",
                "adapter_iteration_001.log",
                "checks_iteration_001.log",
                "summary.json",
                "final_report.md",
            ]:
                self.assertTrue((result.run_dir / name).exists(), name)

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

    def test_blocked_output_stops_run(self) -> None:
        with self.make_workspace() as temp:
            root = Path(temp)
            path = self.write_loop(root, "blocked", {"prompt": "echo 'BLOCKED: missing data'"})
            loop = load_loop(path, root)
            result = execute_loop(loop, {"task_description": "x"})
            assert not isinstance(result, DryRunResult)
            self.assertEqual(result.status, "blocked")

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


if __name__ == "__main__":
    unittest.main()
