import { fireEvent, render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, describe, expect, it, vi } from 'vitest'
import * as chatApi from '../api/chat'
import { Chat } from './Chat'

describe('Chat', () => {
  afterEach(() => {
    vi.restoreAllMocks()
  })

  it('asks a question and displays the answer', async () => {
    vi.spyOn(chatApi, 'askQuestion').mockResolvedValue({
      answer: 'The secret launch code is Wobble-42.',
      citations: [],
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
      .mockResolvedValue({ answer: 'An answer.', citations: [] })

    render(<Chat docIds={['doc-1', 'doc-2']} />)

    await userEvent.type(screen.getByPlaceholderText(/ask a question/i), 'A question?')
    await userEvent.click(screen.getByRole('button', { name: /ask/i }))

    expect(askSpy).toHaveBeenCalledWith('A question?', ['doc-1', 'doc-2'])
  })

  it('renders markdown formatting in the answer instead of raw syntax', async () => {
    vi.spyOn(chatApi, 'askQuestion').mockResolvedValue({
      answer: '**Category:** Negligible\n\n- item one\n- item two',
      citations: [],
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
    })

    render(<Chat />)

    await userEvent.type(screen.getByPlaceholderText(/ask a question/i), 'A question?')
    await userEvent.click(screen.getByRole('button', { name: /ask/i }))

    await screen.findByText(/don't have any supporting information/i)
    expect(screen.queryByText(/sources/i)).not.toBeInTheDocument()
  })

  it('clears the input after asking', async () => {
    vi.spyOn(chatApi, 'askQuestion').mockResolvedValue({ answer: 'An answer.', citations: [] })

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
