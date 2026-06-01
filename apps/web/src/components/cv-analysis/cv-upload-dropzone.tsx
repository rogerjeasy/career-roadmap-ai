"use client";

import { toast } from "sonner";
import { FileUpload } from "@/components/shared/file-upload";
import { LoadingSpinner } from "@/components/shared/loading-spinner";

export interface CvUploadDropzoneProps {
  isUploading: boolean;
  onFile: (file: File) => void;
}

export function CvUploadDropzone({ isUploading, onFile }: CvUploadDropzoneProps) {
  if (isUploading) {
    return (
      <div className="flex flex-col items-center justify-center gap-4 rounded-[12px] border-2 border-dashed border-green bg-green-faint px-6 py-14">
        <LoadingSpinner size="lg" />
        <div className="text-center">
          <p className="text-[14px] font-medium text-ink">Analysing your CV…</p>
          <p className="mt-1 text-[12.5px] text-ink-3">
            Extracting roles, skills, and experience. This takes a few seconds.
          </p>
        </div>
      </div>
    );
  }

  return (
    <FileUpload
      accept=".pdf,.doc,.docx"
      maxSizeMb={10}
      hint="PDF or Word · up to 10 MB"
      onFileSelected={onFile}
      onError={(msg) => toast.error(msg)}
    />
  );
}
