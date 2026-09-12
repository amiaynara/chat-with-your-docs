import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
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
  it('shows an empty state when there are no documents', () => {
    render(<DocumentList documents={[]} />)

    expect(screen.getByText(/no documents yet/i)).toBeInTheDocument()
  })

  it('renders each document with its filename and status', () => {
    render(
      <DocumentList
        documents={[
          makeDocument({ id: '1', filename: 'a.txt', status: 'ready' }),
          makeDocument({ id: '2', filename: 'b.pdf', status: 'processing' }),
        ]}
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
      />,
    )

    expect(screen.getByText(/could not read pdf/i)).toBeInTheDocument()
  })
})
