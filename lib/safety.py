"""Safety net minimaliste — retry + circuit breaker + alerting + audit log.

Implementation MIT indépendante (inspirée du pattern Hermès Agent Skills).
Zero dépendance externe, testable offline.

Expose :
- mask_pii(text) : redaction PII simple (email / téléphone FR / NIR)
- RetryExponential : retry avec backoff exponentiel + jitter
- CircuitBreaker : 3-states (closed/open/half_open)
- AlertPump : alerting Telegram avec dédup (bot token via env)
- audit_log(event, skill, detail) : JSONL append-only signé SHA-256
- with_safety_net(skill, retry=..., breaker=..., alerts=...)(fn) : wrapper

Customisation :
- AUDIT_LOG_PATH : via env TERC_AUDIT_LOG_PATH (default /tmp/terc_audit.jsonl)
- TELEGRAM_BOT_TOKEN, TELEGRAM_ALERT_CHAT_ID : env
"""

from __future__ import annotations

import functools
import hashlib
import json
import logging
import os
import random
import re
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Callable, Optional, TypeVar

logger = logging.getLogger("email_curator.safety")
T = TypeVar("T")

AUDIT_LOG_PATH = Path(
    os.environ.get("TERC_AUDIT_LOG_PATH", "/tmp/terc_audit.jsonl")
)
AUDIT_LOG_PATH.parent.mkdir(parents=True, exist_ok=True)


PII_PATTERNS = [
    re.compile(r"\b\d{13}\b"),
    re.compile(r"\b\d{15}\b"),
    re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}"),
    re.compile(r"(?:\+33\s?[1-9]|\b0[1-9])(?:[\s.-]?\d{2}){4}\b"),
    re.compile(
        r"\b\d{1,3}\s?(?:rue|avenue|boulevard|place|chemin|impasse)\b[^\n]{5,60}",
        re.IGNORECASE,
    ),
]


def mask_pii(text: str) -> str:
    """Masque les patterns PII usuels par `[REDACTED]`."""
    masked = text
    for pattern in PII_PATTERNS:
        masked = pattern.sub("[REDACTED]", masked)
    return masked


# Alias de compatibilité
mask_phi = mask_pii


def audit_log(event: str, skill: str, detail: dict[str, Any]) -> None:
    """Append une entrée audit JSONL signée SHA-256.

    Pour un vrai usage prod, remplacer la signature par Ed25519 (cf. cryptography).
    """
    entry: dict[str, Any] = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "event": event,
        "skill": skill,
        "detail": {
            k: (mask_pii(v) if isinstance(v, str) else v) for k, v in detail.items()
        },
    }
    canon = json.dumps(entry, sort_keys=True, separators=(",", ":"))
    entry["sig"] = hashlib.sha256(canon.encode()).hexdigest()
    try:
        with AUDIT_LOG_PATH.open("a", encoding="utf-8") as f:
            f.write(json.dumps(entry) + "\n")
    except OSError as e:
        logger.warning("audit_log write failed: %s", e)


@dataclass
class RetryExponential:
    max_attempts: int = 3
    base_delay: float = 1.0
    max_delay: float = 30.0
    jitter: float = 0.25
    retryable: tuple[type[Exception], ...] = (ConnectionError, TimeoutError)

    def run(self, fn: Callable[..., T], *args: Any, **kwargs: Any) -> T:
        last_exc: Optional[Exception] = None
        for attempt in range(1, self.max_attempts + 1):
            try:
                return fn(*args, **kwargs)
            except self.retryable as exc:
                last_exc = exc
                if attempt == self.max_attempts:
                    break
                delay = min(self.max_delay, self.base_delay * (2 ** (attempt - 1)))
                delay += random.uniform(-self.jitter * delay, self.jitter * delay)
                logger.warning(
                    "Retry %d/%d after %.2fs (error=%s)",
                    attempt,
                    self.max_attempts,
                    delay,
                    type(exc).__name__,
                )
                time.sleep(max(0.0, delay))
        assert last_exc is not None
        raise last_exc


class CircuitState(str, Enum):
    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"


class CircuitBreakerOpenError(RuntimeError):
    pass


@dataclass
class CircuitBreaker:
    name: str
    failure_threshold: int = 5
    recovery_timeout: float = 60.0
    state: CircuitState = CircuitState.CLOSED
    _consecutive_failures: int = 0
    _opened_at: Optional[float] = None

    def call(self, fn: Callable[..., T], *args: Any, **kwargs: Any) -> T:
        if self.state == CircuitState.OPEN:
            assert self._opened_at is not None
            if time.time() - self._opened_at >= self.recovery_timeout:
                self.state = CircuitState.HALF_OPEN
            else:
                raise CircuitBreakerOpenError(f"Circuit '{self.name}' OPEN")

        try:
            result = fn(*args, **kwargs)
            if self.state == CircuitState.HALF_OPEN:
                self._reset()
            else:
                self._consecutive_failures = 0
            return result
        except Exception as exc:
            self._on_failure(exc)
            raise

    def _on_failure(self, exc: Exception) -> None:
        self._consecutive_failures += 1
        if (
            self.state == CircuitState.HALF_OPEN
            or self._consecutive_failures >= self.failure_threshold
        ):
            if self.state != CircuitState.OPEN:
                audit_log(
                    "circuit_breaker_opened",
                    self.name,
                    {"last_error": str(exc)[:200]},
                )
            self.state = CircuitState.OPEN
            self._opened_at = time.time()

    def _reset(self) -> None:
        self.state = CircuitState.CLOSED
        self._consecutive_failures = 0
        self._opened_at = None


@dataclass
class AlertPump:
    bot_token_env: str = "TELEGRAM_BOT_TOKEN"
    chat_id_env: str = "TELEGRAM_ALERT_CHAT_ID"
    dedup_window_seconds: float = 300.0
    _recent: dict[str, float] = field(default_factory=dict)

    def send(
        self,
        skill: str,
        level: str,
        message: str,
        context: Optional[dict[str, Any]] = None,
    ) -> None:
        icon = {"info": "i", "warning": "!", "error": "X", "critical": "!!"}.get(
            level, "*"
        )
        safe_msg = mask_pii(message)
        body = f"{icon} [{skill}] {level.upper()}\n{safe_msg}"
        if context:
            safe_ctx = {k: mask_pii(str(v))[:200] for k, v in context.items()}
            body += "\n" + json.dumps(safe_ctx, indent=2, ensure_ascii=False)[:800]

        dedup_key = hashlib.sha256(
            (skill + level + safe_msg[:200]).encode()
        ).hexdigest()
        now = time.time()
        if dedup_key in self._recent and (now - self._recent[dedup_key]) < self.dedup_window_seconds:
            return
        self._recent[dedup_key] = now

        token = os.environ.get(self.bot_token_env)
        chat_id = os.environ.get(self.chat_id_env, "")
        if not token or not chat_id:
            logger.warning("AlertPump: token/chat_id absent, skip")
            return

        try:
            import urllib.request as _r

            data = json.dumps(
                {"chat_id": chat_id, "text": body, "disable_web_page_preview": True}
            ).encode()
            req = _r.Request(
                f"https://api.telegram.org/bot{token}/sendMessage",
                data=data,
                headers={"Content-Type": "application/json"},
            )
            _r.urlopen(req, timeout=10)  # noqa: S310
            audit_log("alert_sent", skill, {"level": level})
        except Exception as exc:
            logger.error("AlertPump: send failed (%s)", exc)


def with_safety_net(
    skill: str,
    *,
    retry: Optional[RetryExponential] = None,
    breaker: Optional[CircuitBreaker] = None,
    alerts: Optional[AlertPump] = None,
    alert_level: str = "error",
) -> Callable[[Callable[..., T]], Callable[..., T]]:
    """Decorator combining retry + breaker + alerts."""
    r = retry or RetryExponential()
    b = breaker
    ap = alerts

    def _decorator(fn: Callable[..., T]) -> Callable[..., T]:
        @functools.wraps(fn)
        def _wrapped(*args: Any, **kwargs: Any) -> T:
            def _call() -> T:
                return fn(*args, **kwargs)

            try:
                if b is not None:
                    return b.call(lambda: r.run(_call))
                return r.run(_call)
            except Exception as exc:
                if ap is not None:
                    ap.send(
                        skill,
                        alert_level,
                        f"{fn.__name__} failed: {type(exc).__name__}",
                    )
                audit_log(
                    "safety_net_exception",
                    skill,
                    {"fn": fn.__name__, "error": str(exc)[:200]},
                )
                raise

        return _wrapped

    return _decorator
