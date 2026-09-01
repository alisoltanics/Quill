import React, { useCallback, useEffect, useRef, useState } from 'react'
import {
  ReactFlow,
  addEdge,
  Background,
  BackgroundVariant,
  Controls,
  MiniMap,
  useEdgesState,
  useNodesState,
  type Connection,
  type Edge,
  type Node,
  type NodeProps,
  Handle,
  Position,
} from '@xyflow/react'
import '@xyflow/react/dist/style.css'

// ─── Editable shape node ────────────────────────────────────────────────────

function ShapeNode({ data, selected }: NodeProps) {
  const [editing, setEditing] = useState(false)
  const [label, setLabel] = useState(data.label as string)
  const inputRef = useRef<HTMLTextAreaElement>(null)

  useEffect(() => {
    if (editing) inputRef.current?.focus()
  }, [editing])

  const style: React.CSSProperties = {
    width: (data.width as number) ?? 140,
    height: (data.height as number) ?? 60,
    borderRadius: data.shape === 'circle' ? '50%' : data.shape === 'rounded' ? 12 : 4,
    background: (data.bg as string) ?? '#fff',
    border: `2px solid ${selected ? '#2563eb' : '#6b7280'}`,
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
    fontSize: 13,
    fontWeight: 500,
    cursor: 'default',
    userSelect: 'none',
    boxShadow: selected ? '0 0 0 3px #bfdbfe' : '0 1px 4px rgba(0,0,0,.1)',
    position: 'relative',
    overflow: 'hidden',
  }

  return (
    <div style={style} onDoubleClick={() => setEditing(true)}>
      <Handle type="target" position={Position.Top} />
      <Handle type="source" position={Position.Bottom} />
      <Handle type="target" position={Position.Left} />
      <Handle type="source" position={Position.Right} />

      {editing ? (
        <textarea
          ref={inputRef}
          value={label}
          onChange={e => setLabel(e.target.value)}
          onBlur={() => { setEditing(false); data.onLabelChange?.(label) }}
          onKeyDown={e => { if (e.key === 'Escape') setEditing(false) }}
          style={{
            width: '90%', height: '80%', border: 'none', resize: 'none',
            outline: 'none', background: 'transparent', textAlign: 'center',
            fontSize: 13, fontFamily: 'inherit', fontWeight: 500,
          }}
          onClick={e => e.stopPropagation()}
        />
      ) : (
        <span style={{ textAlign: 'center', padding: '0 8px', wordBreak: 'break-word' }}>
          {label || <em style={{ color: '#9ca3af' }}>double-click to edit</em>}
        </span>
      )}
    </div>
  )
}

const nodeTypes = { shape: ShapeNode }

// ─── DiagramEditor ──────────────────────────────────────────────────────────

interface DiagramEditorProps {
  docId: number
}

const storageKey = (id: number) => `diagram_${id}`

const SHAPES = [
  { label: 'Rectangle', shape: 'rect',    bg: '#fff',    w: 140, h: 60 },
  { label: 'Square',    shape: 'rect',    bg: '#fff',    w: 80,  h: 80 },
  { label: 'Rounded',   shape: 'rounded', bg: '#eff6ff', w: 140, h: 60 },
  { label: 'Circle',    shape: 'circle',  bg: '#fef9c3', w: 80,  h: 80 },
  { label: 'Blue box',  shape: 'rounded', bg: '#dbeafe', w: 140, h: 60 },
  { label: 'Red box',   shape: 'rounded', bg: '#fee2e2', w: 140, h: 60 },
]

let _id = 1
function uid() { return `n${_id++}` }

export default function DiagramEditor({ docId }: DiagramEditorProps) {
  const [nodes, setNodes, onNodesChange] = useNodesState([])
  const [edges, setEdges, onEdgesChange] = useEdgesState([])

  // Persist state to localStorage
  useEffect(() => {
    const saved = localStorage.getItem(storageKey(docId))
    if (saved) {
      try {
        const { nodes: n, edges: e } = JSON.parse(saved)
        setNodes(n ?? [])
        setEdges(e ?? [])
      } catch { /* ignore */ }
    }
  }, [docId])

  const save = useCallback((n: Node[], e: Edge[]) => {
    localStorage.setItem(storageKey(docId), JSON.stringify({ nodes: n, edges: e }))
  }, [docId])

  const onConnect = useCallback((params: Connection) => {
    setEdges(eds => {
      const next = addEdge({ ...params, animated: false, markerEnd: { type: 'arrowclosed' as any } }, eds)
      save(nodes, next)
      return next
    })
  }, [nodes, save])

  function addShape(cfg: typeof SHAPES[0]) {
    const id = uid()
    const node: Node = {
      id,
      type: 'shape',
      position: { x: 80 + Math.random() * 200, y: 80 + Math.random() * 150 },
      data: {
        label: cfg.label,
        shape: cfg.shape,
        bg: cfg.bg,
        width: cfg.w,
        height: cfg.h,
        onLabelChange: (label: string) => {
          setNodes(ns => {
            const next = ns.map(n => n.id === id ? { ...n, data: { ...n.data, label } } : n)
            save(next, edges)
            return next
          })
        },
      },
    }
    setNodes(ns => {
      const next = [...ns, node]
      save(next, edges)
      return next
    })
  }

  function clearAll() {
    if (!confirm('Clear the entire diagram?')) return
    setNodes([])
    setEdges([])
    localStorage.removeItem(storageKey(docId))
  }

  return (
    <div className="diagram-wrapper">
      {/* Shape palette */}
      <div className="diagram-palette">
        {SHAPES.map(s => (
          <button
            key={s.label}
            className="palette-btn"
            style={{ background: s.bg, borderRadius: s.shape === 'circle' ? '50%' : s.shape === 'rounded' ? 8 : 4 }}
            onClick={() => addShape(s)}
            title={`Add ${s.label}`}
          >
            {s.label}
          </button>
        ))}
        <div style={{ flex: 1 }} />
        <button className="palette-btn palette-btn--danger" onClick={clearAll} title="Clear diagram">
          Clear
        </button>
      </div>

      {/* Canvas */}
      <div className="diagram-canvas">
        <ReactFlow
          nodes={nodes}
          edges={edges}
          onNodesChange={e => { onNodesChange(e); }}
          onEdgesChange={e => { onEdgesChange(e); }}
          onConnect={onConnect}
          onNodeDragStop={(_, __, ns) => save(ns, edges)}
          nodeTypes={nodeTypes}
          fitView
          deleteKeyCode="Delete"
        >
          <Background variant={BackgroundVariant.Dots} gap={20} size={1} color="#e5e7eb" />
          <Controls />
          <MiniMap nodeColor={n => (n.data?.bg as string) ?? '#e5e7eb'} />
        </ReactFlow>
      </div>

      <p className="diagram-hint">
        Click a shape to add · Drag handles to connect · Double-click to edit text · Delete key removes selected
      </p>
    </div>
  )
}
