# Changelog

## 0.3.0 — 2026-09-05

- Added fresh account-level allowance reads through the Codex app-server.
- Made backend account state primary so usage on another computer appears
  without starting a local Codex task.
- Kept local session rate-limit metadata as an automatic offline fallback.
- Added an `ACCOUNT` versus `LOCAL CACHE` freshness indicator to the popover.
- Documented the required user-service restart when upgrading an active
  installation.

## 0.2.0 — 2026-09-05

- Replaced the original Tkinter dashboard with a GNOME Shell 42 top-panel addon.
- Added a frameless usage popover with short- and long-window allowance status.
- Added an on-demand D-Bus service so GNOME Shell never parses session logs.
- Added native GTK4 and Libadwaita preferences.
- Added Debian packaging, service activation, notifications, and privacy tests.

## 0.1.0 — 2026-09-05

- Added the initial local Codex session parser and standalone desktop prototype.
