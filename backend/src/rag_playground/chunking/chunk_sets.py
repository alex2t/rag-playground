"""Chunk sets: every KB document split by LlamaIndex's default SentenceSplitter, built once and reused
by both stacks (T01, T35, T39)."""

from pathlib import Path

from llama_index.core.node_parser import SentenceSplitter
from llama_index.core.utils import get_tokenizer
from pydantic import BaseModel

from rag_playground.datasets.schema import KB_DIR
from rag_playground.settings import settings

METHOD = "fixed"
MIN_SIZE, MAX_SIZE = 64, 2048
MAX_OVERLAP_SHARE = 0.5


class Chunk(BaseModel):
    """One chunk with its source document and its exact character span in that document."""

    chunk_id: str
    source: str
    doc_type: str
    index: int
    text: str
    tokens: int
    start: int
    end: int


def check_params(size: int, overlap: int) -> None:
    """T35 ranges: size 64-2,048 tokens, overlap 0 to half the size."""
    if not MIN_SIZE <= size <= MAX_SIZE:
        raise ValueError(f"chunk size {size} is outside {MIN_SIZE}-{MAX_SIZE} tokens")
    if not 0 <= overlap <= MAX_OVERLAP_SHARE * size:
        raise ValueError(f"overlap {overlap} is outside 0-{int(MAX_OVERLAP_SHARE * size)} tokens for size {size}")


def chunk_set_id(size: int, overlap: int) -> str:
    return f"{METHOD}__c{size}__o{overlap}"


def kb_documents() -> dict[str, str]:
    """Every KB document as {path relative to the KB, such as "clients/x.md": markdown}."""
    return {p.relative_to(KB_DIR).as_posix(): p.read_text(encoding="utf-8") for p in sorted(KB_DIR.rglob("*.md"))}


def search_from(prev: Chunk | None, piece: str, overlap: int) -> int:
    """Where to look for the next chunk: it starts no earlier than the previous chunk and ends after it, and
    without overlap it starts at or after the previous end. It can start exactly where the previous chunk
    starts, when the whole previous chunk fits in the overlap. Searching from just after the previous start
    can match a short piece, such as a lone "|", inside the previous chunk."""
    if prev is None:
        return 0
    if overlap == 0:
        return prev.end
    return max(prev.start, prev.end - len(piece) + 1)


def split_document(path: str, text: str, splitter: SentenceSplitter) -> list[Chunk]:
    """Split one document and locate each chunk's exact span in it."""
    tokens = get_tokenizer()
    chunks = []
    for i, piece in enumerate(splitter.split_text(text)):
        start = text.find(piece, search_from(chunks[-1] if chunks else None, piece, splitter.chunk_overlap))
        if start < 0:
            raise ValueError(f"chunk {i} of {path} is not a piece of the document")
        chunks.append(Chunk(chunk_id=f"{path}#{i}", source=path, doc_type=path.split("/")[0], index=i, text=piece,
                            tokens=len(tokens(piece)), start=start, end=start + len(piece)))
    return chunks


def build_chunk_set(docs: dict[str, str], size: int, overlap: int) -> list[Chunk]:
    check_params(size, overlap)
    splitter = SentenceSplitter(chunk_size=size, chunk_overlap=overlap)
    return [c for path, text in docs.items() for c in split_document(path, text, splitter)]


def chunk_set_path(size: int, overlap: int) -> Path:
    return settings.var_dir / "chunk_sets" / f"{chunk_set_id(size, overlap)}.jsonl"


def load_or_build(size: int, overlap: int) -> list[Chunk]:
    """Load the saved chunk set, or build it from the KB and save it. Out-of-range settings always raise."""
    check_params(size, overlap)
    path = chunk_set_path(size, overlap)
    if path.exists():
        lines = path.read_text(encoding="utf-8").splitlines()
        return [Chunk.model_validate_json(line) for line in lines if line.strip()]
    chunks = build_chunk_set(kb_documents(), size, overlap)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(c.model_dump_json() + "\n" for c in chunks), encoding="utf-8")
    return chunks
