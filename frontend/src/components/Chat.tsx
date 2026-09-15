import { useEffect, useState } from 'react'
import ReactMarkdown from 'react-markdown'
import {
  AskError,
  askQuestion,
  getMessageHistory,
  type Citation,
  type HistoryMessage,
  type Trace,
} from '../api/chat'

interface Turn {
  question: string
  answer: string
  citations: Citation[]
  // Only set for a turn answered in this session — a turn restored from
  // GET /chat/messages history has no trace, since it isn't persisted.
  trace?: Trace
}

// Messages come back as a flat, role-tagged list; a "turn" is one user
// question paired with the assistant reply that followed it. A user message
// with no reply yet (e.g. the assistant call failed before persisting one) is
// still shown, with an empty answer, rather than silently dropped.
function groupIntoTurns(messages: HistoryMessage[]): Turn[] {
  const turns: Turn[] = []
  let pending: Turn | null = null

  for (const message of messages) {
    if (message.role === 'user') {
      if (pending) turns.push(pending)
      pending = { question: message.content, answer: '', citations: [] }
    } else if (pending) {
      pending.answer = message.content
      pending.citations = message.citations ?? []
      turns.push(pending)
      pending = null
    }
  }
  if (pending) turns.push(pending)

  return turns
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
  const [openTraceIndex, setOpenTraceIndex] = useState<number | null>(null)

  useEffect(() => {
    getMessageHistory()
      .then((messages) => setTurns(groupIntoTurns(messages)))
      .catch(() => {
        // No history to restore, or the request failed — either way, starting
        // from an empty conversation is a safe, non-crashing fallback.
      })
  }, [])

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
        {
          question: trimmed,
          answer: result.answer,
          citations: result.citations,
          trace: result.trace,
        },
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

  function toggleTrace(turnIndex: number) {
    setOpenTraceIndex((current) => (current === turnIndex ? null : turnIndex))
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
            {turn.trace && (
              <button
                type="button"
                onClick={() => toggleTrace(turnIndex)}
                aria-expanded={openTraceIndex === turnIndex}
                className="self-start text-xs text-neutral-400 hover:text-neutral-700"
              >
                {openTraceIndex === turnIndex ? 'Hide trace' : 'Inspect this answer'}
              </button>
            )}
            {turn.trace && openTraceIndex === turnIndex && <TracePanel trace={turn.trace} />}
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

function TracePanel({ trace }: { trace: Trace }) {
  return (
    <div className="flex w-full flex-col gap-2 self-start rounded-md border border-neutral-200 bg-white px-3 py-2 text-xs text-neutral-600">
      <div>
        <p className="font-medium text-neutral-800">Pipeline timing</p>
        <ul>
          {trace.stage_timings.map((timing) => (
            <li key={timing.stage}>
              {timing.stage}: {timing.duration_ms.toFixed(1)}ms
            </li>
          ))}
        </ul>
      </div>

      <p>
        Tokens: {trace.input_tokens} in / {trace.output_tokens} out
      </p>

      {trace.retrieval_hits.length > 0 && (
        <div>
          <p className="font-medium text-neutral-800">Retrieval hits</p>
          <ul>
            {trace.retrieval_hits.map((hit, index) => (
              <li key={index} className={hit.included ? undefined : 'text-neutral-400'}>
                [{hit.included ? 'used' : 'skipped'}] {hit.filename} ({hit.location_ref}) —
                distance {hit.distance.toFixed(3)}
                {hit.keyword_match ? ', keyword match' : ''}
              </li>
            ))}
          </ul>
        </div>
      )}

      {trace.rerank_scores && (
        <div>
          <p className="font-medium text-neutral-800">Rerank scores</p>
          <ul>
            {trace.rerank_scores.map((score, index) => (
              <li key={index}>
                {score.location_ref} — relevance {score.relevance_score.toFixed(3)}
              </li>
            ))}
          </ul>
        </div>
      )}

      {trace.prompt && (
        <div>
          <p className="font-medium text-neutral-800">Assembled prompt</p>
          <pre className="mt-1 max-h-48 overflow-auto whitespace-pre-wrap rounded bg-neutral-50 p-2">
            {trace.prompt}
          </pre>
        </div>
      )}
    </div>
  )
}
