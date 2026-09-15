import pytest

from app import divide


@pytest.mark.llm_fuzz
def test_divide_handles_adversarial_inputs(llm_fuzz_case):
    """Division must not leak a raw ZeroDivisionError."""
    try:
        result = divide(**llm_fuzz_case.input)
    except ZeroDivisionError:
        pytest.fail("divide should handle y=0")

    assert result is None or isinstance(result, (int, float))
