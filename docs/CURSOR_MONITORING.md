# Cursor Team and Enterprise monitoring

## What can be monitored

Cursor's current Team and Enterprise billing is primarily monthly usage and
spend based. Enterprise can use pooled usage across users, and deployments can
also have team, group, or per-user spend controls. Therefore the addon should
not assume that every account has a simple personal percentage limit.

For an Enterprise workspace, the supported integration is Cursor's Admin API.
The `POST /teams/filtered-usage-events` endpoint provides hourly aggregated
events with fields such as:

- user and model;
- input, output, cache-read, and cache-write tokens when token billing applies;
- `kind` and `isChargeable`;
- `chargedCents`, which Cursor documents as the reconciliation value for spend;
- headless, automation, and cloud-agent attribution where applicable.

Cursor recommends polling this endpoint no more than once per hour. The API is
available to Enterprise customers and requires an Admin API key. A non-admin
team member can still view personal usage in Cursor's web dashboard, but cannot
create an organization-level integration key.

Official references:

- [Cursor Admin API](https://cursor.com/docs/account/teams/admin-api)
- [Cursor Team pricing](https://cursor.com/docs/account/teams/pricing)
- [Cursor usage analytics](https://cursor.com/docs/account/teams/analytics)

## Proposed panel model

The panel should display spend according to the data actually available:

```text
Cursor · $18.42 this cycle
Team pool        $1,482 / $3,000
Your usage       $18.42
On-demand        $3.10
Top model        Claude Sonnet
Updated          24 minutes ago
```

If the API reports a configured spend limit, the UI can show a percentage. If
there is no applicable limit, it should show absolute spend and trend without
inventing a denominator.

## Credential design

The Admin API key must not be committed or written to the existing settings
file. A production implementation should store it in GNOME Keyring through
Secret Service and expose only aggregated cost data over D-Bus.

Suggested configuration:

- provider enabled: explicit opt-in;
- team member email: used to filter personal events;
- billing-cycle start: obtained from the API or configured if unavailable;
- refresh period: 60 minutes or longer;
- optional team/organization identifier for pooled Enterprise usage.

For development only, the service may accept `CURSOR_ADMIN_API_KEY` from the
environment. It must redact the variable from diagnostics and never persist it.

## Fallback without Admin API access

If no admin key is available, the safe fallback is an explicit CSV import from
the Cursor dashboard. Local editor databases are not an authoritative cost
source and should not be used to estimate charges.

