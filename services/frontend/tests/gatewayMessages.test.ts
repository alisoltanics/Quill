import { bytesToBase64, base64ToBytes, YjsGatewayMessage } from '../lib/yjsGateway'

describe('YjsGatewayMessage types', () => {
  it('join message structure', () => {
    const msg: YjsGatewayMessage = { type: 'join', docId: 1, clientId: 'c1' }
    expect(msg.type).toBe('join')
    expect(msg.docId).toBe(1)
    expect(msg.clientId).toBe('c1')
  })

  it('sync-state message with update', () => {
    const msg: YjsGatewayMessage = {
      type: 'sync-state',
      docId: 1,
      clientId: 'document-service',
      update: bytesToBase64(new Uint8Array([1, 2, 3])),
    }
    expect(msg.type).toBe('sync-state')
    expect(msg.update).toBeTruthy()
  })

  it('presence-update message with users', () => {
    const msg: YjsGatewayMessage = {
      type: 'presence-update',
      docId: 1,
      clientId: 'gateway',
      users: ['alice@test.com', 'bob@test.com'],
    }
    expect(msg.type).toBe('presence-update')
    expect(msg.users).toHaveLength(2)
  })

  it('cursor-update message with cursor data', () => {
    const msg: YjsGatewayMessage = {
      type: 'cursor-update',
      docId: 1,
      clientId: 'c1',
      cursor: { email: 'alice@test.com', position: 42 },
    }
    expect(msg.type).toBe('cursor-update')
    expect(msg.cursor?.email).toBe('alice@test.com')
    expect(msg.cursor?.position).toBe(42)
  })
})

describe('JSON serialization of gateway messages', () => {
  it('encodes and decodes join message', () => {
    const msg: YjsGatewayMessage = { type: 'join', docId: 5, clientId: 'client-abc' }
    const json = JSON.stringify(msg)
    const parsed = JSON.parse(json) as YjsGatewayMessage
    expect(parsed.type).toBe('join')
    expect(parsed.docId).toBe(5)
    expect(parsed.clientId).toBe('client-abc')
  })

  it('encodes and decodes sync-state with base64 update', () => {
    const updateBytes = new Uint8Array([10, 20, 30, 40])
    const msg: YjsGatewayMessage = {
      type: 'sync-state',
      docId: 1,
      clientId: 'document-service',
      update: bytesToBase64(updateBytes),
    }
    const json = JSON.stringify(msg)
    const parsed = JSON.parse(json) as YjsGatewayMessage
    const decoded = base64ToBytes(parsed.update!)
    expect(Array.from(decoded)).toEqual(Array.from(updateBytes))
  })

  it('omits optional fields when undefined', () => {
    const msg: YjsGatewayMessage = { type: 'join', docId: 1, clientId: 'c1' }
    const json = JSON.stringify(msg)
    expect(json).not.toContain('update')
    expect(json).not.toContain('users')
    expect(json).not.toContain('cursor')
  })
})
