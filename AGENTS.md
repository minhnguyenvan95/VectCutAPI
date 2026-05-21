# AGENTS.md

Scope: entire repository.

## Mission
Keep VectCutAPI behavior stable while making targeted code changes.
Preserve compatibility for HTTP API, MCP tools, and generated CapCut/Jianying draft outputs.

## Read-first order (mandatory)
1. `README.md`
2. `REVERSE_ENGINEERING.md` (or `REVERSE_ENGINEERING_EN.md`)
3. `capcut_server.py`
4. `mcp_server.py`
5. `create_draft.py`, `draft_cache.py`, `save_task_cache.py`
6. feature file being edited (`add_*_impl.py`, `add_*_track.py`)
7. `save_draft_impl.py` if change affects export/assets

## Core invariants (do not break)
- Keep response shape for feature APIs: usually include `draft_id` and `draft_url`.
- Keep API/MCP parity when adding/removing feature capability.
- Keep time-unit semantics consistent (external seconds, internal microseconds where used).
- Do not change draft JSON/template structure unless explicitly required.
- Do not silently remove metadata compatibility (effect/font/transition IDs).

## Change policy
- Prefer minimal, surgical diffs.
- Fix root cause, not surface patch.
- Avoid unrelated refactors.
- Reuse existing helpers before adding new abstractions.
- Keep naming/style consistent with surrounding files.

## Touchpoints checklist for new features
- Business logic: `*_impl.py` or `add_*_track.py`
- HTTP route: `capcut_server.py`
- MCP schema + dispatch: `mcp_server.py`
- Save/export path: `save_draft_impl.py` (if new assets/material handling)
- Docs: update relevant README/MCP docs

## Validation guidance
- Run focused test/manual check for changed flow first.
- If possible, verify draft still imports/works in target editor flow.
- For save flow changes, validate task status transitions and output zip/upload behavior.

## Risk notes
- Caches are in-memory (`DRAFT_CACHE`, `DRAFT_TASKS`): restart wipes state.
- Concurrent edits on same `draft_id` may race.
- Network download paths can fail; preserve clear error reporting.

## Definition of Done (before merge)
- Changed flow works end-to-end (create/edit/save or affected subset).
- HTTP change mirrored in MCP (`tools/list` schema + `tools/call` dispatch) when applicable.
- Response contract unchanged unless task explicitly requests breaking change.
- Time conversions validated (seconds input, internal units consistent).
- No unrelated files/refactors in diff.
- Docs updated if API/tool behavior changed.
- Error paths return actionable messages (no silent fail).
- Export/save path still generates valid draft structure.

## MCP-first / CapCut-first execution rule (for AI agents)
When task is video editing logic, prefer calling existing CapCut/VectCut APIs (MCP tools or HTTP endpoints) over writing custom processing code.

Preferred order:
1. Use MCP tools in `mcp_server.py` (`create_draft`, `add_video`, `add_audio`, `add_image`, `add_text`, `add_subtitle`, `add_effect`, `add_sticker`, `add_video_keyframe`, `save_draft`).
2. If MCP path unavailable, use equivalent HTTP API in `capcut_server.py`.
3. Only write new code when required capability does not exist in MCP/HTTP surfaces.

Examples:
- Need styled text layer -> call `add_text` with style params (font, size, color, border, background, transform), not custom text-rendering code.
- Need subtitle track -> call `add_subtitle`, not custom SRT parser/render pipeline unless extending feature.
- Need keyframe animation -> call `add_video_keyframe`, not external animation compositor code.

PR rule:
- If custom code added for behavior already covered by existing MCP/HTTP tool, include explicit justification in PR notes; otherwise reject change.
