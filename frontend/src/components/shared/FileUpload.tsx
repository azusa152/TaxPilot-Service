"use client";

import { useRef, useState } from "react";
import { useTranslations } from "next-intl";
import { ACCEPTED_MIME_TYPES, SUPPORTED_FILE_TYPES } from "@/lib/api-client";
import { Upload } from "lucide-react";

const MAX_FILE_SIZE = 10 * 1024 * 1024; // 10 MB

interface FileUploadProps {
  onFileSelected: (file: File) => void;
  onValidationError: (message: string) => void;
  disabled?: boolean;
}

export function FileUpload({
  onFileSelected,
  onValidationError,
  disabled,
}: FileUploadProps) {
  const t = useTranslations("upload");
  const tError = useTranslations("upload.error");
  const inputRef = useRef<HTMLInputElement>(null);
  const [dragOver, setDragOver] = useState(false);

  function validateAndSelect(file: File) {
    if (file.size > MAX_FILE_SIZE) {
      onValidationError(tError("tooLarge"));
      return;
    }
    const ext = file.name.substring(file.name.lastIndexOf(".")).toLowerCase();
    if (
      !SUPPORTED_FILE_TYPES.includes(
        ext as (typeof SUPPORTED_FILE_TYPES)[number],
      )
    ) {
      onValidationError(tError("unsupportedType"));
      return;
    }
    onFileSelected(file);
  }

  function handleDragEnter(e: React.DragEvent) {
    e.preventDefault();
    if (!disabled) setDragOver(true);
  }

  function handleDragOver(e: React.DragEvent) {
    e.preventDefault();
    if (!disabled) setDragOver(true);
  }

  function handleDragLeave(e: React.DragEvent) {
    e.preventDefault();
    setDragOver(false);
  }

  function handleDrop(e: React.DragEvent) {
    e.preventDefault();
    setDragOver(false);
    if (disabled) return;
    const file = e.dataTransfer.files[0];
    if (file) validateAndSelect(file);
  }

  function handleInputChange(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    if (file) validateAndSelect(file);
    // Reset input so re-selecting the same file triggers onChange
    if (inputRef.current) inputRef.current.value = "";
  }

  return (
    <div>
      <div
        onDragEnter={handleDragEnter}
        onDragOver={handleDragOver}
        onDragLeave={handleDragLeave}
        onDrop={handleDrop}
        onClick={() => !disabled && inputRef.current?.click()}
        className={`flex cursor-pointer flex-col items-center justify-center rounded-lg border-2 border-dashed p-8 transition-colors ${
          dragOver
            ? "border-primary bg-primary/5"
            : "border-border hover:border-primary/50"
        } ${disabled ? "cursor-not-allowed opacity-50" : ""}`}
        role="button"
        tabIndex={0}
        onKeyDown={(e) => {
          if ((e.key === "Enter" || e.key === " ") && !disabled) {
            inputRef.current?.click();
          }
        }}
        aria-label={t("instruction")}
      >
        <Upload className="mb-3 h-8 w-8 text-muted-foreground" />
        <p className="text-sm text-foreground">{t("instruction")}</p>
        <p className="mt-1 text-xs text-muted-foreground">
          {t("supportedFormats")}
        </p>
        <button
          type="button"
          disabled={disabled}
          className="mt-4 rounded-md bg-primary px-4 py-2 text-sm font-medium text-primary-foreground transition-colors hover:bg-primary/90 disabled:opacity-50"
          onClick={(e) => {
            e.stopPropagation();
            inputRef.current?.click();
          }}
        >
          {t("browse")}
        </button>
      </div>

      <input
        ref={inputRef}
        type="file"
        accept={ACCEPTED_MIME_TYPES}
        onChange={handleInputChange}
        className="hidden"
        aria-hidden
      />
    </div>
  );
}
