import { useRef, useState } from 'react'
import { UploadError, uploadDocument } from '../api/documents'

interface UploadFormProps {
  onUploaded: () => void
}

export function UploadForm({ onUploaded }: UploadFormProps) {
  const [error, setError] = useState<string | null>(null)
  const [isUploading, setIsUploading] = useState(false)
  const inputRef = useRef<HTMLInputElement>(null)

  async function handleChange(event: React.ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0]
    if (!file) return

    setError(null)
    setIsUploading(true)
    try {
      await uploadDocument(file)
      onUploaded()
    } catch (err) {
      setError(err instanceof UploadError ? err.message : 'Upload failed. Please try again.')
    } finally {
      setIsUploading(false)
      // Guaranteed mounted: this is the ref of the very input whose onChange
      // just fired.
      inputRef.current!.value = ''
    }
  }

  return (
    <div className="flex flex-col gap-2">
      <label className="flex w-fit cursor-pointer items-center gap-2 rounded-md bg-neutral-900 px-4 py-2 text-sm text-white hover:bg-neutral-700">
        {isUploading ? 'Uploading…' : 'Upload document'}
        <input
          ref={inputRef}
          type="file"
          accept=".pdf,.txt,.md"
          className="hidden"
          disabled={isUploading}
          onChange={handleChange}
        />
      </label>
      {error && <p className="text-sm text-red-600">{error}</p>}
    </div>
  )
}
