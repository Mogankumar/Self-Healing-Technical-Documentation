from os import name
import json
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path


# ── Data models ────────────────────────────────────────────────────────────────

@dataclass
class CodeChange:
    """One meaningful change detected from the git diff."""
    chunk_id: str        # e.g. "src/auth.py::verify_token"
    file_path: str
    function_name: str
    change_type: str     # "modified" | "added" | "removed"
    old_code: str        # code before the change
    new_code: str        # code after the change


@dataclass
class SuspectSection:
    section_id: str
    file_path: str
    heading_path: str
    content: str
    triggered_by: CodeChange   # which change flagged this section


# ── Git diff parser ────────────────────────────────────────────────────────────

class DiffParser:

    def get_changed_files(self, repo_root: str, base_branch: str = "HEAD~1") -> list[str]:

        try:
            result = subprocess.run(
                ["git", "diff", "--name-only", base_branch, "HEAD"],
                cwd=repo_root,
                capture_output=True,
                text=True,
            )
            files = result.stdout.strip().split("\n")
            return [f for f in files if f.endswith(".py") and f]
        except Exception as e:
            print(f"[DiffParser] git error: {e}")
            return []

    def get_diff(self, repo_root: str, file_path: str, base_branch: str = "HEAD~1") -> str:
        try:
            result = subprocess.run(
                ["git", "diff", base_branch, "HEAD", "--", file_path],
                cwd=repo_root,
                capture_output=True,
                text=True,
            )
            return result.stdout
        except Exception:
            return ""

    def get_file_content_at(
        self, repo_root: str, file_path: str, ref: str
    ) -> str:
        try:
            result = subprocess.run(
                ["git", "show", f"{ref}:{file_path}"],
                cwd=repo_root,
                capture_output=True,
                text=True,
            )
            return result.stdout
        except Exception:
            return ""


# ── Change filter ──────────────────────────────────────────────────────────────

class ChangeFilter:

    # Changes in these files never affect docs
    SKIP_PATTERNS = [
        r"test_.*\.py$",
        r".*_test\.py$",
        r"conftest\.py$",
        r"setup\.py$",
    ]

    def is_meaningful(self, diff: str) -> bool:
        if not diff.strip():
            return False

        added_lines = [
            l[1:] for l in diff.split("\n")
            if l.startswith("+") and not l.startswith("+++")
        ]
        removed_lines = [
            l[1:] for l in diff.split("\n")
            if l.startswith("-") and not l.startswith("---")
        ]

        meaningful_added = [l for l in added_lines if self._is_meaningful_line(l)]
        meaningful_removed = [l for l in removed_lines if self._is_meaningful_line(l)]

        return bool(meaningful_added or meaningful_removed)

    def should_skip_file(self, file_path: str) -> bool:
        return any(re.search(p, file_path) for p in self.SKIP_PATTERNS)

    def _is_meaningful_line(self, line: str) -> bool:
        stripped = line.strip()
        if not stripped:
            return False
        if stripped.startswith("#"):
            return False
        if stripped.startswith('"""') or stripped.startswith("'''"):
            return False
        if stripped in ('"""', "'''"):
            return False
        return True


# ── Function extractor ─────────────────────────────────────────────────────────

class FunctionExtractor:

    def extract_function(self, source: str, function_name: str) -> str:
        lines = source.split("\n")
        start = None
        indent = None

        for i, line in enumerate(lines):
            if re.match(rf"^(async\s+)?def\s+{re.escape(function_name)}\s*\(", line):
                start = i
                indent = len(line) - len(line.lstrip())
                break

        if start is None:
            return ""

        # Collect lines until we hit a new definition at the same indent level
        result = [lines[start]]
        for line in lines[start + 1:]:
            if line.strip() == "":
                result.append(line)
                continue
            current_indent = len(line) - len(line.lstrip())
            if current_indent <= indent and line.strip() and not line.strip().startswith("#"):
                break
            result.append(line)

        return "\n".join(result).strip()


# ── Main detector ──────────────────────────────────────────────────────────────

class ChangeDetector:


    def __init__(self, repo_root: str, index_path: str):
        self.repo_root = repo_root
        self.index = self.load_index(index_path)
        self.diff_parser = DiffParser()
        self.change_filter = ChangeFilter()
        self.extractor = FunctionExtractor()

    def load_index(self, index_path: str) -> dict:
        with open(index_path, "r") as f:
            return json.load(f)

    def detect(self, base_branch: str = "HEAD~1") -> list[SuspectSection]:
        print(f"\n[Detector] Scanning changes since {base_branch}...")

        changed_files = self.diff_parser.get_changed_files(self.repo_root, base_branch)
        print(f"[Detector] Changed Python files: {changed_files}")

        all_suspects: list[SuspectSection] = []

        for file_path in changed_files:
            if self.change_filter.should_skip_file(file_path):
                print(f"[Detector] Skipping {file_path} (test/config file)")
                continue

            diff = self.diff_parser.get_diff(self.repo_root, file_path, base_branch)
            if not self.change_filter.is_meaningful(diff):
                print(f"[Detector] Skipping {file_path} (no meaningful changes)")
                continue

            print(f"[Detector] Meaningful changes found in {file_path}")
            suspects = self.find_suspects(file_path, diff, base_branch)
            all_suspects.extend(suspects)

        print(f"[Detector] Found {len(all_suspects)} suspect doc sections total.")
        return all_suspects

    def find_chunk_mentioning(self, file_path: str, name: str) -> str:

        for chunk_id, chunk_data in self.index.get("chunks", {}).items():
            chunk_file = chunk_data["file_path"]
            ends_match = chunk_file.endswith(file_path)
            name_match = name in chunk_data.get("mentioned_names", [])
            in_links = chunk_id in self.index.get("links", {})

            if ends_match and name_match and in_links:
                print(f"[Detector]   Matched '{name}' via chunk {chunk_id}")
                return chunk_id

        # Second pass relax to name_match only if no exact file match found
        for chunk_id, chunk_data in self.index.get("chunks", {}).items():
            name_match = name in chunk_data.get("mentioned_names", [])
            in_links = chunk_id in self.index.get("links", {})
            if name_match and in_links:
                print(f"[Detector]   Matched '{name}' via name-only fallback: {chunk_id}")
                return chunk_id

        return ""

    def extract_constant_value(self, diff: str, name: str, removed: bool) -> str:

        prefix = "-" if removed else "+"
        for line in diff.split("\n"):
            if line.startswith(prefix) and not line.startswith(prefix * 3):
                content = line[1:].strip()
                if content.startswith(name):
                    return content
        return f"{name} = (not found in diff)"

    def find_suspects(
        self, file_path: str, diff: str, base_branch: str
    ) -> list[SuspectSection]:

        suspects = []

        changed_function_names = self.extract_changed_functions(diff)
        print(f"[Detector]   Changed functions in {file_path}: {changed_function_names}")

        old_content = self.diff_parser.get_file_content_at(
            self.repo_root, file_path, base_branch
        )
        new_content = self.diff_parser.get_file_content_at(
            self.repo_root, file_path, "HEAD"
        )

        for func_name in changed_function_names:
            chunk_id = None
            for indexed_id in self.index.get("links", {}).keys():
                indexed_file, indexed_func = indexed_id.rsplit("::", 1)
                if indexed_file.endswith(file_path) and indexed_func == func_name:
                    chunk_id = indexed_id
                    break

            if chunk_id not in self.index.get("links", {}):
                chunk_id = self.find_chunk_mentioning(file_path, func_name)

            if not chunk_id:
                print(f"[Detector]   {file_path}::{func_name} not in index — skipping")
                continue

            old_code = self.extractor.extract_function(old_content, func_name)
            new_code = self.extractor.extract_function(new_content, func_name)

            if not old_code and not new_code:
                old_code = self.extract_constant_value(diff, func_name, removed=True)
                new_code = self.extract_constant_value(diff, func_name, removed=False)

            change = CodeChange(
                chunk_id=chunk_id,
                file_path=file_path,
                function_name=func_name,
                change_type="modified",
                old_code=old_code,
                new_code=new_code,
            )

            linked_section_ids = self.index["links"][chunk_id]
            for section_id in linked_section_ids:
                section_data = self.index["sections"].get(section_id)
                if not section_data:
                    continue
                suspects.append(SuspectSection(
                    section_id=section_id,
                    file_path=section_data["file_path"],
                    heading_path=section_data["heading_path"],
                    content=section_data["content"],
                    triggered_by=change,
                ))

        return suspects

    def extract_changed_functions(self, diff: str) -> list[str]:

        changed_lines = [
            l[1:] for l in diff.split("\n")
            if (l.startswith("+") or l.startswith("-"))
            and not l.startswith("+++")
            and not l.startswith("---")
        ]

        names = set()

        for line in changed_lines:
            # Case 1 — changed function or class definition
            match = re.search(r"(async\s+)?def\s+([a-zA-Z_][a-zA-Z0-9_]*)\s*\(", line)
            if match:
                names.add(match.group(2))
                continue

            # Case 2 — changed module-level constant (ALL_CAPS = value)
            match = re.search(r"^([A-Z][A-Z0-9_]{2,})\s*=", line.strip())
            if match:
                names.add(match.group(1))
                continue

            # Case 3 — changed class-level attribute or dataclass field
            match = re.search(r"^\s{4}([a-zA-Z_][a-zA-Z0-9_]*)\s*[:=]", line)
            if match:
                names.add(match.group(1))

        return list(names)

    