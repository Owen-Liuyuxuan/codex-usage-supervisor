"""D-Bus service supplying compact Codex usage snapshots to desktop clients."""

from __future__ import annotations

import argparse
import json
import signal
from datetime import datetime
from pathlib import Path
from typing import Any

import gi

gi.require_version("Gio", "2.0")
gi.require_version("GLib", "2.0")
from gi.repository import Gio, GLib  # noqa: E402

from .account import AccountLimitsError, fetch_account_rate_limits
from .config import Settings
from .metrics import DashboardMetrics, RateLimits, RateWindow, collect_metrics

BUS_NAME = "io.github.owen.CodexUsageSupervisor"
OBJECT_PATH = "/io/github/owen/CodexUsageSupervisor"
INTERFACE = BUS_NAME

INTROSPECTION_XML = f"""
<node>
  <interface name="{INTERFACE}">
    <method name="GetSummary">
      <arg name="summary" type="s" direction="out"/>
    </method>
    <method name="Refresh">
      <arg name="summary" type="s" direction="out"/>
    </method>
    <signal name="UsageChanged">
      <arg name="summary" type="s"/>
    </signal>
  </interface>
</node>
"""


def _window(window: RateWindow | None) -> dict[str, Any] | None:
    if window is None:
        return None
    return {
        "used_percent": window.used_percent,
        "window_minutes": window.window_minutes,
        "resets_at": window.resets_at.isoformat() if window.resets_at else None,
    }


def _limits(limits: RateLimits | None) -> dict[str, Any] | None:
    if limits is None:
        return None
    return {
        "plan_type": limits.plan_type,
        "primary": _window(limits.primary),
        "secondary": _window(limits.secondary),
        "observed_at": limits.observed_at.isoformat(),
    }


def metrics_summary(
    metrics: DashboardMetrics,
    account_limits: RateLimits | None = None,
) -> dict[str, Any]:
    """Convert internal metrics into the stable, content-free desktop contract."""
    return {
        "schema_version": 1,
        "generated_at": metrics.generated_at.isoformat(),
        "today": {
            "tokens": metrics.today_tokens,
            "focus_minutes": metrics.today_minutes,
            "sessions": metrics.today_sessions,
        },
        "week": {"tokens": metrics.week_tokens},
        "rate_limits": _limits(account_limits or metrics.rate_limits),
        "rate_limits_source": "app-server" if account_limits else "local-session",
        "recent": [
            {
                "name": item.name,
                "project": Path(item.cwd).name if item.cwd else "",
                "model": item.model,
                "turns": item.turns,
                "tokens": item.usage.total_tokens,
                "updated_at": item.updated_at.isoformat() if item.updated_at else None,
            }
            for item in metrics.sessions[:5]
        ],
        "privacy": "local-metadata-and-codex-account",
    }


def collect_summary(settings: Settings | None = None) -> dict[str, Any]:
    settings = settings or Settings.load()
    metrics = collect_metrics(Path(settings.codex_home))
    try:
        account_limits = fetch_account_rate_limits()
        refresh_error = None
    except AccountLimitsError as error:
        account_limits = None
        refresh_error = str(error)
    summary = metrics_summary(metrics, account_limits)
    if refresh_error:
        summary["rate_limits_refresh_error"] = refresh_error
    return summary


class UsageService:
    def __init__(self) -> None:
        self.settings = Settings.load()
        self.connection: Gio.DBusConnection | None = None
        self.registration_id = 0
        self.summary = json.dumps(collect_summary(self.settings), separators=(",", ":"))
        self.last_usage_percent = self._maximum_usage_percent(json.loads(self.summary))
        self.node = Gio.DBusNodeInfo.new_for_xml(INTROSPECTION_XML)

    def on_bus_acquired(self, connection: Gio.DBusConnection, _name: str) -> None:
        self.connection = connection
        self.registration_id = connection.register_object(
            OBJECT_PATH,
            self.node.interfaces[0],
            self._handle_method_call,
            None,
            None,
        )

    def _handle_method_call(
        self,
        _connection: Gio.DBusConnection,
        _sender: str,
        _object_path: str,
        _interface_name: str,
        method_name: str,
        _parameters: GLib.Variant,
        invocation: Gio.DBusMethodInvocation,
    ) -> None:
        if method_name == "Refresh":
            self.refresh()
        if method_name in {"GetSummary", "Refresh"}:
            invocation.return_value(GLib.Variant("(s)", (self.summary,)))
            return
        invocation.return_dbus_error(f"{INTERFACE}.UnknownMethod", method_name)

    def refresh(self) -> bool:
        self.settings = Settings.load()
        try:
            summary = collect_summary(self.settings)
            updated = json.dumps(summary, separators=(",", ":"))
        except Exception as error:  # Keep the service alive when a log is transiently unreadable.
            summary = {
                "schema_version": 1,
                "generated_at": datetime.now().astimezone().isoformat(),
                "error": str(error),
            }
            updated = json.dumps(summary)
        changed = updated != self.summary
        self.summary = updated
        current_percent = self._maximum_usage_percent(summary)
        if self.last_usage_percent < self.settings.notify_at_percent <= current_percent:
            self._notify(current_percent)
        self.last_usage_percent = current_percent
        if changed and self.connection:
            self.connection.emit_signal(
                None,
                OBJECT_PATH,
                INTERFACE,
                "UsageChanged",
                GLib.Variant("(s)", (self.summary,)),
            )
        return GLib.SOURCE_CONTINUE

    def schedule(self) -> None:
        GLib.timeout_add_seconds(self.settings.refresh_seconds, self._scheduled_refresh)

    def _scheduled_refresh(self) -> bool:
        self.refresh()
        self.schedule()
        return GLib.SOURCE_REMOVE

    def _maximum_usage_percent(self, summary: dict[str, Any]) -> float:
        if summary.get("error"):
            return 0.0
        today = summary.get("today") or {}
        limits = summary.get("rate_limits") or {}
        primary = limits.get("primary") or {}
        return max(
            float(primary.get("used_percent", 0) or 0),
            100 * float(today.get("tokens", 0) or 0) / self.settings.daily_token_budget,
            100 * float(today.get("focus_minutes", 0) or 0) / self.settings.daily_focus_minutes,
        )

    def _notify(self, percentage: float) -> None:
        if not self.connection:
            return
        parameters = GLib.Variant(
            "(susssasa{sv}i)",
            (
                "Codex Usage Supervisor",
                0,
                "codex-usage-supervisor",
                "Codex usage check-in",
                f"Usage has reached {percentage:.0f}% of a configured threshold.",
                [],
                {},
                -1,
            ),
        )
        self.connection.call(
            "org.freedesktop.Notifications",
            "/org/freedesktop/Notifications",
            "org.freedesktop.Notifications",
            "Notify",
            parameters,
            None,
            Gio.DBusCallFlags.NONE,
            -1,
            None,
            None,
        )


def run_service() -> None:
    service = UsageService()
    loop = GLib.MainLoop()
    owner_id = Gio.bus_own_name(
        Gio.BusType.SESSION,
        BUS_NAME,
        Gio.BusNameOwnerFlags.NONE,
        service.on_bus_acquired,
        None,
        lambda _connection, _name: loop.quit(),
    )
    service.schedule()
    for signum in (signal.SIGINT, signal.SIGTERM):
        GLib.unix_signal_add(GLib.PRIORITY_DEFAULT, signum, loop.quit)
    try:
        loop.run()
    finally:
        Gio.bus_unown_name(owner_id)


def main() -> None:
    parser = argparse.ArgumentParser(description="Codex Usage Supervisor background service")
    parser.add_argument("--once", action="store_true", help="print one JSON snapshot and exit")
    arguments = parser.parse_args()
    if arguments.once:
        print(json.dumps(collect_summary(), indent=2))
    else:
        run_service()


if __name__ == "__main__":
    main()
