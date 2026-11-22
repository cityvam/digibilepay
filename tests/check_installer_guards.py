#!/usr/bin/env python3
"""Safety checks: installers must refuse to run without a verified application root."""
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SHELL_SCRIPTS = (
    "digitalpay-setup.sh", "install-all.sh", "server-run.sh",
    "backend/security/install.sh", "backend/core/install.sh",
    "backend/contracts/install.sh", "backend/ops/install.sh",
    "backend/enterprise/install.sh", "backend/tenancy/install.sh",
)


def run(command, env):
    return subprocess.run(
        command, cwd=ROOT, env=env, text=True,
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=10
    )


def main():
    env = os.environ.copy()
    env.pop("DIGIBILEPAY_ROOT", None)
    env.pop("ROOT", None)

    for script in SHELL_SCRIPTS:
        result = run(["bash", str(ROOT / script)], env)
        assert result.returncode != 0, f"{script} should refuse an unspecified project root"
        assert "DIGIBILEPAY_ROOT" in result.stdout or "مسیر پروژه" in result.stdout, result.stdout

    result = run([sys.executable, str(ROOT / "setup-web.py")], env)
    assert result.returncode != 0, "setup-web.py must refuse an unspecified project root"
    assert "مسیر پروژه" in result.stdout or "مسیر پروژه" in result.stderr, result.stdout

    env["DIGIBILEPAY_ROOT"] = str(ROOT / "does-not-exist")
    for script in SHELL_SCRIPTS:
        result = run(["bash", str(ROOT / script)], env)
        assert result.returncode == 2, (
            f"{script} should refuse an invalid project root; "
            f"exit={result.returncode}, output={result.stdout}"
        )

    result = run([sys.executable, str(ROOT / "setup-web.py")], env)
    assert result.returncode != 0, "setup-web.py must refuse an invalid project root"

    print("PASS: all installer entry points refuse missing or invalid project roots")


if __name__ == "__main__":
    main()
