from __future__ import annotations

from pathlib import Path

from .fixture import fixture_json


def main() -> None:
    repository_root = Path(__file__).parents[3]
    target = repository_root / "course/fixtures/course-btc-l2-v1.json"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(f"{fixture_json()}\n", encoding="utf-8")


if __name__ == "__main__":
    main()
