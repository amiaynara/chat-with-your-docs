import { useCallback, useEffect, useRef, useState } from 'react'
import { type Document, listDocuments } from './api/documents'
import { Chat } from './components/Chat'
import { DocumentList } from './components/DocumentList'
import { UploadForm } from './components/UploadForm'

const POLL_INTERVAL_MS = 2000
const PENDING_STATUSES: Document['status'][] = ['queued', 'processing']

function App() {
  const [documents, setDocuments] = useState<Document[]>([])
  const pollTimeout = useRef<ReturnType<typeof setTimeout> | null>(null)

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
        <DocumentList documents={documents} onDeleted={refresh} />
      </section>

      <section className="flex flex-col gap-3">
        <h2 className="text-sm font-medium text-neutral-600">Ask a question</h2>
        <Chat />
      </section>
    </main>
  )
}

export default App
