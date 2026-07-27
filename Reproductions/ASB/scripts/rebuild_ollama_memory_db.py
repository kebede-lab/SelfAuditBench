#!/usr/bin/env python3
"""Rebuild ASB Chroma memory DBs with local Ollama embeddings.

The upstream ASB memory DB directories are named *_gpt-4o-mini and may contain
vectors produced by an OpenAI embedding model. Ollama models such as
nomic-embed-text use a different vector dimension, so MP runs should query a
fresh Chroma DB rebuilt from the stored documents.
"""
from __future__ import annotations

import os
import shutil
from pathlib import Path

from langchain_chroma import Chroma
from langchain_core.documents import Document
try:
    from langchain_ollama import OllamaEmbeddings
except ImportError as exc:  # pragma: no cover
    raise SystemExit(
        "Missing langchain-ollama. Install requirements.txt before rebuilding memory DBs."
    ) from exc


ROOT = Path(__file__).resolve().parents[1]
SOURCE_ROOT = ROOT / "memory_db" / "direct_prompt_injection"
MODEL = os.getenv("ASB_EMBEDDING_MODEL", "nomic-embed-text")
OLLAMA_URL = os.getenv("ASB_OLLAMA_BASE_URL") or os.getenv("OLLAMA_HOST") or "http://localhost:11434"
SUFFIX = (os.getenv("ASB_MEMORY_DB_SUFFIX") or MODEL).replace("/", "_")


def read_source_documents(source: Path) -> list[Document]:
    source_db = Chroma(persist_directory=str(source), embedding_function=None)
    raw = source_db.get(include=["documents", "metadatas"])
    docs = raw.get("documents") or []
    metas = raw.get("metadatas") or [{} for _ in docs]
    out: list[Document] = []
    for doc, meta in zip(docs, metas):
        if doc:
            out.append(Document(page_content=doc, metadata=meta or {}))
    return out


def rebuild_one(attack_type: str) -> None:
    source = SOURCE_ROOT / f"{attack_type}_gpt-4o-mini"
    dest = SOURCE_ROOT / f"{attack_type}_{SUFFIX}"
    if not source.exists():
        print(f"skip_missing_source={source}")
        return
    docs = read_source_documents(source)
    if not docs:
        raise SystemExit(f"No documents found in {source}; refusing to create an empty DB.")
    if dest.exists():
        shutil.rmtree(dest)
    embeddings = OllamaEmbeddings(model=MODEL, base_url=OLLAMA_URL)
    Chroma.from_documents(documents=docs, embedding=embeddings, persist_directory=str(dest))
    print(f"rebuilt={dest} documents={len(docs)} model={MODEL} ollama={OLLAMA_URL}")


def main() -> int:
    print("ASB Ollama memory DB rebuild")
    print(f"source_root={SOURCE_ROOT}")
    print(f"embedding_model={MODEL}")
    print(f"ollama_base_url={OLLAMA_URL}")
    print(f"memory_db_suffix={SUFFIX}")
    for attack_type in ["naive", "combined_attack", "context_ignoring", "fake_completion", "escape_characters"]:
        rebuild_one(attack_type)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
