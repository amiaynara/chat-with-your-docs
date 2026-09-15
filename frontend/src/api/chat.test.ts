import { afterEach, describe, expect, it, vi } from 'vitest'
import { askQuestion, AskError, getMessageHistory } from './chat'
import type { Trace } from './chat'

function makeTrace(overrides: Partial<Trace> = {}): Trace {
  return {
    retrieval_hits: [],
    rerank_scores: null,
    prompt: null,
    input_tokens: 0,
    output_tokens: 0,
    stage_timings: [],
    ...overrides,
  }
}

describe('askQuestion', () => {
  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it('sends the question and returns the answer with its citations and trace', async () => {
    const citations = [
      { document_id: 'doc-1', filename: 'notes.txt', location_ref: 'document', snippet: 'Wobble-42.' },
    ]
    const trace = makeTrace({ input_tokens: 12, output_tokens: 4 })
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({ answer: 'Wobble-42.', citations, trace }),
    })
    vi.stubGlobal('fetch', fetchMock)

    const result = await askQuestion('What is the secret code?')

    expect(result).toEqual({ answer: 'Wobble-42.', citations, trace })
    const [url, init] = fetchMock.mock.calls[0]
    expect(url).toBe('http://localhost:8000/chat/messages')
    expect(init).toMatchObject({
      method: 'POST',
      credentials: 'include',
      headers: { 'Content-Type': 'application/json' },
    })
    expect(JSON.parse(init.body)).toEqual({ question: 'What is the secret code?' })
  })

  it('includes doc_ids in the request body when scoping to specific documents', async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({ answer: 'Wobble-42.', citations: [], trace: makeTrace() }),
    })
    vi.stubGlobal('fetch', fetchMock)

    await askQuestion('What is the secret code?', ['doc-1', 'doc-2'])

    const [, init] = fetchMock.mock.calls[0]
    expect(JSON.parse(init.body)).toEqual({
      question: 'What is the secret code?',
      doc_ids: ['doc-1', 'doc-2'],
    })
  })

  it('omits doc_ids from the request body when no documents are scoped', async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({ answer: 'Wobble-42.', citations: [], trace: makeTrace() }),
    })
    vi.stubGlobal('fetch', fetchMock)

    await askQuestion('What is the secret code?', [])

    const [, init] = fetchMock.mock.calls[0]
    expect(JSON.parse(init.body)).toEqual({ question: 'What is the secret code?' })
  })

  it('throws AskError with the server-provided detail on failure', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue({
        ok: false,
        status: 502,
        json: async () => ({ detail: 'Could not get an answer right now.' }),
      }),
    )

    await expect(askQuestion('anything')).rejects.toThrow(AskError)
    await expect(askQuestion('anything')).rejects.toThrow('Could not get an answer right now.')
  })

  it('falls back to a generic message when the error body is not JSON', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue({
        ok: false,
        status: 500,
        json: async () => {
          throw new Error('not json')
        },
      }),
    )

    await expect(askQuestion('anything')).rejects.toThrow('Failed to get an answer: 500')
  })
})

describe('getMessageHistory', () => {
  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it('fetches the session message history with credentials included', async () => {
    const messages = [
      { role: 'user', content: 'What is the secret code?', citations: null },
      {
        role: 'assistant',
        content: 'Wobble-42.',
        citations: [
          { document_id: 'doc-1', filename: 'notes.txt', location_ref: 'document', snippet: 'x' },
        ],
      },
    ]
    const fetchMock = vi.fn().mockResolvedValue({ ok: true, json: async () => messages })
    vi.stubGlobal('fetch', fetchMock)

    const result = await getMessageHistory()

    expect(result).toEqual(messages)
    const [url, init] = fetchMock.mock.calls[0]
    expect(url).toBe('http://localhost:8000/chat/messages')
    expect(init).toEqual({ credentials: 'include' })
  })

  it('throws when the response is not ok', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ ok: false, status: 500 }))

    await expect(getMessageHistory()).rejects.toThrow('Failed to load message history: 500')
  })
})
