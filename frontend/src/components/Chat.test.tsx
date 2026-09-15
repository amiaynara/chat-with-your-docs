import { fireEvent, render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, describe, expect, it, vi } from 'vitest'
import * as chatApi from '../api/chat'
import type { Trace } from '../api/chat'
import { Chat } from './Chat'

function makeTrace(overrides: Partial<Trace> = {}): Trace {
  return {
    retrieval_hits: [],
    rerank_scores: null,
    prompt: null,
    input_tokens: 0,
    output_tokens: 0,
    stage_timings: [],
    ...overrides,
  }
}

describe('Chat', () => {
  afterEach(() => {
    vi.restoreAllMocks()
  })

  it('asks a question and displays the answer', async () => {
    vi.spyOn(chatApi, 'askQuestion').mockResolvedValue({
      answer: 'The secret launch code is Wobble-42.',
      citations: [],
      trace: makeTrace(),
    })

    render(<Chat />)

    const input = screen.getByPlaceholderText(/ask a question/i)
    await userEvent.type(input, 'What is the secret launch code?')
    await userEvent.click(screen.getByRole('button', { name: /ask/i }))

    expect(await screen.findByText(/wobble-42/i)).toBeInTheDocument()
    expect(screen.getByText('What is the secret launch code?')).toBeInTheDocument()
  })

  it('loads and displays prior conversation history on mount', async () => {
    vi.spyOn(chatApi, 'getMessageHistory').mockResolvedValue([
      { role: 'user', content: 'What is the secret launch code?', citations: null },
      {
        role: 'assistant',
        content: 'The secret launch code is Wobble-42.',
        citations: [
          {
            document_id: 'doc-1',
            filename: 'notes.txt',
            location_ref: 'document',
            snippet: 'Wobble-42.',
          },
        ],
      },
    ])

    render(<Chat />)

    expect(await screen.findByText('What is the secret launch code?')).toBeInTheDocument()
    expect(screen.getByText(/wobble-42/i)).toBeInTheDocument()
    expect(screen.getByRole('button', { name: '1' })).toBeInTheDocument()
  })

  it('shows a user message with no reply yet, rather than dropping it', async () => {
    vi.spyOn(chatApi, 'getMessageHistory').mockResolvedValue([
      { role: 'user', content: 'An unanswered question.', citations: null },
      { role: 'user', content: 'A question with an answer.', citations: null },
      { role: 'assistant', content: 'Here is the answer.', citations: null },
      { role: 'user', content: 'A trailing unanswered question.', citations: null },
    ])

    render(<Chat />)

    expect(await screen.findByText('An unanswered question.')).toBeInTheDocument()
    expect(screen.getByText('A question with an answer.')).toBeInTheDocument()
    expect(screen.getByText('Here is the answer.')).toBeInTheDocument()
    expect(screen.getByText('A trailing unanswered question.')).toBeInTheDocument()
  })

  it('ignores an assistant message with no preceding user question', async () => {
    vi.spyOn(chatApi, 'getMessageHistory').mockResolvedValue([
      { role: 'assistant', content: 'An orphan reply with no question.', citations: null },
      { role: 'user', content: 'A real question.', citations: null },
      { role: 'assistant', content: 'A real answer.', citations: null },
    ])

    render(<Chat />)

    expect(await screen.findByText('A real question.')).toBeInTheDocument()
    expect(screen.getByText('A real answer.')).toBeInTheDocument()
    expect(screen.queryByText('An orphan reply with no question.')).not.toBeInTheDocument()
  })

  it('does not crash when loading conversation history fails', async () => {
    vi.spyOn(chatApi, 'getMessageHistory').mockRejectedValue(new Error('network down'))

    render(<Chat />)

    expect(await screen.findByPlaceholderText(/ask a question/i)).toBeInTheDocument()
  })

  it('passes the docIds prop through to askQuestion when scoping a question', async () => {
    const askSpy = vi
      .spyOn(chatApi, 'askQuestion')
      .mockResolvedValue({ answer: 'An answer.', citations: [], trace: makeTrace() })

    render(<Chat docIds={['doc-1', 'doc-2']} />)

    await userEvent.type(screen.getByPlaceholderText(/ask a question/i), 'A question?')
    await userEvent.click(screen.getByRole('button', { name: /ask/i }))

    expect(askSpy).toHaveBeenCalledWith('A question?', ['doc-1', 'doc-2'])
  })

  it('renders markdown formatting in the answer instead of raw syntax', async () => {
    vi.spyOn(chatApi, 'askQuestion').mockResolvedValue({
      answer: '**Category:** Negligible\n\n- item one\n- item two',
      citations: [],
      trace: makeTrace(),
    })

    render(<Chat />)

    await userEvent.type(screen.getByPlaceholderText(/ask a question/i), 'A question?')
    await userEvent.click(screen.getByRole('button', { name: /ask/i }))

    expect(await screen.findByText('Category:')).toBeInstanceOf(HTMLElement)
    expect(screen.getByText('Category:').tagName).toBe('STRONG')
    expect(screen.getByText('item one').tagName).toBe('LI')
    expect(screen.getByText('item two').tagName).toBe('LI')
  })

  it('shows numbered citation markers that reveal a source panel on click', async () => {
    vi.spyOn(chatApi, 'askQuestion').mockResolvedValue({
      answer: 'The secret launch code is Wobble-42.',
      citations: [
        {
          document_id: 'doc-1',
          filename: 'notes.txt',
          location_ref: 'document',
          snippet: 'The secret launch code is Wobble-42. Keep it safe.',
        },
      ],
      trace: makeTrace(),
    })

    render(<Chat />)

    await userEvent.type(screen.getByPlaceholderText(/ask a question/i), 'What is the code?')
    await userEvent.click(screen.getByRole('button', { name: /ask/i }))

    const marker = await screen.findByRole('button', { name: '1' })
    expect(screen.queryByText('notes.txt')).not.toBeInTheDocument()

    await userEvent.click(marker)

    expect(screen.getByText('notes.txt')).toBeInTheDocument()
    expect(screen.getByText('document')).toBeInTheDocument()
    expect(screen.getByText(/keep it safe/i)).toBeInTheDocument()

    await userEvent.click(marker)

    expect(screen.queryByText('notes.txt')).not.toBeInTheDocument()
  })

  it('shows no source markers when the answer has no citations', async () => {
    vi.spyOn(chatApi, 'askQuestion').mockResolvedValue({
      answer: "I don't have any supporting information to answer that.",
      citations: [],
      trace: makeTrace(),
    })

    render(<Chat />)

    await userEvent.type(screen.getByPlaceholderText(/ask a question/i), 'A question?')
    await userEvent.click(screen.getByRole('button', { name: /ask/i }))

    await screen.findByText(/don't have any supporting information/i)
    expect(screen.queryByText(/sources/i)).not.toBeInTheDocument()
  })

  it('clears the input after asking', async () => {
    vi.spyOn(chatApi, 'askQuestion').mockResolvedValue({
      answer: 'An answer.',
      citations: [],
      trace: makeTrace(),
    })

    render(<Chat />)

    const input = screen.getByPlaceholderText(/ask a question/i) as HTMLInputElement
    await userEvent.type(input, 'A question?')
    await userEvent.click(screen.getByRole('button', { name: /ask/i }))

    await screen.findByText('An answer.')
    expect(input.value).toBe('')
  })

  it('shows an error message when asking fails', async () => {
    vi.spyOn(chatApi, 'askQuestion').mockRejectedValue(new chatApi.AskError('Something went wrong'))

    render(<Chat />)

    await userEvent.type(screen.getByPlaceholderText(/ask a question/i), 'A question?')
    await userEvent.click(screen.getByRole('button', { name: /ask/i }))

    expect(await screen.findByText(/something went wrong/i)).toBeInTheDocument()
  })

  it('shows a generic error message for a non-AskError failure', async () => {
    vi.spyOn(chatApi, 'askQuestion').mockRejectedValue(new Error('network exploded'))

    render(<Chat />)

    await userEvent.type(screen.getByPlaceholderText(/ask a question/i), 'A question?')
    await userEvent.click(screen.getByRole('button', { name: /ask/i }))

    expect(await screen.findByText(/please try again/i)).toBeInTheDocument()
  })

  it('shows an inspect-this-answer button that reveals the trace panel on click', async () => {
    vi.spyOn(chatApi, 'askQuestion').mockResolvedValue({
      answer: 'The secret launch code is Wobble-42.',
      citations: [],
      trace: makeTrace({
        prompt: 'System prompt with <context>Wobble-42</context>',
        input_tokens: 42,
        output_tokens: 7,
        stage_timings: [
          { stage: 'embed_query', duration_ms: 1.5 },
          { stage: 'retrieve', duration_ms: 3.25 },
          { stage: 'generate', duration_ms: 120 },
        ],
        retrieval_hits: [
          {
            document_id: 'doc-1',
            filename: 'notes.txt',
            location_ref: 'document',
            distance: 0.12,
            keyword_match: true,
            included: true,
          },
          {
            document_id: 'doc-2',
            filename: 'other.txt',
            location_ref: 'document',
            distance: 0.9,
            keyword_match: false,
            included: false,
          },
        ],
        rerank_scores: [{ document_id: 'doc-1', location_ref: 'document', relevance_score: 0.87 }],
      }),
    })

    render(<Chat />)

    await userEvent.type(screen.getByPlaceholderText(/ask a question/i), 'What is the code?')
    await userEvent.click(screen.getByRole('button', { name: /ask/i }))

    const inspectButton = await screen.findByRole('button', { name: /inspect this answer/i })
    expect(screen.queryByText(/pipeline timing/i)).not.toBeInTheDocument()

    await userEvent.click(inspectButton)

    expect(screen.getByText(/pipeline timing/i)).toBeInTheDocument()
    expect(screen.getByText(/embed_query: 1.5ms/i)).toBeInTheDocument()
    expect(screen.getByText(/42 in \/ 7 out/i)).toBeInTheDocument()
    expect(screen.getByText(/notes.txt/i)).toBeInTheDocument()
    expect(screen.getByText(/other.txt/i)).toBeInTheDocument()
    expect(screen.getByText(/relevance 0.870/i)).toBeInTheDocument()
    expect(screen.getByText(/System prompt with/i)).toBeInTheDocument()

    await userEvent.click(screen.getByRole('button', { name: /hide trace/i }))

    expect(screen.queryByText(/pipeline timing/i)).not.toBeInTheDocument()
  })

  it('shows no inspect-this-answer button for a turn restored from history', async () => {
    vi.spyOn(chatApi, 'getMessageHistory').mockResolvedValue([
      { role: 'user', content: 'A question.', citations: null },
      { role: 'assistant', content: 'An answer.', citations: null },
    ])

    render(<Chat />)

    await screen.findByText('An answer.')
    expect(screen.queryByRole('button', { name: /inspect this answer/i })).not.toBeInTheDocument()
  })

  it('does not submit a blank or whitespace-only question', async () => {
    // The submit button is disabled for a blank question (and disables
    // Enter's implicit form submission too), so the guard itself is
    // exercised by dispatching a submit event directly on the form.
    const askSpy = vi.spyOn(chatApi, 'askQuestion')

    render(<Chat />)

    const input = screen.getByPlaceholderText(/ask a question/i)
    fireEvent.change(input, { target: { value: '   ' } })
    fireEvent.submit(input.closest('form')!)

    expect(askSpy).not.toHaveBeenCalled()
  })
})
