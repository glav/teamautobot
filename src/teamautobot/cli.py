from __future__ import annotations

import argparse
import asyncio
import json
import platform
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from . import __version__
from .demo import run_demo_task
from .environment import load_env
from .llm import LLMRequest, ModelSelection
from .llm.azure_openai import AzureOpenAIResponsesClient, resolve_azure_openai_config
from .planner.demo import DEFAULT_OUTPUT_DIR as DEFAULT_PLANNER_OUTPUT_DIR
from .planner.demo import run_planner_demo, run_review_demo
from .planner.models import ReviewDecision

DEFAULT_DEMO_OUTPUT_DIR = Path(".teamautobot/demo-runs")


def _print(payload: dict[str, Any], *, as_json: bool) -> None:
    if as_json:
        print(json.dumps(payload, indent=2, sort_keys=True))
        return

    for key, value in payload.items():
        print(f"{key}: {value}")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="teamautobot", description="TeamAutobot CLI")
    subparsers = parser.add_subparsers(dest="command", required=True)

    status_parser = subparsers.add_parser("status", help="Show runtime readiness")
    status_parser.add_argument("--json", action="store_true", help="Emit JSON")

    demo_parser = subparsers.add_parser("demo", help="Run the minimal single-agent demo")
    demo_parser.add_argument(
        "--task",
        default="Draft a deterministic TeamAutobot demo artifact",
        help="Task description for the scripted single-agent demo",
    )
    demo_parser.add_argument(
        "--output-dir",
        type=Path,
        default=DEFAULT_DEMO_OUTPUT_DIR,
        help="Base directory where TeamAutobot demo run outputs are written",
    )
    demo_parser.add_argument("--provider", default="demo", help="Provider name for model selection")
    demo_parser.add_argument("--model", default="scripted", help="Model name for model selection")
    demo_parser.add_argument("--json", action="store_true", help="Emit JSON")

    azure_parser = subparsers.add_parser(
        "azure-openai",
        help="Inspect or call the Azure OpenAI Responses adapter",
    )
    azure_subparsers = azure_parser.add_subparsers(dest="azure_command", required=True)

    azure_status_parser = azure_subparsers.add_parser(
        "status",
        help="Show resolved Azure OpenAI configuration without calling the network",
    )
    azure_status_parser.add_argument("--json", action="store_true", help="Emit JSON")

    azure_complete_parser = azure_subparsers.add_parser(
        "complete",
        help="Run a single Azure OpenAI Responses completion",
    )
    azure_complete_parser.add_argument("--input", required=True, help="User input text to send")
    azure_complete_parser.add_argument(
        "--instructions",
        default="You are TeamAutobot validating the Azure OpenAI adapter.",
        help="System-style instructions for the model turn",
    )
    azure_complete_parser.add_argument(
        "--model",
        default=None,
        help="Override AZURE_OPENAI_MODEL_DEPLOYMENT for this call",
    )
    azure_complete_parser.add_argument("--json", action="store_true", help="Emit JSON")

    planner_parser = subparsers.add_parser("planner", help="Run planner demo flows")
    planner_subparsers = planner_parser.add_subparsers(dest="planner_command", required=True)
    planner_demo_parser = planner_subparsers.add_parser(
        "demo",
        help="Run the deterministic planner/task-graph demo",
    )
    planner_demo_parser.add_argument(
        "--output-dir",
        type=Path,
        default=DEFAULT_PLANNER_OUTPUT_DIR,
        help="Base directory where planner demo run outputs are written",
    )
    planner_demo_parser.add_argument("--json", action="store_true", help="Emit JSON")
    planner_review_demo_parser = planner_subparsers.add_parser(
        "review-demo",
        help="Run the deterministic builder-reviewer review-gate demo",
    )
    planner_review_demo_parser.add_argument(
        "--output-dir",
        type=Path,
        default=DEFAULT_PLANNER_OUTPUT_DIR,
        help="Base directory where planner review-demo run outputs are written",
    )
    planner_review_demo_parser.add_argument(
        "--review-decision",
        choices=[decision.value for decision in ReviewDecision],
        default=ReviewDecision.APPROVED.value,
        help="Deterministic review outcome to simulate in the review-gate demo",
    )
    planner_review_demo_parser.add_argument("--json", action="store_true", help="Emit JSON")
    return parser


def _status_payload(*, env_loaded: bool) -> dict[str, Any]:
    return {
        "env_loaded": env_loaded,
        "name": "TeamAutobot",
        "version": __version__,
        "python": platform.python_version(),
        "runtime": "ready",
    }


def _azure_status_payload() -> dict[str, Any]:
    try:
        config = resolve_azure_openai_config()
    except ValueError as exc:
        return {
            "provider": "azure_openai",
            "configured": False,
            "error": str(exc),
        }
    missing_fields = config.missing_fields()
    return {
        "provider": "azure_openai",
        "configured": not missing_fields,
        "auth_mode": config.resolved_auth_mode.value,
        "auth_mode_setting": config.auth_mode.value,
        "endpoint_configured": bool(config.endpoint),
        "api_key_configured": bool(config.api_key),
        "model_configured": bool(config.model_deployment),
        "base_url": config.base_url,
        "model": config.model_deployment,
        "missing": list(missing_fields),
    }


async def _run_azure_complete(
    *, instructions: str, user_input: str, model: str | None
) -> dict[str, Any]:
    client = AzureOpenAIResponsesClient()
    result = await client.complete(
        LLMRequest(
            instructions=instructions,
            input=user_input,
            selection=ModelSelection(provider="azure_openai", model=model),
        )
    )
    if result.error is not None:
        return {
            "status": "error",
            "provider": result.error.provider,
            "kind": result.error.kind,
            "message": result.error.message,
            "retryable": result.error.retryable,
            "raw": dict(result.error.raw),
        }

    assert result.response is not None
    return {
        "status": "ok",
        "provider": result.response.provider,
        "model": result.response.model,
        "text": result.response.text,
        "tool_calls": [
            {"id": tool_call.id, "name": tool_call.name, "arguments": tool_call.arguments}
            for tool_call in result.response.tool_calls
        ],
        "finish_reason": result.response.finish_reason,
        "usage": dict(result.response.usage),
    }


def main(argv: Sequence[str] | None = None) -> int:
    env_loaded = load_env(verbose=False)
    parser = build_parser()
    args = parser.parse_args(list(argv) if argv is not None else None)

    if args.command == "status":
        _print(_status_payload(env_loaded=env_loaded), as_json=args.json)
        return 0

    if args.command == "demo":
        payload = asyncio.run(
            run_demo_task(
                task_description=args.task,
                output_dir=args.output_dir,
                selection=ModelSelection(provider=args.provider, model=args.model),
            )
        )
        _print(payload, as_json=args.json)
        return 0

    if args.command == "planner":
        if args.planner_command == "demo":
            payload = asyncio.run(run_planner_demo(output_dir=args.output_dir))
            _print(payload, as_json=args.json)
            return 0 if payload["status"] == "ok" else 1
        if args.planner_command == "review-demo":
            payload = asyncio.run(
                run_review_demo(
                    output_dir=args.output_dir,
                    review_decision=ReviewDecision(args.review_decision),
                )
            )
            _print(payload, as_json=args.json)
            return 0 if payload["status"] == "ok" else 1

    if args.command == "azure-openai":
        if args.azure_command == "status":
            _print(_azure_status_payload(), as_json=args.json)
            return 0

        if args.azure_command == "complete":
            payload = asyncio.run(
                _run_azure_complete(
                    instructions=args.instructions,
                    user_input=args.input,
                    model=args.model,
                )
            )
            _print(payload, as_json=args.json)
            return 0 if payload["status"] == "ok" else 1

    parser.error(f"Unknown command: {args.command}")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
