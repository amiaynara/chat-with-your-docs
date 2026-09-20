const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? 'http://localhost:8000'

export class ResetSessionError extends Error {}

export async function resetSession(): Promise<void> {
  const response = await fetch(`${API_BASE_URL}/session/reset`, {
    method: 'POST',
    credentials: 'include',
  })

  if (!response.ok) {
    throw new ResetSessionError(`Failed to reset session: ${response.status}`)
  }
}
