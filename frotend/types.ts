export type EType = "person" | "phone" | "vehicle" | "location" | "organization" | "transaction" | "event" | "email" | "account";
export type GNode = { id: string; name: string; type: EType; cases: string[]; degree: number; community: number; cross_case: boolean; aliases: string[]; first_seen?: string; last_seen?: string; mentions: number };
export type GEdge = { id: string; source: string; target: string; relation: string; confidence: number; count: number; cases: string[]; start_time?: string; end_time?: string; evidence_ids: string[]; attrs?: any };
export type GraphData = { nodes: GNode[]; edges: GEdge[]; truncated: boolean; total_nodes: number; total_edges: number; edges_truncated: boolean; communities: number };
export type CaseInfo = { id: string; title: string; description: string; status: string; documents: number; entities: number; evidence: number };
export type Tab = "overview" | "network" | "explainer" | "whatif" | "timeline" | "evidence" | "entities";
