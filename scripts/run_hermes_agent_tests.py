from pathlib import Path
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[1]
HERMES_AGENT_DIR = ROOT / "hermes-agent"
PYTEST_BIN = ROOT / ".venv" / "bin" / "pytest"


def main() -> int:
    test_args = ["tests/backend/", "tests/tools/", "-v", "--tb=no"]
    if PYTEST_BIN.exists():
        cmd = [str(PYTEST_BIN), *test_args]
    else:
        cmd = [sys.executable, "-m", "pytest", *test_args]

    try:
        result = subprocess.run(
            cmd,
            cwd=HERMES_AGENT_DIR,
            capture_output=True,
            text=True,
            timeout=120,
        )
    except subprocess.TimeoutExpired as exc:
        if exc.stdout:
            print(exc.stdout)
        if exc.stderr:
            print(exc.stderr, file=sys.stderr)
        print("TIMEOUT", file=sys.stderr)
        return 124

    if result.stdout:
        print(result.stdout, end="")
    if result.stderr:
        print(result.stderr, file=sys.stderr, end="")
    return result.returncode


if __name__ == "__main__":
    raise SystemExit(main())
