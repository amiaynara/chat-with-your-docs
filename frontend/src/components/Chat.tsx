import { useState } from 'react'
import ReactMarkdown from 'react-markdown'
import { AskError, askQuestion, type Citation } from '../api/chat'

interface Turn {
  question: string
  answer: string
  citations: Citation[]
}

interface OpenCitation {
  turnIndex: number
  citationIndex: number
}

interface ChatProps {
  docIds?: string[]
}

export function Chat({ docIds = [] }: ChatProps) {
  const [question, setQuestion] = useState('')
  const [turns, setTurns] = useState<Turn[]>([])
  const [error, setError] = useState<string | null>(null)
  const [isAsking, setIsAsking] = useState(false)
  const [openCitation, setOpenCitation] = useState<OpenCitation | null>(null)

  async function handleSubmit(event: React.FormEvent) {
    event.preventDefault()
    const trimmed = question.trim()
    if (!trimmed) return

    setError(null)
    setIsAsking(true)
    try {
      const result = await askQuestion(trimmed, docIds)
      setTurns((prev) => [
        ...prev,
        { question: trimmed, answer: result.answer, citations: result.citations },
      ])
      setQuestion('')
    } catch (err) {
      setError(err instanceof AskError ? err.message : 'Something went wrong. Please try again.')
    } finally {
      setIsAsking(false)
    }
  }

  function toggleCitation(turnIndex: number, citationIndex: number) {
    setOpenCitation((current) =>
      current?.turnIndex === turnIndex && current.citationIndex === citationIndex
        ? null
        : { turnIndex, citationIndex },
    )
  }

  return (
    <div className="flex flex-col gap-3">
      <ul className="flex flex-col gap-3">
        {turns.map((turn, turnIndex) => (
          <li key={turnIndex} className="flex flex-col gap-1">
            <p className="self-end rounded-lg bg-neutral-900 px-3 py-2 text-sm text-white">
              {turn.question}
            </p>
            <div className="prose prose-sm prose-neutral max-w-none self-start rounded-lg bg-neutral-100 px-3 py-2 text-neutral-800">
              <ReactMarkdown>{turn.answer}</ReactMarkdown>
            </div>
            {turn.citations.length > 0 && (
              <div className="flex flex-wrap items-center gap-1 self-start">
                <span className="text-xs text-neutral-500">Sources:</span>
                {turn.citations.map((_citation, citationIndex) => (
                  <button
                    key={citationIndex}
                    type="button"
                    onClick={() => toggleCitation(turnIndex, citationIndex)}
                    aria-expanded={
                      openCitation?.turnIndex === turnIndex &&
                      openCitation.citationIndex === citationIndex
                    }
                    className="rounded-full bg-neutral-200 px-2 py-0.5 text-xs font-medium text-neutral-700 hover:bg-neutral-300"
                  >
                    {citationIndex + 1}
                  </button>
                ))}
              </div>
            )}
            {openCitation?.turnIndex === turnIndex && (
              <div className="self-start rounded-md border border-neutral-200 bg-white px-3 py-2 text-xs text-neutral-600">
                <p className="font-medium text-neutral-800">
                  <span>{turn.citations[openCitation.citationIndex].filename}</span>
                  {' — '}
                  <span>{turn.citations[openCitation.citationIndex].location_ref}</span>
                </p>
                <p className="mt-1">{turn.citations[openCitation.citationIndex].snippet}</p>
              </div>
            )}
          </li>
        ))}
      </ul>

      <form onSubmit={handleSubmit} className="flex gap-2">
        <input
          type="text"
          value={question}
          onChange={(event) => setQuestion(event.target.value)}
          placeholder="Ask a question about your documents…"
          className="flex-1 rounded-md border border-neutral-300 px-3 py-2 text-sm"
          disabled={isAsking}
        />
        <button
          type="submit"
          disabled={isAsking || !question.trim()}
          className="rounded-md bg-neutral-900 px-4 py-2 text-sm text-white disabled:opacity-50"
        >
          {isAsking ? 'Asking…' : 'Ask'}
        </button>
      </form>
      {error && <p className="text-sm text-red-600">{error}</p>}
    </div>
  )
}
