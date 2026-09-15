import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, describe, expect, it, vi } from 'vitest'
import * as chatApi from './api/chat'
import * as documentsApi from './api/documents'
import App from './App'

describe('App', () => {
  afterEach(() => {
    vi.restoreAllMocks()
  })

  it('lists documents fetched from the API', async () => {
    vi.spyOn(documentsApi, 'listDocuments').mockResolvedValue([
      {
        id: '1',
        filename: 'handbook.pdf',
        format: 'pdf',
        status: 'ready',
        error_reason: null,
        error_category: null,
        created_at: new Date().toISOString(),
      },
    ])

    render(<App />)

    expect(await screen.findByText('handbook.pdf')).toBeInTheDocument()
  })

  it('shows the empty state when there are no documents', async () => {
    vi.spyOn(documentsApi, 'listDocuments').mockResolvedValue([])

    render(<App />)

    expect(await screen.findByText(/no documents yet/i)).toBeInTheDocument()
  })

  it('does not crash when the document list fails to load', async () => {
    vi.spyOn(documentsApi, 'listDocuments').mockRejectedValue(new Error('network down'))

    render(<App />)

    expect(await screen.findByText('Chat With Your Docs')).toBeInTheDocument()
  })

  it('stops polling once every document is in a terminal state', async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true })
    const listSpy = vi.spyOn(documentsApi, 'listDocuments').mockResolvedValue([
      {
        id: '1',
        filename: 'a.txt',
        format: 'txt',
        status: 'ready',
        error_reason: null,
        error_category: null,
        created_at: new Date().toISOString(),
      },
    ])

    render(<App />)
    await vi.waitFor(() => expect(listSpy).toHaveBeenCalledTimes(1))

    await vi.advanceTimersByTimeAsync(10_000)

    expect(listSpy).toHaveBeenCalledTimes(1)
    vi.useRealTimers()
  })

  it('keeps polling while a document is still queued or processing', async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true })
    const listSpy = vi.spyOn(documentsApi, 'listDocuments').mockResolvedValue([
      {
        id: '1',
        filename: 'a.txt',
        format: 'txt',
        status: 'processing',
        error_reason: null,
        error_category: null,
        created_at: new Date().toISOString(),
      },
    ])

    render(<App />)
    await vi.waitFor(() => expect(listSpy).toHaveBeenCalledTimes(1))

    await vi.advanceTimersByTimeAsync(2000)
    expect(listSpy).toHaveBeenCalledTimes(2)

    await vi.advanceTimersByTimeAsync(2000)
    expect(listSpy).toHaveBeenCalledTimes(3)

    vi.useRealTimers()
  })

  it('keeps retrying after a failed poll rather than going silent', async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true })
    const listSpy = vi.spyOn(documentsApi, 'listDocuments').mockRejectedValue(new Error('down'))

    render(<App />)
    await vi.waitFor(() => expect(listSpy).toHaveBeenCalledTimes(1))

    await vi.advanceTimersByTimeAsync(2000)
    expect(listSpy).toHaveBeenCalledTimes(2)

    vi.useRealTimers()
  })

  it('scopes a question to documents selected via their checkboxes', async () => {
    vi.spyOn(documentsApi, 'listDocuments').mockResolvedValue([
      {
        id: '1',
        filename: 'a.txt',
        format: 'txt',
        status: 'ready',
        error_reason: null,
        error_category: null,
        created_at: new Date().toISOString(),
      },
    ])
    const askSpy = vi
      .spyOn(chatApi, 'askQuestion')
      .mockResolvedValue({ answer: 'An answer.', citations: [] })

    render(<App />)
    await screen.findByText('a.txt')

    await userEvent.click(screen.getByRole('checkbox'))
    await userEvent.type(screen.getByPlaceholderText(/ask a question/i), 'A question?')
    await userEvent.click(screen.getByRole('button', { name: /^ask$/i }))

    expect(askSpy).toHaveBeenCalledWith('A question?', ['1'])
  })

  it('unscopes a question again after unchecking a previously selected document', async () => {
    vi.spyOn(documentsApi, 'listDocuments').mockResolvedValue([
      {
        id: '1',
        filename: 'a.txt',
        format: 'txt',
        status: 'ready',
        error_reason: null,
        error_category: null,
        created_at: new Date().toISOString(),
      },
    ])
    const askSpy = vi
      .spyOn(chatApi, 'askQuestion')
      .mockResolvedValue({ answer: 'An answer.', citations: [] })

    render(<App />)
    await screen.findByText('a.txt')

    const checkbox = screen.getByRole('checkbox')
    await userEvent.click(checkbox)
    await userEvent.click(checkbox)
    await userEvent.type(screen.getByPlaceholderText(/ask a question/i), 'A question?')
    await userEvent.click(screen.getByRole('button', { name: /^ask$/i }))

    expect(askSpy).toHaveBeenCalledWith('A question?', [])
  })

  it('pluralizes the selected-document count label for more than one selection', async () => {
    vi.spyOn(documentsApi, 'listDocuments').mockResolvedValue([
      {
        id: '1',
        filename: 'a.txt',
        format: 'txt',
        status: 'ready',
        error_reason: null,
        error_category: null,
        created_at: new Date().toISOString(),
      },
      {
        id: '2',
        filename: 'b.txt',
        format: 'txt',
        status: 'ready',
        error_reason: null,
        error_category: null,
        created_at: new Date().toISOString(),
      },
    ])

    render(<App />)
    await screen.findByText('a.txt')

    const [firstCheckbox, secondCheckbox] = screen.getAllByRole('checkbox')
    await userEvent.click(firstCheckbox)
    await userEvent.click(secondCheckbox)

    expect(await screen.findByText('Asking within 2 selected documents.')).toBeInTheDocument()
  })

  it('asks unscoped when no document is selected', async () => {
    vi.spyOn(documentsApi, 'listDocuments').mockResolvedValue([
      {
        id: '1',
        filename: 'a.txt',
        format: 'txt',
        status: 'ready',
        error_reason: null,
        error_category: null,
        created_at: new Date().toISOString(),
      },
    ])
    const askSpy = vi
      .spyOn(chatApi, 'askQuestion')
      .mockResolvedValue({ answer: 'An answer.', citations: [] })

    render(<App />)
    await screen.findByText('a.txt')

    await userEvent.type(screen.getByPlaceholderText(/ask a question/i), 'A question?')
    await userEvent.click(screen.getByRole('button', { name: /^ask$/i }))

    expect(askSpy).toHaveBeenCalledWith('A question?', [])
  })
})
