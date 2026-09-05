"""Read privacy-conscious usage metrics from local Codex session logs.

Only timestamps, identifiers, working directories, model names, turn IDs, and
numeric token counters are retained. Prompt and response content is ignored.
"""

from __future__ import annotations

import json
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterable


def _timestamp(value: Any) -> datetime | None:
    if not isinstance(value, str):
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone()
    except ValueError:
        return None


@dataclass(slots=True)
class TokenUsage:
    input_tokens: int = 0
    cached_input_tokens: int = 0
    output_tokens: int = 0
    reasoning_output_tokens: int = 0
    total_tokens: int = 0

    @classmethod
    def from_mapping(cls, value: Any) -> "TokenUsage | None":
        if not isinstance(value, dict):
            return None
        fields = cls.__dataclass_fields__
        return cls(**{key: int(value.get(key, 0) or 0) for key in fields})


@dataclass(slots=True)
class RateWindow:
    used_percent: float
    window_minutes: int
    resets_at: datetime | None


@dataclass(slots=True)
class RateLimits:
    plan_type: str
    primary: RateWindow | None
    secondary: RateWindow | None
    observed_at: datetime


def _rate_window(value: Any) -> RateWindow | None:
    if not isinstance(value, dict) or not isinstance(value.get("used_percent"), (int, float)):
        return None
    reset = value.get("resets_at")
    return RateWindow(
        used_percent=float(value["used_percent"]),
        window_minutes=int(value.get("window_minutes", 0) or 0),
        resets_at=datetime.fromtimestamp(reset).astimezone() if isinstance(reset, (int, float)) else None,
    )


def _rate_limits(value: Any, observed_at: datetime | None) -> RateLimits | None:
    if not isinstance(value, dict) or observed_at is None:
        return None
    primary = _rate_window(value.get("primary"))
    secondary = _rate_window(value.get("secondary"))
    if primary is None and secondary is None:
        return None
    return RateLimits(str(value.get("plan_type") or "unknown"), primary, secondary, observed_at)


@dataclass(slots=True)
class SessionMetric:
    session_id: str
    name: str = "Untitled task"
    cwd: str = ""
    model: str = "Unknown"
    started_at: datetime | None = None
    updated_at: datetime | None = None
    turns: int = 0
    usage: TokenUsage = field(default_factory=TokenUsage)
    today_tokens: int = 0
    today_minutes: int = 0
    rate_limits: RateLimits | None = None
    event_times: list[datetime] = field(default_factory=list, repr=False)


@dataclass(slots=True)
class DashboardMetrics:
    sessions: list[SessionMetric]
    today_tokens: int
    week_tokens: int
    today_minutes: int
    today_sessions: int
    generated_at: datetime
    rate_limits: RateLimits | None = None


def load_names(codex_home: Path) -> dict[str, str]:
    names: dict[str, str] = {}
    path = codex_home / "session_index.jsonl"
    try:
        with path.open(encoding="utf-8") as stream:
            for line in stream:
                try:
                    record = json.loads(line)
                except json.JSONDecodeError:
                    continue
                session_id = record.get("id")
                name = record.get("thread_name")
                if isinstance(session_id, str) and isinstance(name, str) and name.strip():
                    names[session_id] = name.strip()
    except OSError:
        pass
    return names


def session_paths(codex_home: Path) -> Iterable[Path]:
    yield from (codex_home / "sessions").glob("**/*.jsonl")
    yield from (codex_home / "archived_sessions").glob("*.jsonl")


def _activity_minutes(times: list[datetime], target: date) -> int:
    same_day = sorted({stamp for stamp in times if stamp.date() == target})
    if not same_day:
        return 0
    seconds = 60.0
    for earlier, later in zip(same_day, same_day[1:]):
        seconds += min((later - earlier).total_seconds(), 15 * 60)
    return max(1, round(seconds / 60))


def parse_session(path: Path, names: dict[str, str], today: date) -> SessionMetric | None:
    session_id = path.stem.rsplit("-", 5)[-1]
    cwd = ""
    model = "Unknown"
    times: list[datetime] = []
    turn_ids: set[str] = set()
    usage = TokenUsage()
    usage_by_day: dict[date, int] = defaultdict(int)
    rate_limits: RateLimits | None = None

    try:
        stream = path.open(encoding="utf-8")
    except OSError:
        return None

    with stream:
        for line in stream:
            try:
                record = json.loads(line)
            except json.JSONDecodeError:
                continue
            stamp = _timestamp(record.get("timestamp"))
            if stamp:
                times.append(stamp)
            payload = record.get("payload")
            if not isinstance(payload, dict):
                continue
            if record.get("type") == "session_meta":
                session_id = str(payload.get("id") or payload.get("session_id") or session_id)
                cwd = str(payload.get("cwd") or cwd)
            elif record.get("type") == "turn_context":
                model = str(payload.get("model") or model)
                turn_id = payload.get("turn_id")
                if isinstance(turn_id, str):
                    turn_ids.add(turn_id)
            elif record.get("type") == "event_msg" and payload.get("type") == "token_count":
                info = payload.get("info")
                current = TokenUsage.from_mapping(
                    info.get("total_token_usage") if isinstance(info, dict) else None
                )
                if current:
                    if current.total_tokens >= usage.total_tokens:
                        usage = current
                    if stamp:
                        usage_by_day[stamp.date()] = max(
                            usage_by_day[stamp.date()], current.total_tokens
                        )
                observed_limits = _rate_limits(payload.get("rate_limits"), stamp)
                if observed_limits and (
                    rate_limits is None or observed_limits.observed_at > rate_limits.observed_at
                ):
                    rate_limits = observed_limits

    if not times:
        try:
            times = [datetime.fromtimestamp(path.stat().st_mtime).astimezone()]
        except OSError:
            return None

    # Daily consumption is the change in the cumulative session counter during
    # that day. Sessions beginning that day have a zero baseline.
    previous_total = max(
        (total for day, total in usage_by_day.items() if day < today), default=0
    )
    today_tokens = max(0, usage_by_day.get(today, 0) - previous_total)
    return SessionMetric(
        session_id=session_id,
        name=names.get(session_id, "Untitled task"),
        cwd=cwd,
        model=model,
        started_at=min(times),
        updated_at=max(times),
        turns=len(turn_ids),
        usage=usage,
        today_tokens=today_tokens,
        today_minutes=_activity_minutes(times, today),
        rate_limits=rate_limits,
        event_times=times,
    )


def collect_metrics(codex_home: Path, now: datetime | None = None) -> DashboardMetrics:
    now = (now or datetime.now().astimezone()).astimezone()
    today = now.date()
    week_start = today - timedelta(days=6)
    names = load_names(codex_home)
    sessions = [
        item
        for path in session_paths(codex_home)
        if (item := parse_session(path, names, today)) is not None
    ]
    sessions.sort(key=lambda item: item.updated_at or datetime.min.astimezone(), reverse=True)

    week_tokens = 0
    for session in sessions:
        daily_max: dict[date, int] = defaultdict(int)
        # Re-reading only token counters keeps SessionMetric compact and makes
        # historical week deltas correct for sessions spanning midnight.
        try:
            with next(p for p in session_paths(codex_home) if session.session_id in p.name).open(
                encoding="utf-8"
            ) as stream:
                for line in stream:
                    try:
                        record = json.loads(line)
                        stamp = _timestamp(record.get("timestamp"))
                        payload = record.get("payload", {})
                        info = payload.get("info", {}) if isinstance(payload, dict) else {}
                        value = TokenUsage.from_mapping(
                            info.get("total_token_usage") if isinstance(info, dict) else None
                        )
                        if stamp and value:
                            daily_max[stamp.date()] = max(daily_max[stamp.date()], value.total_tokens)
                    except (json.JSONDecodeError, TypeError):
                        continue
        except (OSError, StopIteration):
            continue
        baseline = max((v for d, v in daily_max.items() if d < week_start), default=0)
        end = max((v for d, v in daily_max.items() if d <= today), default=baseline)
        week_tokens += max(0, end - baseline)

    return DashboardMetrics(
        sessions=sessions,
        today_tokens=sum(item.today_tokens for item in sessions),
        week_tokens=week_tokens,
        # Merge all task event times so concurrent Codex tasks do not multiply
        # the user's estimated focus time.
        today_minutes=_activity_minutes(
            [stamp for item in sessions for stamp in item.event_times], today
        ),
        today_sessions=sum(1 for item in sessions if item.today_minutes),
        generated_at=now,
        rate_limits=max(
            (item.rate_limits for item in sessions if item.rate_limits),
            key=lambda item: item.observed_at,
            default=None,
        ),
    )
