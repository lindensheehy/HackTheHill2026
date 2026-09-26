import React, { useEffect, useMemo, useState } from 'react'
import { ReactFlow, Background, Handle, Position } from '@xyflow/react'
import '@xyflow/react/dist/style.css'
import { api } from '../api.js'
import { Loading } from '../components/common.jsx'
import { gbp } from '../format.js'

// Fixed layout: entry systems (left) -> CaseTrack; regions (middle) -> the systems that serve them (right).
const POS = {
  'SYS-05': [0, 0], 'SYS-03': [0, 60], 'SYS-01': [0, 150], 'SYS-14': [0, 330],
  'SYS-04': [260, 20],
  Barrowdale: [260, 130], Dunmoor: [260, 180],
  Ashford: [260, 245], Calderfield: [260, 290], Eastmarch: [260, 335], Fenwick: [260, 380],
  'SYS-08': [520, 0], 'SYS-09': [520, 50], 'SYS-10': [520, 100], 'SYS-06': [520, 155],
  'SYS-02': [520, 265], 'SYS-07': [520, 345],
}

function NodeBox({ data }) {
  const { node, selected } = data
  const alert = node.alert
  const isRegion = node.kind === 'region'
  return (
    <div style={{
      padding: '6px 10px', borderRadius: isRegion ? 16 : 8, fontSize: 13, minWidth: 130, textAlign: 'center',
      background: alert ? 'var(--critical)' : isRegion ? (node.focus ? 'var(--focus-wash)' : 'var(--surface-2)') : 'var(--surface)',
      color: alert ? '#fff' : 'var(--ink)',
      border: `1px solid ${selected ? 'var(--ink)' : node.focus && !alert ? 'var(--s2)' : 'var(--border)'}`,
      fontWeight: isRegion ? 600 : 500,
    }}>
      <Handle type="target" position={Position.Left} style={{ opacity: 0 }} />
      {!isRegion && <div style={{ fontSize: 10, opacity: .7 }}>{node.id}</div>}
      {node.label}{alert ? ' ⚠' : ''}
      <Handle type="source" position={Position.Right} style={{ opacity: 0 }} />
    </div>
  )
}
const nodeTypes = { box: NodeBox }

export default function SystemGraph() {
  const [g, setG] = useState(null)
  const [sel, setSel] = useState('SYS-06')
  useEffect(() => { api.graph().then(setG) }, [])

  const { nodes, edges } = useMemo(() => {
    if (!g) return { nodes: [], edges: [] }
    return {
      nodes: g.nodes.filter((n) => POS[n.id]).map((n) => ({
        id: n.id, type: 'box', position: { x: POS[n.id][0], y: POS[n.id][1] },
        data: { node: n, selected: sel === n.id }, draggable: true,
      })),
      edges: g.edges.filter((e) => POS[e.source] && POS[e.target]).map((e, i) => {
        // Always draw left to right, whichever way the relationship points.
        const flip = POS[e.source][0] > POS[e.target][0]
        return {
        id: `e${i}`, source: flip ? e.target : e.source, target: flip ? e.source : e.target, label: e.label,
        labelStyle: { fontSize: 11, fill: 'var(--ink-2)' }, labelBgStyle: { fill: 'var(--surface)' },
        style: { stroke: e.kind === 'transfers_to' ? 'var(--s2)' : 'var(--axis)', strokeWidth: e.kind === 'transfers_to' ? 2 : 1.5 },
        animated: e.kind === 'transfers_to',
      }}),
    }
  }, [g, sel])

  if (!g) return <Loading />
  const info = g.nodes.find((n) => n.id === sel)
  return (
    <div className="stack" style={{ gap: 10 }}>
      <div className="flow-wrap" style={{ height: 420 }}>
        <ReactFlow nodes={nodes} edges={edges} nodeTypes={nodeTypes} fitView fitViewOptions={{ padding: 0.04 }}
          onNodeClick={(_, n) => setSel(n.id)} proOptions={{ hideAttribution: true }}
          nodesConnectable={false} zoomOnScroll={false} panOnScroll={false} preventScrolling={false}>
          <Background color="var(--grid)" gap={20} />
        </ReactFlow>
      </div>
      {info && info.kind === 'system' && (
        <div className="callout info">
          <div>
            <b>{info.id} {info.label}</b> · {info.info.purpose}
            <div className="small ink2">
              Installed {info.info.year_installed} · {info.info.vendor} · {info.info.tech_stack} · {info.info.integration_method} · {gbp(info.info.annual_run_cost)}/yr
            </div>
            <div style={{ marginTop: 4 }}>{info.info.notes}</div>
          </div>
        </div>
      )}
      {info && info.kind === 'region' && <div className="callout info"><div><b>{info.label}</b>: click a system to see its notes.</div></div>}
    </div>
  )
}
