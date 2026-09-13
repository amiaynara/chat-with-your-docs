import { render, screen } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
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
})
