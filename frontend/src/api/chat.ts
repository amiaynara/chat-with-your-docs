const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? 'http://localhost:8000'

export class AskError extends Error {}

export interface Citation {
  document_id: string
  filename: string
  location_ref: string
  snippet: string
}

export interface AskResult {
  answer: string
  citations: Citation[]
}

export interface HistoryMessage {
  role: 'user' | 'assistant'
  content: string
  citations: Citation[] | null
}

export async function askQuestion(question: string, docIds?: string[]): Promise<AskResult> {
  const body: { question: string; doc_ids?: string[] } = { question }
  if (docIds && docIds.length > 0) {
    body.doc_ids = docIds
  }

  const response = await fetch(`${API_BASE_URL}/chat/messages`, {
    method: 'POST',
    credentials: 'include',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })

  if (!response.ok) {
    const body = await response.json().catch(() => null)
    throw new AskError(body?.detail ?? `Failed to get an answer: ${response.status}`)
  }

  return (await response.json()) as AskResult
}

export async function getMessageHistory(): Promise<HistoryMessage[]> {
  const response = await fetch(`${API_BASE_URL}/chat/messages`, { credentials: 'include' })
  if (!response.ok) {
    throw new Error(`Failed to load message history: ${response.status}`)
  }
  return response.json()
}
