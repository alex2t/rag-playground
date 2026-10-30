"""LLM enrichment of a saved chunk set (T47): a headline and a summary per chunk, written from the chunk and its whole
document. They are used for search only; answers read the original text. Each chunk is saved as soon as it is paid
for, so a stopped build resumes and a finished one never calls the LLM again. The instructions are a custom choice."""

from pydantic import BaseModel

from rag_playground.chunking.chunk_sets import METHOD as FIXED_METHOD
from rag_playground.chunking.chunk_sets import Chunk, kb_documents, load, saved_path
from rag_playground.llm.openrouter import chat_structured
from rag_playground.settings import ENRICH_MODEL

METHOD = "llm_enriched"

INSTRUCTIONS = """You describe one chunk of a document, so that a search can find it.
You receive the whole document and one chunk taken from it.
headline: at most 12 words naming what the chunk is about, including the client, service, person or policy concerned.
summary: at most 2 sentences stating what the chunk says, in its document's context.
Use only facts stated in the document. Describe this chunk, not the rest of the document."""


class Enrichment(BaseModel):
    """What the LLM writes for one chunk."""

    headline: str
    summary: str


class EnrichedChunk(Chunk):
    """A chunk with its unchanged original text, plus what the LLM wrote about it."""

    headline: str
    summary: str

    @property
    def indexed_text(self) -> str:
        """What search reads."""
        return f"{self.headline}\n{self.summary}\n\n{self.text}"


def enriched_set_id(base_id: str) -> str:
    """The id of a fixed chunk set's enriched version."""
    prefix = f"{FIXED_METHOD}__"
    if not base_id.startswith(prefix):
        raise ValueError(f"{base_id} is not a {FIXED_METHOD} chunk set")
    return f"{METHOD}__{base_id.removeprefix(prefix)}"


def messages(chunk: Chunk, document: str) -> list[dict]:
    return [{"role": "system", "content": INSTRUCTIONS},
            {"role": "user", "content": f"Document:\n{document}\n\nChunk:\n{chunk.text}"}]


def enrich(chunk: Chunk, document: str) -> EnrichedChunk:
    """One paid call; a blank headline or summary is refused, since it would be saved and never retried."""
    reply, _ = chat_structured(ENRICH_MODEL, messages(chunk, document), Enrichment)
    if not reply.headline.strip() or not reply.summary.strip():
        raise ValueError(f"The LLM left the headline or summary of {chunk.chunk_id} blank")
    return EnrichedChunk(**chunk.model_dump(), headline=reply.headline, summary=reply.summary)


def load_saved(set_id: str, base: list[Chunk]) -> list[EnrichedChunk]:
    """The chunks saved so far; each must still be its base chunk, unchanged."""
    path = saved_path(set_id)
    if not path.exists():
        return []
    lines = path.read_text(encoding="utf-8").splitlines()
    saved = [EnrichedChunk.model_validate_json(line) for line in lines if line.strip()]
    if len(saved) > len(base):
        raise ValueError(f"{set_id} has more chunks than its base set")
    for chunk, original in zip(saved, base):
        if chunk.model_dump(include=set(Chunk.model_fields)) != original.model_dump():
            raise ValueError(f"Saved chunk {chunk.chunk_id} of {set_id} differs from its base chunk")
    return saved


def save(set_id: str, chunks: list[EnrichedChunk]) -> None:
    """Put the new file in place in one atomic step, so a stop can never leave half a line in the saved set."""
    path = saved_path(set_id)
    temporary = path.with_suffix(".tmp")
    temporary.write_text("".join(c.model_dump_json() + "\n" for c in chunks), encoding="utf-8")
    temporary.replace(path)


def load_or_enrich(base_id: str) -> list[EnrichedChunk]:
    """The enriched version of a saved fixed chunk set, calling the LLM only for chunks not saved yet."""
    set_id = enriched_set_id(base_id)
    base, documents = load(base_id), kb_documents()
    for chunk in base:
        if documents[chunk.source][chunk.start:chunk.end] != chunk.text:
            raise ValueError(f"Chunk {chunk.chunk_id} is no longer in {chunk.source}; rebuild {base_id}")
    enriched = load_saved(set_id, base)
    for chunk in base[len(enriched):]:
        enriched.append(enrich(chunk, documents[chunk.source]))
        save(set_id, enriched)
    return enriched
