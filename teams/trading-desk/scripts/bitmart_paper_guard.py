#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

ROOT = Path('/Users/openclaw/.hermes/teams/trading-desk')
CONFIG_PATH = ROOT / 'PAPER_MODE.yaml'


def _normalize_url(url: str | None) -> str:
    return (url or '').strip().rstrip('/')


def _hostname(url: str | None) -> str:
    normalized = _normalize_url(url)
    if not normalized:
        return ''
    return (urlparse(normalized).hostname or '').lower()


def _manual_yaml_parse(text: str) -> dict[str, Any]:
    data: dict[str, Any] = {}
    current_list_key: str | None = None
    for raw_line in text.splitlines():
        line = raw_line.rstrip()
        if not line or line.lstrip().startswith('#'):
            continue
        stripped = line.strip()
        if stripped.startswith('- '):
            if current_list_key is None:
                continue
            data.setdefault(current_list_key, []).append(stripped[2:].strip())
            continue
        current_list_key = None
        if ':' not in stripped:
            continue
        key, value = stripped.split(':', 1)
        key = key.strip()
        value = value.strip()
        if value == '':
            current_list_key = key
            data[key] = []
        elif value.lower() == 'true':
            data[key] = True
        elif value.lower() == 'false':
            data[key] = False
        else:
            data[key] = value
    return data


def load_config() -> dict[str, Any]:
    text = CONFIG_PATH.read_text()
    try:
        import yaml  # type: ignore

        parsed = yaml.safe_load(text)
        if isinstance(parsed, dict):
            return parsed
    except Exception:
        pass
    return _manual_yaml_parse(text)


def evaluate(base_url: str, config: dict[str, Any]) -> dict[str, Any]:
    mode = str(config.get('mode', '')).strip().lower()
    expected_base_url = _normalize_url(config.get('execution_base_url', ''))
    forbidden_urls = [_normalize_url(url) for url in config.get('forbidden_live_base_urls', [])]
    forbidden_urls = [url for url in forbidden_urls if url]
    forbidden_hosts = sorted({_hostname(url) for url in forbidden_urls if _hostname(url)})

    candidate_url = _normalize_url(base_url)
    candidate_host = _hostname(candidate_url)
    reasons: list[str] = []

    if not candidate_url:
        reasons.append('Base URL is required.')

    if mode == 'paper' and candidate_url:
        if candidate_url in forbidden_urls:
            reasons.append(f'Live BitMart base URL explicitly forbidden in paper mode: {candidate_url}')
        if candidate_host in forbidden_hosts:
            reasons.append(f'Live BitMart hostname forbidden in paper mode: {candidate_host}')
        if expected_base_url and candidate_url != expected_base_url:
            reasons.append(
                'Paper mode only allows the configured demo execution base URL '
                f'{expected_base_url}; got {candidate_url}'
            )

    allowed = not reasons
    return {
        'allowed': allowed,
        'mode': mode or 'unknown',
        'base_url': candidate_url,
        'base_host': candidate_host,
        'expected_base_url': expected_base_url,
        'forbidden_live_base_urls': forbidden_urls,
        'forbidden_live_hosts': forbidden_hosts,
        'reasons': reasons,
        'config_path': str(CONFIG_PATH),
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description='Hard paper-mode guard for BitMart calls. Rejects live BitMart URLs in paper mode.'
    )
    parser.add_argument('--base-url', required=True, help='Target BitMart base URL to validate')
    parser.add_argument('--method', default='GET', help='Optional request method for logging only')
    parser.add_argument('--path', default='', help='Optional API path for logging only')
    parser.add_argument('--body', default='', help='Optional request body for logging only')
    parser.add_argument(
        'command',
        nargs=argparse.REMAINDER,
        help='Optional command to execute after validation. Prefix with -- to separate wrapper args.',
    )
    args = parser.parse_args()

    config = load_config()
    verdict = evaluate(args.base_url, config)
    verdict['method'] = args.method.upper()
    verdict['path'] = args.path
    verdict['body_length'] = len(args.body or '')

    command = list(args.command)
    if command and command[0] == '--':
        command = command[1:]

    if not verdict['allowed']:
        print(json.dumps(verdict, indent=2))
        return 2

    if not command:
        print(json.dumps(verdict, indent=2))
        return 0

    result = subprocess.run(command, check=False)
    return result.returncode


if __name__ == '__main__':
    sys.exit(main())
