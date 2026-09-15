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
    error_category: null,
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

  it('lets the user select a document to scope questions to', async () => {
    const onToggleSelect = vi.fn()

    render(
      <DocumentList
        documents={[makeDocument({ id: '1', filename: 'a.txt' })]}
        onDeleted={() => {}}
        selectedIds={new Set()}
        onToggleSelect={onToggleSelect}
      />,
    )

    await userEvent.click(screen.getByRole('checkbox'))

    expect(onToggleSelect).toHaveBeenCalledWith('1')
  })

  it('shows a document as checked when it is selected', () => {
    render(
      <DocumentList
        documents={[makeDocument({ id: '1', filename: 'a.txt' })]}
        onDeleted={() => {}}
        selectedIds={new Set(['1'])}
        onToggleSelect={() => {}}
      />,
    )

    expect(screen.getByRole('checkbox')).toBeChecked()
  })

  it('treats no document as selected when selection props are omitted', async () => {
    render(<DocumentList documents={[makeDocument({ id: '1' })]} onDeleted={() => {}} />)

    expect(screen.getByRole('checkbox')).not.toBeChecked()

    // No onToggleSelect was passed — clicking must not throw, falling back to
    // the default no-op.
    await userEvent.click(screen.getByRole('checkbox'))
  })

  it('shows a retry action for a failed document with a system error', () => {
    render(
      <DocumentList
        documents={[makeDocument({ status: 'failed', error_category: 'system_error' })]}
        onDeleted={() => {}}
      />,
    )

    expect(screen.getByRole('button', { name: /retry/i })).toBeInTheDocument()
  })

  it('does not show a retry action for a failed document with a user error', () => {
    render(
      <DocumentList
        documents={[makeDocument({ status: 'failed', error_category: 'user_error' })]}
        onDeleted={() => {}}
      />,
    )

    expect(screen.queryByRole('button', { name: /retry/i })).not.toBeInTheDocument()
  })

  it('does not show a retry action for a ready document', () => {
    render(<DocumentList documents={[makeDocument({ status: 'ready' })]} onDeleted={() => {}} />)

    expect(screen.queryByRole('button', { name: /retry/i })).not.toBeInTheDocument()
  })

  it('retries a document and notifies the parent to refresh', async () => {
    const retrySpy = vi.spyOn(documentsApi, 'retryDocument').mockResolvedValue(
      makeDocument({ status: 'queued' }),
    )
    const onRetried = vi.fn()

    render(
      <DocumentList
        documents={[makeDocument({ id: '1', status: 'failed', error_category: 'system_error' })]}
        onDeleted={() => {}}
        onRetried={onRetried}
      />,
    )

    await userEvent.click(screen.getByRole('button', { name: /retry/i }))

    expect(retrySpy).toHaveBeenCalledWith('1')
    expect(onRetried).toHaveBeenCalled()
  })

  it('shows an error and does not notify the parent when retry fails', async () => {
    vi.spyOn(documentsApi, 'retryDocument').mockRejectedValue(new Error('boom'))
    const onRetried = vi.fn()

    render(
      <DocumentList
        documents={[makeDocument({ id: '1', status: 'failed', error_category: 'system_error' })]}
        onDeleted={() => {}}
        onRetried={onRetried}
      />,
    )

    await userEvent.click(screen.getByRole('button', { name: /retry/i }))

    expect(await screen.findByText(/failed to retry/i)).toBeInTheDocument()
    expect(onRetried).not.toHaveBeenCalled()
  })

  it('falls back to a no-op when onRetried is omitted', async () => {
    vi.spyOn(documentsApi, 'retryDocument').mockResolvedValue(makeDocument({ status: 'queued' }))

    render(
      <DocumentList
        documents={[makeDocument({ id: '1', status: 'failed', error_category: 'system_error' })]}
        onDeleted={() => {}}
      />,
    )

    // No onRetried was passed — clicking must not throw, falling back to the
    // default no-op.
    await userEvent.click(screen.getByRole('button', { name: /retry/i }))
  })
})
