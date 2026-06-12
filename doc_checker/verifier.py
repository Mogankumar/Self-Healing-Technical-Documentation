import os
import json
import time
from dataclasses import dataclass
from enum import Enum

from groq import Groq
from dotenv import load_dotenv

from doc_checker.detector import SuspectSection

load_dotenv()


# ── Data models ────────────────────────────────────────────────────────────────

class Verdict(Enum):
    ACCURATE   = "accurate"    # doc is still correct
    STALE      = "stale"       # doc is wrong and needs updating
    UNCERTAIN  = "uncertain"   # LLM isn't sure; flag for human review


@dataclass
class VerificationResult:
    """The LLM's verdict on a single suspect section."""
    suspect: SuspectSection
    verdict: Verdict
    diagnosis: str        # what specifically is wrong (if stale)
    confidence: float     # 0.0 - 1.0, how confident the LLM is
    raw_response: str     # full LLM response for debugging


# ── Prompt builder ─────────────────────────────────────────────────────────────

def build_verification_prompt(suspect: SuspectSection) -> str:
    change = suspect.triggered_by
    return f"""You are a strict documentation accuracy auditor.

Your ONLY job is to check if the documentation matches the current code exactly.
If the code changed and the documentation still reflects the OLD value, it is STALE.
Do not give benefit of the doubt. Do not say "approximately correct". Be strict.

## Code Change

**File:** `{change.file_path}`
**Changed entity:** `{change.function_name}`

**BEFORE (old code):**
```python
{change.old_code}
```

**AFTER (new code — this is what the code does NOW):**
```python
{change.new_code}
```

## Documentation Section to Check

**Section:** {suspect.heading_path}
**File:** {suspect.file_path}

**Content:**
{suspect.content}

## Strict Accuracy Rules

- If the doc mentions a number/value that matches the OLD code but not the NEW code → STALE
- If the doc describes behavior that matched the OLD code but not the NEW code → STALE  
- If the doc is completely unrelated to this specific change → ACCURATE
- If you cannot tell without more context → UNCERTAIN
- "1 hour" and "3600 seconds" are the same value. "30 minutes" and "1800 seconds" are the same value.

## Response Format

Respond with ONLY a JSON object:
{{
  "verdict": "accurate" | "stale" | "uncertain",
  "confidence": <float 0.0-1.0>,
  "diagnosis": "<one specific sentence about what is wrong, or 'Documentation is accurate.' if correct>"
}}

No text outside the JSON object.
"""


# ── LLM client ─────────────────────────────────────────────────────────────────

class GroqClient:

    def __init__(self):
        api_key = os.getenv("GROQ_API_KEY")
        if not api_key:
            raise ValueError("GROQ_API_KEY not set in .env")
        self.client = Groq(api_key=api_key)
        self.model = "llama-3.1-8b-instant"
        print("[GroqClient] Ready.")

    def call(self, prompt: str, retries: int = 3) -> str:
        """Calls Groq and returns the raw text response."""
        for attempt in range(retries):
            try:
                response = self.client.chat.completions.create(
                    model=self.model,
                    messages=[{"role": "user", "content": prompt}],
                    temperature=0.1,   # low temperature  more deterministic JSON
                )
                return response.choices[0].message.content.strip()
            except Exception as e:
                print(f"[GroqClient] Attempt {attempt + 1} failed: {e}")
                if attempt < retries - 1:
                    time.sleep(2 ** attempt)
        return ""


# ── Response parser ────────────────────────────────────────────────────────────

def parse_verdict_response(raw: str) -> tuple[Verdict, float, str]:

    try:
        cleaned = raw.strip()
        if cleaned.startswith("```"):
            cleaned = "\n".join(cleaned.split("\n")[1:-1])

        data = json.loads(cleaned)

        verdict_str = data.get("verdict", "uncertain").lower()
        verdict = Verdict(verdict_str) if verdict_str in Verdict._value2member_map_ else Verdict.UNCERTAIN
        confidence = float(data.get("confidence", 0.5))
        diagnosis = data.get("diagnosis", "No diagnosis provided.")

        return verdict, confidence, diagnosis

    except Exception as e:
        print(f"[Verifier] Failed to parse LLM response: {e}")
        print(f"[Verifier] Raw response was: {raw[:200]}")
        return Verdict.UNCERTAIN, 0.0, "Failed to parse LLM response."


# ── Main verifier ──────────────────────────────────────────────────────────────

class Verifier:


    def __init__(self):
        self.llm = GroqClient()

    def verify_all(
        self,
        suspects: list[SuspectSection],
        skip_duplicates: bool = True,
    ) -> list[VerificationResult]:

        results = []
        seen_headings = set()

        for i, suspect in enumerate(suspects):
            if skip_duplicates and suspect.heading_path in seen_headings:
                print(f"[Verifier] Skipping duplicate: {suspect.heading_path}")
                continue
            seen_headings.add(suspect.heading_path)

            print(f"\n[Verifier] Verifying ({i+1}/{len(suspects)}): {suspect.heading_path}")
            result = self.verify_one(suspect)
            results.append(result)

            time.sleep(0.5)

        return results

    def verify_one(self, suspect: SuspectSection) -> VerificationResult:
        prompt = build_verification_prompt(suspect)
        raw = self.llm.call(prompt)

        if not raw:
            return VerificationResult(
                suspect=suspect,
                verdict=Verdict.UNCERTAIN,
                diagnosis="LLM returned empty response.",
                confidence=0.0,
                raw_response="",
            )

        verdict, confidence, diagnosis = parse_verdict_response(raw)

        print(f"[Verifier]   verdict={verdict.value}, confidence={confidence:.2f}")
        print(f"[Verifier]   diagnosis: {diagnosis}")

        return VerificationResult(
            suspect=suspect,
            verdict=verdict,
            diagnosis=diagnosis,
            confidence=confidence,
            raw_response=raw,
        )