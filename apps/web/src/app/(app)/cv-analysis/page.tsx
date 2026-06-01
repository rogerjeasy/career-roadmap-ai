"use client";

import { useCvUpload } from "@/hooks/use-cv-upload";
import { formatRelative } from "@/lib/date";
import { PageHeader } from "@/components/shared/page-header";
import { CvUploadDropzone } from "@/components/cv-analysis/cv-upload-dropzone";
import { CvResults } from "@/components/cv-analysis/cv-results";

export default function CvAnalysisPage() {
  const { analysis, fileName, analysedAt, isUploading, error, upload, reset } = useCvUpload();

  return (
    <div className="mx-auto max-w-[1000px] px-7 pb-24 pt-7">
      <PageHeader
        eyebrow="Your profile"
        title="CV & Profile"
        description="Upload your CV to see the skills, experience, and signals our agents extract — the foundation for your roadmap."
        actions={
          analysis ? (
            <button
              type="button"
              onClick={reset}
              className="inline-flex items-center rounded-[7px] border border-rule-strong bg-paper px-3.5 py-2 text-[13px] font-medium text-ink-2 transition-colors duration-150 hover:bg-bg-2"
            >
              Upload a new CV
            </button>
          ) : undefined
        }
      />

      {!analysis || isUploading ? (
        <div className="mx-auto max-w-[640px]">
          <CvUploadDropzone isUploading={isUploading} onFile={upload} />
          {error && (
            <p className="mt-3 text-center text-[12.5px] text-terra-2" role="alert">
              {error}
            </p>
          )}
        </div>
      ) : (
        <>
          {(fileName || analysedAt) && (
            <p className="mb-5 text-[12.5px] text-ink-3">
              {fileName && <span className="font-medium text-ink-2">{fileName}</span>}
              {fileName && analysedAt && " · "}
              {analysedAt && `analysed ${formatRelative(analysedAt)}`}
            </p>
          )}
          <CvResults analysis={analysis} />
        </>
      )}
    </div>
  );
}
