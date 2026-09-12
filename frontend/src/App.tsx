import { useCallback, useEffect, useState } from 'react'
import { type Document, listDocuments } from './api/documents'
import { Chat } from './components/Chat'
import { DocumentList } from './components/DocumentList'
import { UploadForm } from './components/UploadForm'

const POLL_INTERVAL_MS = 2000

function App() {
  const [documents, setDocuments] = useState<Document[]>([])

  const refresh = useCallback(() => {
    listDocuments().then(setDocuments).catch(() => {})
  }, [])

  useEffect(() => {
    refresh()
    const interval = setInterval(refresh, POLL_INTERVAL_MS)
    return () => clearInterval(interval)
  }, [refresh])

  return (
    <main className="mx-auto flex min-h-screen max-w-2xl flex-col gap-6 px-4 py-10">
      <h1 className="text-2xl font-semibold text-neutral-900">Chat With Your Docs</h1>

      <section className="flex flex-col gap-3">
        <h2 className="text-sm font-medium text-neutral-600">Documents</h2>
        <UploadForm onUploaded={refresh} />
        <DocumentList documents={documents} />
      </section>

      <section className="flex flex-col gap-3">
        <h2 className="text-sm font-medium text-neutral-600">Ask a question</h2>
        <Chat />
      </section>
    </main>
  )
}

export default App
