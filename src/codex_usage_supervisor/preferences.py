"""Libadwaita preferences for Codex Usage Supervisor."""

from __future__ import annotations

import gi

gi.require_version("Adw", "1")
gi.require_version("Gtk", "4.0")
from gi.repository import Adw, Gtk  # noqa: E402

from .config import Settings


class PreferencesApplication(Adw.Application):
    def __init__(self) -> None:
        super().__init__(application_id="io.github.owen.CodexUsageSupervisor.Preferences")
        self.settings = Settings.load()

    def do_activate(self) -> None:
        existing = self.get_active_window()
        if existing:
            existing.present()
            return

        window = Adw.PreferencesWindow(application=self)
        window.set_title("Codex Usage Supervisor")
        window.set_default_size(560, 570)

        page = Adw.PreferencesPage(title="Usage")
        window.add(page)

        goals = Adw.PreferencesGroup(
            title="Personal goals",
            description="Optional reminders independent of the Codex allowance windows.",
        )
        page.add(goals)
        goals.add(self._spin_row(
            "Daily token goal", "tokens", self.settings.daily_token_budget,
            1_000, 100_000_000, 10_000, "daily_token_budget"
        ))
        goals.add(self._spin_row(
            "Daily focus-time goal", "minutes", self.settings.daily_focus_minutes,
            15, 1_440, 15, "daily_focus_minutes"
        ))

        behavior = Adw.PreferencesGroup(title="Behavior")
        page.add(behavior)
        behavior.add(self._spin_row(
            "Notify at", "%", self.settings.notify_at_percent, 1, 100, 1, "notify_at_percent"
        ))
        behavior.add(self._spin_row(
            "Refresh interval", "seconds", self.settings.refresh_seconds, 5, 3_600, 5,
            "refresh_seconds"
        ))

        source = Adw.PreferencesGroup(
            title="Data source",
            description="Session content stays on this computer. Only metadata and numeric counters are read.",
        )
        page.add(source)
        source.add(self._text_row("Codex data folder", self.settings.codex_home))

        about = Adw.PreferencesGroup(title="About")
        page.add(about)
        privacy = Adw.ActionRow(
            title="Local-only monitoring",
            subtitle="No API key, telemetry, or network connection",
        )
        privacy.add_prefix(Gtk.Image.new_from_icon_name("security-high-symbolic"))
        about.add(privacy)

        window.present()

    def _spin_row(
        self,
        title: str,
        unit: str,
        value: int,
        minimum: int,
        maximum: int,
        step: int,
        attribute: str,
    ) -> Adw.ActionRow:
        row = Adw.ActionRow(title=title)
        control = Gtk.SpinButton(
            adjustment=Gtk.Adjustment(
                value=value, lower=minimum, upper=maximum, step_increment=step,
                page_increment=step * 10
            ),
            numeric=True,
            valign=Gtk.Align.CENTER,
        )
        control.set_tooltip_text(unit)
        control.connect("value-changed", self._save_number, attribute)
        row.add_suffix(control)
        row.set_activatable_widget(control)
        return row

    def _text_row(self, title: str, value: str) -> Adw.ActionRow:
        row = Adw.ActionRow(title=title)
        entry = Gtk.Entry(text=value, valign=Gtk.Align.CENTER, width_chars=28)
        entry.connect("activate", self._save_path)
        entry.connect("notify::has-focus", self._save_path_on_blur)
        row.add_suffix(entry)
        row.set_activatable_widget(entry)
        return row

    def _save_number(self, control: Gtk.SpinButton, attribute: str) -> None:
        setattr(self.settings, attribute, control.get_value_as_int())
        self.settings.validated().save()

    def _save_path(self, entry: Gtk.Entry) -> None:
        self.settings.codex_home = entry.get_text()
        self.settings.validated().save()

    def _save_path_on_blur(self, entry: Gtk.Entry, _parameter: object) -> None:
        if not entry.get_property("has-focus"):
            self._save_path(entry)


def main() -> None:
    PreferencesApplication().run(None)


if __name__ == "__main__":
    main()

