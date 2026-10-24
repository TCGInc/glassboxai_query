import pytest

from agent.tools import reset_plan


def pytest_configure(config: pytest.Config) -> None:
    config.addinivalue_line(
        "markers", "agent: slow tests that call the LLM and cost tokens"
    )


def pytest_terminal_summary(terminalreporter) -> None:
    import os

    import evalreport

    if not evalreport.RESULTS:
        return
    terminalreporter.section("agent eval summary")
    for line in evalreport.render(evalreport.RESULTS):
        terminalreporter.write_line(line)
    path = evalreport.write_report(
        evalreport.RESULTS, os.environ.get("LLM_MODEL_ID", "")
    )
    terminalreporter.write_line(f"\nFull report: {path}")


@pytest.fixture(autouse=True)
def fresh_plan() -> None:
    reset_plan()
