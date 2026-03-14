import { useState } from "react";
import type { FormEvent } from "react";
import type { ProfileDraft, ProviderProfile } from "../types";
import { StatusPill } from "./StatusPill";

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
  }

  const isBedrock = draft.providerType === "bedrock";

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
                  <span>Model ID</span>
                  <input
                    value={draft.modelId ?? ""}
                    onChange={(event) => setDraft({ ...draft, modelId: event.target.value })}
                    placeholder="amazon.nova-lite-v1:0"
                  />
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
                  <span>Model alias</span>
                  <input
                    value={draft.model ?? ""}
                    onChange={(event) => setDraft({ ...draft, model: event.target.value })}
                    placeholder="gpt-5.4"
                  />
                </label>

                <label>
                  <span>Snapshot model</span>
                  <input
                    value={draft.snapshotModel ?? ""}
                    onChange={(event) =>
                      setDraft({ ...draft, snapshotModel: event.target.value })
                    }
                    placeholder="gpt-5.4-2026-03-05"
                  />
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
