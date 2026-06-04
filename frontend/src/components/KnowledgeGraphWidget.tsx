import React, { useEffect, useState, useRef } from 'react';
import { Network, Info } from 'lucide-react';
import type { KnowledgeGraphData, KGNode } from '../types';
import { mockApi } from '../services/mockApi';

const NODE_TYPE_LABELS: Record<KGNode['type'], string> = {
  standard: 'Стандарт',
  control: 'Мера защиты',
  threat: 'Угроза',
  asset: 'Актив',
};

const NODE_COLORS: Record<KGNode['type'], { fill: string; stroke: string }> = {
  standard: { fill: '#3b82f6', stroke: '#1d4ed8' },
  control: { fill: '#f59e0b', stroke: '#b45309' },
  threat: { fill: '#ef4444', stroke: '#b91c1c' },
  asset: { fill: '#22c55e', stroke: '#15803d' },
};

const LEGEND: Array<{ type: KGNode['type']; color: string; label: string }> = [
  { type: 'standard', color: '#3b82f6', label: 'Стандарт' },
  { type: 'control', color: '#f59e0b', label: 'Мера защиты' },
  { type: 'threat', color: '#ef4444', label: 'Угроза' },
  { type: 'asset', color: '#22c55e', label: 'Актив' },
];

const VB = 100; // viewBox size (square coordinate space)

export function KnowledgeGraphWidget() {
  const [data, setData] = useState<KnowledgeGraphData | null>(null);
  const [hoveredNode, setHoveredNode] = useState<string | null>(null);
  const svgRef = useRef<SVGSVGElement>(null);

  useEffect(() => {
    mockApi.getKnowledgeGraph().then(setData);
  }, []);

  if (!data) {
    return (
      <div className="card p-4 animate-pulse">
        <div className="h-4 w-40 bg-slate-200 dark:bg-slate-700 rounded mb-3" />
        <div className="rounded-xl bg-slate-100 dark:bg-slate-700/50" style={{ height: 240 }} />
      </div>
    );
  }

  const getConnectedNodes = (nodeId: string): Set<string> => {
    const connected = new Set<string>();
    data.edges.forEach((e) => {
      if (e.from === nodeId) connected.add(e.to);
      if (e.to === nodeId) connected.add(e.from);
    });
    return connected;
  };

  const connectedNodes = hoveredNode ? getConnectedNodes(hoveredNode) : new Set<string>();

  return (
    <div className="card p-4 flex flex-col gap-3">
      <div className="flex items-center gap-2">
        <Network size={15} className="text-blue-500" />
        <span className="text-sm font-semibold text-slate-700 dark:text-slate-300">
          Граф знаний
        </span>
        <span className="text-xs text-slate-400 dark:text-slate-500">
          Стандарт → Мера защиты → Актив
        </span>
        <div className="ml-auto group relative">
          <Info size={13} className="text-slate-400 cursor-help" />
          <div className="absolute right-0 top-full mt-1 w-52 text-xs bg-slate-800 dark:bg-slate-700 text-white
                          p-2 rounded-lg shadow-lg opacity-0 group-hover:opacity-100 transition-opacity z-10 pointer-events-none">
            Визуализация связей между стандартами, мерами защиты, угрозами и активами
          </div>
        </div>
      </div>

      <div className="relative w-full rounded-xl overflow-hidden bg-slate-50 dark:bg-slate-800/60 border border-slate-100 dark:border-slate-700">
        <svg
          ref={svgRef}
          className="w-full"
          viewBox={`0 0 ${VB} ${VB}`}
          style={{ display: 'block', aspectRatio: '1 / 1', maxHeight: 260 }}
        >
          {/* Edges */}
          {data.edges.map((edge) => {
            const from = data.nodes.find((n) => n.id === edge.from);
            const to = data.nodes.find((n) => n.id === edge.to);
            if (!from || !to) return null;
            const highlighted =
              hoveredNode === from.id ||
              hoveredNode === to.id;
            return (
              <line
                key={`${edge.from}-${edge.to}`}
                x1={from.x}
                y1={from.y}
                x2={to.x}
                y2={to.y}
                stroke={highlighted ? '#2563eb' : '#94a3b8'}
                strokeWidth={highlighted ? 0.8 : 0.4}
                strokeOpacity={highlighted ? 1 : edge.strength * 0.5}
                strokeDasharray={highlighted ? undefined : '0'}
                style={{ transition: 'all 0.15s' }}
              />
            );
          })}

          {/* Nodes */}
          {data.nodes.map((node) => {
            const colors = NODE_COLORS[node.type];
            const isHovered = hoveredNode === node.id;
            const isConnected = connectedNodes.has(node.id);
            const isDimmed = hoveredNode !== null && !isHovered && !isConnected;
            const r = (node.size / 2) * 0.55;

            return (
              <g
                key={node.id}
                transform={`translate(${node.x}, ${node.y})`}
                style={{ cursor: 'pointer' }}
                onMouseEnter={() => setHoveredNode(node.id)}
                onMouseLeave={() => setHoveredNode(null)}
              >
                {isHovered && (
                  <circle
                    r={r + 2}
                    fill="white"
                    fillOpacity={0.25}
                    stroke={colors.fill}
                    strokeWidth={0.5}
                    strokeOpacity={0.6}
                  />
                )}
                <circle
                  r={r}
                  fill={colors.fill}
                  stroke={colors.stroke}
                  strokeWidth={0.5}
                  fillOpacity={isDimmed ? 0.25 : 1}
                  style={{ transition: 'all 0.15s' }}
                />
                {/* Label below node */}
                <text
                  y={r + 3.5}
                  textAnchor="middle"
                  fontSize={2.8}
                  fill={isDimmed ? '#94a3b8' : '#1e293b'}
                  className="select-none dark:fill-slate-200"
                  style={{ transition: 'opacity 0.15s', fontWeight: isHovered ? 'bold' : 'normal' }}
                >
                  {node.label.length > 14 ? node.label.slice(0, 13) + '…' : node.label}
                </text>
                {/* Tooltip on hover */}
                {isHovered && (
                  <g transform={`translate(0, ${-r - 7})`}>
                    <rect
                      x={-16}
                      y={-5}
                      width={32}
                      height={8}
                      rx={1.5}
                      fill="#0f172a"
                      fillOpacity={0.9}
                    />
                    <text
                      textAnchor="middle"
                      y={-1.5}
                      fontSize={2.8}
                      fill="white"
                      className="select-none"
                      fontWeight="600"
                    >
                      {node.label}
                    </text>
                    <text
                      textAnchor="middle"
                      y={1.8}
                      fontSize={2.2}
                      fill="#94a3b8"
                      className="select-none"
                    >
                      {NODE_TYPE_LABELS[node.type]}
                    </text>
                  </g>
                )}
              </g>
            );
          })}
        </svg>
      </div>

      <div className="flex flex-wrap gap-3">
        {LEGEND.map(({ type, color, label }) => (
          <div key={type} className="flex items-center gap-1.5">
            <div
              className="w-2.5 h-2.5 rounded-full"
              style={{ backgroundColor: color }}
            />
            <span className="text-xs text-slate-500 dark:text-slate-400">{label}</span>
          </div>
        ))}
      </div>
    </div>
  );
}
