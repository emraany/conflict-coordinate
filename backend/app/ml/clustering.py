"""Topic-aware clustering of raw ACLED events within a country partition.

Replaces pure-geographic DBSCAN as the unit-of-crisis decision. Two events
land in the same crisis only if they share a topical signature — derived
from NER entity sets over their `notes` plus normalized ACLED actor names —
or if their TF-IDF cosine similarity is high.

Inputs are raw ACLED event dicts (the same shape `acled.py` produces); the
caller pre-partitions by country and passes one country at a time.

Outputs a per-event integer cluster label, where -1 means noise (dropped by
the caller, matching legacy DBSCAN semantics).

Why this and not single-link connected components: a single event mentioning
two unrelated topics would otherwise bridge them. HDBSCAN on a precomputed
distance matrix tolerates such ambiguous events without fusing the clusters.
"""

from __future__ import annotations

import re
from collections.abc import Iterable

import numpy as np
from sklearn.cluster import HDBSCAN
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

from app.ml.ner import extract_signature_entities

# Strip ACLED's parenthetical year/regime suffixes ("Police Forces of the
# United States (2021-)") so the same actor under different regimes maps
# to the same signature token.
_PAREN_RE = re.compile(r"\s*\([^)]*\)\s*")


def _norm_actor(name: str) -> str:
    return _PAREN_RE.sub(" ", name).strip().lower()


def _entity_set_for(ev: dict, ner_ents: set[str]) -> set[str]:
    sig = set(ner_ents)
    for key in ("actor1", "actor2", "assoc_actor_1", "assoc_actor_2"):
        raw = (ev.get(key) or "").strip()
        if not raw:
            continue
        for piece in raw.split(";"):
            n = _norm_actor(piece)
            if n:
                sig.add(f"actor:{n}")
    return sig


def _jaccard_sim(a: set[str], b: set[str]) -> float:
    if not a and not b:
        return 0.0
    inter = len(a & b)
    union = len(a | b)
    if union == 0:
        return 0.0
    return inter / union


def build_entity_sets(
    events: list[dict], ner_entity_sets: list[set[str]]
) -> list[set[str]]:
    """Combine ACLED actor strings with NER-derived entities per event."""
    return [
        _entity_set_for(ev, ents)
        for ev, ents in zip(events, ner_entity_sets, strict=True)
    ]


def cluster_events(
    events: list[dict],
    *,
    entity_sets: list[set[str]] | None = None,
    min_cluster_size: int = 5,
    similarity_threshold: float = 0.50,
    jaccard_alpha: float = 0.5,
    very_large_partition: int = 1000,
) -> list[int]:
    """Return a cluster label per event (-1 = noise).

    `events` is one country partition. Caller drops noise points; non-noise
    labels become the unit of crisis materialization. Pass `entity_sets`
    pre-computed if NER has already been run upstream — avoids re-running
    spaCy on the same texts.
    """
    n = len(events)
    if n == 0:
        return []

    # State-vs-state guardrail: very large country partitions are usually a
    # single ongoing war (Russia–Ukraine, Sudan, Israel–Gaza). Splitting
    # them along topic lines fragments a coherent conflict; keep as one.
    if n >= very_large_partition:
        return [0] * n

    # Too small to support any HDBSCAN cluster — emit noise. Caller drops.
    if n < min_cluster_size:
        return [-1] * n

    notes: list[str] = [(ev.get("notes") or "").strip() for ev in events]
    if entity_sets is None:
        ner_entity_sets: list[set[str]] = extract_signature_entities(notes)
        entity_sets = build_entity_sets(events, ner_entity_sets)

    # TF-IDF over notes (within partition only — local IDF lets common
    # boilerplate downweight). Empty notes get a zero vector, contributing
    # only via the Jaccard term.
    has_text = [bool(t) for t in notes]
    cosine_mat = np.zeros((n, n), dtype=np.float32)
    if any(has_text) and sum(has_text) >= 2:
        vec = TfidfVectorizer(
            min_df=1,
            max_df=0.95,
            ngram_range=(1, 2),
            stop_words="english",
            max_features=20000,
        )
        try:
            X = vec.fit_transform(notes)
            sims = cosine_similarity(X)
            cosine_mat = sims.astype(np.float32)
        except ValueError:
            # All-stopword corpus; leave cosine_mat as zeros.
            pass

    # Combined similarity → distance. dist = 1 - sim, clipped to [0, 1].
    sim = np.zeros((n, n), dtype=np.float32)
    for i in range(n):
        for j in range(i, n):
            jac = _jaccard_sim(entity_sets[i], entity_sets[j])
            cos = float(cosine_mat[i, j])
            s = jaccard_alpha * jac + (1.0 - jaccard_alpha) * cos
            sim[i, j] = s
            sim[j, i] = s
    np.fill_diagonal(sim, 1.0)
    dist = np.clip(1.0 - sim, 0.0, 1.0).astype(np.float64)

    # cluster_selection_epsilon collapses sub-clusters whose mutual distance
    # is already below (1 - threshold), giving us a knob aligned with the
    # similarity threshold the user thinks in terms of.
    eps = max(0.0, 1.0 - similarity_threshold)

    clusterer = HDBSCAN(
        metric="precomputed",
        min_cluster_size=min_cluster_size,
        min_samples=2,
        cluster_selection_epsilon=eps,
        allow_single_cluster=True,
    )
    labels = clusterer.fit_predict(dist)
    return [int(x) for x in labels]


def partition_by_country(events: Iterable[dict]) -> dict[str, list[dict]]:
    """Group raw events by their `country` field for per-partition clustering."""
    out: dict[str, list[dict]] = {}
    for ev in events:
        c = (ev.get("country") or "").strip() or "Unknown"
        out.setdefault(c, []).append(ev)
    return out
