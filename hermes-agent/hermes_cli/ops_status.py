"""Operational runtime status command for Hermes CLI."""

from __future__ import annotations

import json
import os
import shutil
import socket
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from urllib import error, request

from hermes_cli.colors import Colors, color
from hermes_cli.config import get_env_value, get_hermes_home
from hermes_cli.gateway import (
    _gateway_doctor_report,
    _read_active_profile_name,
    get_authoritative_gateway_state_path,
    is_macos,
)
from hermes_constants import get_default_hermes_root

PROJECT_ROOT = Path(__file__).parent.parent.resolve()
WORKSPACE_ROOT = PROJECT_ROOT.parent if (PROJECT_ROOT.parent / "docker-compose.dev.yml").exists() else PROJECT_ROOT
DEV_COMPOSE_FILE = WORKSPACE_ROOT / "docker-compose.dev.yml"
DEV_ENV_FILE = WORKSPACE_ROOT / ".env.dev"

STATUS_OK = "ok"
STATUS_WARN = "warn"
STATUS_FAIL = "fail"
STATUS_INFO = "info"
STATUS_SKIP = "skip"


@dataclass
class CheckResult:
    label: str
    status: str
    summary: str
    details: list[str] = field(default_factory=list)
    critical: bool = False


@dataclass
class Section:
    title: str
    checks: list[CheckResult] = field(default_factory=list)


def _boolish(value: str | None) -> bool:
    return str(value or "").strip().lower() in {"1", "true", "yes", "on"}


def _status_icon(status: str) -> str:
    if status == STATUS_OK:
        return color("✓", Colors.GREEN)
    if status == STATUS_WARN:
        return color("⚠", Colors.YELLOW)
    if status == STATUS_FAIL:
        return color("✗", Colors.RED)
    return color("→", Colors.CYAN)


def _label_width(sections: list[Section]) -> int:
    max_len = max((len(check.label) for section in sections for check in section.checks), default=20)
    return max(20, min(30, max_len))


def _load_env_file(path: Path) -> dict[str, str]:
    if not path.exists():
        return {}

    values: dict[str, str] = {}
    try:
        for raw_line in path.read_text(encoding="utf-8").splitlines():
            line = raw_line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            values[key.strip()] = value.strip().strip("\"'")
    except OSError:
        return {}
    return values


def _masked_preview(value: str | None) -> str:
    if not value:
        return "(not set)"
    value = value.strip()
    if len(value) <= 8:
        return "***"
    return f"{value[:4]}...{value[-4:]}"


def _run_command(cmd: list[str], *, cwd: Path | None = None, timeout: float = 5.0) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        cmd,
        cwd=str(cwd) if cwd else None,
        capture_output=True,
        text=True,
        timeout=timeout,
        check=False,
    )


def _http_probe(label: str, url: str, *, critical: bool = True, timeout: float = 3.0) -> CheckResult:
    try:
        with request.urlopen(url, timeout=timeout) as response:
            code = getattr(response, "status", 200)
            if 200 <= code < 400:
                return CheckResult(label, STATUS_OK, f"HTTP {code}", [url], critical=critical)
            return CheckResult(label, STATUS_FAIL, f"HTTP {code}", [url], critical=critical)
    except error.HTTPError as exc:
        return CheckResult(label, STATUS_FAIL if critical else STATUS_WARN, f"HTTP {exc.code}", [url], critical=critical)
    except Exception as exc:
        return CheckResult(label, STATUS_FAIL if critical else STATUS_WARN, str(exc), [url], critical=critical)


def _socket_connect(host: str, port: int, *, timeout: float = 2.0) -> tuple[bool, str]:
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True, f"{host}:{port} reachable"
    except OSError as exc:
        return False, str(exc)


def _redis_probe(host: str, port: int, *, critical: bool = True, timeout: float = 2.0) -> CheckResult:
    try:
        with socket.create_connection((host, port), timeout=timeout) as sock:
            sock.sendall(b"*1\r\n$4\r\nPING\r\n")
            reply = sock.recv(16)
        if reply.startswith(b"+PONG"):
            return CheckResult("Redis health", STATUS_OK, f"PONG on {host}:{port}", critical=critical)
        return CheckResult("Redis health", STATUS_FAIL, f"unexpected reply: {reply!r}", critical=critical)
    except OSError as exc:
        return CheckResult("Redis health", STATUS_FAIL if critical else STATUS_WARN, str(exc), critical=critical)


def _postgres_probe(host: str, port: int, database: str, user: str, *, critical: bool = True) -> CheckResult:
    pg_isready = shutil.which("pg_isready")
    if pg_isready:
        result = _run_command([
            pg_isready,
            "-h",
            host,
            "-p",
            str(port),
            "-d",
            database,
            "-U",
            user,
        ], timeout=5.0)
        if result.returncode == 0:
            return CheckResult("Postgres/TimescaleDB health", STATUS_OK, result.stdout.strip() or f"{host}:{port} ready", critical=critical)
        detail = (result.stderr or result.stdout or f"exit {result.returncode}").strip()
        return CheckResult("Postgres/TimescaleDB health", STATUS_FAIL if critical else STATUS_WARN, detail, critical=critical)

    ok, detail = _socket_connect(host, port)
    return CheckResult(
        "Postgres/TimescaleDB health",
        STATUS_OK if ok else (STATUS_FAIL if critical else STATUS_WARN),
        detail,
        critical=critical,
    )


def _normalize_trading_mode(raw_mode: str | None, *, live_enabled: bool, ack_present: bool, paper_mode: bool) -> str:
    mode = str(raw_mode or "").strip().lower().replace("_", "-")
    if mode in {"disabled", "paper", "approval-required", "live"}:
        return mode
    if mode == "approval required":
        return "approval-required"
    if live_enabled and ack_present:
        return "live"
    if paper_mode:
        return "paper"
    return "disabled"


def _profile_name_for_home(home: Path) -> str:
    home = home.resolve()
    default_root = get_default_hermes_root().resolve()
    profiles_root = default_root / "profiles"
    if home == default_root:
        active = _read_active_profile_name().strip()
        return active or "default"
    try:
        rel = home.relative_to(profiles_root)
    except ValueError:
        return home.name
    return rel.parts[0] if rel.parts else "default"


def _parse_profile_list(value: str | None) -> set[str]:
    return {item.strip() for item in str(value or "").split(",") if item.strip()}


def _current_profile_name() -> str:
    return _profile_name_for_home(get_hermes_home())


def _docker_compose_rows() -> tuple[CheckResult, dict[str, dict[str, str]]]:
    if not DEV_COMPOSE_FILE.exists():
        return CheckResult("Dev stack status", STATUS_SKIP, "docker-compose.dev.yml not found"), {}
    if not shutil.which("docker"):
        return CheckResult("Dev stack status", STATUS_WARN, "docker not available"), {}

    cmd = ["docker", "compose", "-f", str(DEV_COMPOSE_FILE)]
    if DEV_ENV_FILE.exists():
        cmd.extend(["--env-file", str(DEV_ENV_FILE)])
    cmd.extend(["ps", "--format", "json"])
    result = _run_command(cmd, cwd=WORKSPACE_ROOT, timeout=10.0)
    if result.returncode != 0:
        detail = (result.stderr or result.stdout or f"exit {result.returncode}").strip()
        return CheckResult("Dev stack status", STATUS_WARN, detail), {}

    raw = result.stdout.strip()
    if not raw:
        return CheckResult("Dev stack status", STATUS_WARN, "no compose services found"), {}

    rows: list[dict[str, Any]]
    try:
        parsed = json.loads(raw)
        if isinstance(parsed, list):
            rows = parsed
        else:
            rows = [parsed]
    except json.JSONDecodeError:
        rows = []
        for line in raw.splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                item = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(item, dict):
                rows.append(item)

    core_services = {"timescaledb", "redis", "litellm", "dashboard", "api", "web", "mission-control"}
    indexed: dict[str, dict[str, str]] = {}
    unhealthy: list[str] = []
    for row in rows:
        service = str(row.get("Service") or row.get("Name") or "").strip()
        if not service:
            continue
        state = str(row.get("State") or row.get("Status") or "unknown").strip().lower()
        health = str(row.get("Health") or "").strip().lower()
        indexed[service] = {
            "state": state,
            "health": health,
            "name": str(row.get("Name") or service),
        }
        if service in core_services:
            bad_health = health and health not in {"healthy", "running"}
            if state not in {"running", "restarting"} or bad_health:
                unhealthy.append(f"{service} ({state or 'unknown'}{f', {health}' if health else ''})")

    missing = sorted(core_services - set(indexed))
    if missing:
        unhealthy.extend(f"{service} (missing)" for service in missing)

    if unhealthy:
        return CheckResult(
            "Dev stack status",
            STATUS_WARN,
            f"{len(core_services) - len(unhealthy)}/{len(core_services)} core services healthy",
            unhealthy,
        ), indexed

    return CheckResult(
        "Dev stack status",
        STATUS_OK,
        f"{len(core_services)}/{len(core_services)} core services healthy",
        [
            f"{name}: {info['state']}{f' ({info['health']})' if info['health'] else ''}"
            for name, info in sorted(indexed.items())
            if name in core_services
        ],
    ), indexed


def _launchd_related_services() -> CheckResult:
    if not is_macos():
        return CheckResult("Loaded launchd services", STATUS_SKIP, "launchd checks are macOS-only")

    launch_agents = Path.home() / "Library" / "LaunchAgents"
    if not launch_agents.exists():
        return CheckResult("Loaded launchd services", STATUS_INFO, "no Hermes launchd plists found")

    details: list[str] = []
    loaded_count = 0
    for plist in sorted(launch_agents.glob("ai.hermes*.plist")):
        label = plist.stem
        result = _run_command(["launchctl", "list", label], timeout=5.0)
        loaded = result.returncode == 0
        if loaded:
            loaded_count += 1
        details.append(f"{label}: {'loaded' if loaded else 'not loaded'}")

    if not details:
        return CheckResult("Loaded launchd services", STATUS_INFO, "no Hermes launchd plists found")

    return CheckResult(
        "Loaded launchd services",
        STATUS_OK if loaded_count else STATUS_WARN,
        f"{loaded_count}/{len(details)} loaded",
        details,
    )


def _gateway_pid_rows() -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for item in _gateway_doctor_report().get("services", []):
        home = Path(str(item["home"]))
        pid_path = home / "gateway.pid"
        if not pid_path.exists():
            continue
        try:
            raw = pid_path.read_text(encoding="utf-8").strip()
            payload = json.loads(raw) if raw.startswith("{") else {"pid": int(raw)}
        except Exception:
            payload = {}
        pid = payload.get("pid")
        alive = False
        if pid is not None:
            try:
                os.kill(int(pid), 0)
                alive = True
            except Exception:
                alive = False
        rows.append({
            "profile": item["profile"],
            "path": str(pid_path),
            "pid": pid,
            "alive": alive,
        })
    return rows


def _stale_lock_rows() -> list[dict[str, Any]]:
    try:
        from gateway.status import _get_lock_dir
    except Exception:
        return []

    lock_dir = _get_lock_dir()
    rows: list[dict[str, Any]] = []
    if not lock_dir.exists():
        return rows

    for lock_file in sorted(lock_dir.glob("*.lock")):
        try:
            payload = json.loads(lock_file.read_text(encoding="utf-8"))
        except Exception:
            rows.append({"path": str(lock_file), "pid": None, "alive": False, "reason": "invalid json"})
            continue
        pid = payload.get("pid")
        alive = False
        if pid is not None:
            try:
                os.kill(int(pid), 0)
                alive = True
            except Exception:
                alive = False
        rows.append({
            "path": str(lock_file),
            "pid": pid,
            "alive": alive,
            "reason": payload.get("scope") or "lock",
        })
    return rows


def _latest_smoke_artifact(platform: str) -> CheckResult:
    roots = [WORKSPACE_ROOT / "reports", WORKSPACE_ROOT / "logs", WORKSPACE_ROOT / "cron" / "output"]
    patterns = [
        f"*{platform}*smoke*",
        f"*smoke*{platform}*",
        f"*{platform}*health*",
        f"*{platform}*test*",
    ]

    matches: list[Path] = []
    for root in roots:
        if not root.exists():
            continue
        for pattern in patterns:
            matches.extend(path for path in root.rglob(pattern) if path.is_file())

    label = f"Last {platform.capitalize()} smoke test"
    if not matches:
        return CheckResult(label, STATUS_INFO, "not available")

    latest = max(matches, key=lambda path: path.stat().st_mtime)
    summary = "artifact found"
    try:
        text = latest.read_text(encoding="utf-8", errors="ignore")[:1000].lower()
        if any(word in text for word in ("success", "passed", '"ok"', "smoke ok")):
            summary = "passed"
        elif any(word in text for word in ("fail", "error", "timeout")):
            summary = "failed"
    except OSError:
        pass

    return CheckResult(label, STATUS_OK if summary == "passed" else STATUS_WARN, summary, [str(latest)])


def _cron_job_check(job: dict[str, Any], label: str) -> CheckResult:
    if not job:
        return CheckResult(label, STATUS_WARN, "job not found")

    enabled = bool(job.get("enabled", True))
    state = str(job.get("state") or ("scheduled" if enabled else "disabled"))
    last_status = job.get("last_status")
    last_run = job.get("last_run_at")
    next_run = job.get("next_run_at")
    details: list[str] = []
    if last_run:
        details.append(f"last run: {last_run}")
    if next_run:
        details.append(f"next run: {next_run}")
    if job.get("last_error"):
        details.append(f"last error: {job['last_error']}")

    if not enabled:
        return CheckResult(label, STATUS_WARN, f"{state} (disabled)", details)
    if last_status == "error":
        return CheckResult(label, STATUS_WARN, f"{state} (last status: error)", details)
    if last_status == "ok":
        return CheckResult(label, STATUS_OK, f"{state} (last status: ok)", details)
    return CheckResult(label, STATUS_WARN, f"{state} (never run yet)", details)


def _platform_runtime_check(
    *,
    platform: str,
    token_env: str,
    enabled_profiles_env: str,
    current_profile: str,
    authoritative_platforms: dict[str, Any],
    gateway_running: bool,
) -> CheckResult:
    label = f"{platform.capitalize()} connection"
    token = get_env_value(token_env) or os.getenv(token_env, "")
    enabled_profiles = _parse_profile_list(get_env_value(enabled_profiles_env) or os.getenv(enabled_profiles_env, ""))
    explicitly_enabled = bool(enabled_profiles) and (current_profile in enabled_profiles or "*" in enabled_profiles)
    runtime = authoritative_platforms.get(platform) if isinstance(authoritative_platforms, dict) else None
    runtime_state = str((runtime or {}).get("state") or "").strip().lower()
    runtime_error = str((runtime or {}).get("error_message") or (runtime or {}).get("error_code") or "").strip()

    if explicitly_enabled and not token:
        return CheckResult(label, STATUS_FAIL, f"enabled for profile '{current_profile}' but token is missing", critical=True)
    if not token:
        return CheckResult(label, STATUS_INFO, "not configured")
    if runtime_state in {"running", "connected", "healthy", "ok"}:
        return CheckResult(label, STATUS_OK, runtime_state, [f"token: {_masked_preview(token)}"], critical=True)
    if runtime_state in {"fatal", "failed", "error", "startup-failed"}:
        details = [f"token: {_masked_preview(token)}"]
        if runtime_error:
            details.append(runtime_error)
        return CheckResult(label, STATUS_FAIL, runtime_state or "fatal", details, critical=True)
    if gateway_running:
        details = [f"token: {_masked_preview(token)}"]
        if runtime_state:
            details.append(f"runtime state: {runtime_state}")
        if runtime_error:
            details.append(runtime_error)
        return CheckResult(label, STATUS_WARN, runtime_state or "configured, awaiting runtime state", details, critical=True)
    return CheckResult(label, STATUS_FAIL, "configured, but gateway is not running", [f"token: {_masked_preview(token)}"], critical=True)


def build_ops_status_report() -> list[Section]:
    dev_env = _load_env_file(DEV_ENV_FILE)
    current_home = get_hermes_home().resolve()
    current_profile = _current_profile_name()
    gateway_report = _gateway_doctor_report()
    authoritative_state_path = Path(str(gateway_report.get("authoritative_state_path") or get_authoritative_gateway_state_path()))
    authoritative_state = gateway_report.get("authoritative_state") or {}
    authoritative_platforms = authoritative_state.get("platforms") or {}
    current_service = next((row for row in gateway_report.get("services", []) if row.get("authoritative")), None) or {}
    gateway_running = bool(current_service.get("runtime_pid_alive"))

    def port_value(name: str, default: str) -> int:
        raw = dev_env.get(name) or os.getenv(name) or default
        return int(str(raw).strip())

    dashboard_port = port_value("HERMES_DASHBOARD_PORT", "9119")
    api_port = port_value("HERMES_API_PORT", "8000")
    web_port = port_value("HERMES_WEB_PORT", "3000")
    mission_port = port_value("HERMES_MISSION_CONTROL_PORT", "3100")
    litellm_port = port_value("LITELLM_PORT", "4000")
    redis_port = port_value("HERMES_REDIS_PORT", os.getenv("REDIS_PORT") or "6379")
    pg_port = port_value("HERMES_TIMESCALE_PORT", "5433")

    compose_check, compose_rows = _docker_compose_rows()

    runtime_section = Section("Profile & runtime", checks=[
        CheckResult("Active profile", STATUS_INFO, current_profile),
        CheckResult("Hermes home", STATUS_INFO, str(current_home)),
        CheckResult(
            "Gateway service status",
            STATUS_OK if gateway_running else STATUS_FAIL,
            current_service.get("runtime_state") or ("running" if gateway_running else "stopped"),
            [
                f"launchd loaded: {current_service.get('loaded')}",
                f"runtime pid: {current_service.get('runtime_pid') or '-'}",
            ],
            critical=bool(get_env_value("SLACK_BOT_TOKEN") or get_env_value("TELEGRAM_BOT_TOKEN") or get_env_value("SLACK_ENABLED_PROFILES") or get_env_value("TELEGRAM_ENABLED_PROFILES")),
        ),
        CheckResult(
            "Authoritative gateway_state",
            STATUS_INFO,
            str(authoritative_state_path),
            [json.dumps(authoritative_state, sort_keys=True) if authoritative_state else "(missing)"],
        ),
        CheckResult(
            "Last known trading mode",
            STATUS_INFO,
            _normalize_trading_mode(
                get_env_value("HERMES_TRADING_MODE") or os.getenv("HERMES_TRADING_MODE"),
                live_enabled=_boolish(get_env_value("HERMES_ENABLE_LIVE_TRADING") or os.getenv("HERMES_ENABLE_LIVE_TRADING")),
                ack_present=bool(get_env_value("HERMES_LIVE_TRADING_ACK") or os.getenv("HERMES_LIVE_TRADING_ACK")),
                paper_mode=_boolish(get_env_value("HERMES_PAPER_MODE") or os.getenv("HERMES_PAPER_MODE")),
            ),
        ),
    ])

    stack_section = Section("Dev stack", checks=[
        compose_check,
        _http_probe("Dashboard health", f"http://127.0.0.1:{dashboard_port}/api/status", critical=True),
        _http_probe("API health", f"http://127.0.0.1:{api_port}/api/v1/healthz", critical=True),
        _http_probe("Web health", f"http://127.0.0.1:{web_port}", critical=True),
        _http_probe("Mission Control health", f"http://127.0.0.1:{mission_port}", critical=True),
        _http_probe("LiteLLM health", f"http://127.0.0.1:{litellm_port}/health/liveliness", critical=True),
    ])

    minio_configured = any(
        key.startswith("MINIO_") and (get_env_value(key) or os.getenv(key))
        for key in os.environ.keys()
    ) or "minio" in {name.lower() for name in compose_rows.keys()}
    minio_check = CheckResult("MinIO health", STATUS_INFO, "not configured")
    if minio_configured:
        minio_host = get_env_value("MINIO_HOST") or os.getenv("MINIO_HOST") or "127.0.0.1"
        minio_port = int(get_env_value("MINIO_PORT") or os.getenv("MINIO_PORT") or 9000)
        ok, detail = _socket_connect(minio_host, minio_port)
        minio_check = CheckResult("MinIO health", STATUS_OK if ok else STATUS_WARN, detail)

    data_section = Section("Data stores", checks=[
        _redis_probe(os.getenv("REDIS_HOST", "127.0.0.1"), redis_port, critical=True),
        _postgres_probe(
            os.getenv("PGHOST", "127.0.0.1"),
            pg_port,
            os.getenv("PGDATABASE", os.getenv("HERMES_TIMESCALE_DB", "hermes_trading")),
            os.getenv("PGUSER", os.getenv("HERMES_TIMESCALE_USER", "hermes")),
            critical=True,
        ),
        minio_check,
    ])

    pid_rows = _gateway_pid_rows()
    duplicate_details: list[str] = []
    loaded_identity_conflicts = gateway_report.get("loaded_identity_conflicts") or []
    for item in loaded_identity_conflicts:
        duplicate_details.append(
            f"{item['resource']} shared by {', '.join(item['loaded_profiles'])} (fingerprint {item['fingerprint']})"
        )
    for row in gateway_report.get("services", []):
        if row.get("stale_state"):
            duplicate_details.append(f"stale state: {row['state_path']} (pid {row['runtime_pid']})")
    for row in pid_rows:
        if not row["alive"]:
            duplicate_details.append(f"stale pid file: {row['path']} (pid {row['pid'] or '-'})")
    if len([row for row in pid_rows if row["alive"]]) > 1 and not duplicate_details:
        duplicate_details.append("multiple gateway processes are running across profiles")

    duplicate_process_check = CheckResult(
        "Duplicate/stale gateway processes",
        STATUS_FAIL if duplicate_details else STATUS_OK,
        "issues detected" if duplicate_details else "none detected",
        duplicate_details,
        critical=bool(duplicate_details),
    )

    lock_rows = _stale_lock_rows()
    stale_lock_details = [f"{row['path']} (pid {row['pid'] or '-'}, {row['reason']})" for row in lock_rows if not row["alive"]]
    stale_lock_check = CheckResult(
        "Stale lock files",
        STATUS_WARN if stale_lock_details else STATUS_OK,
        f"{len(stale_lock_details)} stale" if stale_lock_details else "none detected",
        stale_lock_details,
    )

    messaging_section = Section("Gateway & messaging", checks=[
        _platform_runtime_check(
            platform="telegram",
            token_env="TELEGRAM_BOT_TOKEN",
            enabled_profiles_env="TELEGRAM_ENABLED_PROFILES",
            current_profile=current_profile,
            authoritative_platforms=authoritative_platforms,
            gateway_running=gateway_running,
        ),
        _platform_runtime_check(
            platform="slack",
            token_env="SLACK_BOT_TOKEN",
            enabled_profiles_env="SLACK_ENABLED_PROFILES",
            current_profile=current_profile,
            authoritative_platforms=authoritative_platforms,
            gateway_running=gateway_running,
        ),
        _launchd_related_services(),
        duplicate_process_check,
        stale_lock_check,
        _latest_smoke_artifact("telegram"),
        _latest_smoke_artifact("slack"),
    ])

    cron_jobs_path = WORKSPACE_ROOT / "cron" / "jobs.json"
    jobs_data: list[dict[str, Any]] = []
    if cron_jobs_path.exists():
        try:
            raw_jobs = json.loads(cron_jobs_path.read_text(encoding="utf-8"))
            if isinstance(raw_jobs, dict):
                jobs_data = raw_jobs.get("jobs", []) or []
        except Exception:
            jobs_data = []

    drawdown_job = next((job for job in jobs_data if job.get("name") == "drawdown-guard" or job.get("script") == "drawdown_guard.py"), {})
    whale_job = next((job for job in jobs_data if job.get("name") == "whale-tracker" or job.get("script") == "whale_tracker.py"), {})
    cron_section = Section("Cron", checks=[
        _cron_job_check(drawdown_job, "Drawdown guard"),
        _cron_job_check(whale_job, "Whale tracker"),
    ])

    return [runtime_section, stack_section, data_section, messaging_section, cron_section]


def _render_report(sections: list[Section]) -> None:
    label_width = _label_width(sections)
    print()
    print(color("┌─────────────────────────────────────────────────────────┐", Colors.CYAN))
    print(color("│              ⚕ Hermes Ops Status                       │", Colors.CYAN))
    print(color("└─────────────────────────────────────────────────────────┘", Colors.CYAN))

    for section in sections:
        print()
        print(color(f"◆ {section.title}", Colors.CYAN, Colors.BOLD))
        for check in section.checks:
            print(f"  {_status_icon(check.status)} {check.label:<{label_width}} {check.summary}")
            for detail in check.details:
                print(f"    {color('→', Colors.CYAN)} {detail}")

    critical_failures = [check for section in sections for check in section.checks if check.critical and check.status == STATUS_FAIL]
    warnings = [check for section in sections for check in section.checks if check.status == STATUS_WARN]

    print()
    divider_color = Colors.RED if critical_failures else (Colors.YELLOW if warnings else Colors.GREEN)
    print(color("─" * 60, divider_color))
    if critical_failures:
        print(color(f"  Critical issues detected: {len(critical_failures)} critical, {len(warnings)} warnings", Colors.RED, Colors.BOLD))
    elif warnings:
        print(color(f"  Runtime healthy with warnings: {len(warnings)}", Colors.YELLOW, Colors.BOLD))
    else:
        print(color("  All critical runtime checks passed!", Colors.GREEN, Colors.BOLD))
    print()


def show_ops_status(args) -> int:
    """Show the Hermes operational runtime status report."""
    sections = build_ops_status_report()
    _render_report(sections)
    critical_failures = [check for section in sections for check in section.checks if check.critical and check.status == STATUS_FAIL]
    return 1 if critical_failures else 0