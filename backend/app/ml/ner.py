"""Named-entity extraction over crisis_events.description.

v1: spaCy en_core_web_lg (statistical, ~750MB, ~5–10ms/doc on CPU). Lazy-loaded
singleton — first call pays the ~1s load cost, subsequent calls reuse it.

We persist mentions per event into entity_mentions. Aggregation across events
(top-N per crisis per label) is computed at query time in the API layer.
"""
from __future__ import annotations

from collections.abc import Iterable

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import EntityMention
from app.models.event import CrisisEvent

# Subset of spaCy NER labels worth surfacing for conflict-domain text.
KEEP_LABELS: frozenset[str] = frozenset(
    {"PERSON", "ORG", "GPE", "LOC", "NORP", "EVENT", "FAC"}
)

_nlp = None


def _get_nlp():
    global _nlp
    if _nlp is None:
        import spacy

        _nlp = spacy.load("en_core_web_lg", disable=["parser", "lemmatizer"])
    return _nlp


def _norm(text: str) -> str:
    return " ".join(text.lower().split())


# Labels used to build clustering signatures — broader than dossier display.
# We exclude GPE/LOC because too many ACLED notes mention the same place
# names; that signal duplicates the geographic pre-partition and would
# spuriously fuse topically distinct events that share a city.
_SIGNATURE_LABELS: frozenset[str] = frozenset(
    {"PERSON", "ORG", "NORP", "EVENT"}
)


def extract_signature_entities_labeled(
    texts: list[str],
) -> list[list[tuple[str, str]]]:
    """Run NER over a batch of raw description strings (no DB I/O).

    Returns one list per input text of `(label, text_norm)` tuples, drawn
    from `_SIGNATURE_LABELS`. Used by topic clustering (which discards the
    label) and topic-tag selection (which keeps it for ranking by label).
    """
    if not texts:
        return []
    nlp = _get_nlp()
    out: list[list[tuple[str, str]]] = []
    for doc in nlp.pipe(texts, batch_size=64):
        ents: list[tuple[str, str]] = []
        for ent in doc.ents:
            if ent.label_ not in _SIGNATURE_LABELS:
                continue
            t = ent.text.strip()
            if not t or len(t) > 200:
                continue
            ents.append((ent.label_, _norm(t)[:200]))
        out.append(ents)
    return out


def extract_signature_entities(texts: list[str]) -> list[set[str]]:
    """Unlabeled view of `extract_signature_entities_labeled` for clustering."""
    return [{t for _, t in ents} for ents in extract_signature_entities_labeled(texts)]


def process_pending(
    db: Session, batch_size: int = 64, max_events: int | None = None
) -> dict:
    """Run NER on events whose id is not yet present in entity_mentions.

    `max_events` caps one pass so a large backlog drains across runs instead
    of blocking the ingest cycle. Returns {events_processed, mentions_inserted}.
    """
    stmt = (
        select(CrisisEvent.id, CrisisEvent.description, CrisisEvent.source_id)
        .where(CrisisEvent.description.is_not(None))
        .where(
            ~select(EntityMention.id)
            .where(EntityMention.event_id == CrisisEvent.id)
            .exists()
        )
    )
    if max_events is not None:
        stmt = stmt.limit(max_events)
    rows = list(db.execute(stmt))
    if not rows:
        return {"events_processed": 0, "mentions_inserted": 0}

    nlp = _get_nlp()
    texts: list[str] = [r.description for r in rows]
    metas: Iterable[tuple[int, int | None]] = [
        (r.id, r.source_id) for r in rows
    ]

    inserted = 0
    bulk: list[dict] = []
    for (event_id, source_id), doc in zip(
        metas, nlp.pipe(texts, batch_size=batch_size), strict=True
    ):
        for ent in doc.ents:
            if ent.label_ not in KEEP_LABELS:
                continue
            text = ent.text.strip()
            if not text or len(text) > 200:
                continue
            bulk.append(
                {
                    "event_id": event_id,
                    "source_id": source_id,
                    "label": ent.label_,
                    "text": text,
                    "text_norm": _norm(text)[:200],
                    "start_char": ent.start_char,
                    "end_char": ent.end_char,
                }
            )
        if len(bulk) >= 1000:
            db.bulk_insert_mappings(EntityMention, bulk)
            inserted += len(bulk)
            bulk = []
    if bulk:
        db.bulk_insert_mappings(EntityMention, bulk)
        inserted += len(bulk)

    db.commit()
    return {"events_processed": len(rows), "mentions_inserted": inserted}
