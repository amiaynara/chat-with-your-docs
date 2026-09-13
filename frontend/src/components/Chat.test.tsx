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
    vi.spyOn(chatApi, 'askQuestion').mockResolvedValue('The secret launch code is Wobble-42.')

    render(<Chat />)

    const input = screen.getByPlaceholderText(/ask a question/i)
    await userEvent.type(input, 'What is the secret launch code?')
    await userEvent.click(screen.getByRole('button', { name: /ask/i }))

    expect(await screen.findByText(/wobble-42/i)).toBeInTheDocument()
    expect(screen.getByText('What is the secret launch code?')).toBeInTheDocument()
  })

  it('clears the input after asking', async () => {
    vi.spyOn(chatApi, 'askQuestion').mockResolvedValue('An answer.')

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
