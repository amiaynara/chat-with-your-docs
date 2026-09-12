const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? 'http://localhost:8000'

export class AskError extends Error {}

export async function askQuestion(question: string): Promise<string> {
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

  const data = (await response.json()) as { answer: string }
  return data.answer
}
