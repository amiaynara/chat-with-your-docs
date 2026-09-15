import { afterEach, describe, expect, it, vi } from 'vitest'
import {
  deleteDocument,
  DeleteError,
  listDocuments,
  retryDocument,
  RetryError,
  uploadDocument,
  UploadError,
} from './documents'

describe('listDocuments', () => {
  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it('fetches the document list with credentials included', async () => {
    const document = {
      id: '1',
      filename: 'a.txt',
      format: 'txt' as const,
      status: 'ready' as const,
      error_reason: null,
      error_category: null,
      created_at: new Date().toISOString(),
    }
    const fetchMock = vi.fn().mockResolvedValue({ ok: true, json: async () => [document] })
    vi.stubGlobal('fetch', fetchMock)

    const documents = await listDocuments()

    expect(documents).toEqual([document])
    const [url, init] = fetchMock.mock.calls[0]
    expect(url).toBe('http://localhost:8000/documents')
    expect(init).toEqual({ credentials: 'include' })
  })

  it('throws when the response is not ok', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ ok: false, status: 500 }))

    await expect(listDocuments()).rejects.toThrow('Failed to list documents: 500')
  })
})

describe('uploadDocument', () => {
  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it('posts the file as multipart form data and returns the created document', async () => {
    const document = {
      id: '1',
      filename: 'a.txt',
      format: 'txt' as const,
      status: 'queued' as const,
      error_reason: null,
      error_category: null,
      created_at: new Date().toISOString(),
    }
    const fetchMock = vi.fn().mockResolvedValue({ ok: true, json: async () => document })
    vi.stubGlobal('fetch', fetchMock)

    const file = new File(['hello'], 'a.txt', { type: 'text/plain' })
    const result = await uploadDocument(file)

    expect(result).toEqual(document)
    const [url, init] = fetchMock.mock.calls[0]
    expect(url).toBe('http://localhost:8000/documents')
    expect(init.method).toBe('POST')
    expect(init.credentials).toBe('include')
    expect(init.body).toBeInstanceOf(FormData)
    expect(init.body.get('file')).toBe(file)
  })

  it('throws UploadError with the server-provided detail on failure', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue({
        ok: false,
        status: 422,
        json: async () => ({ detail: 'Unsupported file type' }),
      }),
    )

    const file = new File(['bad'], 'virus.exe')
    await expect(uploadDocument(file)).rejects.toThrow(UploadError)
    await expect(uploadDocument(file)).rejects.toThrow('Unsupported file type')
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

    const file = new File(['bad'], 'a.txt')
    await expect(uploadDocument(file)).rejects.toThrow('Upload failed: 500')
  })
})

describe('deleteDocument', () => {
  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it('sends a DELETE request with credentials included', async () => {
    const fetchMock = vi.fn().mockResolvedValue({ ok: true, status: 204 })
    vi.stubGlobal('fetch', fetchMock)

    await deleteDocument('doc-1')

    const [url, init] = fetchMock.mock.calls[0]
    expect(url).toBe('http://localhost:8000/documents/doc-1')
    expect(init).toEqual({ method: 'DELETE', credentials: 'include' })
  })

  it('throws DeleteError when the response is not ok', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ ok: false, status: 404 }))

    await expect(deleteDocument('doc-1')).rejects.toThrow(DeleteError)
    await expect(deleteDocument('doc-1')).rejects.toThrow('Failed to delete document: 404')
  })
})

describe('retryDocument', () => {
  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it('sends a POST request to the retry endpoint with credentials included', async () => {
    const document = {
      id: '1',
      filename: 'a.txt',
      format: 'txt' as const,
      status: 'queued' as const,
      error_reason: null,
      error_category: null,
      created_at: new Date().toISOString(),
    }
    const fetchMock = vi.fn().mockResolvedValue({ ok: true, json: async () => document })
    vi.stubGlobal('fetch', fetchMock)

    const result = await retryDocument('doc-1')

    expect(result).toEqual(document)
    const [url, init] = fetchMock.mock.calls[0]
    expect(url).toBe('http://localhost:8000/documents/doc-1/retry')
    expect(init).toEqual({ method: 'POST', credentials: 'include' })
  })

  it('throws RetryError with the server-provided detail on failure', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue({
        ok: false,
        status: 422,
        json: async () => ({ detail: 'This document failed because of the file itself' }),
      }),
    )

    await expect(retryDocument('doc-1')).rejects.toThrow(RetryError)
    await expect(retryDocument('doc-1')).rejects.toThrow(
      'This document failed because of the file itself',
    )
  })

  it('falls back to a generic message when the error body is not JSON', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue({
        ok: false,
        status: 409,
        json: async () => {
          throw new Error('not json')
        },
      }),
    )

    await expect(retryDocument('doc-1')).rejects.toThrow('Retry failed: 409')
  })
})
