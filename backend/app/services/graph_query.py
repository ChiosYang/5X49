from __future__ import annotations

from typing import Any

from sqlmodel import Session, select

from app.canonical_models import GraphEdgeReadModel, GraphNodeReadModel, ProjectionState
from app.database import engine
from app.services.projections import PROJECTION_VERSIONS, ProjectionUnavailable


GRAPH_VISIBILITY_POLICY = "graph-visibility.v1"
GRAPH_PROJECTION_VERSION = "film-graph.v1"
MAX_GRAPH_NODES = 65
MAX_GRAPH_EDGES = 64


class GraphQueryService:
    """Serve a bounded factual graph exclusively from synchronous read models."""

    def get_film_graph(self, film_id: str) -> dict[str, Any] | None:
        with Session(engine) as session:
            self._require(session, "graph_nodes")
            self._require(session, "graph_edges")
            root = session.get(GraphNodeReadModel, film_id)
            if root is None or root.entity_type != "film":
                return None
            candidates = session.exec(
                select(GraphEdgeReadModel)
                .where(
                    (GraphEdgeReadModel.subject_entity_id == film_id)
                    | (GraphEdgeReadModel.object_entity_id == film_id)
                )
                .order_by(GraphEdgeReadModel.priority, GraphEdgeReadModel.relation, GraphEdgeReadModel.edge_id)
            ).all()
            visible = [edge for edge in candidates if self._is_visible(edge)]
            nodes = {film_id: self._node_view(root)}
            edges: list[dict[str, Any]] = []
            truncated = False
            for edge in visible:
                if len(edges) >= MAX_GRAPH_EDGES:
                    truncated = True
                    break
                related_id = (
                    edge.object_entity_id
                    if edge.subject_entity_id == film_id
                    else edge.subject_entity_id
                )
                related = session.get(GraphNodeReadModel, related_id)
                if related is None:
                    truncated = True
                    continue
                if related_id not in nodes and len(nodes) >= MAX_GRAPH_NODES:
                    truncated = True
                    continue
                nodes[related_id] = self._node_view(related)
                edges.append(self._edge_view(edge))
            if len(edges) < len(visible):
                truncated = True
            return {
                "root": nodes[film_id],
                "nodes": [nodes[key] for key in sorted(nodes, key=lambda key: (key != film_id, key))],
                "edges": edges,
                "truncated": truncated,
                "visibility_policy": GRAPH_VISIBILITY_POLICY,
                "projection_version": GRAPH_PROJECTION_VERSION,
            }

    @staticmethod
    def _is_visible(edge: GraphEdgeReadModel) -> bool:
        if edge.edge_kind == "credit":
            return True
        payload = edge.payload or {}
        return (
            edge.edge_kind == "assertion"
            and payload.get("review_status") == "accepted"
            and payload.get("source_scope") == "factual"
        )

    @staticmethod
    def _node_view(node: GraphNodeReadModel) -> dict[str, Any]:
        payload = node.payload or {}
        return {
            "id": node.entity_id,
            "entity_type": node.entity_type,
            "display_label": node.display_label,
            "release_year": payload.get("release_year") if node.entity_type == "film" else None,
            "concept_kind": payload.get("kind") if node.entity_type == "concept" else None,
            "in_library": bool(node.owned),
        }

    @staticmethod
    def _edge_view(edge: GraphEdgeReadModel) -> dict[str, Any]:
        payload = edge.payload or {}
        source_kinds = [
            value
            for value in payload.get("source_kinds", [])
            if value in {"curated", "user", "rule", "nfo", "tmdb", "filename"}
        ]
        return {
            "id": edge.edge_id,
            "edge_kind": edge.edge_kind,
            "subject_id": edge.subject_entity_id,
            "object_id": edge.object_entity_id,
            "relation": edge.relation,
            "direction": "subject_to_object",
            "review_status": payload.get("review_status", "accepted"),
            "source_kinds": sorted(set(source_kinds)),
            "active_evidence_count": int(payload.get("evidence_count") or 0),
            "conflicted": bool(payload.get("conflicted")),
        }

    @staticmethod
    def _require(session: Session, name: str) -> None:
        state = session.get(ProjectionState, name)
        if (
            state is None
            or state.status != "ready"
            or state.projection_version != PROJECTION_VERSIONS[name]
        ):
            raise ProjectionUnavailable(f"{name} projection is unavailable")


graph_query_service = GraphQueryService()


__all__ = [
    "GRAPH_PROJECTION_VERSION",
    "GRAPH_VISIBILITY_POLICY",
    "GraphQueryService",
    "graph_query_service",
]
