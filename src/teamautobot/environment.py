from __future__ import annotations

from dotenv import load_dotenv


def load_env(*, verbose: bool = False) -> bool:
    """Locate and load a .env file, returning whether one was loaded."""
    env_loaded = load_dotenv()
    if verbose:
        print(f"Env variables loaded: {env_loaded}")
    return env_loaded
