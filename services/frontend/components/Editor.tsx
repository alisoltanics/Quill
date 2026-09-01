import React, { forwardRef, useEffect, useImperativeHandle, useRef } from 'react'
import { useEditor, EditorContent } from '@tiptap/react'
import StarterKit from '@tiptap/starter-kit'
import Placeholder from '@tiptap/extension-placeholder'
import Collaboration from '@tiptap/extension-collaboration'
import * as Y from 'yjs'

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
      // preventDefault prevents editor losing focus on click
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

// ─── Editor component ─────────────────────────────────────────────────────────
interface EditorProps {
  ydoc: Y.Doc
  initialContent?: string
}

const Editor = forwardRef<EditorHandle, EditorProps>(({ ydoc, initialContent = '' }, ref) => {
  const appliedFallbackRef = useRef(false)
  const editor = useEditor({
    content: '',
    extensions: [
      StarterKit.configure({ history: false }),
      Collaboration.configure({ document: ydoc }),
      Placeholder.configure({ placeholder: 'Start writing your document…' }),
    ],
  })

  useImperativeHandle(ref, () => ({
    getHTML:   () => editor?.getHTML() ?? '',
    getText:   () => editor?.getText() ?? '',
    setHTML:   (html: string) => { editor?.commands.setContent(html, false) },
    isFocused: () => editor?.isFocused ?? false,
  }), [editor])

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
