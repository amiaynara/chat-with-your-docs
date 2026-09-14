import { afterEach, describe, expect, it, vi } from 'vitest'
import { askQuestion, AskError } from './chat'

describe('askQuestion', () => {
  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it('sends the question and returns the answer with its citations', async () => {
    const citations = [
      { document_id: 'doc-1', filename: 'notes.txt', location_ref: 'document', snippet: 'Wobble-42.' },
    ]
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({ answer: 'Wobble-42.', citations }),
    })
    vi.stubGlobal('fetch', fetchMock)

    const result = await askQuestion('What is the secret code?')

    expect(result).toEqual({ answer: 'Wobble-42.', citations })
    const [url, init] = fetchMock.mock.calls[0]
    expect(url).toBe('http://localhost:8000/chat/messages')
    expect(init).toMatchObject({
      method: 'POST',
      credentials: 'include',
      headers: { 'Content-Type': 'application/json' },
    })
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
