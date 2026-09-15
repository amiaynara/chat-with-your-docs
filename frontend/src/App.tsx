import { useCallback, useEffect, useRef, useState } from 'react'
import { type Document, listDocuments } from './api/documents'
import { Chat } from './components/Chat'
import { DocumentList } from './components/DocumentList'
import { UploadForm } from './components/UploadForm'

const POLL_INTERVAL_MS = 2000
const PENDING_STATUSES: Document['status'][] = ['queued', 'processing']

function App() {
  const [documents, setDocuments] = useState<Document[]>([])
  const [selectedDocIds, setSelectedDocIds] = useState<Set<string>>(new Set())
  const pollTimeout = useRef<ReturnType<typeof setTimeout> | null>(null)

  function toggleSelectedDocument(id: string) {
    setSelectedDocIds((prev) => {
      const next = new Set(prev)
      if (next.has(id)) {
        next.delete(id)
      } else {
        next.add(id)
      }
      return next
    })
  }

  // Dropped once a document no longer exists (e.g. deleted), rather than
  // silently scoping a future question to a document id that's gone.
  const scopedDocIds = documents
    .filter((document) => selectedDocIds.has(document.id))
    .map((document) => document.id)

  const refresh = useCallback(function poll() {
    if (pollTimeout.current) clearTimeout(pollTimeout.current)
    listDocuments()
      .then((docs) => {
        setDocuments(docs)
        // Only keep polling while something could still change — once every
        // document is ready/failed there's nothing left to watch for.
        if (docs.some((doc) => PENDING_STATUSES.includes(doc.status))) {
          pollTimeout.current = setTimeout(poll, POLL_INTERVAL_MS)
        }
      })
      .catch(() => {
        // Unknown state on a failed fetch — keep watching rather than going
        // silent, since something could still be pending.
        pollTimeout.current = setTimeout(poll, POLL_INTERVAL_MS)
      })
  }, [])

  useEffect(() => {
    refresh()
    return () => {
      if (pollTimeout.current) clearTimeout(pollTimeout.current)
    }
  }, [refresh])

  return (
    <main className="mx-auto flex min-h-screen max-w-2xl flex-col gap-6 px-4 py-10">
      <h1 className="text-2xl font-semibold text-neutral-900">Chat With Your Docs</h1>

      <section className="flex flex-col gap-3">
        <h2 className="text-sm font-medium text-neutral-600">Documents</h2>
        <UploadForm onUploaded={refresh} />
        <DocumentList
          documents={documents}
          onDeleted={refresh}
          onRetried={refresh}
          selectedIds={selectedDocIds}
          onToggleSelect={toggleSelectedDocument}
        />
      </section>

      <section className="flex flex-col gap-3">
        <h2 className="text-sm font-medium text-neutral-600">Ask a question</h2>
        {scopedDocIds.length > 0 && (
          <p className="text-xs text-neutral-500">
            Asking within {scopedDocIds.length} selected document
            {scopedDocIds.length > 1 ? 's' : ''}.
          </p>
        )}
        <Chat docIds={scopedDocIds} />
      </section>
    </main>
  )
}

export default App
