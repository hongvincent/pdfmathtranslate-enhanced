const DOCX_CONTENT_TYPE =
  "application/vnd.openxmlformats-officedocument.wordprocessingml.document";
const PDF_SIGNATURE = "%PDF-";

type UploadValidationCode = "docx" | "non_pdf";

export type UploadValidationError = {
  code: UploadValidationCode;
  file: File;
};

function pluralize(count: number, singular: string, plural: string): string {
  return count === 1 ? singular : plural;
}

function isDocxFile(file: File): boolean {
  const lowerName = file.name.toLowerCase();
  return lowerName.endsWith(".docx") || file.type === DOCX_CONTENT_TYPE;
}

async function hasPdfSignature(file: File): Promise<boolean> {
  try {
    const signature = await file.slice(0, PDF_SIGNATURE.length).text();
    return signature === PDF_SIGNATURE;
  } catch {
    return false;
  }
}

export async function validateUploadFile(
  file: File,
): Promise<UploadValidationError | null> {
  if (isDocxFile(file)) {
    return { code: "docx", file };
  }

  return (await hasPdfSignature(file)) ? null : { code: "non_pdf", file };
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
  const docxFiles = errors
    .filter((error) => error.code === "docx")
    .map((error) => error.file.name);
  const nonPdfFiles = errors
    .filter((error) => error.code === "non_pdf")
    .map((error) => error.file.name);

  const messages: string[] = [];

  if (docxFiles.length > 0) {
    messages.push(
      `${docxFiles.join(", ")} ${pluralize(docxFiles.length, "is", "are")} a DOCX ${pluralize(docxFiles.length, "file", "files")}. Convert ${pluralize(docxFiles.length, "it", "them")} to PDF before queueing.`,
    );
  }

  if (nonPdfFiles.length > 0) {
    messages.push(
      `${nonPdfFiles.join(", ")} ${pluralize(nonPdfFiles.length, "is", "are")} not a valid PDF ${pluralize(nonPdfFiles.length, "file", "files")}. Only PDF files can be queued right now.`,
    );
  }

  return messages.join(" ");
}
