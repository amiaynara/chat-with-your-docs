import { useState } from 'react'
import { deleteDocument, type Document } from '../api/documents'

const STATUS_STYLES: Record<Document['status'], string> = {
  queued: 'bg-neutral-200 text-neutral-700',
  processing: 'bg-amber-100 text-amber-800',
  ready: 'bg-green-100 text-green-800',
  failed: 'bg-red-100 text-red-800',
}

interface DocumentListProps {
  documents: Document[]
  onDeleted: () => void
}

export function DocumentList({ documents, onDeleted }: DocumentListProps) {
  const [deletingId, setDeletingId] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)

  async function handleDelete(id: string) {
    setError(null)
    setDeletingId(id)
    try {
      await deleteDocument(id)
      onDeleted()
    } catch {
      setError('Failed to delete document. Please try again.')
    } finally {
      setDeletingId(null)
    }
  }

  if (documents.length === 0) {
    return (
      <p className="text-sm text-neutral-500">
        No documents yet — upload a PDF, txt, or Markdown file to get started.
      </p>
    )
  }

  return (
    <div className="flex flex-col gap-2">
      <ul className="flex flex-col gap-2">
        {documents.map((document) => (
          <li
            key={document.id}
            className="flex items-center justify-between gap-3 rounded-md border border-neutral-200 px-3 py-2"
          >
            <span className="truncate text-sm text-neutral-800">{document.filename}</span>
            <span className="flex items-center gap-2">
              <span
                className={`rounded-full px-2 py-0.5 text-xs font-medium ${STATUS_STYLES[document.status]}`}
              >
                {document.status}
              </span>
              <button
                type="button"
                onClick={() => handleDelete(document.id)}
                disabled={deletingId === document.id}
                className="text-xs text-neutral-500 hover:text-red-600 disabled:opacity-50"
              >
                {deletingId === document.id ? 'Deleting…' : 'Delete'}
              </button>
            </span>
            {document.status === 'failed' && document.error_reason && (
              <span className="text-xs text-red-600">{document.error_reason}</span>
            )}
          </li>
        ))}
      </ul>
      {error && <p className="text-sm text-red-600">{error}</p>}
    </div>
  )
}
