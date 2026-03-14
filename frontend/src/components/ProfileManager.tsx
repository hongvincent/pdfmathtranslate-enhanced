import { useState } from "react";
import type { FormEvent } from "react";
import type { ProfileDraft, ProviderProfile } from "../types";
import { StatusPill } from "./StatusPill";

type JsonRecord = Record<string, unknown>;

function isRecord(value: unknown): value is JsonRecord {
  return Boolean(value) && typeof value === "object" && !Array.isArray(value);
}

function getValidatedModelOptions(
  profiles: ProviderProfile[],
  providerType: ProfileDraft["providerType"],
  fallback: string[],
): string[] {
  const options = new Set<string>();
  profiles
    .filter((profile) => profile.providerType === providerType)
    .flatMap((profile) => profile.validatedModels)
    .forEach((model) => options.add(model));

  if (options.size === 0) {
    fallback.forEach((model) => options.add(model));
  }

  return [...options].sort((left, right) => left.localeCompare(right));
}

const emptyDraft: ProfileDraft = {
  name: "",
  providerType: "openai",
  model: "gpt-5.4",
  snapshotModel: "gpt-5.4-2026-03-05",
  reasoningEffort: "medium",
  authMode: "mounted_aws_profile",
  region: "us-east-1",
  modelId: "amazon.nova-lite-v1:0",
};

export function ProfileManager(props: {
  profiles: ProviderProfile[];
  saving: boolean;
  validatingProfileId: string | null;
  deletingProfileId: string | null;
  onSave: (draft: ProfileDraft) => Promise<void>;
  onValidate: (profileId: string) => Promise<void>;
  onDelete: (profileId: string) => Promise<void>;
}) {
  const {
    profiles,
    saving,
    validatingProfileId,
    deletingProfileId,
    onSave,
    onValidate,
    onDelete,
  } = props;
  const [draft, setDraft] = useState<ProfileDraft>(emptyDraft);
  const [jsonText, setJsonText] = useState("");
  const [jsonError, setJsonError] = useState<string | null>(null);

  const openAiModelOptions = getValidatedModelOptions(profiles, "openai", [
    "gpt-5.4",
    "gpt-5.4-2026-03-05",
  ]);
  const bedrockModelOptions = getValidatedModelOptions(profiles, "bedrock", [
    "amazon.nova-lite-v1:0",
  ]);

  const openAiHasValidatedModels = profiles.some(
    (profile) => profile.providerType === "openai" && profile.validatedModels.length > 0,
  );
  const bedrockHasValidatedModels = profiles.some(
    (profile) => profile.providerType === "bedrock" && profile.validatedModels.length > 0,
  );

  function serializeDraftJson(source: ProfileDraft): string {
    const json: JsonRecord = {
      name: source.name,
      providerType: source.providerType,
      isDefault: Boolean(source.isDefault),
    };

    if (source.providerType === "bedrock") {
      json.region = source.region;
      json.modelId = source.modelId;
      json.authMode = source.authMode;
      json.profileName = source.profileName;
      json.timeoutSeconds = source.timeoutSeconds;
      json.temperature = source.temperature;
    } else {
      json.model = source.model;
      json.snapshotModel = source.snapshotModel;
      json.useSnapshot = Boolean(source.useSnapshot);
      json.baseUrl = source.baseUrl;
      json.reasoningEffort = source.reasoningEffort;
      json.timeoutSeconds = source.timeoutSeconds;
      json.temperature = source.temperature;
    }

    return JSON.stringify(json, null, 2);
  }

  function applyDraftJson(nextJsonText: string) {
    let parsed: unknown;
    try {
      parsed = JSON.parse(nextJsonText);
    } catch (error) {
      setJsonError(error instanceof Error ? error.message : "Invalid JSON.");
      return;
    }

    if (!isRecord(parsed)) {
      setJsonError("JSON must be an object.");
      return;
    }

    let nextDraft: ProfileDraft = { ...draft };

    if ("providerType" in parsed) {
      const providerType = parsed.providerType;
      if (providerType === "openai" || providerType === "bedrock") {
        if (providerType !== nextDraft.providerType) {
          nextDraft = {
            ...emptyDraft,
            ...nextDraft,
            providerType,
          };
        }
      } else if (providerType !== undefined && providerType !== null) {
        setJsonError("providerType must be either \"openai\" or \"bedrock\".");
        return;
      }
    }

    if ("name" in parsed) {
      const value = parsed.name;
      nextDraft.name = typeof value === "string" ? value : "";
    }

    if ("isDefault" in parsed) {
      const value = parsed.isDefault;
      if (typeof value === "boolean") {
        nextDraft.isDefault = value;
      } else if (value === null) {
        nextDraft.isDefault = undefined;
      }
    }

    if (nextDraft.providerType === "bedrock") {
      if ("region" in parsed) {
        const value = parsed.region;
        nextDraft.region = typeof value === "string" && value.trim() ? value : undefined;
      }

      if ("modelId" in parsed) {
        const value = parsed.modelId;
        nextDraft.modelId = typeof value === "string" && value.trim() ? value : undefined;
      }

      if ("authMode" in parsed) {
        const value = parsed.authMode;
        if (value === "mounted_aws_profile" || value === "stored_keys") {
          nextDraft.authMode = value;
        } else if (value === null) {
          nextDraft.authMode = undefined;
        }
      }

      if ("profileName" in parsed) {
        const value = parsed.profileName;
        nextDraft.profileName = typeof value === "string" && value.trim() ? value : undefined;
      }
    } else {
      if ("model" in parsed) {
        const value = parsed.model;
        nextDraft.model = typeof value === "string" && value.trim() ? value : undefined;
      }

      if ("snapshotModel" in parsed) {
        const value = parsed.snapshotModel;
        nextDraft.snapshotModel =
          typeof value === "string" && value.trim() ? value : undefined;
      }

      if ("useSnapshot" in parsed) {
        const value = parsed.useSnapshot;
        if (typeof value === "boolean") {
          nextDraft.useSnapshot = value;
        } else if (value === "true") {
          nextDraft.useSnapshot = true;
        } else if (value === "false") {
          nextDraft.useSnapshot = false;
        } else if (value === null) {
          nextDraft.useSnapshot = undefined;
        }
      }

      if ("baseUrl" in parsed) {
        const value = parsed.baseUrl;
        nextDraft.baseUrl = typeof value === "string" && value.trim() ? value : undefined;
      }

      if ("reasoningEffort" in parsed) {
        const value = parsed.reasoningEffort;
        nextDraft.reasoningEffort = typeof value === "string" && value.trim() ? value : undefined;
      }
    }

    if ("timeoutSeconds" in parsed) {
      const value = parsed.timeoutSeconds;
      if (typeof value === "number" && Number.isFinite(value)) {
        nextDraft.timeoutSeconds = value;
      } else if (typeof value === "string" && value.trim()) {
        const parsedNumber = Number(value);
        nextDraft.timeoutSeconds = Number.isFinite(parsedNumber) ? parsedNumber : undefined;
      } else {
        nextDraft.timeoutSeconds = undefined;
      }
    }

    if ("temperature" in parsed) {
      const value = parsed.temperature;
      if (typeof value === "number" && Number.isFinite(value)) {
        nextDraft.temperature = value;
      } else if (typeof value === "string" && value.trim()) {
        const parsedNumber = Number(value);
        nextDraft.temperature = Number.isFinite(parsedNumber) ? parsedNumber : undefined;
      } else {
        nextDraft.temperature = undefined;
      }
    }

    setDraft(nextDraft);
    setJsonError(null);
    setJsonText(serializeDraftJson(nextDraft));
  }

  function editProfile(profile: ProviderProfile) {
    setDraft({
      id: profile.id,
      name: profile.name,
      providerType: profile.providerType,
      isDefault: profile.isDefault,
      model: profile.model,
      snapshotModel: profile.snapshotModel,
      useSnapshot: profile.useSnapshot,
      baseUrl: profile.baseUrl,
      reasoningEffort: profile.reasoningEffort,
      timeoutSeconds: profile.timeoutSeconds,
      temperature: profile.temperature,
      region: profile.region,
      modelId: profile.modelId,
      authMode: profile.authMode,
      profileName: profile.profileName,
    });
  }

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    await onSave(draft);
    setDraft(emptyDraft);
    setJsonError(null);
  }

  const isBedrock = draft.providerType === "bedrock";
  const MODEL_CUSTOM = "__custom__";

  const openAiModelSelectValue =
    draft.model && openAiModelOptions.includes(draft.model) ? draft.model : MODEL_CUSTOM;
  const openAiSnapshotSelectValue =
    draft.snapshotModel && openAiModelOptions.includes(draft.snapshotModel)
      ? draft.snapshotModel
      : MODEL_CUSTOM;
  const bedrockModelSelectValue =
    draft.modelId && bedrockModelOptions.includes(draft.modelId) ? draft.modelId : MODEL_CUSTOM;

  return (
    <div className="panel-grid panel-grid--two">
      <section className="panel">
        <div className="section-heading">
          <div>
            <span className="eyebrow">Provider Profiles</span>
            <h2>{draft.id ? "Edit preset" : "Create preset"}</h2>
          </div>
          {draft.id ? (
            <button type="button" className="ghost-button" onClick={() => setDraft(emptyDraft)}>
              Reset form
            </button>
          ) : null}
        </div>

        <form className="stack-form" onSubmit={handleSubmit}>
          <div className="form-grid">
            <label>
              <span>Name</span>
              <input
                required
                value={draft.name}
                onChange={(event) => setDraft({ ...draft, name: event.target.value })}
                placeholder="Primary OpenAI"
              />
            </label>

            <label>
              <span>Provider</span>
              <select
                value={draft.providerType}
                onChange={(event) =>
                  setDraft({
                    ...emptyDraft,
                    ...draft,
                    providerType: event.target.value as ProfileDraft["providerType"],
                  })
                }
              >
                <option value="openai">OpenAI</option>
                <option value="bedrock">Amazon Bedrock</option>
              </select>
            </label>

            {isBedrock ? (
              <>
                <label>
                  <span>Region</span>
                  <input
                    value={draft.region ?? ""}
                    onChange={(event) => setDraft({ ...draft, region: event.target.value })}
                    placeholder="us-east-1"
                  />
                </label>

                <label>
                  <span>Model</span>
                  <select
                    value={bedrockModelSelectValue}
                    onChange={(event) => {
                      const value = event.target.value;
                      if (value === MODEL_CUSTOM) {
                        setDraft({ ...draft, modelId: draft.modelId ?? "" });
                        return;
                      }
                      setDraft({ ...draft, modelId: value });
                    }}
                  >
                    {bedrockModelOptions.map((model) => (
                      <option key={model} value={model}>
                        {model}
                      </option>
                    ))}
                    <option value={MODEL_CUSTOM}>Custom...</option>
                  </select>
                  {bedrockModelSelectValue === MODEL_CUSTOM ? (
                    <input
                      value={draft.modelId ?? ""}
                      onChange={(event) => setDraft({ ...draft, modelId: event.target.value })}
                      placeholder="amazon.nova-lite-v1:0"
                    />
                  ) : null}
                  <small className="subtle-copy">
                    {bedrockHasValidatedModels
                      ? "Dropdown values come from the last successful validation (Bedrock ListFoundationModels)."
                      : "Validate a saved Bedrock profile to fetch an up-to-date model list."}
                  </small>
                </label>

                <label>
                  <span>Auth mode</span>
                  <select
                    value={draft.authMode ?? "mounted_aws_profile"}
                    onChange={(event) =>
                      setDraft({
                        ...draft,
                        authMode: event.target.value as ProfileDraft["authMode"],
                      })
                    }
                  >
                    <option value="mounted_aws_profile">Mounted AWS profile</option>
                    <option value="stored_keys">Stored access keys</option>
                  </select>
                </label>

                <label>
                  <span>AWS profile name</span>
                  <input
                    value={draft.profileName ?? ""}
                    onChange={(event) => setDraft({ ...draft, profileName: event.target.value })}
                    placeholder="default"
                  />
                </label>

                {draft.authMode === "stored_keys" ? (
                  <>
                    <label>
                      <span>Access key ID</span>
                      <input
                        value={draft.accessKeyId ?? ""}
                        onChange={(event) =>
                          setDraft({ ...draft, accessKeyId: event.target.value })
                        }
                        placeholder="AKIA..."
                      />
                    </label>

                    <label>
                      <span>Secret access key</span>
                      <input
                        type="password"
                        value={draft.secretAccessKey ?? ""}
                        onChange={(event) =>
                          setDraft({ ...draft, secretAccessKey: event.target.value })
                        }
                        placeholder="Only sent when you save"
                      />
                    </label>

                    <label>
                      <span>Session token</span>
                      <input
                        type="password"
                        value={draft.sessionToken ?? ""}
                        onChange={(event) =>
                          setDraft({ ...draft, sessionToken: event.target.value })
                        }
                        placeholder="Optional temporary token"
                      />
                    </label>
                  </>
                ) : null}
              </>
            ) : (
              <>
                <label>
                  <span>Model</span>
                  <select
                    value={openAiModelSelectValue}
                    onChange={(event) => {
                      const value = event.target.value;
                      if (value === MODEL_CUSTOM) {
                        setDraft({ ...draft, model: draft.model ?? "" });
                        return;
                      }
                      setDraft({ ...draft, model: value });
                    }}
                  >
                    {openAiModelOptions.map((model) => (
                      <option key={model} value={model}>
                        {model}
                      </option>
                    ))}
                    <option value={MODEL_CUSTOM}>Custom...</option>
                  </select>
                  {openAiModelSelectValue === MODEL_CUSTOM ? (
                    <input
                      value={draft.model ?? ""}
                      onChange={(event) => setDraft({ ...draft, model: event.target.value })}
                      placeholder="gpt-5.4"
                    />
                  ) : null}
                  <small className="subtle-copy">
                    {openAiHasValidatedModels
                      ? "Dropdown values come from the last successful validation (OpenAI models.list)."
                      : "Validate a saved OpenAI profile to fetch an up-to-date model list."}
                  </small>
                </label>

                <label>
                  <span>Snapshot model</span>
                  <select
                    value={openAiSnapshotSelectValue}
                    onChange={(event) => {
                      const value = event.target.value;
                      if (value === MODEL_CUSTOM) {
                        setDraft({ ...draft, snapshotModel: draft.snapshotModel ?? "" });
                        return;
                      }
                      setDraft({ ...draft, snapshotModel: value });
                    }}
                  >
                    {openAiModelOptions.map((model) => (
                      <option key={model} value={model}>
                        {model}
                      </option>
                    ))}
                    <option value={MODEL_CUSTOM}>Custom...</option>
                  </select>
                  {openAiSnapshotSelectValue === MODEL_CUSTOM ? (
                    <input
                      value={draft.snapshotModel ?? ""}
                      onChange={(event) =>
                        setDraft({ ...draft, snapshotModel: event.target.value })
                      }
                      placeholder="gpt-5.4-2026-03-05"
                    />
                  ) : null}
                </label>

                <label>
                  <span>Base URL</span>
                  <input
                    value={draft.baseUrl ?? ""}
                    onChange={(event) => setDraft({ ...draft, baseUrl: event.target.value })}
                    placeholder="https://api.openai.com/v1"
                  />
                </label>

                <label>
                  <span>Reasoning effort</span>
                  <select
                    value={draft.reasoningEffort ?? "medium"}
                    onChange={(event) =>
                      setDraft({ ...draft, reasoningEffort: event.target.value })
                    }
                  >
                    <option value="low">low</option>
                    <option value="medium">medium</option>
                    <option value="high">high</option>
                  </select>
                </label>

                <label>
                  <span>API key</span>
                  <input
                    type="password"
                    value={draft.apiKey ?? ""}
                    onChange={(event) => setDraft({ ...draft, apiKey: event.target.value })}
                    placeholder="Only sent when you save"
                  />
                </label>
              </>
            )}

            <label>
              <span>Timeout seconds</span>
              <input
                inputMode="numeric"
                value={draft.timeoutSeconds ?? ""}
                onChange={(event) =>
                  setDraft({
                    ...draft,
                    timeoutSeconds: event.target.value
                      ? Number(event.target.value)
                      : undefined,
                  })
                }
                placeholder="optional"
              />
            </label>

            <label>
              <span>Temperature</span>
              <input
                inputMode="decimal"
                value={draft.temperature ?? ""}
                onChange={(event) =>
                  setDraft({
                    ...draft,
                    temperature: event.target.value
                      ? Number(event.target.value)
                      : undefined,
                  })
                }
                placeholder="optional"
              />
            </label>

            <details
              className="json-settings form-grid__span"
              onToggle={(event) => {
                if (event.currentTarget.open) {
                  setJsonText(serializeDraftJson(draft));
                  setJsonError(null);
                }
              }}
            >
              <summary>Advanced: JSON settings</summary>
              <p className="subtle-copy">
                Edit profile settings as JSON (secrets are intentionally excluded). Use the dropdown
                above when possible, and Validate a saved profile to refresh the backend-provided
                model list.
              </p>
              <textarea
                className="json-textarea"
                spellCheck={false}
                value={jsonText}
                onChange={(event) => {
                  setJsonText(event.target.value);
                  setJsonError(null);
                }}
                placeholder={serializeDraftJson(draft)}
              />
              {jsonError ? <p className="inline-error">{jsonError}</p> : null}
              <div className="json-settings__actions">
                <button
                  type="button"
                  className="ghost-button"
                  onClick={() => {
                    setJsonText(serializeDraftJson(draft));
                    setJsonError(null);
                  }}
                >
                  Refresh from form
                </button>
                <button
                  type="button"
                  className="primary-button"
                  onClick={() => applyDraftJson(jsonText)}
                >
                  Apply JSON
                </button>
              </div>
            </details>
          </div>

          <label className="checkbox-row">
            <input
              type="checkbox"
              checked={Boolean(draft.useSnapshot)}
              disabled={isBedrock}
              onChange={(event) => setDraft({ ...draft, useSnapshot: event.target.checked })}
            />
            <span>Pin OpenAI jobs to the snapshot model for repeatable runs.</span>
          </label>

          <label className="checkbox-row">
            <input
              type="checkbox"
              checked={Boolean(draft.isDefault)}
              onChange={(event) => setDraft({ ...draft, isDefault: event.target.checked })}
            />
            <span>Use this profile as the default for new jobs.</span>
          </label>

          <div className="form-footer">
            <div>
              <span className="eyebrow">Persistence</span>
              <strong>Secrets are encrypted at rest and reused after restart.</strong>
            </div>
            <button type="submit" className="primary-button" disabled={saving}>
              {saving ? "Saving..." : draft.id ? "Save changes" : "Create profile"}
            </button>
          </div>
        </form>
      </section>

      <section className="panel">
        <div className="section-heading">
          <div>
            <span className="eyebrow">Saved Presets</span>
            <h2>Reusable providers</h2>
          </div>
          <div className="section-heading__meta">{profiles.length} configured</div>
        </div>

        {profiles.length === 0 ? (
          <div className="empty-state">
            <h3>No provider profiles</h3>
            <p>Create one here so New Job submissions can reuse model and auth settings.</p>
          </div>
        ) : (
          <div className="card-list">
            {profiles.map((profile) => (
              <article key={profile.id} className="profile-card">
                <div className="profile-card__header">
                  <div>
                    <span className="eyebrow">{profile.provider}</span>
                    <h3>{profile.name}</h3>
                  </div>
                  {profile.isDefault ? <StatusPill tone="success" /> : null}
                </div>

                <dl className="profile-card__meta">
                  <div>
                    <dt>Model</dt>
                    <dd>{profile.model ?? profile.modelId ?? "Backend default"}</dd>
                  </div>
                  <div>
                    <dt>Endpoint</dt>
                    <dd>{profile.baseUrl ?? profile.region ?? "Provider default"}</dd>
                  </div>
                  <div>
                    <dt>Secrets</dt>
                    <dd>{profile.hasSecret ? "Stored" : "Mounted/default chain"}</dd>
                  </div>
                  <div>
                    <dt>Validation</dt>
                    <dd>{profile.validationStatus ?? "Not validated yet"}</dd>
                  </div>
                </dl>

                {profile.validationError ? (
                  <p className="subtle-copy">{profile.validationError}</p>
                ) : null}

                <div className="profile-card__actions">
                  <button type="button" className="ghost-button" onClick={() => editProfile(profile)}>
                    Edit
                  </button>
                  <button
                    type="button"
                    className="ghost-button"
                    onClick={() => void onValidate(profile.id)}
                    disabled={validatingProfileId === profile.id}
                  >
                    {validatingProfileId === profile.id ? "Validating..." : "Validate"}
                  </button>
                  <button
                    type="button"
                    className="ghost-button ghost-button--danger"
                    onClick={() => void onDelete(profile.id)}
                    disabled={deletingProfileId === profile.id}
                  >
                    {deletingProfileId === profile.id ? "Deleting..." : "Delete"}
                  </button>
                </div>
              </article>
            ))}
          </div>
        )}
      </section>
    </div>
  );
}
