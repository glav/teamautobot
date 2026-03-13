import sys

from load_env import load_env
from teamautobot.cli import main as cli_main


def main() -> int:
    load_env(verbose=False)
    if len(sys.argv) == 1:
        return cli_main(["status"])
    return cli_main(sys.argv[1:])


if __name__ == "__main__":
    raise SystemExit(main())
