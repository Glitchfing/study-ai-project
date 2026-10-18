import React, { memo, useCallback, useEffect, useMemo, useState } from "react";
import ReactFlow, {
  Background,
  Controls,
  Handle,
  MiniMap,
  Position,
  ReactFlowProvider,
  useEdgesState,
  useNodesState,
  useReactFlow,
} from "@xyflow/react";
import "@xyflow/react/dist/style.css";
import "../styles/mind-map.css";
import {
  getMindMap,
  generateMindMap,
  regenerateMindMap,
} from "../services/api";

const BRANCH_COLORS = ["#119da4", "#e29578", "#7c83fd", "#65b891", "#d77ba8", "#d7b45d"];

function ConceptNode({ id, data }) {
  const color = BRANCH_COLORS[data.branchIndex % BRANCH_COLORS.length];
  return (
    <div className={`mind-node mind-node-${data.type || "concept"}`} style={{ "--branch-color": color }}>
      <Handle type="target" position={Position.Left} className="mind-handle" />
      <div className="mind-node-heading">
        <span className="mind-node-label">{data.label}</span>
        {data.hasChildren ? (
          <button
            type="button"
            className="mind-node-toggle"
            title={data.expanded ? "Collapse branch" : "Expand branch"}
            aria-label={data.expanded ? `Collapse ${data.label}` : `Expand ${data.label}`}
            onClick={(event) => { event.stopPropagation(); data.onToggle(id); }}
          >
            {data.expanded ? "−" : "+"}
          </button>
        ) : null}
      </div>
      {data.description ? <div className="mind-node-description">{data.description}</div> : null}
      {data.sourcePages?.length ? <div className="mind-node-pages">Pages {data.sourcePages.slice(0, 4).join(", ")}</div> : null}
      <Handle type="source" position={Position.Right} className="mind-handle" />
    </div>
  );
}

const nodeTypes = { concept: memo(ConceptNode) };

function buildGraph(map, expandedIds, selectedId, onToggle, onSelect) {
  const allNodes = map?.nodes || [];
  const allEdges = map?.edges || [];
  if (!allNodes.length) return { nodes: [], edges: [] };
  const byId = new Map(allNodes.map((node) => [node.id, node]));
  const children = new Map();
  allNodes.forEach((node) => {
    if (node.parent_id && byId.has(node.parent_id)) {
      if (!children.has(node.parent_id)) children.set(node.parent_id, []);
      children.get(node.parent_id).push(node.id);
    }
  });
  const root = allNodes.find((node) => !node.parent_id) || allNodes[0];
  const visible = new Set();
  const depthById = new Map();
  const visibleByDepth = new Map();
  const visit = (node, depth) => {
    if (!node || visible.has(node.id)) return;
    visible.add(node.id);
    depthById.set(node.id, depth);
    if (!visibleByDepth.has(depth)) visibleByDepth.set(depth, []);
    visibleByDepth.get(depth).push(node.id);
    if (expandedIds.has(node.id)) {
      (children.get(node.id) || []).forEach((childId) => visit(byId.get(childId), depth + 1));
    }
  };
  visit(root, 0);
  const positions = new Map();
  [...visibleByDepth.entries()].forEach(([depth, ids]) => {
    ids.forEach((id, index) => positions.set(id, { x: depth * 280, y: index * 132 }));
  });
  const branchIndexById = new Map();
  const rootChildren = children.get(root.id) || [];
  const assignBranch = (nodeId, branchIndex) => {
    branchIndexById.set(nodeId, branchIndex);
    (children.get(nodeId) || []).forEach((childId) => assignBranch(childId, branchIndex));
  };
  rootChildren.forEach((childId, index) => assignBranch(childId, index));
  const nodes = allNodes.filter((node) => visible.has(node.id)).map((node) => ({
    id: node.id,
    type: "concept",
    position: positions.get(node.id) || { x: 0, y: 0 },
    selected: node.id === selectedId,
    data: {
      label: node.label,
      type: node.type,
      description: node.description,
      sourcePages: node.source_pages || [],
      branchIndex: branchIndexById.get(node.id) ?? 0,
      hasChildren: Boolean(children.get(node.id)?.length),
      expanded: expandedIds.has(node.id),
      onToggle,
    },
    style: { width: node.parent_id ? 218 : 238 },
  }));
  const edges = allEdges
    .filter((edge) => visible.has(edge.source) && visible.has(edge.target))
    .map((edge, index) => ({
      id: `${edge.source}-${edge.target}-${index}`,
      source: edge.source,
      target: edge.target,
      label: edge.label && edge.label !== "includes" ? edge.label : undefined,
      type: "smoothstep",
      animated: false,
      style: { stroke: "#4c8e91", strokeWidth: 1.6 },
      labelStyle: { fill: "#9bbdbb", fontSize: 10 },
      labelBgStyle: { fill: "#10282d", fillOpacity: 0.94 },
    }));
  return { nodes, edges, byId, children };
}

function GraphCanvas({ map, selectedNode, onSelect }) {
  const { fitView } = useReactFlow();
  const [expandedIds, setExpandedIds] = useState(() => new Set());
  const toggleNode = useCallback((id) => {
    setExpandedIds((current) => {
      const next = new Set(current);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }, []);
  useEffect(() => {
    const root = map?.nodes?.find((node) => !node.parent_id);
    if (root) setExpandedIds(new Set([root.id]));
  }, [map?.source_version, map?.topic]);
  const graph = useMemo(
    () => buildGraph(map, expandedIds, selectedNode?.id, toggleNode, onSelect),
    [map, expandedIds, selectedNode?.id, toggleNode, onSelect],
  );
  const [nodes, setNodes, onNodesChange] = useNodesState(graph.nodes);
  const [edges, setEdges, onEdgesChange] = useEdgesState(graph.edges);
  useEffect(() => { setNodes(graph.nodes); setEdges(graph.edges); }, [graph.nodes, graph.edges, setNodes, setEdges]);
  useEffect(() => { const id = setTimeout(() => fitView({ padding: 0.18, duration: 220 }), 60); return () => clearTimeout(id); }, [graph.nodes.length, fitView]);
  const expandAll = () => setExpandedIds(new Set((map?.nodes || []).map((node) => node.id)));
  const collapseAll = () => {
    const root = map?.nodes?.find((node) => !node.parent_id);
    setExpandedIds(new Set(root ? [root.id] : []));
  };
  return (
    <div className="mind-graph-shell">
      <div className="mind-graph-toolbar">
        <span>{graph.nodes.length} of {(map?.nodes || []).length} concepts visible</span>
        <div>
          <button type="button" className="mind-tool-button" onClick={expandAll}>Expand all</button>
          <button type="button" className="mind-tool-button" onClick={collapseAll}>Collapse all</button>
          <button type="button" className="mind-tool-button" onClick={() => fitView({ padding: 0.18, duration: 250 })}>Fit view</button>
        </div>
      </div>
      <div className="mind-graph-canvas">
        <ReactFlow
          nodes={nodes.map((node) => ({ ...node, data: { ...node.data, onSelect } }))}
          edges={edges}
          onNodesChange={onNodesChange}
          onEdgesChange={onEdgesChange}
          onNodeClick={(_, node) => onSelect(node.id)}
          nodeTypes={nodeTypes}
          fitView
          minZoom={0.15}
          maxZoom={1.6}
          proOptions={{ hideAttribution: true }}
        >
          <Background color="#24434a" gap={24} size={1} />
          <Controls />
          <MiniMap
            pannable
            zoomable
            nodeColor={(node) => BRANCH_COLORS[node.data?.branchIndex % BRANCH_COLORS.length] || "#119da4"}
            maskColor="rgba(4, 15, 18, 0.72)"
          />
        </ReactFlow>
      </div>
    </div>
  );
}

function MindMapInner({ noteId, noteTitle, defaultTopic, onNavigate, onOpenSource, toast }) {
  const [map, setMap] = useState(null);
  const [topic, setTopic] = useState("");
  const [selectedId, setSelectedId] = useState(null);
  const [loading, setLoading] = useState(true);
  const [generating, setGenerating] = useState(false);
  const [error, setError] = useState("");
  const selectedNode = map?.nodes?.find((node) => node.id === selectedId) || map?.nodes?.find((node) => !node.parent_id) || null;

  const loadMap = useCallback(async (force = false, selectedTopic = topic) => {
    if (!noteId) return;
    setError("");
    setGenerating(true);
    try {
      const response = force
        ? await regenerateMindMap(noteId, selectedTopic || null)
        : await getMindMap(noteId, selectedTopic || null);
      let nextMap = response?.mind_map;
      if (!nextMap && !force) {
        nextMap = (await generateMindMap(noteId, selectedTopic || null))?.mind_map;
      }
      if (!nextMap) throw new Error("No mind map could be generated from this note.");
      setMap(nextMap);
      setSelectedId(nextMap.nodes?.find((node) => !node.parent_id)?.id || nextMap.nodes?.[0]?.id || null);
    } catch (err) {
      setError(err?.message || "Could not load the mind map.");
    } finally {
      setGenerating(false);
      setLoading(false);
    }
  }, [noteId, topic]);

  useEffect(() => {
    setLoading(true);
    setMap(null);
    setTopic("");
    setSelectedId(null);
    loadMap(false, "");
  }, [noteId]); // Load a saved map first; only generate when missing.

  const runTopic = async (event) => {
    event.preventDefault();
    setLoading(false);
    await loadMap(true, topic.trim());
  };

  const requestQuiz = () => {
    const selectedTopic = selectedNode?.label || map?.topic || topic || defaultTopic;
    if (typeof onNavigate === "function") {
      onNavigate("quiz", { quizNoteId: noteId, quizTopic: selectedTopic });
    } else if (typeof toast === "function") {
      toast("Quiz navigation is not available here.", "coral");
    }
  };

  if (loading && !map) return <div className="mind-map-state"><span className="mind-map-spinner" />Loading mind map…</div>;
  if (error && !map) return (
    <div className="mind-map-state">
      <div className="mind-map-error-title">Mind map unavailable</div>
      <p>{error}</p>
      <button type="button" className="btn btn-primary btn-sm" onClick={() => loadMap(false, topic)}>Retry</button>
    </div>
  );

  return (
    <div className="mind-map-page">
      <div className="mind-map-heading">
        <div>
          <div className="mind-map-eyebrow">VISUAL LEARNING</div>
          <h2>{map?.topic || defaultTopic || noteTitle || "Mind Map"}</h2>
          <p>Explore how the concepts in your study material connect.</p>
        </div>
        <button type="button" className="btn btn-secondary btn-sm" disabled={generating} onClick={() => loadMap(true, topic)}>
          {generating ? "Working…" : "↻ Regenerate"}
        </button>
      </div>
      <form className="mind-map-topic-form" onSubmit={runTopic}>
        <label htmlFor="mind-map-topic">Focus on a specific topic</label>
        <input
          id="mind-map-topic"
          value={topic}
          onChange={(event) => setTopic(event.target.value)}
          placeholder="e.g. Virtualization, SQL joins, Normalization"
          maxLength={180}
        />
        <button type="submit" className="btn btn-primary btn-sm" disabled={generating || !topic.trim()}>
          {generating ? "Generating…" : "Generate topic map"}
        </button>
        {topic ? <button type="button" className="mind-tool-button" disabled={generating} onClick={() => { setTopic(""); loadMap(true, ""); }}>Full note</button> : null}
      </form>
      {error ? <div className="mind-map-inline-error">{error}</div> : null}
      {generating ? <div className="mind-map-progress">Preparing a source-grounded concept map…</div> : null}
      <div className="mind-map-content">
        <div className="mind-map-graph-column">
          {map ? (
            <ReactFlowProvider>
              <GraphCanvas map={map} selectedNode={selectedNode} onSelect={(value) => setSelectedId(typeof value === "string" ? value : value?.id)} />
            </ReactFlowProvider>
          ) : null}
          <div className="mind-map-footnote">
            {map?.generation_method === "llm" ? "AI-structured from saved study content" : "Built from saved study content"} · Reused from storage on future visits
          </div>
        </div>
        <aside className="mind-map-details">
          <div className="mind-map-details-kicker">CONCEPT DETAILS</div>
          <h3>{selectedNode?.label || "Select a concept"}</h3>
          <p>{selectedNode?.description || "Select a node to explore its definition and supporting notes."}</p>
          {selectedNode?.key_points?.length ? (
            <div className="mind-map-detail-section"><h4>Key points</h4><ul>{selectedNode.key_points.map((item, index) => <li key={index}>{item}</li>)}</ul></div>
          ) : null}
          {selectedNode?.examples?.length ? (
            <div className="mind-map-detail-section"><h4>Examples</h4><ul>{selectedNode.examples.map((item, index) => <li key={index}>{item}</li>)}</ul></div>
          ) : null}
          {selectedNode?.source_pages?.length ? (
            <div className="mind-map-source">
              <strong>Source pages</strong><div>{selectedNode.source_pages.join(", ")}</div>
              {onOpenSource ? <button type="button" className="mind-source-link" onClick={() => onOpenSource(selectedNode)}>Open related notes ↗</button> : null}
            </div>
          ) : <div className="mind-map-source">No page-level source reference was saved for this concept.</div>}
          <button type="button" className="btn btn-primary btn-sm mind-map-quiz-button" disabled={!selectedNode} onClick={requestQuiz}>Practice this concept</button>
        </aside>
      </div>
    </div>
  );
}

export default function MindMapView(props) {
  return <MindMapInner {...props} />;
}
