import React, { useCallback, useEffect, useState, useMemo } from 'react';
import ReactFlow, {
  Node,
  Edge,
  Background,
  Controls,
  MiniMap,
  useNodesState,
  useEdgesState,
  addEdge,
  Connection,
  NodeTypes,
  MarkerType,
  Panel,
  ConnectionMode,
} from 'reactflow';
import 'reactflow/dist/style.css';
import dagre from 'dagre';
import api from '../services/api';
import graphApi, { GraphNode, GraphEdge } from '../services/graphApi';
import {
  CircleStackIcon,
  ArrowPathIcon,
  MagnifyingGlassIcon,
  FunnelIcon,
  PlusCircleIcon,
  XMarkIcon,
  PencilIcon,
  TrashIcon,
  ExclamationTriangleIcon,
} from '@heroicons/react/24/outline';

// Custom node components
import EntityNode from './graph/EntityNode';
import EventClusterNode from './graph/EventClusterNode';
import NodeEditorModal from './graph/NodeEditorModal';
import EdgeEditorModal from './graph/EdgeEditorModal';

// Node type registry
const nodeTypes: NodeTypes = {
  entity: EntityNode,
  eventCluster: EventClusterNode,
};

// Interfaces imported from graphApi

interface Props {
  investigationId: string;
  onCountsChange?: (nodeCount: number, edgeCount: number) => void;
}

// Layout configuration
const dagreGraph = new dagre.graphlib.Graph();
dagreGraph.setDefaultEdgeLabel(() => ({}));

const nodeWidth = 220;
const nodeHeight = 80;

// LocalStorage helpers
const STORAGE_KEY_PREFIX = 'graph_layout_';

const getStorageKey = (investigationId: string) => `${STORAGE_KEY_PREFIX}${investigationId}`;

const saveLayoutToStorage = (investigationId: string, positions: Record<string, { x: number; y: number }>) => {
  try {
    localStorage.setItem(getStorageKey(investigationId), JSON.stringify(positions));
  } catch (error) {
    console.error('Failed to save layout to localStorage:', error);
  }
};

const loadLayoutFromStorage = (investigationId: string): Record<string, { x: number; y: number }> | null => {
  try {
    const stored = localStorage.getItem(getStorageKey(investigationId));
    return stored ? JSON.parse(stored) : null;
  } catch (error) {
    console.error('Failed to load layout from localStorage:', error);
    return null;
  }
};

const clearLayoutFromStorage = (investigationId: string) => {
  try {
    localStorage.removeItem(getStorageKey(investigationId));
  } catch (error) {
    console.error('Failed to clear layout from localStorage:', error);
  }
};

// Helper to check if two nodes overlap
const nodesOverlap = (
  pos1: { x: number; y: number },
  pos2: { x: number; y: number },
  padding = 20
): boolean => {
  // AABB (Axis-Aligned Bounding Box) collision detection
  const overlap = (
    pos1.x < pos2.x + nodeWidth + padding &&
    pos1.x + nodeWidth + padding > pos2.x &&
    pos1.y < pos2.y + nodeHeight + padding &&
    pos1.y + nodeHeight + padding > pos2.y
  );

  return overlap;
};

// Helper to resolve overlapping positions
const resolveOverlaps = (positions: Record<string, { x: number; y: number }>): Record<string, { x: number; y: number }> => {
  const nodeIds = Object.keys(positions);
  if (nodeIds.length === 0) return positions;

  const resolvedPositions = { ...positions };
  const maxIterations = 100;
  let iteration = 0;
  let hasOverlaps = true;

  while (hasOverlaps && iteration < maxIterations) {
    hasOverlaps = false;
    iteration++;

    for (let i = 0; i < nodeIds.length; i++) {
      for (let j = i + 1; j < nodeIds.length; j++) {
        const id1 = nodeIds[i];
        const id2 = nodeIds[j];
        const pos1 = resolvedPositions[id1];
        const pos2 = resolvedPositions[id2];

        if (nodesOverlap(pos1, pos2, 20)) {
          hasOverlaps = true;

          // Calculate displacement vector
          const centerDx = pos2.x - pos1.x;
          const centerDy = pos2.y - pos1.y;
          const distance = Math.sqrt(centerDx * centerDx + centerDy * centerDy);

          // Minimum distance needed (with padding)
          const minDistance = Math.sqrt(
            Math.pow(nodeWidth + 40, 2) + Math.pow(nodeHeight + 40, 2)
          ) / 2;

          if (distance === 0 || distance < 1) {
            // Nodes are at exact same position, move them apart horizontally
            resolvedPositions[id2] = {
              x: pos2.x + nodeWidth + 60,
              y: pos2.y,
            };
          } else {
            // Move nodes apart along the vector connecting them
            const moveDistance = (minDistance - distance) / 2 + 20;
            const moveX = (centerDx / distance) * moveDistance;
            const moveY = (centerDy / distance) * moveDistance;

            resolvedPositions[id1] = {
              x: pos1.x - moveX,
              y: pos1.y - moveY,
            };
            resolvedPositions[id2] = {
              x: pos2.x + moveX,
              y: pos2.y + moveY,
            };
          }
        }
      }
    }
  }

  return resolvedPositions;
}

const getLayoutedElements = (nodes: Node[], edges: Edge[], direction = 'TB') => {
  // Grid layout configuration
  const nodesPerRow = 6;
  const horizontalSpacing = nodeWidth + 100; // Space between nodes horizontally
  const verticalSpacing = nodeHeight + 120; // Space between rows
  const startX = 50; // Starting X position
  const startY = 50; // Starting Y position

  // Create a simple grid layout
  const layoutedNodes = nodes.map((node, index) => {
    const row = Math.floor(index / nodesPerRow);
    const col = index % nodesPerRow;

    return {
      ...node,
      position: {
        x: startX + col * horizontalSpacing,
        y: startY + row * verticalSpacing,
      },
    };
  });

  return { nodes: layoutedNodes, edges };
};

const InteractiveGraphViewer: React.FC<Props> = ({ investigationId, onCountsChange }) => {
  const [nodes, setNodes, onNodesChange] = useNodesState([]);
  const [edges, setEdges, onEdgesChange] = useEdgesState([]);
  const [rawNodes, setRawNodes] = useState<GraphNode[]>([]);
  const [rawEdges, setRawEdges] = useState<GraphEdge[]>([]);
  const [loading, setLoading] = useState(true);
  const [selectedNode, setSelectedNode] = useState<GraphNode | null>(null);
  const [selectedEdge, setSelectedEdge] = useState<GraphEdge | null>(null);
  const [searchTerm, setSearchTerm] = useState('');
  const [filterTags, setFilterTags] = useState<string[]>([]);
  const [showEventClusters, setShowEventClusters] = useState(true);

  // Draggable panel states - use refs to track panel elements
  const containerRef = React.useRef<HTMLDivElement>(null);
  const nodePanelRef = React.useRef<HTMLDivElement>(null);
  const edgePanelRef = React.useRef<HTMLDivElement>(null);
  const [nodePanelPosition, setNodePanelPosition] = useState<{ x: number; y: number } | null>(null);
  const [edgePanelPosition, setEdgePanelPosition] = useState<{ x: number; y: number } | null>(null);
  const [isDraggingNodePanel, setIsDraggingNodePanel] = useState(false);
  const [isDraggingEdgePanel, setIsDraggingEdgePanel] = useState(false);
  const [dragStartPos, setDragStartPos] = useState({ x: 0, y: 0 });

  // Modal states
  const [showNodeModal, setShowNodeModal] = useState(false);
  const [showEdgeModal, setShowEdgeModal] = useState(false);
  const [editingNode, setEditingNode] = useState<GraphNode | null>(null);
  const [editingEdge, setEditingEdge] = useState<GraphEdge | null>(null);
  const [connectingFrom, setConnectingFrom] = useState<number | null>(null);

  // Confirmation modals
  const [deleteNodeModalOpen, setDeleteNodeModalOpen] = useState(false);
  const [nodeToDelete, setNodeToDelete] = useState<number | null>(null);
  const [deleteEdgeModalOpen, setDeleteEdgeModalOpen] = useState(false);
  const [edgeToDelete, setEdgeToDelete] = useState<number | null>(null);
  const [clearLayoutModalOpen, setClearLayoutModalOpen] = useState(false);
  const [errorModalOpen, setErrorModalOpen] = useState(false);
  const [errorMessage, setErrorMessage] = useState('');

  // Detect dark mode
  const [isDarkMode, setIsDarkMode] = useState(
    document.documentElement.classList.contains('dark')
  );

  useEffect(() => {
    // Watch for theme changes
    const observer = new MutationObserver(() => {
      setIsDarkMode(document.documentElement.classList.contains('dark'));
    });

    observer.observe(document.documentElement, {
      attributes: true,
      attributeFilter: ['class'],
    });

    return () => observer.disconnect();
  }, []);



  // Fetch graph data
  const fetchGraph = useCallback(async () => {
    try {
      const response = await api.get(`/api/v1/graph/${investigationId}`);
      const { nodes: fetchedNodes, edges: fetchedEdges } = response.data;

      const nodes = fetchedNodes || [];
      const edges = fetchedEdges || [];
      setRawNodes(nodes);
      setRawEdges(edges);
      onCountsChange?.(nodes.length, edges.length);
    } catch (error) {
      console.error('Failed to fetch graph:', error);
    } finally {
      setLoading(false);
    }
  }, [investigationId]);

  useEffect(() => {
    fetchGraph();
    // Increase polling interval to reduce interference with manual positioning
    const interval = setInterval(fetchGraph, 30000); // Poll every 30 seconds instead of 5
    return () => clearInterval(interval);
  }, [fetchGraph]);

  // Cluster event nodes
  const { processedNodes, eventClusters } = useMemo(() => {
    if (!showEventClusters) {
      return { processedNodes: rawNodes, eventClusters: new Map() };
    }

    const eventNodes: GraphNode[] = [];
    const regularNodes: GraphNode[] = [];
    const clusters = new Map<string, GraphNode[]>();

    rawNodes.forEach((node) => {
      const nodeType = node.data.node_type || 'entity';

      if (nodeType === 'event' || nodeType === 'parsed_event') {
        eventNodes.push(node);

        // Cluster by event_type or artifact
        const clusterKey = node.data.event_type || node.data.artifact_id || 'unknown';
        if (!clusters.has(clusterKey)) {
          clusters.set(clusterKey, []);
        }
        clusters.get(clusterKey)!.push(node);
      } else {
        regularNodes.push(node);
      }
    });

    return { processedNodes: regularNodes, eventClusters: clusters };
  }, [rawNodes, showEventClusters]);

  // Convert to ReactFlow format
  useEffect(() => {
    const flowNodes: Node[] = [];
    const flowEdges: Edge[] = [];

    // Load saved layout from localStorage
    const savedLayout = loadLayoutFromStorage(investigationId);

    // Collect all positions first (before resolving overlaps)
    const allPositions: Record<string, { x: number; y: number }> = {};

    // Add regular nodes
    processedNodes.forEach((node) => {
      const hasPosition = node.data.position?.x !== undefined && node.data.position?.y !== undefined;

      // Ensure node.data has a 'name' field, fallback to label if missing
      const nodeName = node.data.name || node.label;

      // Update node.data to ensure it has a name field
      const updatedData = {
        ...node.data,
        name: nodeName,
      };

      const nodeId = String(node.node_id);

      // Priority: 1. localStorage, 2. backend position, 3. default (0,0)
      let position = { x: 0, y: 0 };
      if (savedLayout && savedLayout[nodeId]) {
        position = savedLayout[nodeId];
      } else if (hasPosition) {
        position = { x: node.data.position.x, y: node.data.position.y };
      }

      // Store position for overlap resolution
      allPositions[nodeId] = position;

      flowNodes.push({
        id: nodeId,
        type: 'entity',
        data: {
          label: nodeName, // Use name from data dictionary
          tags: node.tags,
          rawData: updatedData,
          onSelect: () => setSelectedNode({ ...node, data: updatedData }),
          onDelete: () => handleDeleteNodeClick(node.node_id),
        },
        position,
      });
    });

    // Add event cluster nodes
    if (showEventClusters) {
      let clusterIndex = 0;
      eventClusters.forEach((clusterNodes, clusterKey) => {
        if (clusterNodes.length > 0) {
          const clusterNode = clusterNodes[0];
          const clusterLabel = clusterNode.data.event_type || `Cluster: ${clusterKey}`;
          const clusterId = `cluster-${clusterKey}`;

          // Check if we have a saved position for this cluster
          let clusterPosition: { x: number; y: number };
          if (savedLayout && savedLayout[clusterId]) {
            // Use saved position from localStorage
            clusterPosition = savedLayout[clusterId];
          } else {
            // Default position: below regular nodes to avoid overlap
            clusterPosition = { x: clusterIndex * (nodeWidth + 60), y: 400 };
          }

          allPositions[clusterId] = clusterPosition;

          flowNodes.push({
            id: clusterId,
            type: 'eventCluster',
            data: {
              label: clusterLabel,
              count: clusterNodes.length,
              events: clusterNodes,
              onExpand: () => {
                // TODO: Expand cluster to show individual events
              },
            },
            position: clusterPosition,
          });

          clusterIndex++;
        }
      });
    }

    // Add edges - filter out invalid edges
    const nodeIdSet = new Set(flowNodes.map(n => n.id));

    rawEdges.forEach((edge) => {
      const sourceId = String(edge.source_id);
      const targetId = String(edge.target_id);

      // Skip edges where source or target nodes don't exist
      if (!nodeIdSet.has(sourceId) || !nodeIdSet.has(targetId)) {
        return;
      }

      // Skip self-loops (edges where source === target)
      if (sourceId === targetId) {
        return;
      }

      const isSuspicious = edge.tags?.includes('suspicious') || false;

      flowEdges.push({
        id: String(edge.edge_id),
        source: sourceId,
        target: targetId,
        sourceHandle: null,
        targetHandle: null,
        label: edge.relationship,
        type: 'smoothstep',
        animated: isSuspicious,
        markerEnd: {
          type: MarkerType.ArrowClosed,
          width: 20,
          height: 20,
        },
        style: {
          stroke: isSuspicious ? '#ef4444' : '#94a3b8',
          strokeWidth: 2,
        },
        labelStyle: {
          fill: isDarkMode ? '#f3f4f6' : '#1f2937',
          fontWeight: 500,
          fontSize: 12,
        },
        labelBgStyle: {
          fill: isDarkMode ? '#1f2937' : '#dbeafe',
          fillOpacity: 0.9,
        },
        labelBgPadding: [4, 6] as [number, number],
        labelBgBorderRadius: 4,
      });
    });

    // Auto-layout if nodes don't have positions
    const hasPositions = flowNodes.some((n) => n.position.x !== 0 || n.position.y !== 0);

    if (!hasPositions && flowNodes.length > 0) {
      const { nodes: layoutedNodes, edges: layoutedEdges } = getLayoutedElements(
        flowNodes,
        flowEdges,
        'TB'
      );
      setNodes(layoutedNodes);
      setEdges(layoutedEdges);

      // Save initial layout to localStorage
      const positions: Record<string, { x: number; y: number }> = {};
      layoutedNodes.forEach((node) => {
        positions[node.id] = node.position;
      });
      saveLayoutToStorage(investigationId, positions);
    } else {
      // ALWAYS resolve overlaps in all positions
      const resolvedPositions = resolveOverlaps(allPositions);

      // Apply resolved positions to flowNodes
      flowNodes.forEach((node) => {
        if (resolvedPositions[node.id]) {
          node.position = resolvedPositions[node.id];
        }
      });

      // Save resolved positions to localStorage
      saveLayoutToStorage(investigationId, resolvedPositions);

      setNodes(flowNodes);
      setEdges(flowEdges);
    }
  }, [processedNodes, rawEdges, eventClusters, showEventClusters, isDarkMode, investigationId, setNodes, setEdges]);

  // Save node positions when dragged
  const onNodeDragStop = useCallback(
    async (event: React.MouseEvent, node: Node) => {
      // Save to localStorage immediately (this takes priority)
      const savedLayout = loadLayoutFromStorage(investigationId) || {};
      savedLayout[node.id] = { x: node.position.x, y: node.position.y };
      saveLayoutToStorage(investigationId, savedLayout);

      // Only save to backend for real nodes (not cluster nodes)
      // Cluster nodes have IDs like "cluster-xxx", real nodes are numeric
      const isClusterNode = node.id.startsWith('cluster-');
      if (!isClusterNode) {
        try {
          await api.patch(
            `/api/v1/graph/nodes/${investigationId}/${node.id}/position`,
            {
              x: node.position.x,
              y: node.position.y,
            }
          );
        } catch (error) {
          console.error('Failed to save node position to backend:', error);
        }
      }
    },
    [investigationId]
  );

  // Handle node selection
  const onNodeClick = useCallback((event: React.MouseEvent, node: Node) => {
    const rawNode = rawNodes.find((n) => String(n.node_id) === node.id);
    if (rawNode) {
      setSelectedNode(rawNode);
      setSelectedEdge(null);
    }
  }, [rawNodes]);

  // Handle edge selection
  const onEdgeClick = useCallback((event: React.MouseEvent, edge: Edge) => {
    const rawEdge = rawEdges.find((e) => String(e.edge_id) === edge.id);
    if (rawEdge) {
      setSelectedEdge(rawEdge);
      setSelectedNode(null);
    }
  }, [rawEdges]);

  // CRUD operations
  const handleCreateNode = async (nodeData: {
    label: string;
    data: Record<string, any>;
    tags: string[];
  }) => {
    try {
      await graphApi.createNode(investigationId, nodeData);
      await fetchGraph();
    } catch (error: any) {
      console.error('Failed to create node:', error);
      setErrorMessage(error.response?.data?.detail || error.message || 'Failed to create node');
      setErrorModalOpen(true);
    }
  };

  const handleUpdateNode = async (nodeData: {
    label: string;
    data: Record<string, any>;
    tags: string[];
  }) => {
    if (!editingNode) return;
    try {
      await graphApi.updateNode(investigationId, editingNode.node_id, nodeData);
      await fetchGraph();
      setEditingNode(null);
      setSelectedNode(null);
    } catch (error: any) {
      console.error('Failed to update node:', error);
      setErrorMessage(error.response?.data?.detail || error.message || 'Failed to update node');
      setErrorModalOpen(true);
    }
  };

  const handleDeleteNodeClick = (nodeId: number) => {
    setNodeToDelete(nodeId);
    setDeleteNodeModalOpen(true);
  };

  const confirmDeleteNode = async () => {
    if (!nodeToDelete) return;
    try {
      await graphApi.deleteNode(investigationId, nodeToDelete);
      await fetchGraph();
      setSelectedNode(null);
      setDeleteNodeModalOpen(false);
      setNodeToDelete(null);
    } catch (error: any) {
      console.error('Failed to delete node:', error);
      setDeleteNodeModalOpen(false);
      setNodeToDelete(null);
      setErrorMessage(error.response?.data?.detail || error.message || 'Failed to delete node');
      setErrorModalOpen(true);
    }
  };

  const cancelDeleteNode = () => {
    setDeleteNodeModalOpen(false);
    setNodeToDelete(null);
  };

  const handleCreateEdge = async (edgeData: {
    source_id: number;
    target_id: number;
    relationship: string;
    data: Record<string, any>;
    tags: string[];
  }) => {
    try {
      await graphApi.createEdge(investigationId, edgeData);
      await fetchGraph();
      setConnectingFrom(null);
    } catch (error: any) {
      console.error('Failed to create edge:', error);
      setErrorMessage(error.response?.data?.detail || error.message || 'Failed to create edge');
      setErrorModalOpen(true);
    }
  };

  const handleUpdateEdge = async (edgeData: {
    relationship: string;
    data: Record<string, any>;
    tags: string[];
  }) => {
    if (!editingEdge) return;
    try {
      await graphApi.updateEdge(investigationId, editingEdge.edge_id, edgeData);
      await fetchGraph();
      setEditingEdge(null);
      setSelectedEdge(null);
    } catch (error: any) {
      console.error('Failed to update edge:', error);
      setErrorMessage(error.response?.data?.detail || error.message || 'Failed to update edge');
      setErrorModalOpen(true);
    }
  };

  const handleDeleteEdgeClick = (edgeId: number) => {
    setEdgeToDelete(edgeId);
    setDeleteEdgeModalOpen(true);
  };

  const confirmDeleteEdge = async () => {
    if (!edgeToDelete) return;
    try {
      await graphApi.deleteEdge(investigationId, edgeToDelete);
      await fetchGraph();
      setSelectedEdge(null);
      setDeleteEdgeModalOpen(false);
      setEdgeToDelete(null);
    } catch (error: any) {
      console.error('Failed to delete edge:', error);
      setDeleteEdgeModalOpen(false);
      setEdgeToDelete(null);
      setErrorMessage(error.response?.data?.detail || error.message || 'Failed to delete edge');
      setErrorModalOpen(true);
    }
  };

  const cancelDeleteEdge = () => {
    setDeleteEdgeModalOpen(false);
    setEdgeToDelete(null);
  };

  // Auto-layout handler
  const handleAutoLayout = useCallback(() => {
    const { nodes: layoutedNodes, edges: layoutedEdges } = getLayoutedElements(
      nodes,
      edges,
      'TB'
    );

    setNodes(layoutedNodes);
    setEdges(layoutedEdges);

    // Save all positions to localStorage
    const positions: Record<string, { x: number; y: number }> = {};
    layoutedNodes.forEach((node) => {
      positions[node.id] = node.position;
    });
    saveLayoutToStorage(investigationId, positions);
  }, [nodes, edges, investigationId, setNodes, setEdges]);

  // Clear layout handler
  const handleClearLayoutClick = useCallback(() => {
    setClearLayoutModalOpen(true);
  }, []);

  const confirmClearLayout = useCallback(() => {
    clearLayoutFromStorage(investigationId);
    setClearLayoutModalOpen(false);
    // Trigger re-fetch to reload with default positions
    fetchGraph();
  }, [investigationId, fetchGraph]);

  const cancelClearLayout = () => {
    setClearLayoutModalOpen(false);
  };

  // Draggable panel handlers
  const handleNodePanelMouseDown = useCallback((e: React.MouseEvent<HTMLDivElement>) => {
    if ((e.target as HTMLElement).closest('button, pre, input, select, textarea')) {
      return; // Don't start drag if clicking on interactive elements
    }

    if (!nodePanelRef.current || !containerRef.current) return;

    const panelRect = nodePanelRef.current.getBoundingClientRect();
    const containerRect = containerRef.current.getBoundingClientRect();

    // Calculate position relative to container
    const relativeX = panelRect.left - containerRect.left;
    const relativeY = panelRect.top - containerRect.top;

    // Calculate offset from mouse to top-left of panel
    const offsetX = e.clientX - panelRect.left;
    const offsetY = e.clientY - panelRect.top;

    // Set position immediately to current location before starting drag
    setNodePanelPosition({ x: relativeX, y: relativeY });
    setDragStartPos({ x: offsetX, y: offsetY });

    // Use setTimeout to ensure state is updated before enabling drag
    setTimeout(() => {
      setIsDraggingNodePanel(true);
    }, 0);
  }, []);

  const handleEdgePanelMouseDown = useCallback((e: React.MouseEvent<HTMLDivElement>) => {
    if ((e.target as HTMLElement).closest('button, pre, input, select, textarea')) {
      return; // Don't start drag if clicking on interactive elements
    }

    if (!edgePanelRef.current || !containerRef.current) return;

    const panelRect = edgePanelRef.current.getBoundingClientRect();
    const containerRect = containerRef.current.getBoundingClientRect();

    // Calculate position relative to container
    const relativeX = panelRect.left - containerRect.left;
    const relativeY = panelRect.top - containerRect.top;

    // Calculate offset from mouse to top-left of panel
    const offsetX = e.clientX - panelRect.left;
    const offsetY = e.clientY - panelRect.top;

    // Set position immediately to current location before starting drag
    setEdgePanelPosition({ x: relativeX, y: relativeY });
    setDragStartPos({ x: offsetX, y: offsetY });

    // Use setTimeout to ensure state is updated before enabling drag
    setTimeout(() => {
      setIsDraggingEdgePanel(true);
    }, 0);
  }, []);

  const handleMouseMove = useCallback((e: MouseEvent) => {
    if (!containerRef.current) return;

    const containerRect = containerRef.current.getBoundingClientRect();

    if (isDraggingNodePanel) {
      // Calculate position relative to container
      const newX = e.clientX - containerRect.left - dragStartPos.x;
      const newY = e.clientY - containerRect.top - dragStartPos.y;
      setNodePanelPosition({ x: newX, y: newY });
    }
    if (isDraggingEdgePanel) {
      // Calculate position relative to container
      const newX = e.clientX - containerRect.left - dragStartPos.x;
      const newY = e.clientY - containerRect.top - dragStartPos.y;
      setEdgePanelPosition({ x: newX, y: newY });
    }
  }, [isDraggingNodePanel, isDraggingEdgePanel, dragStartPos]);

  const handleMouseUp = useCallback(() => {
    setIsDraggingNodePanel(false);
    setIsDraggingEdgePanel(false);
  }, []);

  useEffect(() => {
    if (isDraggingNodePanel || isDraggingEdgePanel) {
      window.addEventListener('mousemove', handleMouseMove);
      window.addEventListener('mouseup', handleMouseUp);
      return () => {
        window.removeEventListener('mousemove', handleMouseMove);
        window.removeEventListener('mouseup', handleMouseUp);
      };
    }
  }, [isDraggingNodePanel, isDraggingEdgePanel, handleMouseMove, handleMouseUp]);

  // Reset panel position when panel is closed
  useEffect(() => {
    if (!selectedNode) {
      setNodePanelPosition(null);
    }
  }, [selectedNode]);

  useEffect(() => {
    if (!selectedEdge) {
      setEdgePanelPosition(null);
    }
  }, [selectedEdge]);

  if (loading) {
    return (
      <div className="flex items-center justify-center p-8">
        <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-blue-600 dark:border-blue-400"></div>
      </div>
    );
  }

  if (rawNodes.length === 0 && rawEdges.length === 0) {
    return (
      <div className="text-center p-8">
        <CircleStackIcon className="w-12 h-12 mx-auto mb-3 text-gray-400 dark:text-gray-600" />
        <p className="text-gray-600 dark:text-gray-400 text-sm">
          No graph data yet. Start analyzing to build the knowledge graph.
        </p>
      </div>
    );
  }

  return (
    <div ref={containerRef} className="relative h-full w-full">
      {/* Graph Canvas */}
      <ReactFlow
        nodes={nodes}
        edges={edges}
        onNodesChange={onNodesChange}
        onEdgesChange={onEdgesChange}
        onNodeDragStop={onNodeDragStop}
        onNodeClick={onNodeClick}
        onEdgeClick={onEdgeClick}
        nodeTypes={nodeTypes}
        attributionPosition="bottom-left"
        className="bg-gray-50 dark:bg-gray-900"
        connectionMode={ConnectionMode.Loose}
        defaultEdgeOptions={{
          type: 'smoothstep',
          animated: false,
        }}
        defaultViewport={{ x: 0, y: 0, zoom: 1 }}
      >
        <Background color="#94a3b8" gap={16} />
        <Controls />
        <MiniMap
          nodeColor={(node) => {
            if (node.type === 'eventCluster') return '#3b82f6';
            return '#10b981';
          }}
          nodeStrokeWidth={3}
          nodeBorderRadius={2}
          maskColor={isDarkMode ? 'rgb(31, 41, 55, 0.6)' : 'rgb(229, 231, 235, 0.6)'}
          className="bg-white dark:bg-gray-800 border border-gray-200 dark:border-gray-700 rounded-lg shadow-md cursor-pointer"
          zoomable
          pannable
        />

        {/* Control Panel */}
        <Panel position="top-right" className="space-y-2">
          <button
            onClick={() => {
              setEditingNode(null);
              setShowNodeModal(true);
            }}
            className="flex items-center gap-2 px-3 py-2 bg-gray-700 dark:bg-gray-700 text-white rounded-lg shadow-md hover:bg-gray-600 dark:hover:bg-gray-600 transition-colors"
            title="Create new node"
          >
            <PlusCircleIcon className="w-4 h-4" />
            <span className="text-sm font-medium">Add Node</span>
          </button>

          <button
            onClick={() => {
              setEditingEdge(null);
              setConnectingFrom(null);
              setShowEdgeModal(true);
            }}
            className="flex items-center gap-2 px-3 py-2 bg-gray-700 dark:bg-gray-700 text-white rounded-lg shadow-md hover:bg-gray-600 dark:hover:bg-gray-600 transition-colors"
            title="Create new edge"
          >
            <PlusCircleIcon className="w-4 h-4" />
            <span className="text-sm font-medium">Add Edge</span>
          </button>

          <button
            onClick={handleAutoLayout}
            className="flex items-center gap-2 px-3 py-2 bg-white dark:bg-gray-800 text-gray-900 dark:text-white rounded-lg shadow-md hover:bg-gray-50 dark:hover:bg-gray-700 transition-colors"
            title="Auto-arrange layout"
          >
            <ArrowPathIcon className="w-4 h-4" />
            <span className="text-sm font-medium">Auto Layout</span>
          </button>

          <button
            onClick={() => setShowEventClusters(!showEventClusters)}
            className={`flex items-center gap-2 px-3 py-2 rounded-lg shadow-md transition-colors ${showEventClusters
                ? 'bg-gray-600 dark:bg-gray-600 text-white hover:bg-gray-500 dark:hover:bg-gray-500'
                : 'bg-white dark:bg-gray-800 text-gray-900 dark:text-white hover:bg-gray-50 dark:hover:bg-gray-700'
              }`}
            title="Toggle event clustering"
          >
            <FunnelIcon className="w-4 h-4" />
            <span className="text-sm font-medium">
              {showEventClusters ? 'Clusters On' : 'Clusters Off'}
            </span>
          </button>

          <button
            onClick={fetchGraph}
            className="flex items-center gap-2 px-3 py-2 bg-white dark:bg-gray-800 text-gray-900 dark:text-white rounded-lg shadow-md hover:bg-gray-50 dark:hover:bg-gray-700 transition-colors"
            title="Refresh graph"
          >
            <ArrowPathIcon className="w-4 h-4" />
            <span className="text-sm font-medium">Refresh</span>
          </button>

          <button
            onClick={handleClearLayoutClick}
            className="flex items-center gap-2 px-3 py-2 bg-gray-700 dark:bg-gray-700 text-white rounded-lg shadow-md hover:bg-gray-600 dark:hover:bg-gray-600 transition-colors"
            title="Clear saved layout"
          >
            <TrashIcon className="w-4 h-4" />
            <span className="text-sm font-medium">Clear Layout</span>
          </button>
        </Panel>

        {/* Stats Panel */}
        <Panel position="top-left" className="bg-white dark:bg-gray-800 rounded-lg shadow-md p-3">
          <div className="text-sm space-y-1 text-gray-900 dark:text-white">
            <div className="flex items-center gap-2">
              <CircleStackIcon className="w-4 h-4 text-green-600 dark:text-green-400" />
              <span className="font-medium">{processedNodes.length} Entities</span>
            </div>
            {showEventClusters && eventClusters.size > 0 && (
              <div className="flex items-center gap-2">
                <FunnelIcon className="w-4 h-4 text-blue-600 dark:text-blue-400" />
                <span className="font-medium">
                  {eventClusters.size} Clusters ({Array.from(eventClusters.values()).reduce((sum, cluster) => sum + cluster.length, 0)} events)
                </span>
              </div>
            )}
            <div className="flex items-center gap-2">
              <span className="text-purple-600 dark:text-purple-400">↔</span>
              <span className="font-medium">{rawEdges.length} Relationships</span>
            </div>
          </div>
        </Panel>
      </ReactFlow>

      {/* Node Details Panel (bottom overlay) - Outside ReactFlow to avoid context issues */}
      {selectedNode && (
        <div
          ref={nodePanelRef}
          className="absolute bg-white dark:bg-gray-800 rounded-lg shadow-2xl border border-gray-200 dark:border-gray-700"
          style={{
            left: nodePanelPosition ? `${nodePanelPosition.x}px` : '50%',
            top: nodePanelPosition ? `${nodePanelPosition.y}px` : '50%',
            transform: nodePanelPosition ? 'none' : 'translate(-50%, -50%)',
            width: '48rem',
            maxWidth: '90vw',
            cursor: isDraggingNodePanel ? 'grabbing' : 'default',
            userSelect: 'none',
            zIndex: 9999,
          }}
        >
          <div
            className="p-3 border-b border-gray-200 dark:border-gray-700 flex items-center justify-between cursor-grab active:cursor-grabbing"
            onMouseDown={handleNodePanelMouseDown}
          >
            <h3 className="font-semibold text-base text-gray-900 dark:text-white">
              Node Details
            </h3>
            <button
              onClick={() => setSelectedNode(null)}
              className="p-1 hover:bg-gray-100 dark:hover:bg-gray-700 rounded"
            >
              <XMarkIcon className="w-4 h-4" />
            </button>
          </div>

          <div className="p-3 space-y-3 max-h-64 overflow-y-auto">
            <div>
              <label className="text-xs font-medium text-gray-500 dark:text-gray-400 uppercase">
                Name
              </label>
              <p className="mt-1 text-sm font-medium text-gray-900 dark:text-white">
                {selectedNode.data.name || selectedNode.label}
              </p>
            </div>

            {selectedNode.tags.length > 0 && (
              <div>
                <label className="text-xs font-medium text-gray-500 dark:text-gray-400 uppercase">
                  Tags
                </label>
                <div className="mt-1 flex flex-wrap gap-1">
                  {selectedNode.tags.map((tag, idx) => (
                    <span
                      key={idx}
                      className="px-2 py-0.5 bg-blue-100 dark:bg-blue-900/30 text-blue-700 dark:text-blue-300 rounded text-xs"
                    >
                      {tag}
                    </span>
                  ))}
                </div>
              </div>
            )}

            <div>
              <label className="text-xs font-medium text-gray-500 dark:text-gray-400 uppercase">
                Data
              </label>
              <pre className="mt-1 p-2 bg-gray-50 dark:bg-gray-900 text-gray-900 dark:text-gray-100 rounded text-xs overflow-x-auto">
                {JSON.stringify(selectedNode.data, null, 2)}
              </pre>
            </div>

            <div className="grid grid-cols-2 gap-3 text-xs">
              <div>
                <label className="font-medium text-gray-500 dark:text-gray-400">
                  Created
                </label>
                <p className="mt-1 text-gray-900 dark:text-white">
                  {new Date(selectedNode.created_at).toLocaleString()}
                </p>
              </div>
              <div>
                <label className="font-medium text-gray-500 dark:text-gray-400">
                  Updated
                </label>
                <p className="mt-1 text-gray-900 dark:text-white">
                  {new Date(selectedNode.updated_at).toLocaleString()}
                </p>
              </div>
            </div>

            {/* Action Buttons */}
            <div className="flex gap-2 pt-2 border-t border-gray-200 dark:border-gray-700">
              <button
                onClick={() => {
                  setEditingNode(selectedNode);
                  setShowNodeModal(true);
                }}
                className="flex-1 flex items-center justify-center gap-2 px-3 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 text-sm font-medium"
              >
                <PencilIcon className="w-4 h-4" />
                Edit
              </button>
              <button
                onClick={() => handleDeleteNodeClick(selectedNode.node_id)}
                className="flex-1 flex items-center justify-center gap-2 px-3 py-2 bg-red-600 text-white rounded-lg hover:bg-red-700 text-sm font-medium"
              >
                <TrashIcon className="w-4 h-4" />
                Delete
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Edge Details Panel - Outside ReactFlow to avoid context issues */}
      {selectedEdge && (
        <div
          ref={edgePanelRef}
          className="absolute bg-white dark:bg-gray-800 rounded-lg shadow-2xl border border-gray-200 dark:border-gray-700"
          style={{
            left: edgePanelPosition ? `${edgePanelPosition.x}px` : '50%',
            top: edgePanelPosition ? `${edgePanelPosition.y}px` : '50%',
            transform: edgePanelPosition ? 'none' : 'translate(-50%, -50%)',
            width: '48rem',
            maxWidth: '90vw',
            cursor: isDraggingEdgePanel ? 'grabbing' : 'default',
            userSelect: 'none',
            zIndex: 9999,
          }}
        >
          <div
            className="p-3 border-b border-gray-200 dark:border-gray-700 flex items-center justify-between cursor-grab active:cursor-grabbing"
            onMouseDown={handleEdgePanelMouseDown}
          >
            <h3 className="font-semibold text-base text-gray-900 dark:text-white">
              Edge Details
            </h3>
            <button
              onClick={() => setSelectedEdge(null)}
              className="p-1 hover:bg-gray-100 dark:hover:bg-gray-700 rounded"
            >
              <XMarkIcon className="w-4 h-4" />
            </button>
          </div>

          <div className="p-3 space-y-3 max-h-64 overflow-y-auto">
            <div>
              <label className="text-xs font-medium text-gray-500 dark:text-gray-400 uppercase">
                Relationship
              </label>
              <p className="mt-1 text-sm font-medium text-gray-900 dark:text-white">
                {selectedEdge.relationship}
              </p>
            </div>

            <div className="grid grid-cols-2 gap-3">
              <div>
                <label className="text-xs font-medium text-gray-500 dark:text-gray-400 uppercase">
                  Source
                </label>
                <p className="mt-1 text-sm text-gray-900 dark:text-white">
                  Node {selectedEdge.source_id}
                </p>
              </div>
              <div>
                <label className="text-xs font-medium text-gray-500 dark:text-gray-400 uppercase">
                  Target
                </label>
                <p className="mt-1 text-sm text-gray-900 dark:text-white">
                  Node {selectedEdge.target_id}
                </p>
              </div>
            </div>

            {selectedEdge.tags.length > 0 && (
              <div>
                <label className="text-xs font-medium text-gray-500 dark:text-gray-400 uppercase">
                  Tags
                </label>
                <div className="mt-1 flex flex-wrap gap-1">
                  {selectedEdge.tags.map((tag, idx) => (
                    <span
                      key={idx}
                      className="px-2 py-0.5 bg-purple-100 dark:bg-purple-900/30 text-purple-700 dark:text-purple-300 rounded text-xs"
                    >
                      {tag}
                    </span>
                  ))}
                </div>
              </div>
            )}

            <div>
              <label className="text-xs font-medium text-gray-500 dark:text-gray-400 uppercase">
                Data
              </label>
              <pre className="mt-1 p-2 bg-gray-50 dark:bg-gray-900 text-gray-900 dark:text-gray-100 rounded text-xs overflow-x-auto">
                {JSON.stringify(selectedEdge.data, null, 2)}
              </pre>
            </div>

            {/* Action Buttons */}
            <div className="flex gap-2 pt-2 border-t border-gray-200 dark:border-gray-700">
              <button
                onClick={() => {
                  setEditingEdge(selectedEdge);
                  setShowEdgeModal(true);
                }}
                className="flex-1 flex items-center justify-center gap-2 px-3 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 text-sm font-medium"
              >
                <PencilIcon className="w-4 h-4" />
                Edit
              </button>
              <button
                onClick={() => handleDeleteEdgeClick(selectedEdge.edge_id)}
                className="flex-1 flex items-center justify-center gap-2 px-3 py-2 bg-red-600 text-white rounded-lg hover:bg-red-700 text-sm font-medium"
              >
                <TrashIcon className="w-4 h-4" />
                Delete
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Modals */}
      <NodeEditorModal
        isOpen={showNodeModal}
        onClose={() => {
          setShowNodeModal(false);
          setEditingNode(null);
        }}
        onSave={editingNode ? handleUpdateNode : handleCreateNode}
        node={editingNode}
        title={editingNode ? 'Edit Node' : 'Create Node'}
      />

      <EdgeEditorModal
        isOpen={showEdgeModal}
        onClose={() => {
          setShowEdgeModal(false);
          setEditingEdge(null);
          setConnectingFrom(null);
        }}
        onSave={editingEdge ? (data) => handleUpdateEdge(data) : handleCreateEdge}
        edge={editingEdge}
        nodes={rawNodes}
        preselectedSource={connectingFrom || undefined}
        title={editingEdge ? 'Edit Edge' : 'Create Edge'}
      />

      {/* Delete Node Confirmation Modal */}
      {deleteNodeModalOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center">
          <div
            className="absolute inset-0 bg-black bg-opacity-50"
            onClick={cancelDeleteNode}
          />
          <div className="relative bg-white dark:bg-gray-800 rounded-lg shadow-xl max-w-md w-full mx-4 p-6">
            <div className="flex items-start gap-4">
              <div className="flex-shrink-0">
                <div className="w-12 h-12 rounded-full bg-red-100 dark:bg-red-900/30 flex items-center justify-center">
                  <ExclamationTriangleIcon className="w-6 h-6 text-red-600 dark:text-red-400" />
                </div>
              </div>
              <div className="flex-1">
                <h3 className="text-lg font-semibold text-gray-900 dark:text-white mb-2">
                  Delete Node
                </h3>
                <p className="text-sm text-gray-600 dark:text-gray-400 mb-6">
                  Are you sure you want to delete this node? This will also delete all connected edges. This action cannot be undone.
                </p>
                <div className="flex gap-3 justify-end">
                  <button
                    onClick={cancelDeleteNode}
                    className="px-4 py-2 text-sm font-medium text-gray-700 dark:text-gray-300 bg-white dark:bg-gray-700 border border-gray-300 dark:border-gray-600 rounded-lg hover:bg-gray-50 dark:hover:bg-gray-600 transition-colors"
                  >
                    Cancel
                  </button>
                  <button
                    onClick={confirmDeleteNode}
                    className="px-4 py-2 text-sm font-medium text-white bg-red-600 rounded-lg hover:bg-red-700 transition-colors"
                  >
                    Delete
                  </button>
                </div>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* Delete Edge Confirmation Modal */}
      {deleteEdgeModalOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center">
          <div
            className="absolute inset-0 bg-black bg-opacity-50"
            onClick={cancelDeleteEdge}
          />
          <div className="relative bg-white dark:bg-gray-800 rounded-lg shadow-xl max-w-md w-full mx-4 p-6">
            <div className="flex items-start gap-4">
              <div className="flex-shrink-0">
                <div className="w-12 h-12 rounded-full bg-red-100 dark:bg-red-900/30 flex items-center justify-center">
                  <ExclamationTriangleIcon className="w-6 h-6 text-red-600 dark:text-red-400" />
                </div>
              </div>
              <div className="flex-1">
                <h3 className="text-lg font-semibold text-gray-900 dark:text-white mb-2">
                  Delete Edge
                </h3>
                <p className="text-sm text-gray-600 dark:text-gray-400 mb-6">
                  Are you sure you want to delete this edge? This action cannot be undone.
                </p>
                <div className="flex gap-3 justify-end">
                  <button
                    onClick={cancelDeleteEdge}
                    className="px-4 py-2 text-sm font-medium text-gray-700 dark:text-gray-300 bg-white dark:bg-gray-700 border border-gray-300 dark:border-gray-600 rounded-lg hover:bg-gray-50 dark:hover:bg-gray-600 transition-colors"
                  >
                    Cancel
                  </button>
                  <button
                    onClick={confirmDeleteEdge}
                    className="px-4 py-2 text-sm font-medium text-white bg-red-600 rounded-lg hover:bg-red-700 transition-colors"
                  >
                    Delete
                  </button>
                </div>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* Clear Layout Confirmation Modal */}
      {clearLayoutModalOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center">
          <div
            className="absolute inset-0 bg-black bg-opacity-50"
            onClick={cancelClearLayout}
          />
          <div className="relative bg-white dark:bg-gray-800 rounded-lg shadow-xl max-w-md w-full mx-4 p-6">
            <div className="flex items-start gap-4">
              <div className="flex-shrink-0">
                <div className="w-12 h-12 rounded-full bg-orange-100 dark:bg-orange-900/30 flex items-center justify-center">
                  <ExclamationTriangleIcon className="w-6 h-6 text-orange-600 dark:text-orange-400" />
                </div>
              </div>
              <div className="flex-1">
                <h3 className="text-lg font-semibold text-gray-900 dark:text-white mb-2">
                  Clear Saved Layout
                </h3>
                <p className="text-sm text-gray-600 dark:text-gray-400 mb-6">
                  Are you sure you want to clear the saved layout? This will reset all node positions to their default locations.
                </p>
                <div className="flex gap-3 justify-end">
                  <button
                    onClick={cancelClearLayout}
                    className="px-4 py-2 text-sm font-medium text-gray-700 dark:text-gray-300 bg-white dark:bg-gray-700 border border-gray-300 dark:border-gray-600 rounded-lg hover:bg-gray-50 dark:hover:bg-gray-600 transition-colors"
                  >
                    Cancel
                  </button>
                  <button
                    onClick={confirmClearLayout}
                    className="px-4 py-2 text-sm font-medium text-white bg-orange-600 rounded-lg hover:bg-orange-700 transition-colors"
                  >
                    Clear Layout
                  </button>
                </div>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* Error Modal */}
      {errorModalOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center">
          <div
            className="absolute inset-0 bg-black bg-opacity-50"
            onClick={() => setErrorModalOpen(false)}
          />
          <div className="relative bg-white dark:bg-gray-800 rounded-lg shadow-xl max-w-md w-full mx-4 p-6">
            <div className="flex items-start gap-4">
              <div className="flex-shrink-0">
                <div className="w-12 h-12 rounded-full bg-red-100 dark:bg-red-900/30 flex items-center justify-center">
                  <ExclamationTriangleIcon className="w-6 h-6 text-red-600 dark:text-red-400" />
                </div>
              </div>
              <div className="flex-1">
                <h3 className="text-lg font-semibold text-gray-900 dark:text-white mb-2">
                  Error
                </h3>
                <p className="text-sm text-gray-600 dark:text-gray-400 mb-6">
                  {errorMessage}
                </p>
                <div className="flex justify-end">
                  <button
                    onClick={() => setErrorModalOpen(false)}
                    className="px-4 py-2 text-sm font-medium text-white bg-blue-600 rounded-lg hover:bg-blue-700 transition-colors"
                  >
                    OK
                  </button>
                </div>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};

export default InteractiveGraphViewer;
