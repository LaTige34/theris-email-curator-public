"""Tests circuit breaker + retry + mask_pii + safety-net wrapper.

Teste `lib.safety` (minimal reimplementation MIT) : retry exponentiel avec
jitter, circuit breaker 3-states, redaction PII, et le décorateur
`with_safety_net` qui combine les 3.
"""

from __future__ import annotations

import pytest

from lib.safety import (
    CircuitBreaker,
    CircuitBreakerOpenError,
    CircuitState,
    RetryExponential,
    mask_pii,
    with_safety_net,
)

# Alias legacy pour les tests historiques
mask_phi = mask_pii


class TestCircuitBreakerBasics:
    def test_closed_state_passes_calls(self):
        cb = CircuitBreaker(name="test-closed", failure_threshold=3)
        result = cb.call(lambda: "ok")
        assert result == "ok"
        assert cb.state == CircuitState.CLOSED

    def test_opens_after_threshold_failures(self):
        cb = CircuitBreaker(name="test-open", failure_threshold=2)

        def fail():
            raise RuntimeError("boom")

        for _ in range(2):
            with pytest.raises(RuntimeError):
                cb.call(fail)
        assert cb.state == CircuitState.OPEN

    def test_open_short_circuits(self):
        cb = CircuitBreaker(name="test-short", failure_threshold=1, recovery_timeout=60.0)

        def fail():
            raise RuntimeError("x")

        with pytest.raises(RuntimeError):
            cb.call(fail)
        assert cb.state == CircuitState.OPEN
        with pytest.raises(CircuitBreakerOpenError):
            cb.call(lambda: "should not run")

    def test_half_open_recovers_on_success(self):
        cb = CircuitBreaker(name="test-recover", failure_threshold=1, recovery_timeout=0.0)

        def fail():
            raise RuntimeError("x")

        with pytest.raises(RuntimeError):
            cb.call(fail)
        assert cb.state == CircuitState.OPEN
        # recovery_timeout=0 → immediate half_open on next call
        result = cb.call(lambda: "recovered")
        assert result == "recovered"
        assert cb.state == CircuitState.CLOSED


class TestRetryExponential:
    def test_retries_and_succeeds(self):
        counter = {"n": 0}

        def flaky():
            counter["n"] += 1
            if counter["n"] < 3:
                raise ConnectionError("transient")
            return "ok"

        retry = RetryExponential(max_attempts=5, base_delay=0.01, jitter=0.0)
        assert retry.run(flaky) == "ok"
        assert counter["n"] == 3

    def test_gives_up_after_max_attempts(self):
        retry = RetryExponential(max_attempts=2, base_delay=0.01, jitter=0.0)

        def always_fail():
            raise TimeoutError("nope")

        with pytest.raises(TimeoutError):
            retry.run(always_fail)

    def test_non_retryable_exception_raised_immediately(self):
        retry = RetryExponential(max_attempts=3, base_delay=0.01)

        def raises_value():
            raise ValueError("not retryable")

        with pytest.raises(ValueError):
            retry.run(raises_value)


class TestMaskPii:
    def test_masks_email(self):
        assert "[REDACTED]" in mask_phi("mail user@example.com ici")

    def test_masks_phone_fr(self):
        assert "[REDACTED]" in mask_phi("tel 06 12 34 56 78")

    def test_masks_nir_13_digits(self):
        assert "[REDACTED]" in mask_phi("NIR 1800675123456")

    def test_passthrough_safe_text(self):
        safe = "Le courrier est arrivé hier matin"
        assert mask_phi(safe) == safe


class TestSafetyNetDecorator:
    def test_integrates_retry_and_breaker(self):
        cb = CircuitBreaker(name="integ", failure_threshold=5)
        retry = RetryExponential(max_attempts=2, base_delay=0.01, jitter=0.0)

        @with_safety_net(
            skill="email-curator-test",
            retry=retry,
            breaker=cb,
            alerts=None,
        )
        def do_work(x):
            return x * 2

        assert do_work(21) == 42
        assert cb.state == CircuitState.CLOSED
