import { useState } from 'react'
import ReactMarkdown from 'react-markdown'
import { AskError, askQuestion } from '../api/chat'

interface Turn {
  question: string
  answer: string
}

export function Chat() {
  const [question, setQuestion] = useState('')
  const [turns, setTurns] = useState<Turn[]>([])
  const [error, setError] = useState<string | null>(null)
  const [isAsking, setIsAsking] = useState(false)

  async function handleSubmit(event: React.FormEvent) {
    event.preventDefault()
    const trimmed = question.trim()
    if (!trimmed) return

    setError(null)
    setIsAsking(true)
    try {
      const answer = await askQuestion(trimmed)
      setTurns((prev) => [...prev, { question: trimmed, answer }])
      setQuestion('')
    } catch (err) {
      setError(err instanceof AskError ? err.message : 'Something went wrong. Please try again.')
    } finally {
      setIsAsking(false)
    }
  }

  return (
    <div className="flex flex-col gap-3">
      <ul className="flex flex-col gap-3">
        {turns.map((turn, index) => (
          <li key={index} className="flex flex-col gap-1">
            <p className="self-end rounded-lg bg-neutral-900 px-3 py-2 text-sm text-white">
              {turn.question}
            </p>
            <div className="prose prose-sm prose-neutral max-w-none self-start rounded-lg bg-neutral-100 px-3 py-2 text-neutral-800">
              <ReactMarkdown>{turn.answer}</ReactMarkdown>
            </div>
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
