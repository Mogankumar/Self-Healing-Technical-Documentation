"""
Indexer — takes parsed code chunks and doc sections,
links them by name-matching and embedding similarity,
and persists the graph as docs-index.json.
"""

import json
import os
from dataclasses import asdict
from pathlib import Path
from typing import Any

import chromadb
from sentence_transformers import SentenceTransformer
from sklearn.metrics.pairwise import cosine_similarity
import numpy as np

from doc_checker.parser import CodeChunk, DocSection, CodeParser, MarkdownParser


# ── Constants ──────────────────────────────────────────────────────────────────

SIMILARITY_THRESHOLD = 0.75   # cosine similarity cutoff for semantic linking
INDEX_FILE = "docs-index.json"
EMBEDDING_MODEL = "all-MiniLM-L6-v2"  # fast, free, runs locally via sentence-transformers


# ── Embedder ───────────────────────────────────────────────────────────────────

class Embedder:
    """
    Wraps sentence-transformers to produce embeddings.
    Runs entirely locally — no API calls, no cost.
    """

    def __init__(self, model_name: str = EMBEDDING_MODEL):
        print(f"[Embedder] Loading model '{model_name}'...")
        self.model = SentenceTransformer(model_name)
        print("[Embedder] Model ready.")

    def embed_text(self, text: str) -> list[float]:
        return self.model.encode(text, convert_to_numpy=True).tolist()

    def embed_batch(self, texts: list[str]) -> list[list[float]]:
        return self.model.encode(texts, convert_to_numpy=True).tolist()


# ── Text builders ──────────────────────────────────────────────────────────────
# These decide what text we actually embed for each chunk/section.
# More context = better embeddings.

def chunk_to_embed_text(chunk: CodeChunk) -> str:
    """Build the text we embed for a code chunk."""
    parts = [chunk.signature]
    if chunk.docstring:
        parts.append(chunk.docstring)
    return "\n".join(parts)


def section_to_embed_text(section: DocSection) -> str:
    """Build the text we embed for a doc section."""
    # Use heading path + first 500 chars of content
    # (full content can be noisy; heading + intro is usually most signal-rich)
    return f"{section.heading_path}\n{section.content[:500]}"


# ── Linker ─────────────────────────────────────────────────────────────────────

class Linker:
    """
    Links code chunks to doc sections two ways:
    1. Lexical  — doc section mentions the chunk's name (fast, zero-cost)
    2. Semantic — cosine similarity between embeddings exceeds threshold
    """

    def __init__(self, embedder: Embedder):
        self.embedder = embedder

    def build_links(
        self,
        chunks: list[CodeChunk],
        sections: list[DocSection],
    ) -> dict[str, list[str]]:
        """
        Returns a dict mapping each chunk ID to a list of linked section IDs.

        Example:
            {
                "src/auth.py::verify_token": [
                    "docs/authentication.md::Authentication > Token Verification"
                ]
            }
        """
        print(f"[Linker] Building links for {len(chunks)} chunks and {len(sections)} sections...")

        # Step 1 — lexical links (name-matching)
        lexical_links = self._lexical_links(chunks, sections)

        # Step 2 — semantic links (embedding similarity)
        semantic_links = self._semantic_links(chunks, sections)

        # Merge both: union of links per chunk
        all_links: dict[str, set[str]] = {}
        for chunk in chunks:
            lex = set(lexical_links.get(chunk.id, []))
            sem = set(semantic_links.get(chunk.id, []))
            combined = lex | sem
            if combined:
                all_links[chunk.id] = combined

        # Log a summary
        total_links = sum(len(v) for v in all_links.values())
        print(f"[Linker] Done. {total_links} total links across {len(all_links)} chunks.")

        return {k: sorted(v) for k, v in all_links.items()}

    def _lexical_links(
        self,
        chunks: list[CodeChunk],
        sections: list[DocSection],
    ) -> dict[str, list[str]]:
        """
        Links a chunk to a section if the section's text explicitly
        mentions the chunk's name (in backticks or plain prose).
        """
        links: dict[str, list[str]] = {}

        for chunk in chunks:
            matched_sections = []
            for section in sections:
                if chunk.name in section.mentioned_names:
                    matched_sections.append(section.id)
            if matched_sections:
                links[chunk.id] = matched_sections

        lexical_count = sum(len(v) for v in links.values())
        print(f"[Linker]   Lexical pass: {lexical_count} links found.")
        return links

    def _semantic_links(
        self,
        chunks: list[CodeChunk],
        sections: list[DocSection],
    ) -> dict[str, list[str]]:
        """
        Embeds all chunks and sections, then links pairs whose
        cosine similarity exceeds SIMILARITY_THRESHOLD.
        """
        if not chunks or not sections:
            return {}

        # Build text representations
        chunk_texts = [chunk_to_embed_text(c) for c in chunks]
        section_texts = [section_to_embed_text(s) for s in sections]

        print(f"[Linker]   Embedding {len(chunk_texts)} chunks...")
        chunk_embeddings = np.array(self.embedder.embed_batch(chunk_texts))

        print(f"[Linker]   Embedding {len(section_texts)} sections...")
        section_embeddings = np.array(self.embedder.embed_batch(section_texts))

        # Compute full similarity matrix: shape (n_chunks, n_sections)
        print("[Linker]   Computing similarity matrix...")
        similarity_matrix = cosine_similarity(chunk_embeddings, section_embeddings)

        # Build links where similarity exceeds threshold
        links: dict[str, list[str]] = {}
        semantic_count = 0

        for i, chunk in enumerate(chunks):
            matched = []
            for j, section in enumerate(sections):
                score = similarity_matrix[i, j]
                if score >= SIMILARITY_THRESHOLD:
                    matched.append(section.id)
                    semantic_count += 1
            if matched:
                links[chunk.id] = matched

        print(f"[Linker]   Semantic pass: {semantic_count} links found.")
        return links


# ── Index builder ──────────────────────────────────────────────────────────────

class IndexBuilder:
    """
    Orchestrates parsing → linking → persisting the index.
    Call build() to run the full pipeline.
    """

    def __init__(self, repo_root: str):
        self.repo_root = repo_root
        self.embedder = Embedder()
        self.linker = Linker(self.embedder)

    def build(self) -> dict[str, Any]:
        """
        Full pipeline:
          1. Parse all code chunks from repo_root
          2. Parse all doc sections from repo_root
          3. Link them
          4. Save to docs-index.json
          5. Return the index dict
        """
        print(f"\n[IndexBuilder] Starting index build for: {self.repo_root}")

        # Parse
        chunks = CodeParser().parse_directory(self.repo_root)
        sections = MarkdownParser().parse_directory(self.repo_root)
        print(f"[IndexBuilder] Parsed {len(chunks)} code chunks, {len(sections)} doc sections.")

        if not chunks or not sections:
            print("[IndexBuilder] WARNING: No chunks or sections found. Check your paths.")
            return {}

        # Link
        links = self.linker.build_links(chunks, sections)

        # Build the full index structure
        index = {
            "meta": {
                "repo_root": self.repo_root,
                "chunk_count": len(chunks),
                "section_count": len(sections),
                "link_count": sum(len(v) for v in links.values()),
                "similarity_threshold": SIMILARITY_THRESHOLD,
            },
            "chunks": {c.id: asdict(c) for c in chunks},
            "sections": {s.id: asdict(s) for s in sections},
            "links": links,
        }

        # Persist
        output_path = Path(self.repo_root) / INDEX_FILE
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(index, f, indent=2)

        print(f"[IndexBuilder] Index saved to: {output_path}")
        print(f"[IndexBuilder] Summary: {index['meta']}")
        return index


# ── CLI entry point ────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import sys
    root = sys.argv[1] if len(sys.argv) > 1 else "."
    IndexBuilder(root).build()