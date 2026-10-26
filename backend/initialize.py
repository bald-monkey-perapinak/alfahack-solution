"""Apply schema and load the configured dataset before the queue worker starts."""

import subprocess
import sys


def main() -> None:
    subprocess.run([sys.executable, "-m", "backend.manage", "migrate"], check=True)
    subprocess.run([sys.executable, "-m", "backend.bootstrap"], check=True)


if __name__ == "__main__":
    main()
