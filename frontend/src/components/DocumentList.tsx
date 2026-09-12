import type { Document } from '../api/documents'

const STATUS_STYLES: Record<Document['status'], string> = {
  queued: 'bg-neutral-200 text-neutral-700',
  processing: 'bg-amber-100 text-amber-800',
  ready: 'bg-green-100 text-green-800',
  failed: 'bg-red-100 text-red-800',
}

interface DocumentListProps {
  documents: Document[]
}

export function DocumentList({ documents }: DocumentListProps) {
  if (documents.length === 0) {
    return (
      <p className="text-sm text-neutral-500">
        No documents yet — upload a PDF, txt, or Markdown file to get started.
      </p>
    )
  }

  return (
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
          </span>
          {document.status === 'failed' && document.error_reason && (
            <span className="text-xs text-red-600">{document.error_reason}</span>
          )}
        </li>
      ))}
    </ul>
  )
}
