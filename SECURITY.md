# Security and privacy

## Data boundaries

Codex Usage Supervisor reads local session metadata and numeric counters from
the configured Codex directory. It does not require a Codex API key and does
not transmit Codex data over the network.

Task names and project directory names can still be sensitive. They remain on
the local desktop and are exposed only on the user's session D-Bus.

Future remote providers, including Cursor Enterprise, must follow these rules:

- credentials must come from the desktop secret service or process environment;
- credentials must never be written to settings JSON, logs, reports, or D-Bus;
- API responses must be reduced to the minimum summary needed by the UI;
- TLS verification must remain enabled;
- remote providers must be disabled by default and explicitly configured.

## Reporting a vulnerability

Please report vulnerabilities privately through GitHub's security advisory
feature rather than opening a public issue containing sensitive details.

