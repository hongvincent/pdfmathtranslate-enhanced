const PDF_SIGNATURE = "%PDF-";

const SUPPORTED_IMAGE_EXTENSIONS = new Set([
  ".bmp",
  ".gif",
  ".jpeg",
  ".jpg",
  ".png",
  ".tif",
  ".tiff",
  ".webp",
]);
const SUPPORTED_OFFICE_EXTENSIONS = new Set([
  ".csv",
  ".doc",
  ".docm",
  ".docx",
  ".odp",
  ".ods",
  ".odt",
  ".ppt",
  ".pptm",
  ".pptx",
  ".rtf",
  ".tsv",
  ".txt",
  ".xls",
  ".xlsm",
  ".xlsx",
]);
const SUPPORTED_IMAGE_TYPES = new Set([
  "image/bmp",
  "image/gif",
  "image/jpeg",
  "image/png",
  "image/tiff",
  "image/webp",
]);
const SUPPORTED_OFFICE_TYPES = new Set([
  "application/msword",
  "application/rtf",
  "application/vnd.ms-excel",
  "application/vnd.ms-excel.sheet.macroenabled.12",
  "application/vnd.ms-powerpoint",
  "application/vnd.ms-powerpoint.presentation.macroenabled.12",
  "application/vnd.openxmlformats-officedocument.presentationml.presentation",
  "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
  "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
  "application/vnd.oasis.opendocument.presentation",
  "application/vnd.oasis.opendocument.spreadsheet",
  "application/vnd.oasis.opendocument.text",
  "text/csv",
  "text/plain",
  "text/rtf",
  "text/tab-separated-values",
]);

type UploadValidationCode = "invalid_pdf" | "unsupported";

export type UploadValidationError = {
  code: UploadValidationCode;
  file: File;
};

export const SUPPORTED_UPLOAD_ACCEPT = [
  ".pdf",
  ".doc",
  ".docx",
  ".docm",
  ".ppt",
  ".pptx",
  ".pptm",
  ".xls",
  ".xlsx",
  ".xlsm",
  ".odt",
  ".ods",
  ".odp",
  ".rtf",
  ".txt",
  ".csv",
  ".tsv",
  ".png",
  ".jpg",
  ".jpeg",
  ".bmp",
  ".gif",
  ".tif",
  ".tiff",
  ".webp",
].join(",");

function pluralize(count: number, singular: string, plural: string): string {
  return count === 1 ? singular : plural;
}

function normalizeMime(type: string): string {
  return type.split(";", 1)[0]?.trim().toLowerCase() ?? "";
}

function lowerSuffix(name: string): string {
  const lastDot = name.lastIndexOf(".");
  return lastDot >= 0 ? name.slice(lastDot).toLowerCase() : "";
}

async function hasPdfSignature(file: File): Promise<boolean> {
  try {
    const signature = await file.slice(0, PDF_SIGNATURE.length).text();
    return signature === PDF_SIGNATURE;
  } catch {
    return false;
  }
}

function isConvertibleUpload(file: File): boolean {
  const suffix = lowerSuffix(file.name);
  const mime = normalizeMime(file.type);
  return (
    SUPPORTED_IMAGE_EXTENSIONS.has(suffix) ||
    SUPPORTED_OFFICE_EXTENSIONS.has(suffix) ||
    SUPPORTED_IMAGE_TYPES.has(mime) ||
    SUPPORTED_OFFICE_TYPES.has(mime)
  );
}

export async function validateUploadFile(
  file: File,
): Promise<UploadValidationError | null> {
  if (await hasPdfSignature(file)) {
    return null;
  }

  const suffix = lowerSuffix(file.name);
  const mime = normalizeMime(file.type);
  if (suffix === ".pdf" || mime === "application/pdf") {
    return { code: "invalid_pdf", file };
  }

  return isConvertibleUpload(file) ? null : { code: "unsupported", file };
}

export async function validateUploadFiles(
  files: File[],
): Promise<UploadValidationError[]> {
  const results = await Promise.all(files.map((file) => validateUploadFile(file)));
  return results.filter((result): result is UploadValidationError => result !== null);
}

export function formatUploadValidationMessage(
  errors: UploadValidationError[],
): string {
  const invalidPdfFiles = errors
    .filter((error) => error.code === "invalid_pdf")
    .map((error) => error.file.name);
  const unsupportedFiles = errors
    .filter((error) => error.code === "unsupported")
    .map((error) => error.file.name);

  const messages: string[] = [];

  if (invalidPdfFiles.length > 0) {
    messages.push(
      `${invalidPdfFiles.join(", ")} ${pluralize(invalidPdfFiles.length, "is", "are")} not a valid PDF ${pluralize(invalidPdfFiles.length, "file", "files")}. Re-export ${pluralize(invalidPdfFiles.length, "it", "them")} as PDF or upload a supported source format for automatic conversion.`,
    );
  }

  if (unsupportedFiles.length > 0) {
    messages.push(
      `${unsupportedFiles.join(", ")} ${pluralize(unsupportedFiles.length, "is", "are")} not supported for automatic conversion. Upload PDF, Office documents, text files, or common images instead.`,
    );
  }

  return messages.join(" ");
}
