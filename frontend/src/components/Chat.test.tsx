import { render, screen } from '@testing-library/react'
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
})
