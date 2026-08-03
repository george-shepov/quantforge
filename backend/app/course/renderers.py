from __future__ import annotations

import json
from typing import Any


PLATFORM_NAMES = (
    "guided",
    "expert",
    "instructor",
    "workbook",
    "kdp",
    "quiz",
    "youtube",
    "udemy",
    "pluralsight",
    "linkedin_learning",
    "marketing",
)


def _evidence_lines(result: dict[str, Any]) -> str:
    lines: list[str] = []
    for lab in result.get("labs", []):
        for delta in lab.get("delta", []):
            lines.append(
                f"| {delta['metric']} | {delta.get('expected')} | {delta.get('actual')} | "
                f"{delta.get('absolute_delta', '—')} | {delta['classification']} |"
            )
    return "\n".join(lines) or "| No measurements | — | — | — | data_quality_warning |"


def render_research_report(result: dict[str, Any]) -> str:
    provenance = result["provenance"]
    return f"""# QuantForge research report: {result['title']}

## Question
{result['question']}

## Hypothesis
{result['hypothesis']}

## Expected versus actual
| Measurement | Expected | Actual | Absolute delta | Classification |
|---|---:|---:|---:|---|
{_evidence_lines(result)}

## Invalidation conditions
{chr(10).join(f"- {item}" for item in result.get('invalidation_conditions', []))}

## Verdict
{result.get('verdict', 'continue_research')}

## Reproduction metadata
```json
{json.dumps(provenance, indent=2, sort_keys=True)}
```
"""


def render_platform_exports(result: dict[str, Any]) -> dict[str, str]:
    report = render_research_report(result)
    draft_notice = "> Source draft generated from executable evidence; recording, packaging, and platform submission are separate acceptance steps.\n\n"
    provenance = json.dumps(result["provenance"], sort_keys=True)
    evidence = _evidence_lines(result)
    return {
        "guided": f"# Guided laboratory\n\n{draft_notice}{result['question']}\n\n{report}",
        "expert": f"# Expert evidence view\n\n{draft_notice}{evidence}\n\nEvidence provenance: {provenance}",
        "instructor": f"# Instructor script\n\n{draft_notice}Ask: {result['question']}\nHypothesis: {result['hypothesis']}\n\n{report}",
        "workbook": f"# Learner workbook\n\n{draft_notice}Question: {result['question']}\n\nRecord the delta and explain why it occurred.\n\n{evidence}",
        "kdp": f"# {result['title']}\n\n{draft_notice}{report}",
        "quiz": f"# Quiz and assignment bank\n\n{draft_notice}1. What changed between expected and actual evidence?\n2. Which assumption could invalidate the verdict?\n\nScenario version: {result['provenance']['scenario_version']}",
        "youtube": f"# YouTube lesson\n\n{draft_notice}{result['title']}\n\n{report}",
        "udemy": f"# Udemy preview\n\n{draft_notice}{result['title']}\n\n{report}",
        "pluralsight": f"# Pluralsight audition\n\n{draft_notice}{result['title']}\n\n{report}",
        "linkedin_learning": f"# LinkedIn Learning sample\n\n{draft_notice}{result['title']}\n\n{report}",
        "marketing": f"# Landing page\n\n{draft_notice}{result['title']}\n\nRun the reproducible experiment. Do not confuse one result with a profitability claim.\n\nScenario version: {result['provenance']['scenario_version']}",
    }
