const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? 'http://localhost:8000'

export type DocumentStatus = 'queued' | 'processing' | 'ready' | 'failed'

export interface Document {
  id: string
  filename: string
  format: 'pdf' | 'txt' | 'md'
  status: DocumentStatus
  error_reason: string | null
  created_at: string
}

export class UploadError extends Error {}

export async function listDocuments(): Promise<Document[]> {
  const response = await fetch(`${API_BASE_URL}/documents`, { credentials: 'include' })
  if (!response.ok) {
    throw new Error(`Failed to list documents: ${response.status}`)
  }
  return response.json()
}

export async function uploadDocument(file: File): Promise<Document> {
  const formData = new FormData()
  formData.append('file', file)

  const response = await fetch(`${API_BASE_URL}/documents`, {
    method: 'POST',
    credentials: 'include',
    body: formData,
  })

  if (!response.ok) {
    const body = await response.json().catch(() => null)
    throw new UploadError(body?.detail ?? `Upload failed: ${response.status}`)
  }

  return response.json()
}
