# Pass 3.8 Screenshot Manifest

Captured directly via browser automation during Pass 3.8.

## Captures
1. browser_initial_frame.png
2. browser_mid_navigation.png
3. browser_glow_active.png
4. browser_glow_idle.png
5. telegram_settings_connected.png
6. telegram_test_console.png
7. dashboard_regression_check.png

Artifact base path:
`browser:/tmp/codex_browser_invocations/a17a36de49380e10/artifacts/docs/screenshots/`

Notes:
- Browser captures are direct Playwright screenshots from the app UI surface.
- This environment lacked local backend Playwright browser binaries, so backend-driven live browser frames could not be fully validated end-to-end despite the new screenshot streaming code path and passing tests.
