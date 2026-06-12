"""
Main entry point for the GitHub Action.
Reads environment variables, runs the full pipeline,
and reports results back to GitHub.
"""

import os
import sys
from dotenv import load_dotenv

load_dotenv()


def main():
    # ── Read config from environment ───────────────────────────────────────────
    repo_root     = os.getenv("REPO_ROOT", ".")
    index_path    = os.getenv("INDEX_PATH", "docs-index.json")
    pr_number_str = os.getenv("PR_NUMBER", "")
    base_branch   = os.getenv("BASE_BRANCH", "HEAD~1")

    print(f"[Main] Starting self-healing docs pipeline")
    print(f"[Main] repo_root={repo_root}, index_path={index_path}")

    # ── Phase 2: Detect changes ────────────────────────────────────────────────
    from doc_checker.detector import ChangeDetector
    detector = ChangeDetector(repo_root, index_path)
    suspects = detector.detect(base_branch)

    if not suspects:
        print("[Main] No suspect sections found. All docs look good!")
        _write_outputs(sections_checked=0, sections_fixed=0, sections_flagged=0)
        return

    # ── Phase 3: Verify with LLM ───────────────────────────────────────────────
    from doc_checker.verifier import Verifier, Verdict
    verifier = Verifier()
    results = verifier.verify_all(suspects)

    accurate_count = sum(1 for r in results if r.verdict == Verdict.ACCURATE)
    stale_count    = sum(1 for r in results if r.verdict == Verdict.STALE)
    print(f"[Main] Verification: {accurate_count} accurate, {stale_count} stale")

    # ── Phase 4: Repair stale sections ────────────────────────────────────────
    from doc_checker.repairer import Repairer
    repairer = Repairer()
    repairs = repairer.repair_all(results)

    # ── Phase 5: GitHub integration ────────────────────────────────────────────
    if pr_number_str and os.getenv("GITHUB_TOKEN") and os.getenv("GITHUB_REPOSITORY"):
        from doc_checker.github_integration import GitHubIntegration
        pr_number = int(pr_number_str)
        github = GitHubIntegration()
        output = github.process_repairs(
            repairs=repairs,
            pr_number=pr_number,
            verified_accurate_count=accurate_count,
        )
        _write_outputs(
            sections_checked=output.sections_checked,
            sections_fixed=output.sections_autofix,
            sections_flagged=output.sections_flagged,
        )
    else:
        # Running locally — just print results
        print("\n[Main] GitHub integration skipped (no PR_NUMBER or GITHUB_TOKEN)")
        print("\n=== FINAL RESULTS ===")
        for repair in repairs:
            print(f"\nSection:      {repair.verification.suspect.heading_path}")
            print(f"Verdict:      {repair.verification.verdict.value}")
            print(f"Ready for PR: {repair.ready_for_pr}")
            print(f"Corrected:\n{repair.corrected_content[:300]}")


def _write_outputs(sections_checked: int, sections_fixed: int, sections_flagged: int):
    """Writes outputs to GitHub Actions output file if running in CI."""
    github_output = os.getenv("GITHUB_OUTPUT", "")
    if github_output:
        with open(github_output, "a") as f:
            f.write(f"sections_checked={sections_checked}\n")
            f.write(f"sections_fixed={sections_fixed}\n")
            f.write(f"sections_flagged={sections_flagged}\n")
    print(f"[Main] Done. checked={sections_checked}, "
          f"fixed={sections_fixed}, flagged={sections_flagged}")


if __name__ == "__main__":
    main()