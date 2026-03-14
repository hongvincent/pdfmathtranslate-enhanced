import { useEffect, useState } from "react";
import type { DragEvent, FormEvent } from "react";
import { formatBytes } from "../lib/format";
import {
  formatUploadValidationMessage,
  SUPPORTED_UPLOAD_ACCEPT,
  validateUploadFiles,
} from "../lib/fileValidation";
import type {
  NewJobInput,
  OutputMode,
  ProviderProfile,
  SystemHealth,
} from "../types";

const outputModes: Array<{ id: OutputMode; label: string; helper: string }> = [
  { id: "dual", label: "Dual PDF", helper: "Original and translated pages paired." },
  { id: "mono", label: "Mono PDF", helper: "Translated output only." },
  { id: "both", label: "Both", helper: "Keep both mono and dual artifacts." },
];

export function NewJobForm(props: {
  profiles: ProviderProfile[];
  health: SystemHealth | null;
  loading: boolean;
  onSubmit: (input: NewJobInput) => Promise<void>;
}) {
  const { profiles, health, loading, onSubmit } = props;
  const defaultProfile =
    profiles.find((profile) => profile.id === health?.defaultProfileId) ??
    profiles.find((profile) => profile.isDefault) ??
    profiles[0];
  const lastJobOptions = health?.lastJobOptions ?? {};

  const [files, setFiles] = useState<File[]>([]);
  const [profileId, setProfileId] = useState<string>(defaultProfile?.id ?? "");
  const [sourceLang, setSourceLang] = useState<string>(
    typeof lastJobOptions.lang_in === "string" ? lastJobOptions.lang_in : "en",
  );
  const [targetLang, setTargetLang] = useState<string>(
    typeof lastJobOptions.lang_out === "string" ? lastJobOptions.lang_out : "ko",
  );
  const [outputMode, setOutputMode] = useState<OutputMode>(
    lastJobOptions.no_dual
      ? "mono"
      : lastJobOptions.no_mono
        ? "dual"
        : "both",
  );
  const [pages, setPages] = useState(
    typeof lastJobOptions.pages === "string" ? lastJobOptions.pages : "",
  );
  const [qps, setQps] = useState(
    typeof lastJobOptions.qps === "number" ? String(lastJobOptions.qps) : "",
  );
  const [saveGlossary, setSaveGlossary] = useState(
    Boolean(
      lastJobOptions.save_auto_extracted_glossary &&
        !lastJobOptions.no_auto_extract_glossary,
    ),
  );
  const [dragging, setDragging] = useState(false);
  const [selectionError, setSelectionError] = useState<string | null>(null);

  useEffect(() => {
    if (!defaultProfile || profileId) {
      return;
    }

    setProfileId(defaultProfile.id);
  }, [defaultProfile, profileId]);

  async function mergeFiles(nextFiles: FileList | File[]) {
    const candidates = Array.from(nextFiles);
    const rejected = await validateUploadFiles(candidates);
    const rejectedFiles = new Set(rejected.map((error) => error.file));
    const accepted = candidates.filter((file) => !rejectedFiles.has(file));

    setSelectionError(
      rejected.length > 0 ? formatUploadValidationMessage(rejected) : null,
    );

    if (accepted.length === 0) {
      return;
    }

    setFiles((current) => {
      const merged = new Map<string, File>();
      [...current, ...accepted].forEach((file) => {
        merged.set(`${file.name}:${file.size}:${file.lastModified}`, file);
      });
      return Array.from(merged.values());
    });
  }

  function handleDrop(event: DragEvent<HTMLLabelElement>) {
    event.preventDefault();
    setDragging(false);
    if (event.dataTransfer.files.length > 0) {
      void mergeFiles(event.dataTransfer.files);
    }
  }

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (files.length === 0) {
      return;
    }

    await onSubmit({
      files,
      profileId: profileId || undefined,
      sourceLang,
      targetLang,
      outputMode,
      pages: pages || undefined,
      qps: qps.trim().length > 0 ? Number(qps) : undefined,
      saveGlossary,
    });

    setFiles([]);
    setPages("");
    setQps("");
    setSaveGlossary(false);
    setSelectionError(null);
  }

  const selectedProfile = profiles.find((profile) => profile.id === profileId);
  const totalSize = files.reduce((sum, file) => sum + file.size, 0);

  return (
    <div className="panel-grid panel-grid--two">
      <section className="panel">
        <div className="section-heading">
          <div>
            <span className="eyebrow">New Job</span>
            <h2>Queue one or many source files</h2>
          </div>
          <div className="section-heading__meta">Multipart upload</div>
        </div>

        <form className="stack-form" onSubmit={handleSubmit}>
          <label
            className={`dropzone ${dragging ? "dropzone--active" : ""}`}
            onDragEnter={() => setDragging(true)}
            onDragLeave={() => setDragging(false)}
            onDragOver={(event) => event.preventDefault()}
            onDrop={handleDrop}
          >
            <input
              type="file"
              accept={SUPPORTED_UPLOAD_ACCEPT}
              multiple
              onChange={(event) => {
                if (event.target.files) {
                  void mergeFiles(event.target.files);
                }
              }}
            />
            <strong>Drop PDFs, Office docs, text files, or images here</strong>
            <span>
              Non-PDF uploads are converted to PDF automatically before they enter
              the translation queue.
            </span>
          </label>

          {selectionError ? <p className="inline-error">{selectionError}</p> : null}

          <div className="file-list">
            {files.length === 0 ? (
              <p className="subtle-copy">No source files selected yet.</p>
            ) : (
              files.map((file) => (
                <div key={`${file.name}:${file.lastModified}`} className="file-chip">
                  <span>{file.name}</span>
                  <small>{formatBytes(file.size)}</small>
                  <button
                    type="button"
                    onClick={() =>
                      setFiles((current) =>
                        current.filter(
                          (candidate) =>
                            `${candidate.name}:${candidate.lastModified}` !==
                            `${file.name}:${file.lastModified}`,
                        ),
                      )
                    }
                  >
                    Remove
                  </button>
                </div>
              ))
            )}
          </div>

          <div className="form-grid">
            <label>
              <span>Provider profile</span>
              <select
                value={profileId}
                onChange={(event) => {
                  setProfileId(event.target.value);
                }}
              >
                {profiles.map((profile) => (
                  <option key={profile.id} value={profile.id}>
                    {profile.name} · {profile.provider}
                  </option>
                ))}
              </select>
            </label>

            <label>
              <span>Source language</span>
              <input
                value={sourceLang}
                onChange={(event) => setSourceLang(event.target.value)}
                placeholder="auto"
              />
            </label>

            <label>
              <span>Target language</span>
              <input
                value={targetLang}
                onChange={(event) => setTargetLang(event.target.value)}
                placeholder="en"
              />
            </label>

            <label>
              <span>Pages</span>
              <input
                value={pages}
                onChange={(event) => setPages(event.target.value)}
                placeholder="1-5,9,12-"
              />
            </label>

            <label>
              <span>QPS override</span>
              <input
                inputMode="numeric"
                value={qps}
                onChange={(event) => setQps(event.target.value)}
                placeholder={
                  typeof lastJobOptions.qps === "number"
                    ? String(lastJobOptions.qps)
                    : "optional"
                }
              />
            </label>

          </div>

          <div className="mode-grid">
            {outputModes.map((mode) => (
              <button
                key={mode.id}
                type="button"
                className={`mode-card ${outputMode === mode.id ? "mode-card--active" : ""}`}
                onClick={() => setOutputMode(mode.id)}
              >
                <strong>{mode.label}</strong>
                <small>{mode.helper}</small>
              </button>
            ))}
          </div>

          <label className="checkbox-row">
            <input
              type="checkbox"
              checked={saveGlossary}
              onChange={(event) => setSaveGlossary(event.target.checked)}
            />
            <span>Request glossary extraction artifact when the backend supports it.</span>
          </label>

          <div className="form-footer">
            <div>
              <span className="eyebrow">Batch summary</span>
              <strong>
                {files.length} files · {formatBytes(totalSize)}
              </strong>
            </div>
            <button type="submit" className="primary-button" disabled={loading || files.length === 0}>
              {loading ? "Queueing..." : "Queue translation job"}
            </button>
          </div>
        </form>
      </section>

      <section className="panel panel--accent">
        <div className="section-heading">
          <div>
            <span className="eyebrow">Current Preset</span>
            <h2>{selectedProfile?.name ?? "Manual submission"}</h2>
          </div>
        </div>

        <div className="profile-glance">
          <div>
            <span className="eyebrow">Provider</span>
            <strong>{selectedProfile?.provider ?? "Select a profile"}</strong>
          </div>
          <div>
            <span className="eyebrow">Model</span>
            <strong>{selectedProfile?.model ?? selectedProfile?.modelId ?? "Backend default"}</strong>
          </div>
          <div>
            <span className="eyebrow">Languages</span>
            <strong>
              {sourceLang || "en"} to {targetLang || "ko"}
            </strong>
          </div>
          <div>
            <span className="eyebrow">Auth</span>
            <strong>{selectedProfile?.providerType === "bedrock" ? selectedProfile.authMode ?? "mounted profile" : "API key"}</strong>
          </div>
        </div>

        <p className="subtle-copy">
          The backend remembers your last-used profile and job options, so this
          form restores them after restart without touching provider secrets.
        </p>
      </section>
    </div>
  );
}
