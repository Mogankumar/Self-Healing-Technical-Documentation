import ast
import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

# ── Data models ────────────────────────────────────────────────────────────────

@dataclass
class CodeChunk:
    id: str                  # e.g. "src/auth.py::verify_token"
    file_path: str
    name: str                # function/class name
    chunk_type: str          # "function" | "class" | "method"
    signature: str           # def verify_token(token: str) -> bool:
    docstring: Optional[str]
    body: str                # full source of the chunk
    lineno: int              # where it starts in the file
    mentioned_names: list[str] = field(default_factory=list)  # names referenced inside


@dataclass
class DocSection:
    id: str                  # e.g. "docs/api.md::Authentication > Verifying Tokens"
    file_path: str
    heading_path: str        # "Authentication > Verifying Tokens"
    content: str             # raw markdown content of the section
    depth: int               # heading level (1-6)
    mentioned_names: list[str] = field(default_factory=list)  # code names found in text


# ── Code parser ────────────────────────────────────────────────────────────────

class CodeParser:

    SKIP_DIRS = {'.git', '__pycache__', 'venv', '.venv', 'node_modules', '.mypy_cache'}

    def parse_directory(self, root: str) -> list[CodeChunk]:
        chunks = []
        for path in Path(root).rglob("*.py"):
            if any(skip in path.parts for skip in self.SKIP_DIRS):
                continue
            chunks.extend(self.parse_file(str(path)))
        return chunks

    def parse_file(self, file_path: str) -> list[CodeChunk]:
        try:
            source = Path(file_path).read_text(encoding="utf-8")
            tree = ast.parse(source)
        except (SyntaxError, UnicodeDecodeError):
            return []  # skip unparseable files gracefully

        chunks = []
        source_lines = source.splitlines()

        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                chunk = self._extract_function(node, file_path, source_lines)
                if chunk:
                    chunks.append(chunk)
            elif isinstance(node, ast.ClassDef):
                chunk = self._extract_class(node, file_path, source_lines)
                if chunk:
                    chunks.append(chunk)

        return chunks

    def _extract_function(self, node, file_path, source_lines) -> Optional[CodeChunk]:
        name = node.name
        if name.startswith("_") and not name.startswith("__"):
            return None  # skip private helpers; they rarely have docs

        docstring = ast.get_docstring(node)
        signature = self._build_signature(node)
        body = "\n".join(source_lines[node.lineno - 1 : node.end_lineno])
        chunk_id = f"{file_path}::{name}"
        mentioned = self._extract_mentioned_names(body)

        return CodeChunk(
            id=chunk_id,
            file_path=file_path,
            name=name,
            chunk_type="function",
            signature=signature,
            docstring=docstring,
            body=body,
            lineno=node.lineno,
            mentioned_names=mentioned,
        )

    def _extract_class(self, node, file_path, source_lines) -> Optional[CodeChunk]:
        name = node.name
        docstring = ast.get_docstring(node)
        body = "\n".join(source_lines[node.lineno - 1 : node.end_lineno])
        chunk_id = f"{file_path}::{name}"
        mentioned = self._extract_mentioned_names(body)

        # Build a minimal signature showing base classes
        bases = [ast.unparse(b) for b in node.bases]
        signature = f"class {name}({', '.join(bases)}):" if bases else f"class {name}:"

        return CodeChunk(
            id=chunk_id,
            file_path=file_path,
            name=name,
            chunk_type="class",
            signature=signature,
            docstring=docstring,
            body=body,
            lineno=node.lineno,
            mentioned_names=mentioned,
        )

    def _build_signature(self, node) -> str:
        try:

            full = ast.unparse(node)
            return full.split("\n")[0].replace("    ", "")
        except Exception:
            return f"def {node.name}(...):"

    def _extract_mentioned_names(self, text: str) -> list[str]:

        return list(set(re.findall(r'\b[a-zA-Z_][a-zA-Z0-9_]{2,}\b', text)))


# ── Markdown parser ────────────────────────────────────────────────────────────

class MarkdownParser:

    SKIP_DIRS = {'.git', 'venv', '.venv', 'node_modules'}
    HEADING_RE = re.compile(r'^(#{1,6})\s+(.+)$', re.MULTILINE)

    def parse_directory(self, root: str) -> list[DocSection]:
        sections = []
        for path in Path(root).rglob("*.md"):
            if any(skip in path.parts for skip in self.SKIP_DIRS):
                continue
            sections.extend(self.parse_file(str(path)))
        return sections

    def parse_file(self, file_path: str) -> list[DocSection]:
        try:
            content = Path(file_path).read_text(encoding="utf-8")
        except UnicodeDecodeError:
            return []

        sections = []
        matches = list(self.HEADING_RE.finditer(content))

        for i, match in enumerate(matches):
            depth = len(match.group(1))       # number of # characters
            heading = match.group(2).strip()
            start = match.start()
            end = matches[i + 1].start() if i + 1 < len(matches) else len(content)
            section_content = content[start:end].strip()

            heading_path = self._build_heading_path(matches, i)
            section_id = f"{file_path}::{heading_path}"
            mentioned = self._extract_code_names(section_content)

            sections.append(DocSection(
                id=section_id,
                file_path=file_path,
                heading_path=heading_path,
                content=section_content,
                depth=depth,
                mentioned_names=mentioned,
            ))

        return sections

    def _build_heading_path(self, matches, current_idx) -> str:

        current_depth = len(matches[current_idx].group(1))
        current_heading = matches[current_idx].group(2).strip()

        path_parts = [current_heading]
        depth_to_beat = current_depth

        for j in range(current_idx - 1, -1, -1):
            d = len(matches[j].group(1))
            if d < depth_to_beat:
                path_parts.insert(0, matches[j].group(2).strip())
                depth_to_beat = d

        return " > ".join(path_parts)

    def _extract_code_names(self, text: str) -> list[str]:

        # Prioritise backtick-wrapped names — these are explicit code refs
        backtick_names = re.findall(r'`([a-zA-Z_][a-zA-Z0-9_]*)`', text)
        # Also grab general identifiers from the prose
        prose_names = re.findall(r'\b[a-zA-Z_][a-zA-Z0-9_]{3,}\b', text)
        return list(set(backtick_names + prose_names))