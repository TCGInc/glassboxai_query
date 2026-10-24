import pytest

from agent.tools import reset_plan


def pytest_configure(config: pytest.Config) -> None:
    config.addinivalue_line(
        "markers", "agent: slow tests that call the LLM and cost tokens"
    )


@pytest.fixture(autouse=True)
def fresh_plan() -> None:
    reset_plan()
