import os
import re
import time
from dataclasses import dataclass
from enum import Enum

from groq import Groq
from dotenv import load_dotenv

from doc_checker.verifier import VerificationResult, Verdict

load_dotenv()


# ── Data models ────────────────────────────────────────────────────────────────

class ConfidenceLevel(Enum):
    HIGH   = "high"    # auto-fix: create PR directly
    LOW    = "low"     # flag for human review with draft


@dataclass
class RepairResult:
    """The output of attempting to repair a stale doc section."""
    verification: VerificationResult
    original_content: str
    corrected_content: str
    confidence_level: ConfidenceLevel
    validation_passed: bool
    validation_notes: str
    ready_for_pr: bool             # True only if high confidence + validation passed


# ── Prompt builders ────────────────────────────────────────────────────────────

def build_repair_prompt(result: VerificationResult) -> str:

    change = result.suspect.triggered_by
    return f"""You are a technical documentation editor.

A code change has made part of a documentation section inaccurate.
Your job is to fix ONLY the inaccurate parts. Do not rewrite the whole section.
Preserve the original writing style, tone, heading structure, and code examples.
Only change what is factually wrong.

## The Code Change

**File:** `{change.file_path}`
**Changed entity:** `{change.function_name}`

**Before:**
```python
{change.old_code}
```

**After:**
```python
{change.new_code}
```

## What Is Wrong (Diagnosis)

{result.diagnosis}

## Current Documentation Section

**Section:** {result.suspect.heading_path}

{result.suspect.content}

## Your Task

Rewrite the documentation section with ONLY the inaccurate parts corrected.
- Keep all accurate information exactly as-is
- Keep the same markdown formatting and structure
- Keep the same code examples, updating only what changed
- Do not add new sections or information not already present
- Do not change the writing style or tone

Respond with ONLY the corrected markdown content, nothing else.
No preamble, no explanation, no code fences around the whole response.
"""


def build_validation_prompt(
    result: VerificationResult,
    corrected_content: str,
) -> str:
    change = result.suspect.triggered_by
    return f"""You are a documentation reviewer checking if a correction is accurate.

## The CURRENT code (this is what the code does RIGHT NOW)

```python
{change.new_code}
```

## The corrected documentation

{corrected_content}

## Staleness that was fixed

{result.diagnosis}

## Your job

Does the corrected documentation match the CURRENT code shown above?
Ignore the old code entirely — only compare the corrected doc to the current code.

Simple check: if the doc says "1800 seconds" or "30 minutes" and the current code 
has TOKEN_EXPIRY_SECONDS = 1800, that is CORRECT. Mark passed=true.

Respond with ONLY this JSON:
{{
  "passed": true | false,
  "confidence": <float 0.0-1.0>,
  "notes": "<one sentence: confirm what was correctly fixed, or what is still wrong>"
}}
"""


# ── LLM client ─────────────────────────────────────────────────────────────────

class RepairClient:

    def __init__(self):
        api_key = os.getenv("GROQ_API_KEY")
        if not api_key:
            raise ValueError("GROQ_API_KEY not set in .env")
        self.client = Groq(api_key=api_key)
        self.model = "llama-3.3-70b-versatile"
        print("[RepairClient] Ready.")

    def call(self, prompt: str, retries: int = 3) -> str:
        for attempt in range(retries):
            try:
                response = self.client.chat.completions.create(
                    model=self.model,
                    messages=[{"role": "user", "content": prompt}],
                    temperature=0.2,
                )
                return response.choices[0].message.content.strip()
            except Exception as e:
                print(f"[RepairClient] Attempt {attempt + 1} failed: {e}")
                if attempt < retries - 1:
                    time.sleep(2 ** attempt)
        return ""


# ── Validation parser ──────────────────────────────────────────────────────────

def parse_validation_response(raw: str) -> tuple[bool, float, str]:

    import json
    try:
        cleaned = raw.strip()
        if cleaned.startswith("```"):
            cleaned = "\n".join(cleaned.split("\n")[1:-1])
        data = json.loads(cleaned)
        passed = bool(data.get("passed", False))
        confidence = float(data.get("confidence", 0.5))
        notes = data.get("notes", "No notes.")
        return passed, confidence, notes
    except Exception as e:
        print(f"[Repairer] Failed to parse validation response: {e}")
        return False, 0.0, "Failed to parse validation response."


# ── Confidence scorer ──────────────────────────────────────────────────────────

def score_confidence(
    verification_confidence: float,
    validation_confidence: float,
    validation_passed: bool,
) -> ConfidenceLevel:
    """
    Determines whether the repair is high or low confidence.
    High confidence = auto-fix PR.
    Low confidence  = flag for human review.

    Threshold logic:
    - Both confidences must be high AND validation must pass for HIGH
    - Anything else is LOW — we'd rather be cautious
    """
    if (
        validation_passed
        and verification_confidence >= 0.8
        and validation_confidence >= 0.8
    ):
        return ConfidenceLevel.HIGH
    return ConfidenceLevel.LOW


# ── Main repairer ──────────────────────────────────────────────────────────────

class Repairer:

    def __init__(self):
        self.llm = RepairClient()

    def repair_all(
        self,
        results: list[VerificationResult],
    ) -> list[RepairResult]:
 
        stale = [r for r in results if r.verdict == Verdict.STALE]
        print(f"\n[Repairer] {len(stale)} stale sections to repair "
              f"(skipping {len(results) - len(stale)} accurate/uncertain).")

        repairs = []
        for i, result in enumerate(stale):
            print(f"\n[Repairer] Repairing ({i+1}/{len(stale)}): "
                  f"{result.suspect.heading_path}")
            repair = self.repair_one(result)
            repairs.append(repair)
            time.sleep(0.5)  # rate limit buffer

        return repairs

    def repair_one(self, result: VerificationResult) -> RepairResult:

        original = result.suspect.content

        # ── Pass 1: Generate correction ────────────────────────────────────────
        print("[Repairer]   Pass 1: generating correction...")
        repair_prompt = build_repair_prompt(result)
        corrected = self.llm.call(repair_prompt)

        if not corrected:
            return RepairResult(
                verification=result,
                original_content=original,
                corrected_content=original,
                confidence_level=ConfidenceLevel.LOW,
                validation_passed=False,
                validation_notes="LLM returned empty correction.",
                ready_for_pr=False,
            )

        # ── Pass 2: Validate correction ────────────────────────────────────────
        print("[Repairer]   Pass 2: validating correction...")
        validation_prompt = build_validation_prompt(result, corrected)
        validation_raw = self.llm.call(validation_prompt)

        val_passed, val_confidence, val_notes = parse_validation_response(
            validation_raw
        )

        print(f"[Repairer]   validation passed={val_passed}, "
              f"confidence={val_confidence:.2f}")
        print(f"[Repairer]   notes: {val_notes}")

        # ── Score confidence ───────────────────────────────────────────────────
        confidence_level = score_confidence(
            verification_confidence=result.confidence,
            validation_confidence=val_confidence,
            validation_passed=val_passed,
        )

        ready = (
            confidence_level == ConfidenceLevel.HIGH
            and val_passed
        )

        print(f"[Repairer]   confidence_level={confidence_level.value}, "
              f"ready_for_pr={ready}")

        return RepairResult(
            verification=result,
            original_content=original,
            corrected_content=corrected,
            confidence_level=confidence_level,
            validation_passed=val_passed,
            validation_notes=val_notes,
            ready_for_pr=ready,
        )