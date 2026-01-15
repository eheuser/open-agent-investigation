import api from './api';

export interface GraphNode {
  node_id: number;
  label: string;
  data: Record<string, any>;
  tags: string[];
  created_at: string;
  updated_at: string;
}

export interface GraphEdge {
  edge_id: number;
  source_id: number;
  target_id: number;
  relationship: string;
  data: Record<string, any>;
  tags: string[];
  created_at: string;
  updated_at: string;
}

export interface GraphResponse {
  nodes: GraphNode[];
  edges: GraphEdge[];
}

export interface CreateNodeRequest {
  label: string;
  data?: Record<string, any>;
  tags?: string[];
}

export interface UpdateNodeRequest {
  label?: string;
  data?: Record<string, any>;
  tags?: string[];
}

export interface CreateEdgeRequest {
  source_id: number;
  target_id: number;
  relationship: string;
  data?: Record<string, any>;
  tags?: string[];
}

export interface UpdateEdgeRequest {
  relationship?: string;
  data?: Record<string, any>;
  tags?: string[];
}

export interface NodePositionUpdate {
  x: number;
  y: number;
}

export interface BulkPositionUpdate {
  positions: Record<string, { x: number; y: number }>;
}

const graphApi = {
  // Get full graph
  getGraph: async (investigationId: string): Promise<GraphResponse> => {
    const response = await api.get(`/api/v1/graph/${investigationId}`);
    return response.data;
  },

  // Node operations
  getNode: async (investigationId: string, nodeId: number): Promise<GraphNode> => {
    const response = await api.get(`/api/v1/graph/nodes/${investigationId}/${nodeId}`);
    return response.data;
  },

  createNode: async (investigationId: string, node: CreateNodeRequest): Promise<GraphNode> => {
    const response = await api.post(`/api/v1/graph/nodes/${investigationId}`, node);
    return response.data;
  },

  updateNode: async (
    investigationId: string,
    nodeId: number,
    updates: UpdateNodeRequest
  ): Promise<GraphNode> => {
    const response = await api.patch(
      `/api/v1/graph/nodes/${investigationId}/${nodeId}`,
      updates
    );
    return response.data;
  },

  deleteNode: async (investigationId: string, nodeId: number): Promise<void> => {
    await api.delete(`/api/v1/graph/nodes/${investigationId}/${nodeId}`);
  },

  updateNodePosition: async (
    investigationId: string,
    nodeId: number,
    position: NodePositionUpdate
  ): Promise<void> => {
    await api.patch(
      `/api/v1/graph/nodes/${investigationId}/${nodeId}/position`,
      position
    );
  },

  updateBulkPositions: async (
    investigationId: string,
    positions: BulkPositionUpdate
  ): Promise<void> => {
    await api.post(`/api/v1/graph/nodes/${investigationId}/positions/bulk`, positions);
  },

  // Edge operations
  createEdge: async (investigationId: string, edge: CreateEdgeRequest): Promise<GraphEdge> => {
    const response = await api.post(`/api/v1/graph/edges/${investigationId}`, edge);
    return response.data;
  },

  updateEdge: async (
    investigationId: string,
    edgeId: number,
    updates: UpdateEdgeRequest
  ): Promise<GraphEdge> => {
    const response = await api.patch(
      `/api/v1/graph/edges/${investigationId}/${edgeId}`,
      updates
    );
    return response.data;
  },

  deleteEdge: async (investigationId: string, edgeId: number): Promise<void> => {
    await api.delete(`/api/v1/graph/edges/${investigationId}/${edgeId}`);
  },
};

export default graphApi;
