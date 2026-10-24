import pytest

from agent import tools


def pytest_configure(config: pytest.Config) -> None:
    config.addinivalue_line(
        "markers", "agent: slow tests that call the LLM and cost tokens"
    )


@pytest.fixture(autouse=True)
def reset_plan() -> None:
    tools._plan.clear()
