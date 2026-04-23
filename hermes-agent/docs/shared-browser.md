# Shared Browser Sessions

Hermes supports persistent headed browser sessions for exchange workflows where
login, CAPTCHA, 2FA, OTP, device trust, or suspicious-login approvals require a
human to use the exact same browser Hermes is controlling.

This is separate from the older task-scoped browser tools. Exchange automation
should use the `shared_browser` tool or Slack `/browser` commands instead of
ephemeral hidden contexts.

## Runtime Model

- Each session has a stable name such as `bitmart-main` or `exchange-main`.
- Profile data is stored under `~/.hermes/browser-profiles/<session>`.
- Session metadata is stored under `~/.hermes/browser-state/sessions/<session>.json`.
- Screenshots are stored under `~/.hermes/browser-state/sessions/screenshots/<session>/`.
- Browser windows run headed by default so the operator can manually interact.

Control modes:

- `agent`: Hermes may send browser actions.
- `human`: Hermes must not send actions. Use this during login/security flows.
- `paused`: no actions should run.
- `stopped`: browser/context is closed.

## Configuration

Environment variables:

- `HERMES_BROWSER_PROFILE_ROOT`: override profile storage root. Default: `~/.hermes/browser-profiles`.
- `HERMES_BROWSER_STATE_DIR`: override metadata/screenshot root. Default: `~/.hermes/browser-state`.
- `HERMES_SHARED_BROWSER_HEADLESS=1`: run headless. Do not use this for exchange handoff workflows.

Install browser dependencies:

```bash
cd /Users/openclaw/.hermes/hermes-agent
pip install -e .
playwright install chromium
```

## Slack Commands

Use `/hermes browser ...` from Slack:

```text
browser start exchange-main
browser open bitmart-main https://www.bitmart.com/
browser status bitmart-main
browser snapshot bitmart-main
browser handoff bitmart-main
browser resume bitmart-main
browser stop bitmart-main
```

Slack is only the control plane. The browser UI is the visible Playwright
Chromium window running on the desktop session.

## Human Handoff Flow

1. Start or open a session: `/hermes browser open bitmart-main https://www.bitmart.com/`.
2. Hermes navigates using the persistent profile at `~/.hermes/browser-profiles/bitmart-main`.
3. If the page appears to require sign-in, CAPTCHA, 2FA, OTP, slider challenge, or security verification, Hermes switches to `human` mode and stops automation.
4. Complete the login/security flow manually in the visible browser window.
5. Resume agent control with `/hermes browser resume bitmart-main`.
6. Hermes continues in the same browser context with the same cookies, local storage, and device-trust state.

Hermes should not try to bypass CAPTCHA or exchange security barriers. The safe
behavior is pause, hand off to the human, and resume after completion.

## Agent Tool

The `shared_browser` tool supports:

- `start`
- `stop`
- `status`
- `open` / `navigate`
- `click`
- `type`
- `wait`
- `snapshot`
- `handoff`
- `resume`
- `lock` / `unlock` / `mode`
- `list`

Agent actions fail gracefully outside `agent` mode, so a human handoff prevents
simultaneous control.
