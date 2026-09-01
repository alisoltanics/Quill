import { bytesToBase64, base64ToBytes } from '../lib/yjsGateway'

describe('bytesToBase64', () => {
  it('encodes empty array', () => {
    const result = bytesToBase64(new Uint8Array(0))
    expect(result).toBe('')
  })

  it('encodes simple bytes', () => {
    const bytes = new Uint8Array([72, 101, 108, 108, 111]) // "Hello"
    const result = bytesToBase64(bytes)
    expect(result).toBe('SGVsbG8=')
  })

  it('encodes bytes with values > 127', () => {
    const bytes = new Uint8Array([255, 254, 253])
    const result = bytesToBase64(bytes)
    expect(typeof result).toBe('string')
    expect(result.length).toBeGreaterThan(0)
  })
})

describe('base64ToBytes', () => {
  it('decodes empty string', () => {
    const result = base64ToBytes('')
    expect(result.length).toBe(0)
  })

  it('decodes base64 string', () => {
    const result = base64ToBytes('SGVsbG8=')
    expect(Array.from(result)).toEqual([72, 101, 108, 108, 111])
  })
})

describe('base64 roundtrip', () => {
  it('bytesToBase64 -> base64ToBytes preserves data', () => {
    const original = new Uint8Array([0, 1, 127, 128, 255, 42, 99])
    const encoded = bytesToBase64(original)
    const decoded = base64ToBytes(encoded)
    expect(Array.from(decoded)).toEqual(Array.from(original))
  })

  it('roundtrip with large payload', () => {
    const original = new Uint8Array(1024)
    for (let i = 0; i < 1024; i++) original[i] = i % 256
    const encoded = bytesToBase64(original)
    const decoded = base64ToBytes(encoded)
    expect(Array.from(decoded)).toEqual(Array.from(original))
  })

  it('roundtrip with Yjs-like state', () => {
    const yjsState = new Uint8Array([1, 0, 3, 72, 101, 108, 108, 111, 0])
    const encoded = bytesToBase64(yjsState)
    const decoded = base64ToBytes(encoded)
    expect(Array.from(decoded)).toEqual(Array.from(yjsState))
  })
})
