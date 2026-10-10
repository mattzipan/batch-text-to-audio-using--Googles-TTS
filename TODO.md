# TODO

## Spec: Gemini 3.8 TTS backend migration

Status: **complete (2026-10-10)**. All 12 tasks finished and verified
(31 mocked tests green; live smoke test: WAV probe `24000 1 2`, single RIFF header).
Finished items moved to [TODO-DONE.md](TODO-DONE.md).

### Follow-ups (out of scope, still open)

- **Batch API** (half price): deferred. No official TTS-in-batch worked example exists and the batch JSONL parser reportedly requires snake_case fields; not worth the risk at this scale. Revisit with a spike if cost ever matters. The `batch_jobs.json` resume design is unnecessary while sync-only.
- **Interface phase:** own spec in TODO.md once this backend is stable (deployment options are sketched in `IDEA.md`). The boundary contract for it is: import `backends/`, call `synthesize_many(items, progress=..., cancel=...)`, write the yielded WAV bytes.
- **Per-line style / multi-speaker:** interface-era features.
