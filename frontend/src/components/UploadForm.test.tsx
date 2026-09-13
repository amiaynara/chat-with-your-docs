import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import * as documentsApi from '../api/documents'
import { UploadForm } from './UploadForm'

describe('UploadForm', () => {
  beforeEach(() => {
    vi.restoreAllMocks()
  })

  it('uploads the selected file and notifies the caller', async () => {
    const uploadSpy = vi.spyOn(documentsApi, 'uploadDocument').mockResolvedValue({
      id: '1',
      filename: 'notes.txt',
      format: 'txt',
      status: 'queued',
      error_reason: null,
      created_at: new Date().toISOString(),
    })
    const onUploaded = vi.fn()

    render(<UploadForm onUploaded={onUploaded} />)

    const file = new File(['hello world'], 'notes.txt', { type: 'text/plain' })
    const input = screen.getByLabelText(/upload document/i, { selector: 'input' })
    await userEvent.upload(input, file)

    await waitFor(() => expect(onUploaded).toHaveBeenCalled())
    expect(uploadSpy).toHaveBeenCalledWith(file)
  })

  it('shows an error message when the upload is rejected', async () => {
    vi.spyOn(documentsApi, 'uploadDocument').mockRejectedValue(
      new documentsApi.UploadError('File exceeds the 20MB size limit'),
    )

    render(<UploadForm onUploaded={vi.fn()} />)

    const file = new File(['bad'], 'huge.txt', { type: 'text/plain' })
    const input = screen.getByLabelText(/upload document/i, { selector: 'input' })
    await userEvent.upload(input, file)

    expect(await screen.findByText(/exceeds the 20mb size limit/i)).toBeInTheDocument()
  })

  it('shows a generic error message for a non-UploadError failure', async () => {
    vi.spyOn(documentsApi, 'uploadDocument').mockRejectedValue(new Error('network exploded'))

    render(<UploadForm onUploaded={vi.fn()} />)

    const file = new File(['bad'], 'huge.txt', { type: 'text/plain' })
    const input = screen.getByLabelText(/upload document/i, { selector: 'input' })
    await userEvent.upload(input, file)

    expect(await screen.findByText(/upload failed\. please try again/i)).toBeInTheDocument()
  })

  it('does nothing when the file dialog is cancelled', async () => {
    const uploadSpy = vi.spyOn(documentsApi, 'uploadDocument')

    render(<UploadForm onUploaded={vi.fn()} />)

    const input = screen.getByLabelText(/upload document/i, { selector: 'input' })
    fireEvent.change(input, { target: { files: [] } })

    expect(uploadSpy).not.toHaveBeenCalled()
  })
})
