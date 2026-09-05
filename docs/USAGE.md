# Usage guide

## Where the visualization lives

The application launcher opens **preferences only**. The live visualization is
the `Codex <percent>%` indicator in the upper-right GNOME panel.

After installing the package, GNOME Shell must discover the extension. On X11:

1. Press `Alt+F2`.
2. Enter `r` and press Enter.
3. Enable the extension:

   ```bash
   gnome-extensions enable codex-usage-supervisor@owen.local
   ```

On Wayland, log out and sign in again before enabling it.

Click the panel indicator to see:

- current short-window allowance usage and reset countdown;
- current long-window allowance usage;
- today's tasks, estimated focus time, and local token count;
- the three most recently active tasks.

The allowance values come from the latest rate-limit metadata reported in a
local Codex session. Token and focus-time figures are local estimates, not
official account billing records.

## Preferences

Open **Codex Usage Supervisor Preferences** from the application launcher or run:

```bash
codex-usage-supervisor-preferences
```

Personal token and focus-time goals affect notifications; they do not change
Codex account limits. Changes are stored in
`~/.config/codex-usage-supervisor/settings.json`.

## Diagnostics

Check the extension state:

```bash
gnome-extensions info codex-usage-supervisor@owen.local
```

Request a backend snapshot:

```bash
gdbus call --session \
  --dest io.github.owen.CodexUsageSupervisor \
  --object-path /io/github/owen/CodexUsageSupervisor \
  --method io.github.owen.CodexUsageSupervisor.GetSummary
```

Inspect service or extension errors:

```bash
systemctl --user status codex-usage-supervisor.service
journalctl --user -b | grep -i codex-usage
```

