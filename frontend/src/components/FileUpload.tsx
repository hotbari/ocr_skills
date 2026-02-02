import { useCallback, useState } from 'react'
import { Upload, File, X, Loader2 } from 'lucide-react'
import clsx from 'clsx'

interface FileUploadProps {
  onUpload: (file: File) => Promise<void>
  isUploading: boolean
}

export default function FileUpload({ onUpload, isUploading }: FileUploadProps) {
  const [dragActive, setDragActive] = useState(false)
  const [selectedFile, setSelectedFile] = useState<File | null>(null)

  const handleDrag = useCallback((e: React.DragEvent) => {
    e.preventDefault()
    e.stopPropagation()
    if (e.type === 'dragenter' || e.type === 'dragover') {
      setDragActive(true)
    } else if (e.type === 'dragleave') {
      setDragActive(false)
    }
  }, [])

  const handleDrop = useCallback((e: React.DragEvent) => {
    e.preventDefault()
    e.stopPropagation()
    setDragActive(false)

    const files = e.dataTransfer.files
    if (files?.[0]?.type === 'application/pdf') {
      setSelectedFile(files[0])
    }
  }, [])

  const handleChange = useCallback((e: React.ChangeEvent<HTMLInputElement>) => {
    const files = e.target.files
    if (files?.[0]) {
      setSelectedFile(files[0])
    }
  }, [])

  const handleUpload = async () => {
    if (selectedFile) {
      await onUpload(selectedFile)
      setSelectedFile(null)
    }
  }

  const handleClear = () => {
    setSelectedFile(null)
  }

  return (
    <div className="w-full">
      <div
        className={clsx(
          'border-2 border-dashed rounded-lg p-8 text-center transition-all duration-300 bg-cp-card/30 backdrop-blur-sm',
          dragActive
            ? 'border-cp-neon-green bg-cp-neon-green/10 shadow-[0_0_20px_rgba(57,255,20,0.2)]'
            : 'border-cp-neon-purple/30 hover:border-cp-neon-purple hover:bg-cp-neon-purple/5',
          isUploading && 'opacity-50 pointer-events-none'
        )}
        onDragEnter={handleDrag}
        onDragLeave={handleDrag}
        onDragOver={handleDrag}
        onDrop={handleDrop}
      >
        {selectedFile ? (
          <div className="flex flex-col items-center gap-4">
            <File className="h-12 w-12 text-cp-neon-blue drop-shadow-[0_0_8px_rgba(0,243,255,0.5)]" />
            <div className="flex items-center gap-2">
              <span className="text-sm font-medium text-cp-text">
                {selectedFile.name}
              </span>
              <button
                onClick={handleClear}
                className="p-1 hover:bg-gray-100 rounded"
                disabled={isUploading}
              >
                <X className="h-4 w-4 text-gray-500" />
              </button>
            </div>
            <p className="text-sm text-gray-500">
              {(selectedFile.size / 1024 / 1024).toFixed(2)} MB
            </p>
            <button
              onClick={handleUpload}
              disabled={isUploading}
              className={clsx(
                'px-6 py-2 rounded-md text-cp-dark font-bold tracking-wide transition-all duration-300',
                isUploading
                  ? 'bg-cp-text-muted cursor-not-allowed'
                  : 'bg-cp-neon-green hover:bg-cp-neon-green/90 btn-glow'
              )}
            >
              {isUploading ? (
                <span className="flex items-center gap-2">
                  <Loader2 className="h-4 w-4 animate-spin" />
                  Uploading...
                </span>
              ) : (
                'Upload PDF'
              )}
            </button>
          </div>
        ) : (
          <label className="cursor-pointer group">
            <div className="flex flex-col items-center gap-4">
              <Upload className="h-12 w-12 text-cp-text-muted group-hover:text-cp-neon-green transition-colors duration-300" />
              <div>
                <span className="text-cp-neon-green font-medium group-hover:text-cp-neon-blue transition-colors duration-300">
                  Click to upload
                </span>{' '}
                <span className="text-cp-text-muted">or drag and drop</span>
              </div>
              <p className="text-sm text-cp-text-muted/70">PDF files only</p>
            </div>
            <input
              type="file"
              accept=".pdf,application/pdf"
              onChange={handleChange}
              className="hidden"
            />
          </label>
        )}
      </div>
    </div>
  )
}
