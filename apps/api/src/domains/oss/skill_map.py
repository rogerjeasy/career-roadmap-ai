"""Open-Source Contribution Finder — pure skill→language mapping.

Translates free-text user skills into GitHub language qualifiers and keeps the
leftover skills as keyword hints. Pure and table-driven so it is trivially
unit-testable and easy to extend.
"""
from __future__ import annotations

# Lowercased skill/alias → canonical GitHub language qualifier.
_SKILL_TO_LANGUAGE: dict[str, str] = {
    "python": "Python",
    "django": "Python",
    "flask": "Python",
    "fastapi": "Python",
    "pandas": "Python",
    "javascript": "JavaScript",
    "js": "JavaScript",
    "node": "JavaScript",
    "node.js": "JavaScript",
    "react": "TypeScript",
    "next.js": "TypeScript",
    "nextjs": "TypeScript",
    "typescript": "TypeScript",
    "ts": "TypeScript",
    "angular": "TypeScript",
    "vue": "Vue",
    "go": "Go",
    "golang": "Go",
    "rust": "Rust",
    "java": "Java",
    "kotlin": "Kotlin",
    "spring": "Java",
    "c#": "C#",
    "csharp": "C#",
    ".net": "C#",
    "dotnet": "C#",
    "c++": "C++",
    "cpp": "C++",
    "c": "C",
    "ruby": "Ruby",
    "rails": "Ruby",
    "php": "PHP",
    "laravel": "PHP",
    "swift": "Swift",
    "ios": "Swift",
    "android": "Kotlin",
    "scala": "Scala",
    "elixir": "Elixir",
    "haskell": "Haskell",
    "r": "R",
    "sql": "PLpgSQL",
    "solidity": "Solidity",
    "dart": "Dart",
    "flutter": "Dart",
    "shell": "Shell",
    "bash": "Shell",
}


def derive_languages(skills: list[str]) -> list[str]:
    """Map skills to a de-duplicated, ordered list of GitHub languages."""
    out: list[str] = []
    for skill in skills:
        lang = _SKILL_TO_LANGUAGE.get(skill.strip().lower())
        if lang and lang not in out:
            out.append(lang)
    return out


def keyword_hints(skills: list[str]) -> list[str]:
    """Skills that don't map to a language — usable as free-text search hints."""
    out: list[str] = []
    for skill in skills:
        key = skill.strip().lower()
        if key and key not in _SKILL_TO_LANGUAGE and skill.strip() not in out:
            out.append(skill.strip())
    return out
