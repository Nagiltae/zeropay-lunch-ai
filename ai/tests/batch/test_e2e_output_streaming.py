"""E2E 하위 CLI stdout/stderr 실시간 전달 계약을 mock subprocess로 검증한다."""

from pathlib import Path

from app.batch import e2e_pipeline_orchestrator as orchestrator


def test_child_stdout_and_stderr_are_forwarded_before_wait(monkeypatch, capsys):
    events = []

    class FakeProcess:
        stdout = iter(("[Place ID] current 1/2 id=10 name=식당\n", "BLOCKED: HTTP 429\n"))

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def wait(self):
            events.append("wait")
            return 1

    def fake_popen(command, **kwargs):
        assert command == ["python", "-u", "child.py"]
        assert kwargs["stderr"] == orchestrator.subprocess.STDOUT
        assert kwargs["env"]["PYTHONUNBUFFERED"] == "1"
        assert kwargs["cwd"] == Path("ai")
        return FakeProcess()

    monkeypatch.setattr(orchestrator.subprocess, "Popen", fake_popen)
    ok = orchestrator._run_cmd(
        ["python", "-u", "child.py"], cwd=Path("ai"),
        on_line=lambda line: events.append(line.strip()),
    )
    assert not ok
    assert events == ["[Place ID] current 1/2 id=10 name=식당", "BLOCKED: HTTP 429", "wait"]
    assert "BLOCKED: HTTP 429" in capsys.readouterr().out
