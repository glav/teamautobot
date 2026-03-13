from __future__ import annotations

import json
from pathlib import Path

import app
from teamautobot import cli
from teamautobot.cli import main
from teamautobot.llm import (
    AzureOpenAIAuthMode,
    AzureOpenAIConfig,
    LLMError,
    LLMErrorKind,
    LLMResponse,
    LLMResult,
)


def test_status_json(capsys) -> None:
    exit_code = main(["status", "--json"])
    captured = capsys.readouterr()

    assert exit_code == 0
    payload = json.loads(captured.out)
    assert payload["name"] == "TeamAutobot"
    assert payload["runtime"] == "ready"


def test_app_entrypoint_defaults_to_status(monkeypatch, capsys) -> None:
    monkeypatch.setattr(app.sys, "argv", ["src/app.py"])

    exit_code = app.main()
    captured = capsys.readouterr()

    assert exit_code == 0
    assert "runtime: ready" in captured.out


def test_demo_json_writes_artifact_and_event_log(tmp_path: Path, capsys) -> None:
    exit_code = main(
        [
            "demo",
            "--json",
            "--output-dir",
            str(tmp_path),
            "--task",
            "Ship a small TeamAutobot foundation slice",
        ]
    )
    captured = capsys.readouterr()

    assert exit_code == 0
    payload = json.loads(captured.out)
    artifact_path = Path(payload["artifact_path"])
    event_log_path = Path(payload["event_log_path"])
    run_dir = Path(payload["run_dir"])

    assert payload["status"] == "ok"
    assert payload["tool_names"] == ["prepare_demo_artifact"]
    assert run_dir.exists()
    assert artifact_path.exists()
    assert event_log_path.exists()

    artifact_payload = json.loads(artifact_path.read_text(encoding="utf-8"))
    assert artifact_payload["task"]["description"] == "Ship a small TeamAutobot foundation slice"
    assert artifact_payload["assistant_text"].startswith("Demo complete.")

    event_types = [
        json.loads(line)["type"]
        for line in event_log_path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    assert event_types == [
        "task.started",
        "tool.called",
        "tool.completed",
        "artifact.created",
        "task.completed",
    ]


def test_demo_json_uses_unique_run_paths(tmp_path: Path, capsys) -> None:
    first_exit_code = main(["demo", "--json", "--output-dir", str(tmp_path)])
    first_output = json.loads(capsys.readouterr().out)

    second_exit_code = main(["demo", "--json", "--output-dir", str(tmp_path)])
    second_output = json.loads(capsys.readouterr().out)

    assert first_exit_code == 0
    assert second_exit_code == 0
    assert first_output["task_id"] != second_output["task_id"]
    assert first_output["artifact_path"] != second_output["artifact_path"]
    assert first_output["event_log_path"] != second_output["event_log_path"]


def test_azure_openai_status_json_reports_missing_fields(monkeypatch, capsys) -> None:
    monkeypatch.setattr(
        cli,
        "resolve_azure_openai_config",
        lambda: AzureOpenAIConfig(
            endpoint="https://example.openai.azure.com",
            api_key=None,
            model_deployment=None,
        ),
    )

    exit_code = main(["azure-openai", "status", "--json"])
    payload = json.loads(capsys.readouterr().out)

    assert exit_code == 0
    assert payload["configured"] is False
    assert payload["auth_mode"] == "rbac"
    assert payload["auth_mode_setting"] == "auto"
    assert payload["base_url"] == "https://example.openai.azure.com/openai/v1/"
    assert payload["missing"] == ["AZURE_OPENAI_MODEL_DEPLOYMENT"]


def test_azure_openai_status_json_reports_rbac_mode(monkeypatch, capsys) -> None:
    monkeypatch.setattr(
        cli,
        "resolve_azure_openai_config",
        lambda: AzureOpenAIConfig(
            endpoint="https://example.openai.azure.com",
            api_key=None,
            model_deployment="gpt-4.1-nano",
            auth_mode=AzureOpenAIAuthMode.RBAC,
        ),
    )

    exit_code = main(["azure-openai", "status", "--json"])
    payload = json.loads(capsys.readouterr().out)

    assert exit_code == 0
    assert payload["configured"] is True
    assert payload["auth_mode"] == "rbac"
    assert payload["auth_mode_setting"] == "rbac"


def test_azure_openai_complete_json_returns_error_payload(monkeypatch, capsys) -> None:
    class StubClient:
        async def complete(self, request):
            return LLMResult(
                error=LLMError(
                    kind=LLMErrorKind.AUTHENTICATION,
                    message="missing key",
                    provider="azure_openai",
                )
            )

    monkeypatch.setattr(cli, "AzureOpenAIResponsesClient", lambda: StubClient())

    exit_code = main(["azure-openai", "complete", "--input", "hello", "--json"])
    payload = json.loads(capsys.readouterr().out)

    assert exit_code == 1
    assert payload["status"] == "error"
    assert payload["kind"] == "authentication"
    assert payload["message"] == "missing key"


def test_azure_openai_complete_json_returns_success_payload(monkeypatch, capsys) -> None:
    class StubClient:
        async def complete(self, request):
            assert request.selection is not None
            assert request.selection.provider == "azure_openai"
            assert request.selection.model == "gpt-4.1-nano"
            return LLMResult(
                response=LLMResponse(
                    text="Hello from Azure OpenAI",
                    provider="azure_openai",
                    model="gpt-4.1-nano",
                    usage={"input_tokens": 2, "output_tokens": 4, "total_tokens": 6},
                )
            )

    monkeypatch.setattr(cli, "AzureOpenAIResponsesClient", lambda: StubClient())

    exit_code = main(
        [
            "azure-openai",
            "complete",
            "--input",
            "hello",
            "--model",
            "gpt-4.1-nano",
            "--json",
        ]
    )
    payload = json.loads(capsys.readouterr().out)

    assert exit_code == 0
    assert payload["status"] == "ok"
    assert payload["provider"] == "azure_openai"
    assert payload["model"] == "gpt-4.1-nano"
    assert payload["text"] == "Hello from Azure OpenAI"
