import * as Y from 'yjs'

export type YjsGatewayMessageType = 'join' | 'update' | 'sync-state'

export interface YjsGatewayMessage {
  type: YjsGatewayMessageType
  docId: number
  clientId: string
  update?: string
}

export interface YjsGatewayOptions {
  doc: Y.Doc
  docId: number
  clientId: string
  wsUrl: string
  token?: string
  onStatus?: (connected: boolean) => void
  onLocalDocumentUpdate?: () => void
}

export function bytesToBase64(bytes: Uint8Array) {
  if (typeof window === 'undefined') {
    return Buffer.from(bytes).toString('base64')
  }
  let binary = ''
  const chunkSize = 0x8000
  for (let i = 0; i < bytes.length; i += chunkSize) {
    const chunk = bytes.subarray(i, i + chunkSize)
    binary += String.fromCharCode(...chunk)
  }
  return window.btoa(binary)
}

export function base64ToBytes(encoded: string) {
  if (typeof window === 'undefined') {
    return new Uint8Array(Buffer.from(encoded, 'base64'))
  }
  const binary = window.atob(encoded)
  const bytes = new Uint8Array(binary.length)
  for (let i = 0; i < binary.length; i += 1) {
    bytes[i] = binary.charCodeAt(i)
  }
  return bytes
}

function encodeMessage(message: YjsGatewayMessage) {
  return JSON.stringify(message)
}

function decodeMessage(raw: string) {
  try {
    const parsed = JSON.parse(raw) as Partial<YjsGatewayMessage>
    if (typeof parsed.type !== 'string' || typeof parsed.docId !== 'number' || typeof parsed.clientId !== 'string') {
      return null
    }
    return parsed as YjsGatewayMessage
  } catch {
    return null
  }
}

export function createYjsGatewayConnection({ doc, docId, clientId, wsUrl, token, onStatus, onLocalDocumentUpdate }: YjsGatewayOptions) {
  const socketUrl = token ? `${wsUrl}?token=${encodeURIComponent(token)}` : wsUrl
  const socket = new WebSocket(socketUrl)
  const connectionTag = Symbol('yjs-gateway-connection')
  let closed = false

  const send = (message: YjsGatewayMessage) => {
    if (socket.readyState !== WebSocket.OPEN) return
    socket.send(encodeMessage(message))
  }

  const onLocalUpdate = (_update: Uint8Array, origin: unknown) => {
    if (origin === connectionTag || closed) return
    onLocalDocumentUpdate?.()
  }

  doc.on('update', onLocalUpdate)

  socket.onopen = () => {
    onStatus?.(true)
    send({ type: 'join', docId, clientId })
  }

  socket.onmessage = (event) => {
    if (typeof event.data !== 'string') return
    const message = decodeMessage(event.data)
    if (!message || message.docId !== docId || message.clientId === clientId) return
    if (message.type === 'sync-state' && message.clientId !== 'document-service') return
    if (!message.update) return

    const update = base64ToBytes(message.update)
    Y.applyUpdate(doc, update, connectionTag)
  }

  socket.onclose = () => {
    closed = true
    doc.off('update', onLocalUpdate)
    onStatus?.(false)
  }

  socket.onerror = () => {
    onStatus?.(false)
  }

  return {
    close() {
      closed = true
      doc.off('update', onLocalUpdate)
      socket.close()
    },
  }
}
