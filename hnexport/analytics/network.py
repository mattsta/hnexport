"""User network graph generation and analysis."""

import json
import lzma
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple

from ..logger import logger

try:
    import networkx as nx

    NETWORKX_AVAILABLE = True
except ImportError:
    NETWORKX_AVAILABLE = False
    logger.warning(
        "NetworkX not available. Install with: pip install networkx"
    )


@dataclass
class NetworkStats:
    """Network graph statistics."""

    total_nodes: int = 0
    total_edges: int = 0
    density: float = 0.0
    avg_degree: float = 0.0
    top_users: List[Tuple[str, Dict[str, float]]] = field(default_factory=list)
    components: int = 0
    largest_component_size: int = 0

    def to_dict(self) -> Dict:
        """Convert to dictionary."""
        return {
            "total_nodes": self.total_nodes,
            "total_edges": self.total_edges,
            "density": self.density,
            "avg_degree": self.avg_degree,
            "top_users": self.top_users,
            "components": self.components,
            "largest_component_size": self.largest_component_size,
        }


class NetworkGraphBuilder:
    """Build network graphs from HackerNews data.

    Creates graphs showing user interactions, comment threads, and
    community structure.

    Requires: networkx (pip install networkx)

    Example:
        builder = NetworkGraphBuilder(data_dir=Path("hn/item"))
        graph = builder.build_user_interaction_graph(max_bundles=100)
        stats = builder.analyze_graph(graph)
        print(f"Network has {stats.total_nodes} users and {stats.total_edges} interactions")
    """

    def __init__(self, data_dir: Path):
        if not NETWORKX_AVAILABLE:
            raise ImportError(
                "NetworkX is required for network analysis. "
                "Install with: pip install networkx"
            )

        self.data_dir = data_dir
        self.item_dir = data_dir / "item" if (data_dir / "item").exists() else data_dir

    def build_user_interaction_graph(
        self,
        max_bundles: Optional[int] = None,
        min_interactions: int = 1,
        progress_callback: Optional[callable] = None,
    ) -> "nx.DiGraph":
        """Build directed graph of user interactions (replies).

        Args:
            max_bundles: Maximum bundles to process (None = all)
            min_interactions: Minimum interactions required to include edge
            progress_callback: Optional callback(current, total) for progress

        Returns:
            NetworkX directed graph with users as nodes and replies as edges
        """
        logger.info("Building user interaction graph")

        # Track interactions: (from_user, to_user) -> count
        interactions: Dict[Tuple[str, str], int] = defaultdict(int)

        # Track all items to map parent -> author
        item_authors: Dict[int, str] = {}

        bundles = sorted(self.item_dir.glob("*.xz"))
        if max_bundles:
            bundles = bundles[:max_bundles]

        total_bundles = len(bundles)
        logger.info(f"Processing {total_bundles:,} bundles")

        # First pass: collect all item authors
        for idx, bundle_path in enumerate(bundles):
            if progress_callback and idx % 100 == 0:
                progress_callback(idx * 2, total_bundles * 2)

            try:
                with lzma.open(bundle_path, "rt", encoding="utf-8") as f:
                    for line in f:
                        if not line.strip() or line.strip() == "null":
                            continue

                        try:
                            item = json.loads(line)
                        except json.JSONDecodeError:
                            continue

                        item_id = item.get("id")
                        author = item.get("by")

                        if item_id and author:
                            item_authors[item_id] = author

            except Exception as e:
                logger.warning(f"Error processing bundle {bundle_path.name}: {e}")
                continue

        logger.info(f"Collected {len(item_authors):,} item authors")

        # Second pass: build interaction graph
        for idx, bundle_path in enumerate(bundles):
            if progress_callback and idx % 100 == 0:
                progress_callback(total_bundles + idx, total_bundles * 2)

            try:
                with lzma.open(bundle_path, "rt", encoding="utf-8") as f:
                    for line in f:
                        if not line.strip() or line.strip() == "null":
                            continue

                        try:
                            item = json.loads(line)
                        except json.JSONDecodeError:
                            continue

                        # Only process comments (items with parents)
                        parent_id = item.get("parent")
                        author = item.get("by")

                        if not parent_id or not author:
                            continue

                        # Find parent author
                        parent_author = item_authors.get(parent_id)

                        if parent_author and parent_author != author:
                            # Track interaction: author replied to parent_author
                            interactions[(author, parent_author)] += 1

            except Exception as e:
                logger.warning(f"Error processing bundle {bundle_path.name}: {e}")
                continue

        if progress_callback:
            progress_callback(total_bundles * 2, total_bundles * 2)

        # Build NetworkX graph
        graph = nx.DiGraph()

        for (from_user, to_user), count in interactions.items():
            if count >= min_interactions:
                graph.add_edge(
                    from_user,
                    to_user,
                    weight=count,
                    interactions=count,
                )

        logger.info(
            f"Graph built: {graph.number_of_nodes():,} users, "
            f"{graph.number_of_edges():,} interactions"
        )

        return graph

    def build_story_comment_graph(
        self,
        max_bundles: Optional[int] = None,
        story_ids: Optional[List[int]] = None,
    ) -> "nx.DiGraph":
        """Build graph of stories and their comments.

        Args:
            max_bundles: Maximum bundles to process
            story_ids: Specific story IDs to include (None = all stories)

        Returns:
            NetworkX directed graph with items as nodes and parent relationships as edges
        """
        logger.info("Building story-comment graph")

        graph = nx.DiGraph()
        items: Dict[int, Dict] = {}

        bundles = sorted(self.item_dir.glob("*.xz"))
        if max_bundles:
            bundles = bundles[:max_bundles]

        # Collect all items
        for bundle_path in bundles:
            try:
                with lzma.open(bundle_path, "rt", encoding="utf-8") as f:
                    for line in f:
                        if not line.strip() or line.strip() == "null":
                            continue

                        try:
                            item = json.loads(line)
                        except json.JSONDecodeError:
                            continue

                        item_id = item.get("id")
                        if not item_id:
                            continue

                        # Filter by story IDs if specified
                        if story_ids and item.get("type") == "story":
                            if item_id not in story_ids:
                                continue

                        items[item_id] = item

            except Exception as e:
                logger.warning(f"Error processing bundle {bundle_path.name}: {e}")
                continue

        # Build graph
        for item_id, item in items.items():
            node_type = item.get("type", "unknown")
            author = item.get("by", "unknown")

            graph.add_node(
                item_id,
                type=node_type,
                by=author,
                title=item.get("title"),
                score=item.get("score", 0),
            )

            # Add edge to parent
            parent_id = item.get("parent")
            if parent_id and parent_id in items:
                graph.add_edge(parent_id, item_id)

        logger.info(
            f"Story-comment graph: {graph.number_of_nodes():,} items, "
            f"{graph.number_of_edges():,} edges"
        )

        return graph

    def analyze_graph(self, graph: "nx.Graph", top_n: int = 20) -> NetworkStats:
        """Analyze network graph and compute statistics.

        Args:
            graph: NetworkX graph to analyze
            top_n: Number of top users to return

        Returns:
            NetworkStats with analysis results
        """
        logger.info("Analyzing graph statistics")

        stats = NetworkStats()

        stats.total_nodes = graph.number_of_nodes()
        stats.total_edges = graph.number_of_edges()

        if stats.total_nodes == 0:
            return stats

        # Density
        if isinstance(graph, nx.DiGraph):
            stats.density = nx.density(graph)
        else:
            stats.density = nx.density(graph)

        # Average degree
        degrees = [d for n, d in graph.degree()]
        stats.avg_degree = sum(degrees) / len(degrees) if degrees else 0.0

        # Connected components
        if isinstance(graph, nx.DiGraph):
            components = list(nx.weakly_connected_components(graph))
        else:
            components = list(nx.connected_components(graph))

        stats.components = len(components)
        stats.largest_component_size = max(len(c) for c in components) if components else 0

        # Top users by various centrality metrics
        logger.info("Calculating centrality metrics")

        # Degree centrality
        degree_centrality = nx.degree_centrality(graph)

        # In-degree centrality (for directed graphs)
        if isinstance(graph, nx.DiGraph):
            in_degree_centrality = nx.in_degree_centrality(graph)
            out_degree_centrality = nx.out_degree_centrality(graph)
        else:
            in_degree_centrality = degree_centrality
            out_degree_centrality = degree_centrality

        # Combine metrics for top users
        user_metrics: Dict[str, Dict[str, float]] = {}

        for user in graph.nodes():
            user_metrics[user] = {
                "degree": degree_centrality.get(user, 0.0),
                "in_degree": in_degree_centrality.get(user, 0.0),
                "out_degree": out_degree_centrality.get(user, 0.0),
            }

        # Sort by total degree centrality
        top_users = sorted(
            user_metrics.items(),
            key=lambda x: x[1]["degree"],
            reverse=True,
        )[:top_n]

        stats.top_users = top_users

        logger.info("Graph analysis complete")
        return stats

    def export_graph(
        self,
        graph: "nx.Graph",
        output_path: Path,
        format: str = "gexf",
    ) -> None:
        """Export graph to file.

        Args:
            graph: NetworkX graph to export
            output_path: Output file path
            format: Export format (gexf, graphml, gml, edgelist, json)
        """
        logger.info(f"Exporting graph to {output_path} ({format} format)")

        if format == "gexf":
            nx.write_gexf(graph, output_path)
        elif format == "graphml":
            nx.write_graphml(graph, output_path)
        elif format == "gml":
            nx.write_gml(graph, output_path)
        elif format == "edgelist":
            nx.write_edgelist(graph, output_path)
        elif format == "json":
            from networkx.readwrite import json_graph

            data = json_graph.node_link_data(graph)
            output_path.write_text(json.dumps(data, indent=2))
        else:
            raise ValueError(
                f"Unsupported format: {format}. "
                f"Use: gexf, graphml, gml, edgelist, json"
            )

        logger.info(f"Graph exported: {output_path}")

    def find_communities(
        self, graph: "nx.Graph", algorithm: str = "louvain"
    ) -> Dict[str, int]:
        """Detect communities in the graph.

        Args:
            graph: NetworkX graph
            algorithm: Community detection algorithm (louvain, label_propagation)

        Returns:
            Dictionary mapping node -> community_id
        """
        logger.info(f"Finding communities using {algorithm} algorithm")

        try:
            if algorithm == "louvain":
                import community as community_louvain

                # Convert directed to undirected for Louvain
                if isinstance(graph, nx.DiGraph):
                    graph = graph.to_undirected()

                communities = community_louvain.best_partition(graph)

            elif algorithm == "label_propagation":
                # Convert to undirected if needed
                if isinstance(graph, nx.DiGraph):
                    graph = graph.to_undirected()

                communities_gen = nx.algorithms.community.label_propagation_communities(
                    graph
                )
                communities = {}
                for idx, community in enumerate(communities_gen):
                    for node in community:
                        communities[node] = idx

            else:
                raise ValueError(
                    f"Unsupported algorithm: {algorithm}. "
                    f"Use: louvain, label_propagation"
                )

            logger.info(f"Found {len(set(communities.values()))} communities")
            return communities

        except ImportError as e:
            logger.error(
                f"Community detection requires additional packages: {e}\n"
                f"Install with: pip install python-louvain"
            )
            raise

    def get_user_ego_network(
        self, graph: "nx.Graph", user: str, radius: int = 1
    ) -> "nx.Graph":
        """Extract ego network for a specific user.

        Args:
            graph: Full network graph
            user: User to center ego network around
            radius: Number of hops from user to include

        Returns:
            Ego network subgraph
        """
        if user not in graph:
            raise ValueError(f"User '{user}' not found in graph")

        logger.info(f"Extracting ego network for user '{user}' (radius={radius})")

        ego_graph = nx.ego_graph(graph, user, radius=radius)

        logger.info(
            f"Ego network: {ego_graph.number_of_nodes():,} nodes, "
            f"{ego_graph.number_of_edges():,} edges"
        )

        return ego_graph
