"""
Transaction Graph Builder — Phase 2.

Constructs a directed NetworkX graph from database records.

Node types:
  - "account"   : bank account (victim, mule, clean)
  - "location"  : ATM/cash-out location cluster

Edge types:
  - "transfer"  : account → account transaction
  - "withdrawal": account → location (cash withdrawal)
  - "complaint" : complaint links to victim account (stored as node attribute)

Design note: NetworkX is used for the prototype.
To replace with Neo4j, swap this module — all callers use the same interface.
The graph is rebuilt in-memory on demand (fast enough for prototype scale).
"""

import json
from datetime import datetime
from typing import Optional

import networkx as nx


class TransactionGraph:
    """
    Directed weighted graph of the financial transaction network.

    Usage:
        builder = TransactionGraph()
        builder.build_from_db(db_session, cutoff_time=datetime(...))
        G = builder.graph
        paths = builder.find_paths("VIC_ABC", "LOC_M17", max_hops=5)
    """

    def __init__(self):
        # Directed graph: edges go from sender → receiver
        self.graph: nx.DiGraph = nx.DiGraph()
        self.built_at: Optional[str] = None
        self.cutoff_time: Optional[datetime] = None

    def build_from_db(self, db_session, cutoff_time: Optional[datetime] = None):
        """
        Build graph from database.

        IMPORTANT: If cutoff_time is provided, only transactions with
        timestamp <= cutoff_time are included. This prevents temporal leakage.
        """
        from backend.database.models import Account, Transaction, Withdrawal, Location, Complaint

        self.cutoff_time = cutoff_time
        cutoff_str = cutoff_time.isoformat() if cutoff_time else None

        # ── Add account nodes ──────────────────────────────────────────────
        accounts = db_session.query(Account).all()
        for acc in accounts:
            self.graph.add_node(
                acc.account_id,
                node_type="account",
                city=acc.city,
                state=acc.state,
                location_id=acc.location_id,
                risk_label=acc.risk_label,
                mule_risk_score=acc.mule_risk_score,
                account_age_days=acc.account_age_days,
            )

        # ── Add location nodes ────────────────────────────────────────────
        locations = db_session.query(Location).all()
        for loc in locations:
            self.graph.add_node(
                loc.location_id,
                node_type="location",
                city=loc.city,
                state=loc.state,
                latitude=loc.latitude,
                longitude=loc.longitude,
                location_type=loc.location_type,
            )

        # ── Add transaction edges ─────────────────────────────────────────
        transactions = db_session.query(Transaction)
        if cutoff_str:
            transactions = transactions.filter(Transaction.timestamp <= cutoff_str)
        transactions = transactions.all()

        for txn in transactions:
            if txn.source_account_id not in self.graph:
                continue
            if txn.dest_account_id not in self.graph:
                continue
            self.graph.add_edge(
                txn.source_account_id,
                txn.dest_account_id,
                edge_type="transfer",
                transaction_id=txn.transaction_id,
                amount=txn.amount,
                timestamp=txn.timestamp,
                transaction_type=txn.transaction_type,
                scenario_id=txn.scenario_id,
            )

        # ── Add withdrawal edges (ONLY past withdrawals if cutoff) ────────
        withdrawals = db_session.query(Withdrawal)
        if cutoff_str:
            withdrawals = withdrawals.filter(Withdrawal.timestamp <= cutoff_str)
        withdrawals = withdrawals.all()

        for wdr in withdrawals:
            if wdr.account_id not in self.graph:
                continue
            if wdr.location_id not in self.graph:
                continue
            self.graph.add_edge(
                wdr.account_id,
                wdr.location_id,
                edge_type="withdrawal",
                withdrawal_id=wdr.withdrawal_id,
                amount=wdr.amount,
                timestamp=wdr.timestamp,
                atm_id=wdr.atm_id,
            )

        # ── Annotate complaint-linked accounts ────────────────────────────
        complaints = db_session.query(Complaint)
        if cutoff_str:
            complaints = complaints.filter(Complaint.timestamp <= cutoff_str)
        complaints = complaints.all()

        for cmp in complaints:
            if cmp.victim_id in self.graph:
                node = self.graph.nodes[cmp.victim_id]
                existing = node.get("complaints", [])
                existing.append(cmp.complaint_id)
                node["complaints"] = existing
                node["is_victim"] = True

        # ── Add controlled decoy nodes (Honeypot simulation layer) ────────
        from backend.database.models import Decoy, DecoyInteraction
        decoys = db_session.query(Decoy).all()
        for dec in decoys:
            self.graph.add_node(
                dec.decoy_id,
                node_type="decoy",
                decoy_type=dec.decoy_type,
                city=dec.city,
                status=dec.status,
                synthetic_account_id=dec.synthetic_account_id,
                activation_reason=dec.activation_reason,
                monitoring_status=dec.monitoring_status,
                risk_context=dec.risk_context,
                interaction_count=dec.interaction_count or 0,
                is_synthetic=True,
                is_decoy=True,
                risk_label="controlled_decoy",
            )

        # ── Add decoy interaction edges ──────────────────────────────────
        decoy_interactions = db_session.query(DecoyInteraction)
        if cutoff_str:
            decoy_interactions = decoy_interactions.filter(DecoyInteraction.timestamp <= cutoff_str)
        decoy_interactions = decoy_interactions.all()

        for d_int in decoy_interactions:
            if d_int.source_account_id not in self.graph:
                continue
            if d_int.decoy_id not in self.graph:
                continue
            self.graph.add_edge(
                d_int.source_account_id,
                d_int.decoy_id,
                edge_type="decoy_simulation",
                interaction_id=d_int.interaction_id,
                amount=d_int.synthetic_amount,
                timestamp=d_int.timestamp,
                interaction_type=d_int.interaction_type,
                hop_number=d_int.hop_number,
                is_synthetic=True,
            )

        self.built_at = datetime.utcnow().isoformat()
        print(f"  [Graph] Built: {self.graph.number_of_nodes()} nodes, "
              f"{self.graph.number_of_edges()} edges "
              f"(cutoff: {cutoff_str or 'none'})")

    # ── QUERY METHODS ─────────────────────────────────────────────────────────

    def get_account_subgraph(self, account_id: str, hops: int = 2) -> nx.DiGraph:
        """Return ego-graph centered on account_id within given hop radius."""
        if account_id not in self.graph:
            return nx.DiGraph()
        nodes = nx.ego_graph(self.graph, account_id, radius=hops,
                              undirected=True).nodes()
        return self.graph.subgraph(nodes).copy()

    def find_paths(self, source: str, target: str,
                   max_hops: int = 5) -> list[list]:
        """Find all simple paths from source to target up to max_hops."""
        if source not in self.graph or target not in self.graph:
            return []
        try:
            paths = list(nx.all_simple_paths(
                self.graph, source=source, target=target, cutoff=max_hops
            ))
            return paths
        except nx.NetworkXNoPath:
            return []

    def get_transaction_path_for_complaint(self, complaint_account: str,
                                            location_id: str) -> list[dict]:
        """
        Find the money-flow path from a victim account toward a cash-out location.
        Returns a list of hop dicts with node details and edge amounts.
        """
        paths = self.find_paths(complaint_account, location_id, max_hops=6)
        if not paths:
            return []
        # Return the shortest path
        best_path = min(paths, key=len)
        result = []
        for i, node_id in enumerate(best_path):
            node_data = self.graph.nodes[node_id]
            hop = {
                "node_id": node_id,
                "node_type": node_data.get("node_type", "account"),
                "city": node_data.get("city", ""),
                "risk_label": node_data.get("risk_label", ""),
                "hop_index": i,
            }
            if i < len(best_path) - 1:
                next_node = best_path[i + 1]
                edges = self.graph.get_edge_data(node_id, next_node, default={})
                # Handle parallel edges (MultiDiGraph would have keys, DiGraph has one)
                hop["outgoing_amount"] = edges.get("amount", 0)
                hop["outgoing_timestamp"] = edges.get("timestamp", "")
                hop["edge_type"] = edges.get("edge_type", "transfer")
            result.append(hop)
        return result

    def compute_graph_features(self, account_id: str) -> dict:
        """
        Compute graph-derived features for a single account.
        Used by the feature engineering pipeline.
        """
        if account_id not in self.graph:
            return {}

        in_degree = self.graph.in_degree(account_id)
        out_degree = self.graph.out_degree(account_id)

        # In-neighbours (who sent money to this account)
        predecessors = list(self.graph.predecessors(account_id))
        # Out-neighbours (who this account sent money to)
        successors = list(self.graph.successors(account_id))

        # Unique counterparties
        unique_counterparties = len(set(predecessors + successors))

        # Count suspicious neighbours (accounts with risk_label in mule/suspect)
        suspicious_labels = {"mule", "suspect"}
        suspicious_neighbours = sum(
            1 for n in predecessors + successors
            if self.graph.nodes[n].get("risk_label", "") in suspicious_labels
        )

        # Count complaint-linked neighbours
        complaint_neighbours = sum(
            1 for n in predecessors
            if self.graph.nodes[n].get("is_victim", False)
        )

        # Check if any direct predecessor is a victim account
        has_victim_predecessor = any(
            self.graph.nodes[n].get("is_victim", False)
            for n in predecessors
        )

        # Incoming edge amounts
        in_amounts = [
            data.get("amount", 0)
            for _, _, data in self.graph.in_edges(account_id, data=True)
            if data.get("edge_type") == "transfer"
        ]
        out_amounts = [
            data.get("amount", 0)
            for _, _, data in self.graph.out_edges(account_id, data=True)
            if data.get("edge_type") == "transfer"
        ]

        total_in = sum(in_amounts)
        total_out = sum(out_amounts)

        # Pass-through ratio: how much of incoming immediately goes out
        pass_through = total_out / total_in if total_in > 0 else 0.0

        # Count connected location nodes (historical cash-out behaviour)
        location_successors = [
            n for n in successors
            if self.graph.nodes[n].get("node_type") == "location"
        ]

        return {
            "in_degree": in_degree,
            "out_degree": out_degree,
            "unique_counterparties": unique_counterparties,
            "suspicious_neighbours": suspicious_neighbours,
            "complaint_neighbours": complaint_neighbours,
            "has_victim_predecessor": int(has_victim_predecessor),
            "total_incoming_amount": total_in,
            "total_outgoing_amount": total_out,
            "pass_through_ratio": round(pass_through, 4),
            "historical_cashout_locations": len(location_successors),
            "fan_in": in_degree,
            "fan_out": out_degree,
        }

    def to_json(self, account_id: str = None, hops: int = 2) -> dict:
        """
        Serialize graph (or subgraph) to JSON for the frontend.
        Frontend uses this to render the interactive transaction network.
        """
        if account_id:
            g = self.get_account_subgraph(account_id, hops)
        else:
            g = self.graph

        nodes = []
        for node_id, data in g.nodes(data=True):
            nodes.append({
                "id": node_id,
                "type": data.get("node_type", "account"),
                "city": data.get("city", ""),
                "risk_label": data.get("risk_label", ""),
                "mule_risk_score": data.get("mule_risk_score", 0),
                "is_victim": data.get("is_victim", False),
                "latitude": data.get("latitude"),
                "longitude": data.get("longitude"),
                "is_decoy": data.get("is_decoy", False),
                "decoy_type": data.get("decoy_type"),
                "status": data.get("status"),
                "synthetic_account_id": data.get("synthetic_account_id"),
                "activation_reason": data.get("activation_reason"),
                "interaction_count": data.get("interaction_count", 0),
                "is_synthetic": data.get("is_synthetic", False),
            })

        edges = []
        for src, dst, data in g.edges(data=True):
            edges.append({
                "source": src,
                "target": dst,
                "edge_type": data.get("edge_type", "transfer"),
                "amount": data.get("amount", 0),
                "timestamp": data.get("timestamp", ""),
                "interaction_id": data.get("interaction_id"),
                "interaction_type": data.get("interaction_type"),
                "is_synthetic": data.get("is_synthetic", False),
            })

        return {"nodes": nodes, "edges": edges}
