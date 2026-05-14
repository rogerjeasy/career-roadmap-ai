#!/usr/bin/env python3
"""
Pre-commit scanner: detects hardcoded secrets in staged files.

Scans only files staged for commit (git diff --cached). Exits 1 if any
secrets are found, which aborts the commit.
"""

import re
import subprocess
import sys
from pathlib import Path

# ── Patterns that indicate a real secret value is hardcoded ──────────────────

# Variable name patterns that are secret-sensitive
SECRET_NAMES = re.compile(
    r"""(?xi)
    (?:
        api[_\-]?key | secret[_\-]?key | secret | password | passwd | pwd |
        token | auth[_\-]?token | access[_\-]?token | refresh[_\-]?token |
        private[_\-]?key | signing[_\-]?key | encryption[_\-]?key |
        database[_\-]?url | db[_\-]?url | redis[_\-]?url |
        connection[_\-]?string | dsn |
        client[_\-]?secret | client[_\-]?id |
        webhook[_\-]?secret | jwt[_\-]?secret | session[_\-]?secret |
        sentry[_\-]?dsn | smtp[_\-]?pass | sendgrid[_\-]?key |
        stripe[_\-]?key | twilio[_\-]?token | slack[_\-]?token |
        firebase[_\-]?key | anthropic[_\-]?key | openai[_\-]?key
    )
""",
    re.IGNORECASE,
)

# Assignment patterns: catches both Python and .env style
ASSIGNMENT = re.compile(
    r"""(?xi)
    (?P<name>[A-Za-z_][A-Za-z0-9_]*)          # variable name
    \s* [=:] \s*                                # = or :
    (?P<quote>["']?)                            # optional quote
    (?P<value>[^\s"'#\n]{8,})                   # value (min 8 chars, no whitespace/quote)
    (?P=quote)                                  # closing quote
""",
)

# Provider-specific token prefixes that are always secrets when appearing as values
KNOWN_PREFIXES = re.compile(
    r"""(?x)
    (?:
        sk-ant-[A-Za-z0-9\-_]{20,} |   # Anthropic
        sk-[A-Za-z0-9]{20,} |           # OpenAI
        xoxb-[0-9\-]+ |                 # Slack bot token
        xoxp-[0-9\-]+ |                 # Slack user token
        ghp_[A-Za-z0-9]{36} |           # GitHub personal access token
        ghs_[A-Za-z0-9]{36} |           # GitHub Actions token
        AIza[0-9A-Za-z\-_]{35} |        # Google API key
        AKIA[0-9A-Z]{16} |              # AWS access key ID
        [0-9a-f]{32}:[0-9a-f]{32} |     # Generic key:secret pair
        postgresql://[^@]+:[^@]+@[^/]   # PostgreSQL DSN with credentials
    )
""",
)

# Values that are safe — placeholders, references, empty
SAFE_VALUE = re.compile(
    r"""(?xi)
    ^(
        your[-_]?.*          | # your-key-here, your_api_key
        <.*>                 | # <API_KEY>
        \$\{.*\}             | # ${API_KEY}
        \$[A-Z_]+            | # $API_KEY
        os\.                 | # os.getenv / os.environ
        env\[                | # env["KEY"]
        getenv               |
        environ              |
        process\.env         | # Node.js
        settings\.           | # settings.api_key
        config\.             |
        None | null | false | true | "" | ''
        | \*+ | xxx+ | zzz+ | placeholder | changeme | replace_me | dummy | test
    )$
""",
    re.IGNORECASE,
)

# Files to always skip (binary, generated, lock files)
SKIP_EXTENSIONS = {
    ".png", ".jpg", ".jpeg", ".gif", ".ico", ".svg", ".pdf", ".docx",
    ".zip", ".tar", ".gz", ".whl", ".pyc", ".pyo", ".so", ".dll", ".exe",
    ".lock", ".sum",
}
SKIP_PATHS = {
    ".git", "node_modules", ".venv", "__pycache__", ".mypy_cache",
    ".pytest_cache", "dist", "build", ".next",
}


def get_staged_files() -> list[Path]:
    result = subprocess.run(
        ["git", "diff", "--cached", "--name-only", "--diff-filter=ACM"],
        capture_output=True, text=True,
    )
    return [Path(p) for p in result.stdout.splitlines() if p.strip()]


def should_skip(path: Path) -> bool:
    if path.suffix.lower() in SKIP_EXTENSIONS:
        return True
    return any(part in SKIP_PATHS for part in path.parts)


def get_staged_content(path: Path) -> str:
    """Return the staged (index) content of the file, not the working tree."""
    result = subprocess.run(
        ["git", "show", f":{path}"],
        capture_output=True,
    )
    try:
        return result.stdout.decode("utf-8", errors="replace")
    except Exception:
        return ""


def scan_file(path: Path) -> list[tuple[int, str, str]]:
    """Return list of (line_number, variable_name, value) findings."""
    content = get_staged_content(path)
    findings: list[tuple[int, str, str]] = []

    for lineno, line in enumerate(content.splitlines(), start=1):
        stripped = line.strip()

        # Skip comments and obvious non-assignments
        if stripped.startswith(("#", "//", "/*", "*", "<!--", "import ", "from ")):
            continue

        # Check for known provider token patterns anywhere in the line
        for match in KNOWN_PREFIXES.finditer(line):
            findings.append((lineno, "token", match.group()))

        # Check assignment patterns with secret-looking variable names
        for match in ASSIGNMENT.finditer(line):
            name = match.group("name")
            value = match.group("value")
            if SECRET_NAMES.search(name) and not SAFE_VALUE.match(value):
                findings.append((lineno, name, value))

    return findings


def redact(value: str) -> str:
    if len(value) <= 8:
        return "****"
    return value[:4] + "****" + value[-2:]


def main() -> int:
    staged = get_staged_files()
    if not staged:
        return 0

    total_findings = 0

    for path in staged:
        if should_skip(path):
            continue
        findings = scan_file(path)
        if findings:
            if total_findings == 0:
                print("\n\033[31m[pre-commit] Hardcoded secrets detected — commit blocked.\033[0m\n")
            total_findings += len(findings)
            print(f"  \033[33m{path}\033[0m")
            for lineno, name, value in findings:
                print(f"    line {lineno:4d}  {name} = {redact(value)}")
            print()

    if total_findings:
        print(
            "\033[31mFix: move secrets to environment variables or .env (git-ignored).\033[0m\n"
            "To bypass in an emergency: git commit --no-verify\n"
        )
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
