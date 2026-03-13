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
from .llm import ModelSelection

DEFAULT_OUTPUT_DIR = Path(".teambot/demo-runs")



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
        default=DEFAULT_OUTPUT_DIR,
        help="Base directory where TeamAutobot demo run outputs are written",
    )
    demo_parser.add_argument("--provider", default="demo", help="Provider name for model selection")
    demo_parser.add_argument("--model", default="scripted", help="Model name for model selection")
    demo_parser.add_argument("--json", action="store_true", help="Emit JSON")
    return parser



def _status_payload(*, env_loaded: bool) -> dict[str, Any]:
    return {
        "env_loaded": env_loaded,
        "name": "TeamAutobot",
        "version": __version__,
        "python": platform.python_version(),
        "runtime": "ready",
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

    parser.error(f"Unknown command: {args.command}")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
