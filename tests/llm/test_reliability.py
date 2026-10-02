import pytest

from business_brain.llm.reliability import RetryPolicy


def test_exponential_backoff_is_bounded_and_jittered() -> None:
    policy = RetryPolicy(
        max_attempts=5,
        base_delay_seconds=1,
        max_delay_seconds=2,
        jitter_ratio=0.25,
    )

    assert policy.delay_for_retry(1, 0) == 1
    assert policy.delay_for_retry(2, 0) == 2
    assert policy.delay_for_retry(3, 0) == 2
    assert policy.delay_for_retry(3, 1) == 2.5


@pytest.mark.parametrize(
    ("kwargs", "message"),
    [
        ({"max_attempts": 0}, "max_attempts"),
        ({"base_delay_seconds": -1}, "negative"),
        ({"base_delay_seconds": 2, "max_delay_seconds": 1}, "exceed"),
        ({"jitter_ratio": 1.1}, "jitter_ratio"),
    ],
)
def test_retry_policy_rejects_invalid_configuration(kwargs: dict, message: str) -> None:
    with pytest.raises(ValueError, match=message):
        RetryPolicy(**kwargs)
