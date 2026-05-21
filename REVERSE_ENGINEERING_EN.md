# VectCutAPI Reverse Engineering Guide (EN)

## 1) Repository purpose
VectCutAPI exposes two interfaces over one draft-editing core:
- HTTP API via Flask (`capcut_server.py`)
- MCP server via JSON-RPC over stdio (`mcp_server.py`)

Business logic lives mostly in `*_impl.py`, `add_*_track.py`, `create_draft.py`, `save_draft_impl.py`, and `pyJianYingDraft/`.

---

## 2) Quick directory map
- `capcut_server.py`: HTTP entrypoint, request -> impl mapping.
- `mcp_server.py`: MCP entrypoint, tool schema + dispatch.
- `add_video_track.py`, `add_audio_track.py`: main media track operations.
- `add_image_impl.py`, `add_text_impl.py`, `add_subtitle_impl.py`, `add_effect_impl.py`, `add_sticker_impl.py`, `add_video_keyframe_impl.py`: feature-specific logic.
- `create_draft.py`: create/retrieve draft object in memory cache.
- `save_draft_impl.py`: package draft, fetch assets, upload (optional), async task status.
- `draft_cache.py`: LRU cache for `draft_id -> script`.
- `save_task_cache.py`: LRU cache for save-task status.
- `downloader.py`: download remote media before materializing draft files.
- `oss.py`: upload draft zip to OSS endpoint.
- `settings/local.py`: environment flags (CapCut/Jianying, upload on/off, host/path).
- `template/`, `template_jianying/`: draft skeletons for target app compatibility.
- `pyJianYingDraft/`: timeline/segment/effect engine and metadata.

---

## 3) High-level runtime flow
1. Client calls endpoint/tool with media/style/timeline args.
2. Service calls `get_or_create_draft()` to get script by `draft_id`.
3. Feature function (`add_video_track`, `add_text_impl`, etc.) mutates script in memory.
4. Each mutation returns `draft_id` + `draft_url`.
5. On finalize, `save_draft`:
   - collect assets, copy/download into draft folder
   - write draft files based on templates
   - zip draft
   - upload to OSS when enabled
   - update `DRAFT_TASKS` progress/status

Key point: editing is mostly in-memory until save step.

---

## 4) Entrypoints

### HTTP (`capcut_server.py`)
Main routes:
- `POST /create_draft`
- `POST /add_video`
- `POST /add_audio`
- `POST /add_image`
- `POST /add_text`
- `POST /add_subtitle`
- `POST /add_effect`
- `POST /add_sticker`
- `POST /add_video_keyframe`
- `POST /save_draft`
- `POST /query_draft_status`
- `POST /query_script`

Metadata routes (GET) return animation/effect/font/mask/transition catalogs from `pyJianYingDraft.metadata.*`.

### MCP (`mcp_server.py`)
- Exposes tool list equivalent to HTTP APIs.
- `tools/list` returns input schemas.
- `tools/call` parses args and dispatches to impl.

For new features, update both Flask routes and MCP tools for parity.

---

## 5) Cache and state model

### Draft cache (`draft_cache.py`)
- Global `DRAFT_CACHE` using LRU (`OrderedDict`).
- Key: `draft_id`; Value: `pyJianYingDraft.Script_file`.
- `create_draft()` id format: `dfd_cat_<unix>_<uuid8>`.

### Task cache (`save_task_cache.py`)
- `DRAFT_TASKS` tracks save workflow:
  - `initialized`, `processing`, `completed`, `failed`, `not_found`
- Standard fields: `progress`, `completed_files`, `total_files`, `draft_url`, `message`.

Implication: process restart drops in-memory state.

---

## 6) Timeline mutation pattern
Most `add_*` features follow same pattern:
1. Normalize input (URL/path/text/time/range).
2. Create/get track by `track_name`.
3. Build segment object (`Video_segment`, `Audio_segment`, `Text_segment`, etc.).
4. Apply `Clip_settings` (transform, scale, rotation, alpha...).
5. Apply secondary effects (transition/mask/animation/filter/keyframe...).
6. Add segment into track.
7. Return `draft_id` + `draft_url`.

Engine often uses microseconds internally; external APIs usually accept seconds and convert.

---

## 7) Save-draft critical path
`save_draft_impl.py` is most complex:
- Cross-platform asset path resolution (`build_asset_path`, Windows/Linux handling).
- Download remote files (video/audio/image) into draft assets.
- Thread pool for parallel asset fetch.
- Progress tracking through `DRAFT_TASKS`.
- Zip output via `util.zip_draft`.
- Optional OSS upload via `oss.upload_to_oss` when `IS_UPLOAD_DRAFT = True`.

Technical risks:
- Race conditions if concurrent requests mutate same `draft_id` (no per-draft lock).
- Memory growth risk when cache pressure is high.
- Mid-flow failures from network/download errors.

---

## 8) `pyJianYingDraft` reading order before deep changes
Recommended order:
1. `pyJianYingDraft/script_file.py` (central mutation API)
2. `pyJianYingDraft/track.py` (track management)
3. `pyJianYingDraft/video_segment.py`, `audio_segment.py`, `text_segment.py`, `effect_segment.py`
4. `pyJianYingDraft/keyframe.py`, `animation.py`
5. `pyJianYingDraft/metadata/*.py` (effect/font/transition IDs)

Safe-change rules:
- Do not change draft JSON output format without import validation in CapCut/Jianying.
- Do not silently change time-unit behavior (seconds vs microseconds).
- Do not hardcode new metadata IDs without metadata source alignment.

---

## 9) New-feature playbook
1. Add/extend relevant `*_impl.py` logic.
2. Reuse `get_or_create_draft()` for consistent state model.
3. Keep response format: `{ "draft_id": ..., "draft_url": ... }`.
4. Add route in `capcut_server.py`.
5. Add tool schema + dispatch in `mcp_server.py`.
6. If new asset type needed, extend `save_draft_impl.py`.
7. Update docs: `README.md`, `MCP_Documentation_English.md`, `MCP_文档_中文.md`.

---

## 10) Known pitfalls
- In-memory cache is not multi-instance safe without external shared state.
- Windows path adaptation in non-Windows environments is fragile.
- Some impl paths call network directly (`requests.get`), so timeout/retry hardening matters.
- Metadata endpoints are only as good as data in `pyJianYingDraft/metadata`.

---

## 11) 15-minute onboarding checklist for new AI/dev
1. Read `README.md` for product intent.
2. Read `capcut_server.py` for API surface.
3. Read `create_draft.py` + `draft_cache.py` for state model.
4. Read `add_video_track.py`, `add_text_impl.py`, `add_subtitle_impl.py` for mutation pattern.
5. Read `save_draft_impl.py` for finalize/output pipeline.
6. Read `mcp_server.py` for MCP parity mapping.

Complete checklist before changing features to reduce compatibility break risk.

---

## 12) Important files
- `capcut_server.py`
- `mcp_server.py`
- `create_draft.py`
- `draft_cache.py`
- `save_task_cache.py`
- `save_draft_impl.py`
- `add_video_track.py`
- `add_audio_track.py`
- `add_image_impl.py`
- `add_text_impl.py`
- `add_subtitle_impl.py`
- `pyJianYingDraft/script_file.py`

---

## 13) MCP-first guidance for AI orchestration
For editing tasks, AI agents should prefer CapCut-native capability via this repo APIs, not external custom media logic.

Priority:
1. MCP tools (`mcp_server.py`) first.
2. HTTP endpoints (`capcut_server.py`) second.
3. New code only when capability gap is confirmed.

Practical examples:
- Styled text layer: use `add_text` params (font/size/color/border/background/transform).
- Subtitle import/styling: use `add_subtitle`.
- Keyframe animation: use `add_video_keyframe`.
- Effects/stickers/transitions: use existing `add_effect` / `add_sticker` / `add_video` transition args.

Reason: preserves compatibility with internal draft model, metadata IDs, save pipeline, and CapCut/Jianying import behavior.
