import pytest

from app import divide


@pytest.mark.llm_fuzz(budget_usd=0.05)
def test_divide_handles_saved_fuzz_cases(llm_fuzz_case):
    """Divide must not leak raw ZeroDivisionError for user-supplied numbers."""
    try:
        result = divide(**llm_fuzz_case.input)
    except ZeroDivisionError:
        pytest.fail("divide should handle y=0 before Python raises ZeroDivisionError")

    assert result is None or isinstance(result, (int, float))
