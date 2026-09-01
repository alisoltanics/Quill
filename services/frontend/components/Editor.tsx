import React, { forwardRef, useEffect, useImperativeHandle, useRef, useState } from 'react'
import { useEditor, EditorContent } from '@tiptap/react'
import StarterKit from '@tiptap/starter-kit'
import Placeholder from '@tiptap/extension-placeholder'
import Collaboration from '@tiptap/extension-collaboration'
import { Extension } from '@tiptap/core'
import { Plugin, PluginKey } from '@tiptap/pm/state'
import { Decoration, DecorationSet } from '@tiptap/pm/view'
import * as Y from 'yjs'
import type { CursorData } from '../lib/yjsGateway'

// ─── Cursor colors ────────────────────────────────────────────────────────────
const CURSOR_COLORS = [
  '#f43f5e', '#8b5cf6', '#3b82f6', '#10b981',
  '#f59e0b', '#ef4444', '#06b6d4', '#84cc16',
]

function getCursorColor(email: string): string {
  let hash = 0
  for (let i = 0; i < email.length; i++) {
    hash = email.charCodeAt(i) + ((hash << 5) - hash)
  }
  return CURSOR_COLORS[Math.abs(hash) % CURSOR_COLORS.length]
}

// ─── Imperative handle ────────────────────────────────────────────────────────
export interface EditorHandle {
  getHTML: () => string
  getText: () => string
  setHTML: (html: string) => void
  isFocused: () => boolean
}

// ─── Toolbar helpers ──────────────────────────────────────────────────────────
interface TBtnProps {
  onClick: () => void
  active?: boolean
  disabled?: boolean
  title: string
  children: React.ReactNode
}

function TBtn({ onClick, active, disabled, title, children }: TBtnProps) {
  return (
    <button
      type="button"
      className={`tb-btn${active ? ' tb-btn--active' : ''}`}
      onMouseDown={(e) => { e.preventDefault(); if (!disabled) onClick() }}
      title={title}
      aria-label={title}
      aria-pressed={active}
      disabled={disabled}
    >
      {children}
    </button>
  )
}

function TDivider() {
  return <span className="tb-divider" aria-hidden />
}

// ─── Remote cursor decorations plugin ─────────────────────────────────────────
interface CursorState {
  cursors: CursorData[]
  decorations: DecorationSet
}

const remoteCursorsKey = new PluginKey<CursorState>('remoteCursors')

function buildCursorDecorations(doc: any, cursors: CursorData[]): DecorationSet {
  const decos: Decoration[] = []
  for (const c of cursors) {
    const color = getCursorColor(c.email)
    const pos = Math.min(c.position, doc.content.size)
    const name = c.email.split('@')[0]

    decos.push(
      Decoration.widget(pos, () => {
        const wrapper = document.createElement('span')
        wrapper.className = 'remote-cursor-wrapper'
        wrapper.style.cssText = 'position:relative;display:inline;padding:0 2px;cursor:default;'

        const line = document.createElement('span')
        line.className = 'remote-cursor-line'
        line.style.cssText = `
          display:inline-block;width:2px;height:1.2em;
          vertical-align:text-bottom;background:${color};border-radius:1px;
        `
        wrapper.appendChild(line)

        const label = document.createElement('span')
        label.className = 'remote-cursor-label'
        label.textContent = name
        label.style.cssText = `
          position:absolute;bottom:100%;left:0;font-size:10px;font-weight:600;
          color:#fff;background:${color};padding:2px 6px;border-radius:3px;
          white-space:nowrap;pointer-events:none;opacity:0;
          transition:opacity 0.15s ease;z-index:10;
        `
        wrapper.appendChild(label)

        return wrapper
      }, { side: 1 })
    )
  }
  return DecorationSet.create(doc, decos)
}

const RemoteCursorsExtension = Extension.create({
  name: 'remoteCursors',
  addProseMirrorPlugins() {
    return [
      new Plugin({
        key: remoteCursorsKey,
        state: {
          init: (): CursorState => ({ cursors: [], decorations: DecorationSet.empty }),
          apply(tr, old) {
            const incoming = tr.getMeta(remoteCursorsKey)
            const cursors = incoming ?? old.cursors
            return { cursors, decorations: buildCursorDecorations(tr.doc, cursors) }
          },
        },
        props: {
          decorations(state) {
            return this.getState(state).decorations
          },
        },
      }),
    ]
  },
})

// ─── Editor component ─────────────────────────────────────────────────────────
interface EditorProps {
  ydoc: Y.Doc
  initialContent?: string
  editable?: boolean
  remoteCursors?: CursorData[]
  onCursorChange?: (position: number) => void
}

const Editor = forwardRef<EditorHandle, EditorProps>(({ ydoc, initialContent = '', editable = true, remoteCursors = [], onCursorChange }, ref) => {
  const appliedFallbackRef = useRef(false)

  const editor = useEditor({
    content: '',
    editable,
    extensions: [
      StarterKit.configure({ history: false }),
      Collaboration.configure({ document: ydoc }),
      Placeholder.configure({ placeholder: 'Start writing your document…' }),
      RemoteCursorsExtension,
    ],
    onUpdate: ({ editor }) => {
      const { from } = editor.state.selection
      onCursorChange?.(from)
    },
    onSelectionUpdate: ({ editor }) => {
      const { from } = editor.state.selection
      onCursorChange?.(from)
    },
  })

  useImperativeHandle(ref, () => ({
    getHTML:   () => editor?.getHTML() ?? '',
    getText:   () => editor?.getText() ?? '',
    setHTML:   (html: string) => { editor?.commands.setContent(html, false) },
    isFocused: () => editor?.isFocused ?? false,
  }), [editor])

  // Update remote cursor state when remoteCursors changes
  useEffect(() => {
    if (!editor) return
    const { state, dispatch } = editor.view
    dispatch(state.tr.setMeta(remoteCursorsKey, remoteCursors))
  }, [editor, remoteCursors])

  useEffect(() => {
    if (!editor || appliedFallbackRef.current) return
    if (!initialContent.trim()) return
    if (editor.getText().trim() !== '') return

    const fragment = ydoc.getXmlFragment('default')
    if (fragment.length > 0) return

    appliedFallbackRef.current = true
    editor.commands.setContent(initialContent, false)
  }, [editor, initialContent, ydoc])

  if (!editor) return null

  const words = editor.getText().trim().split(/\s+/).filter(Boolean).length
  const chars = editor.getText().length

  return (
    <div className="tiptap-wrapper">

      {/* ── Toolbar ── */}
      {editable && (
        <div className="editor-toolbar" role="toolbar" aria-label="Formatting options">
          <TBtn onClick={() => editor.chain().focus().undo().run()}
                disabled={!editor.can().undo()} title="Undo (Ctrl+Z)">↩</TBtn>
          <TBtn onClick={() => editor.chain().focus().redo().run()}
                disabled={!editor.can().redo()} title="Redo (Ctrl+Y)">↪</TBtn>

          <TDivider />

          <TBtn onClick={() => editor.chain().focus().toggleBold().run()}
                active={editor.isActive('bold')} title="Bold (Ctrl+B)"><b>B</b></TBtn>
          <TBtn onClick={() => editor.chain().focus().toggleItalic().run()}
                active={editor.isActive('italic')} title="Italic (Ctrl+I)"><i>I</i></TBtn>
          <TBtn onClick={() => editor.chain().focus().toggleStrike().run()}
                active={editor.isActive('strike')} title="Strikethrough"><s>S</s></TBtn>
          <TBtn onClick={() => editor.chain().focus().toggleCode().run()}
                active={editor.isActive('code')} title="Inline code">&lt;/&gt;</TBtn>

          <TDivider />

          <TBtn onClick={() => editor.chain().focus().toggleHeading({ level: 1 }).run()}
                active={editor.isActive('heading', { level: 1 })} title="Heading 1">H1</TBtn>
          <TBtn onClick={() => editor.chain().focus().toggleHeading({ level: 2 }).run()}
                active={editor.isActive('heading', { level: 2 })} title="Heading 2">H2</TBtn>
          <TBtn onClick={() => editor.chain().focus().toggleHeading({ level: 3 }).run()}
                active={editor.isActive('heading', { level: 3 })} title="Heading 3">H3</TBtn>

          <TDivider />

          <TBtn onClick={() => editor.chain().focus().toggleBulletList().run()}
                active={editor.isActive('bulletList')} title="Bullet list">≡</TBtn>
          <TBtn onClick={() => editor.chain().focus().toggleOrderedList().run()}
                active={editor.isActive('orderedList')} title="Ordered list">1.</TBtn>

          <TDivider />

          <TBtn onClick={() => editor.chain().focus().toggleBlockquote().run()}
                active={editor.isActive('blockquote')} title="Blockquote">"</TBtn>
          <TBtn onClick={() => editor.chain().focus().toggleCodeBlock().run()}
                active={editor.isActive('codeBlock')} title="Code block">{ '{ }' }</TBtn>
          <TBtn onClick={() => editor.chain().focus().setHorizontalRule().run()}
                title="Horizontal rule">—</TBtn>
        </div>
      )}

      {/* ── Content area ── */}
      <EditorContent editor={editor} className="tiptap-editor" />

      {/* ── Footer / word count ── */}
      <div className="editor-footer">
        <span>{words} {words === 1 ? 'word' : 'words'}</span>
        <span>{chars} characters</span>
      </div>

    </div>
  )
})

Editor.displayName = 'Editor'
export default Editor
