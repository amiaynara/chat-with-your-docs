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

export async function askQuestion(question: string): Promise<AskResult> {
  const response = await fetch(`${API_BASE_URL}/chat/messages`, {
    method: 'POST',
    credentials: 'include',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ question }),
  })

  if (!response.ok) {
    const body = await response.json().catch(() => null)
    throw new AskError(body?.detail ?? `Failed to get an answer: ${response.status}`)
  }

  return (await response.json()) as AskResult
}
