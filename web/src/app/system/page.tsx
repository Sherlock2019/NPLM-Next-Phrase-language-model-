"use client";

import { useEffect, useState } from "react";
import { api, ApiError, compactNumber, fullNumber } from "@/lib/api";
import { ErrorBox, Loading, Panel, Pill, Stat } from "@/components/ui";
import type { SystemResponse } from "@/lib/types";

/**
 * System and model information (spec section 32), plus what is *not* installed.
 *
 * The missing-resources section matters as much as the present ones: a reader looking
 * at a semantic-focus figure needs to know the lexicon is empty and the gazetteers are
 * seeds, and this is where that is stated plainly.
 */
export default function SystemPage() {
  const [data, setData] = useState<SystemResponse | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api
      .system()
      .then(setData)
      .catch((cause) =>
        setError(cause instanceof ApiError ? cause.message : String(cause)),
      );
  }, []);

  if (error) return <ErrorBox error={error} />;
  if (!data) {
    return (
      <Panel>
        <Loading label="Reading system information" />
      </Panel>
    );
  }

  const model = data.model;
  const hardware = data.hardware as Record<string, unknown>;
  const parameters = typeof model.parameters === "number" ? model.parameters : null;

  return (
    <div className="flex flex-col gap-4">
      <div className="grid gap-2 sm:grid-cols-2 lg:grid-cols-4">
        <Stat
          label="Base model"
          value={String(model.model_id ?? "—").split("/").pop() ?? "—"}
          sub={String(model.model_id ?? "")}
        />
        <Stat
          label="Parameters"
          value={parameters ? compactNumber(parameters) : "—"}
          sub={parameters ? fullNumber(parameters) : undefined}
        />
        <Stat
          label="Device"
          value={String(model.device ?? "—")}
          sub={String(model.dtype ?? "")}
          tone={String(model.device ?? "").startsWith("cuda") ? "ok" : "neutral"}
        />
        <Stat
          label="Vocabulary"
          value={model.vocab_size ? compactNumber(Number(model.vocab_size)) : "—"}
          sub={`tokenizer: ${String(model.tokenizer ?? "—")}`}
        />
      </div>

      <div className="grid gap-4 lg:grid-cols-2">
        <Panel title="Model">
          <Rows
            rows={[
              ["Model id", String(model.model_id ?? "—")],
              ["Requested device", String(model.requested_device ?? "—")],
              ["Resolved device", String(model.device ?? "not loaded")],
              ["dtype", String(model.dtype ?? "—")],
              ["Top-K re-scored", String(model.top_k_candidates ?? "—")],
              ["Load time", model.load_time_ms ? `${model.load_time_ms} ms` : "—"],
            ]}
          />
        </Panel>

        <Panel title="Hardware">
          <Rows
            rows={[
              ["torch", String(hardware.torch ?? "—")],
              ["CUDA available", String(hardware.cuda_available ?? "—")],
              ["CUDA usable", String(hardware.cuda_usable ?? "—")],
              ["GPU", String(hardware.gpu_name ?? "—")],
              ["Compute capability", String(hardware.compute_capability ?? "—")],
            ]}
          />
          {hardware.cuda_available === true && hardware.cuda_usable === false && (
            <p className="mt-2 text-[11px] leading-relaxed text-warn-400">
              A GPU is present but this build of torch has no kernels for it, so
              everything runs on CPU. Availability is confirmed by running a real kernel
              rather than trusting the availability flag — otherwise the failure would
              surface much later, inside a model load.
            </p>
          )}
        </Panel>

        <Panel title="MLM configuration">
          <div className="flex flex-col gap-3">
            <Rows
              rows={[
                ["Config fingerprint", data.fingerprint],
                ["Scorer backend", data.scorer_backend],
                [
                  "Scorer trained",
                  data.scorer_trained ? "yes" : "no — using configured weights",
                ],
                ["Slot predictor", data.slot_backend],
                [
                  "Slot predictor trained",
                  data.slot_trained ? "yes" : "no — using language-pack priors",
                ],
                ["Universal pack version", String(data.universal_pack_version ?? "—")],
              ]}
            />

            <div>
              <h3 className="eyebrow mb-1.5">Scoring weights</h3>
              <div className="flex flex-wrap gap-1">
                {Object.entries(data.weights).map(([name, weight]) => (
                  <Pill key={name} tone="neutral">
                    {name} {weight}
                  </Pill>
                ))}
              </div>
            </div>

            <div>
              <h3 className="eyebrow mb-1.5">Active features</h3>
              <div className="flex flex-wrap gap-1">
                {Object.entries(data.features).map(([name, enabled]) => (
                  <Pill key={name} tone={enabled ? "splm" : "neutral"}>
                    {name.replace(/_/g, " ")} {enabled ? "on" : "off"}
                  </Pill>
                ))}
              </div>
            </div>
          </div>
        </Panel>

        <Panel title="Language packs">
          <div className="flex flex-col gap-2">
            {Object.entries(data.language_packs).map(([code, pack]) => (
              <div
                key={code}
                className="panel-raised flex items-center gap-3 px-3 py-2"
              >
                <span className="w-10 shrink-0 text-xs font-semibold">{code}</span>
                <span className="faint text-[11px]">v{String(pack.version ?? "?")}</span>
                <span className="ml-auto">
                  <Pill tone={pack.semantics_coverage === "seed" ? "warn" : "ok"}>
                    slot data: {pack.semantics_coverage}
                  </Pill>
                </span>
              </div>
            ))}
            <p className="faint text-[11px] leading-relaxed">
              Supported: {data.supported_languages.join(", ")}. Adding a language means
              adding a pack directory and listing it in config — no engine change.
            </p>
          </div>
        </Panel>
      </div>

      <Panel
        title="Knowledge base"
        hint="What is installed, and what the numbers therefore mean."
      >
        <div className="flex flex-col gap-3">
          <div className="flex items-center gap-3">
            <Pill tone={data.lexicon.available ? "ok" : "warn"}>
              lexicon {data.lexicon.available ? "built" : "not built"}
            </Pill>
            {data.lexicon.note && (
              <span className="faint text-[11px]">{data.lexicon.note}</span>
            )}
          </div>

          {data.lexicon.loading && (
            <div className="flex flex-col gap-1">
              {Object.entries(data.lexicon.loading.languages).map(([language, status]) => (
                <div key={language} className="flex items-center gap-2">
                  <Pill
                    tone={
                      status.state === "ready"
                        ? "ok"
                        : status.state === "failed"
                          ? "warn"
                          : "neutral"
                    }
                  >
                    {language} {status.state}
                  </Pill>
                  <span className="faint text-[11px]">{status.detail}</span>
                </div>
              ))}
              <p className="faint text-[11px] leading-relaxed">
                {data.lexicon.loading.auto_download
                  ? "A language's dictionary is downloaded from Wiktionary the first time that language is chosen or detected."
                  : "Automatic dictionary download is off; build with scripts/build_lexicon.py."}
              </p>
            </div>
          )}

          {data.lexicon.tables && (
            <div className="flex flex-wrap gap-1">
              {Object.entries(data.lexicon.tables).map(([table, count]) => (
                <Pill key={table} tone="neutral">
                  {table} {fullNumber(count)}
                </Pill>
              ))}
            </div>
          )}

          <div className="rounded-lg border border-warn-400/25 bg-warn-400/6 p-3">
            <h3 className="eyebrow mb-1.5 text-warn-400">
              What this means for the metrics
            </h3>
            <ul className="flex flex-col gap-1.5 text-[11px] leading-relaxed text-warn-400">
              {!data.lexicon.available && (
                <li>
                  With no lexicon, every lexical feature reports &ldquo;no
                  evidence&rdquo; and contributes exactly zero. It does not penalise
                  unknown words — a token is never invalid merely because MLM has no
                  dictionary to check it against.
                </li>
              )}
              {Object.values(data.language_packs).some(
                (pack) => pack.semantics_coverage === "seed",
              ) && (
                <li>
                  Slot-compatibility gazetteers are seeds of a few hundred entries, not
                  coverage. Semantic focus and candidate-relevance figures are
                  indicative, and always reported with the share of candidates the
                  classifier could actually judge.
                </li>
              )}
              {!data.slot_trained && (
                <li>
                  The slot predictor is the rule-based baseline. The trainable version is
                  meant to beat it; until it is trained, the heuristic&apos;s numbers are
                  what is being measured.
                </li>
              )}
            </ul>
          </div>

          {data.ablation_presets.length > 0 && (
            <div>
              <h3 className="eyebrow mb-1.5">Ablation presets</h3>
              <div className="flex flex-wrap gap-1">
                {data.ablation_presets.map((preset) => (
                  <Pill key={preset} tone="neutral">
                    {preset}
                  </Pill>
                ))}
              </div>
            </div>
          )}
        </div>
      </Panel>
    </div>
  );
}

function Rows({ rows }: { rows: [string, string][] }) {
  return (
    <dl className="grid gap-y-1">
      {rows.map(([label, value]) => (
        <div key={label} className="flex items-baseline justify-between gap-3">
          <dt className="faint shrink-0 text-[11px]">{label}</dt>
          <dd className="num truncate text-[11px]" title={value}>
            {value}
          </dd>
        </div>
      ))}
    </dl>
  );
}
