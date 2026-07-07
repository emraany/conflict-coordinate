"""Actor co-occurrence graph for a single crisis.

v1: nodes = ORG mentions in this crisis's events; edge weight = number of
events where both ORGs appear in the same description. Community color
via Louvain, node size via betweenness centrality.

Computed on demand — at our scale (a few hundred crises, <2k unique ORGs
per crisis) Louvain + betweenness run in <500ms.
"""
from __future__ import annotations

import networkx as nx
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import EntityMention
from app.models.event import CrisisEvent


def _louvain_communities(G: nx.Graph) -> list[set[str]]:
    if G.number_of_nodes() == 0:
        return []
    if G.number_of_edges() == 0:
        return [{n} for n in G.nodes]
    try:
        import community as community_louvain  # python-louvain

        partition = community_louvain.best_partition(
            G, weight="weight", random_state=42
        )
    except Exception:
        return [set(G.nodes)]
    by_comm: dict[int, set[str]] = {}
    for node, c in partition.items():
        by_comm.setdefault(c, set()).add(node)
    return list(by_comm.values())


def build_graph(db: Session, crisis_id: int, max_nodes: int = 60) -> dict:
    rows = db.execute(
        select(
            EntityMention.event_id,
            EntityMention.text_norm,
            EntityMention.text,
        )
        .join(CrisisEvent, CrisisEvent.id == EntityMention.event_id)
        .where(CrisisEvent.crisis_id == crisis_id)
        .where(EntityMention.label == "ORG")
    ).all()

    if not rows:
        return {"nodes": [], "edges": [], "communities": []}

    by_event: dict[int, set[str]] = {}
    label_for: dict[str, str] = {}
    mention_count: dict[str, int] = {}
    for r in rows:
        by_event.setdefault(r.event_id, set()).add(r.text_norm)
        label_for[r.text_norm] = r.text
        mention_count[r.text_norm] = mention_count.get(r.text_norm, 0) + 1

    # Cap to top-N most-mentioned to keep the force-directed render legible.
    top = sorted(mention_count.items(), key=lambda kv: kv[1], reverse=True)[:max_nodes]
    keep = {k for k, _ in top}
    by_event = {ev: nodes & keep for ev, nodes in by_event.items()}
    by_event = {ev: ns for ev, ns in by_event.items() if ns}

    G: nx.Graph = nx.Graph()
    for nodes_in_event in by_event.values():
        ns = list(nodes_in_event)
        for n in ns:
            if not G.has_node(n):
                G.add_node(n)
        for i in range(len(ns)):
            for j in range(i + 1, len(ns)):
                a, b = ns[i], ns[j]
                if G.has_edge(a, b):
                    G[a][b]["weight"] += 1
                else:
                    G.add_edge(a, b, weight=1)

    communities = _louvain_communities(G)
    node_to_comm: dict[str, int] = {}
    for i, comm in enumerate(communities):
        for n in comm:
            node_to_comm[n] = i

    if G.number_of_nodes() >= 3 and G.number_of_edges() > 0:
        bc = nx.betweenness_centrality(G, weight="weight", normalized=True)
    else:
        bc = {n: 0.0 for n in G.nodes}

    nodes = [
        {
            "id": n,
            "label": label_for.get(n, n),
            "mentions": mention_count.get(n, 0),
            "community": node_to_comm.get(n, 0),
            "centrality": float(bc.get(n, 0.0)),
        }
        for n in G.nodes
    ]
    edges = [
        {"source": u, "target": v, "weight": G[u][v]["weight"]}
        for u, v in G.edges
    ]
    return {
        "nodes": nodes,
        "edges": edges,
        "communities": [list(c) for c in communities],
    }
