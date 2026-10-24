"""Check tracked + untracked nonignored project files without printing secret values."""

import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PATTERNS = [
    re.compile(rb"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
    re.compile(rb"\bAKIA[0-9A-Z]{16}\b"),
    re.compile(rb"\bgh[pousr]_[A-Za-z0-9]{30,}\b"),
    re.compile(rb"\bsk-[A-Za-z0-9_-]{28,}\b"),
    re.compile(
        rb"(?i)(?:api[_-]?key|access[_-]?token|secret[_-]?key)\s*[=:]\s*[\x22\x27][A-Za-z0-9_+/=-]{24,}[\x22\x27]"
    ),
]


def main():
    result = subprocess.run(
        ["git", "ls-files", "-z", "--cached", "--others", "--exclude-standard"],
        cwd=ROOT,
        capture_output=True,
        check=True,
    )
    problems = []
    for raw in set(result.stdout.split(b"\0")):
        if not raw:
            continue
        relative = raw.decode()
        path = ROOT / relative
        if (
            relative.startswith(("ml/data/", "data/private/", "data/imports/", ".nessy/"))
            or (path.name.startswith(".env") and path.name != ".env.example")
            or path.suffix.lower() in (".pem", ".key", ".p12", ".pfx", ".dump")
            or (path.suffix == ".json" and path.name.startswith(("credentials", "service-account")))
        ):
            problems.append((relative, "private file is tracked"))
            continue
        # Scan the actual staged blob too: a clean worktree does not imply a clean index.
        staged = subprocess.run(["git", "show", ":" + relative], cwd=ROOT, capture_output=True)
        versions = [staged.stdout] if staged.returncode == 0 else []
        if path.is_file():
            versions.append(path.read_bytes())
        if any(pattern.search(content) for content in versions for pattern in PATTERNS):
            problems.append((relative, "potential secret"))
    for path, reason in sorted(problems):
        print(f"{path}: {reason}")
    if problems:
        print("Check failed. Secret values were not printed.")
        return 1
    print(
        "No matching secret patterns or tracked private datasets found. This is not a guarantee against all leaks."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
