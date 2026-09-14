import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, describe, expect, it, vi } from 'vitest'
import * as documentsApi from '../api/documents'
import type { Document } from '../api/documents'
import { DocumentList } from './DocumentList'

function makeDocument(overrides: Partial<Document> = {}): Document {
  return {
    id: '1',
    filename: 'notes.txt',
    format: 'txt',
    status: 'ready',
    error_reason: null,
    created_at: new Date().toISOString(),
    ...overrides,
  }
}

describe('DocumentList', () => {
  afterEach(() => {
    vi.restoreAllMocks()
  })

  it('shows an empty state when there are no documents', () => {
    render(<DocumentList documents={[]} onDeleted={() => {}} />)

    expect(screen.getByText(/no documents yet/i)).toBeInTheDocument()
  })

  it('renders each document with its filename and status', () => {
    render(
      <DocumentList
        documents={[
          makeDocument({ id: '1', filename: 'a.txt', status: 'ready' }),
          makeDocument({ id: '2', filename: 'b.pdf', status: 'processing' }),
        ]}
        onDeleted={() => {}}
      />,
    )

    expect(screen.getByText('a.txt')).toBeInTheDocument()
    expect(screen.getByText('ready')).toBeInTheDocument()
    expect(screen.getByText('b.pdf')).toBeInTheDocument()
    expect(screen.getByText('processing')).toBeInTheDocument()
  })

  it('shows the error reason for a failed document', () => {
    render(
      <DocumentList
        documents={[
          makeDocument({ status: 'failed', error_reason: 'Could not read PDF: bad header' }),
        ]}
        onDeleted={() => {}}
      />,
    )

    expect(screen.getByText(/could not read pdf/i)).toBeInTheDocument()
  })

  it('deletes a document and notifies the parent to refresh', async () => {
    const deleteSpy = vi.spyOn(documentsApi, 'deleteDocument').mockResolvedValue(undefined)
    const onDeleted = vi.fn()

    render(
      <DocumentList documents={[makeDocument({ id: '1', filename: 'a.txt' })]} onDeleted={onDeleted} />,
    )

    await userEvent.click(screen.getByRole('button', { name: /delete/i }))

    expect(deleteSpy).toHaveBeenCalledWith('1')
    expect(onDeleted).toHaveBeenCalled()
  })

  it('shows an error and does not notify the parent when deletion fails', async () => {
    vi.spyOn(documentsApi, 'deleteDocument').mockRejectedValue(new Error('boom'))
    const onDeleted = vi.fn()

    render(
      <DocumentList documents={[makeDocument({ id: '1', filename: 'a.txt' })]} onDeleted={onDeleted} />,
    )

    await userEvent.click(screen.getByRole('button', { name: /delete/i }))

    expect(await screen.findByText(/failed to delete/i)).toBeInTheDocument()
    expect(onDeleted).not.toHaveBeenCalled()
  })
})
