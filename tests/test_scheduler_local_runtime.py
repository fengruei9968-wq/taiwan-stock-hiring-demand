#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from __future__ import annotations

import os
import subprocess
import sys
import tempfile
import textwrap
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class SchedulerLocalRuntimeTests(unittest.TestCase):
    def test_launcher_template_uses_internal_disk_scheduler_venv(self) -> None:
        template = (ROOT / "scheduler_templates" / "run_hiring_demand_launcher.sh.template").read_text(
            encoding="utf-8"
        )

        self.assertIn("LOCAL_VENV_PYTHON=\"__LOCAL_VENV_PYTHON__\"", template)
        self.assertIn("export HIRING_PYTHON=\"$LOCAL_VENV_PYTHON\"", template)
        self.assertNotIn("HIRING_DIR/venv/bin/python3", template)

    def test_render_only_install_outputs_launcher_with_local_venv(self) -> None:
        with tempfile.TemporaryDirectory(dir=ROOT / "_test_runtime") as tmp:
            render_dir = Path(tmp) / "rendered"
            local_dir = Path(tmp) / "HiringDemandLauncher"
            env = os.environ.copy()
            env["HIRING_SCHEDULER_RENDER_DIR"] = str(render_dir)
            env["HIRING_LOCAL_LAUNCHER_DIR"] = str(local_dir)
            env["HIRING_LOCAL_LAUNCHER_PATH"] = str(local_dir / "run_hiring_demand_launcher.sh")
            env["HIRING_LOCAL_MAIN_WRAPPER_PATH"] = str(local_dir / "run_hiring_demand.sh")
            env["HIRING_LOCAL_PROBE_WRAPPER_PATH"] = str(local_dir / "run_telegram_recipient_probe.sh")
            env["HIRING_LOCAL_VENV_DIR"] = str(local_dir / "venv")
            proc = subprocess.run(
                ["bash", "install_scheduler.sh", "--render-only", "install"],
                cwd=ROOT,
                env=env,
                text=True,
                capture_output=True,
            )

            self.assertEqual(proc.returncode, 0, proc.stderr + proc.stdout)
            rendered_launcher = render_dir / "run_hiring_demand_launcher.sh"
            text = rendered_launcher.read_text(encoding="utf-8")
            self.assertIn(f'LOCAL_VENV_PYTHON="{local_dir / "venv" / "bin" / "python3"}"', text)
            self.assertIn(f'LOCAL_MAIN_WRAPPER="{local_dir / "run_hiring_demand.sh"}"', text)
            self.assertIn(f'LOCAL_PROBE_WRAPPER="{local_dir / "run_telegram_recipient_probe.sh"}"', text)
            self.assertIn('export HIRING_PYTHON="$LOCAL_VENV_PYTHON"', text)
            self.assertIn('export HIRING_SCRIPT_DIR="$HIRING_DIR"', text)
            self.assertNotIn('exec "$HIRING_DIR/run_hiring_demand.sh"', text)
            self.assertTrue((render_dir / "run_hiring_demand.sh").exists())
            self.assertTrue((render_dir / "run_telegram_recipient_probe.sh").exists())

    def test_wrappers_support_internal_disk_copy_with_ssd_script_dir_override(self) -> None:
        for wrapper_name in ["run_hiring_demand.sh", "run_telegram_recipient_probe.sh"]:
            text = (ROOT / wrapper_name).read_text(encoding="utf-8")
            self.assertIn("SCRIPT_SELF_DIR=", text)
            self.assertIn('SCRIPT_DIR="${HIRING_SCRIPT_DIR:-$SCRIPT_SELF_DIR}"', text)

    def test_scheduler_doctor_fails_when_local_scheduler_venv_is_missing(self) -> None:
        with tempfile.TemporaryDirectory(dir=ROOT / "_test_runtime") as tmp:
            output_dir = Path(tmp) / "out"
            missing_venv = Path(tmp) / "HiringDemandLauncher" / "venv"
            env = os.environ.copy()
            env["HIRING_LOCAL_VENV_DIR"] = str(missing_venv)
            proc = subprocess.run(
                [
                    sys.executable,
                    "check_scheduler_installation.py",
                    "--root",
                    str(ROOT),
                    "--output-dir",
                    str(output_dir),
                ],
                cwd=ROOT,
                env=env,
                text=True,
                capture_output=True,
            )

            self.assertNotEqual(proc.returncode, 0)
            self.assertIn("local_scheduler_venv_missing", proc.stdout)

    def test_scheduler_manifest_defines_benchmark_isolation_policy(self) -> None:
        manifest = (ROOT / "manifests" / "scheduler_manifest.yaml").read_text(encoding="utf-8")

        self.assertIn("benchmark_isolation:", manifest)
        self.assertIn("main_launchagent_label: com.hiring.demand.updater", manifest)
        self.assertIn("probe_launchagent_label: com.hiring.telegram.recipient.probe", manifest)
        self.assertIn("preflight_checker: python3 check_scheduler_installation.py --root . --benchmark-preflight", manifest)
        self.assertIn("restore_checker: python3 check_scheduler_installation.py --root . --benchmark-restore-check", manifest)
        self.assertIn("invalid_if_second_crawler_starts: true", manifest)

    def test_benchmark_preflight_checker_fails_when_main_launchagent_or_crawler_is_active(self) -> None:
        with tempfile.TemporaryDirectory(dir=ROOT / "_test_runtime") as tmp:
            tmp_path = Path(tmp)
            fake_bin = tmp_path / "bin"
            fake_bin.mkdir()
            (fake_bin / "launchctl").write_text(
                "#!/bin/sh\n"
                "if [ \"$1\" = \"print\" ]; then\n"
                "  echo 'program = /Users/chiufengjui/Library/Application Support/HiringDemandLauncher/run_hiring_demand_launcher.sh'\n"
                "  echo 'arguments = { run-main }'\n"
                "  exit 0\n"
                "fi\n"
                "exit 0\n",
                encoding="utf-8",
            )
            (fake_bin / "ps").write_text(
                "#!/bin/sh\n"
                "echo '123 1 S 00:10 /bin/bash /Users/chiufengjui/Library/Application Support/HiringDemandLauncher/run_hiring_demand.sh'\n",
                encoding="utf-8",
            )
            os.chmod(fake_bin / "launchctl", 0o755)
            os.chmod(fake_bin / "ps", 0o755)

            env = os.environ.copy()
            env["PATH"] = f"{fake_bin}:{env.get('PATH', '')}"
            proc = subprocess.run(
                [
                    sys.executable,
                    "check_scheduler_installation.py",
                    "--root",
                    str(ROOT),
                    "--benchmark-preflight",
                ],
                cwd=ROOT,
                env=env,
                text=True,
                capture_output=True,
            )

            self.assertNotEqual(proc.returncode, 0)
            self.assertIn("benchmark_main_launchagent_loaded", proc.stdout)
            self.assertIn("benchmark_crawler_process_running", proc.stdout)

    def test_benchmark_restore_checker_passes_when_main_launchagent_points_to_local_launcher(self) -> None:
        with tempfile.TemporaryDirectory(dir=ROOT / "_test_runtime") as tmp:
            fake_bin = Path(tmp) / "bin"
            fake_bin.mkdir()
            (fake_bin / "launchctl").write_text(
                textwrap.dedent(
                    """\
                    #!/bin/sh
                    if [ "$1" = "print" ]; then
                      cat <<'EOF'
                    program = /Users/chiufengjui/Library/Application Support/HiringDemandLauncher/run_hiring_demand_launcher.sh
                    arguments = {
                      /Users/chiufengjui/Library/Application Support/HiringDemandLauncher/run_hiring_demand_launcher.sh
                      run-main
                    }
                    EOF
                      exit 0
                    fi
                    exit 0
                    """
                ),
                encoding="utf-8",
            )
            (fake_bin / "ps").write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
            os.chmod(fake_bin / "launchctl", 0o755)
            os.chmod(fake_bin / "ps", 0o755)

            env = os.environ.copy()
            env["PATH"] = f"{fake_bin}:{env.get('PATH', '')}"
            proc = subprocess.run(
                [
                    sys.executable,
                    "check_scheduler_installation.py",
                    "--root",
                    str(ROOT),
                    "--benchmark-restore-check",
                ],
                cwd=ROOT,
                env=env,
                text=True,
                capture_output=True,
            )

            self.assertEqual(proc.returncode, 0, proc.stderr + proc.stdout)
            self.assertIn('"gate_result": "PASS"', proc.stdout)
            self.assertIn("benchmark_restore_check", proc.stdout)

    def test_shell_wrappers_do_not_execute_ssd_python_scripts_as_script_paths(self) -> None:
        main_wrapper = (ROOT / "run_hiring_demand.sh").read_text(encoding="utf-8")
        probe_wrapper = (ROOT / "run_telegram_recipient_probe.sh").read_text(encoding="utf-8")

        for text in [main_wrapper, probe_wrapper]:
            self.assertIn("run_python_script()", text)
            self.assertIn("compile(script.read_text", text)
            self.assertNotIn("sys.path.insert(0, str(script.parent))", text)
            self.assertNotIn('"$PYTHON" "$PROBE_SCRIPT"', text)

        self.assertNotIn('"$PYTHON" "$MAIN_SCRIPT"', main_wrapper)
        self.assertNotIn('"$PYTHON" "$CHECKER_SCRIPT"', main_wrapper)
        self.assertNotIn('"$PYTHON" "$REPORT_SCRIPT"', main_wrapper)
        self.assertNotIn('"$PYTHON" "$REPORT_CHECKER_SCRIPT"', main_wrapper)
        self.assertNotIn('"$PYTHON" "$REPORT_RENDER_SCRIPT"', main_wrapper)
        self.assertNotIn('"$PYTHON" "$WEB_SYNC_SCRIPT"', main_wrapper)
        self.assertNotIn('"$PYTHON" "$TELEGRAM_SCRIPT"', main_wrapper)


if __name__ == "__main__":
    unittest.main()
