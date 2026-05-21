# VectCutAPI Reverse Engineering Guide

## 1) Mục tiêu repo
VectCutAPI cung cấp 2 mặt giao tiếp trên cùng 1 lõi dựng draft video:
- HTTP API qua Flask (`capcut_server.py`)
- MCP server qua JSON-RPC over stdio (`mcp_server.py`)

Lõi nghiệp vụ nằm ở nhóm file `*_impl.py`, `add_*_track.py`, `create_draft.py`, `save_draft_impl.py`, và package `pyJianYingDraft/`.

---

## 2) Bản đồ thư mục nhanh
- `capcut_server.py`: entrypoint HTTP, map request -> hàm impl.
- `mcp_server.py`: entrypoint MCP, khai báo tool schema + dispatch tool call.
- `add_video_track.py`, `add_audio_track.py`: thao tác track media chính.
- `add_image_impl.py`, `add_text_impl.py`, `add_subtitle_impl.py`, `add_effect_impl.py`, `add_sticker_impl.py`, `add_video_keyframe_impl.py`: layer nghiệp vụ từng feature.
- `create_draft.py`: tạo/lấy draft object trong cache RAM.
- `save_draft_impl.py`: đóng gói draft, tải asset, upload (nếu bật), async task status.
- `draft_cache.py`: cache `draft_id -> script` theo LRU.
- `save_task_cache.py`: cache trạng thái tác vụ save draft theo LRU.
- `downloader.py`: tải remote media về local trước khi ghi draft.
- `oss.py`: upload file zip draft lên OSS endpoint.
- `settings/local.py`: cờ môi trường (CapCut/Jianying, upload bật/tắt, host/path).
- `template/`, `template_jianying/`: skeleton draft để xuất file tương thích app đích.
- `pyJianYingDraft/`: engine thao tác timeline/segment/effect và metadata.

---

## 3) Luồng runtime tổng quát
1. Client gọi endpoint/tool, truyền tham số media + style + timeline.
2. Service gọi `get_or_create_draft()` để lấy script object theo `draft_id`.
3. Hàm feature (`add_video_track`, `add_text_impl`, ...) mutate trực tiếp `script` trong RAM.
4. Mỗi lần mutate trả về `draft_id` + `draft_url` (URL preview/định danh draft).
5. Khi finalize, gọi `save_draft`:
   - gom asset, copy/download vào thư mục draft
   - ghi json/tệp draft theo template
   - zip draft
   - upload OSS nếu cấu hình bật
   - cập nhật trạng thái task trong `DRAFT_TASKS`

Điểm quan trọng: phần lớn thao tác edit là in-memory, chưa flush ra file cho tới bước save.

---

## 4) Entry points chi tiết

### HTTP (`capcut_server.py`)
Các route chính:
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

Các route metadata (GET) trả danh mục animation/effect/font/mask/transition từ `pyJianYingDraft.metadata.*`.

### MCP (`mcp_server.py`)
- Expose danh sách tool tương đương HTTP APIs.
- `tools/list` trả schema input.
- `tools/call` parse args rồi gọi đúng impl.

Khi thêm tính năng mới, cần sửa **cả** Flask route và MCP tool (nếu muốn parity).

---

## 5) Cache và state

### Draft cache (`draft_cache.py`)
- Biến toàn cục `DRAFT_CACHE` dạng LRU (`OrderedDict`).
- Key: `draft_id`, Value: `pyJianYingDraft.Script_file`.
- `create_draft()` tạo `draft_id` theo `dfd_cat_<unix>_<uuid8>`.

### Task cache (`save_task_cache.py`)
- `DRAFT_TASKS` giữ trạng thái save draft:
  - `initialized`, `processing`, `completed`, `failed`, `not_found`
- Trường status chuẩn: `progress`, `completed_files`, `total_files`, `draft_url`, `message`.

Hệ quả: restart process sẽ mất toàn bộ cache in-memory.

---

## 6) Cách feature mutate timeline
Pattern gần như giống nhau ở file `add_*`:
1. Normalize input (URL/path/text/time/range).
2. Tạo hoặc lấy track theo `track_name`.
3. Tạo segment object (`Video_segment`, `Audio_segment`, `Text_segment`, ...).
4. Áp `Clip_settings` (transform, scale, rotation, alpha...).
5. Áp effect phụ (transition/mask/animation/filter/keyframe...).
6. Add segment vào script track.
7. Trả `draft_id` + `draft_url`.

Time unit bên trong engine thường dùng microseconds; nhiều API nhận seconds rồi convert.

---

## 7) Phần save draft (critical path)
`save_draft_impl.py` là đoạn phức tạp nhất:
- Resolve asset path đa nền tảng (`build_asset_path`, path Windows/Linux).
- Tải file từ URL (video/audio/image) và map vào thư mục assets của draft.
- Dùng thread pool để tăng tốc tải asset.
- Track tiến độ từng file qua `DRAFT_TASKS`.
- Zip output (`util.zip_draft`).
- Upload OSS (`oss.upload_to_oss`) nếu `IS_UPLOAD_DRAFT = True`.

Rủi ro kỹ thuật:
- Race condition khi nhiều request cùng sửa 1 `draft_id` (không lock toàn cục per draft).
- Memory growth nếu draft cache lớn và chưa eviction phù hợp traffic thực.
- Fail download mạng dẫn tới task fail giữa chừng.

---

## 8) `pyJianYingDraft` cần đọc trước khi sửa sâu
File nên đọc theo thứ tự:
1. `pyJianYingDraft/script_file.py` (API mutate draft trung tâm)
2. `pyJianYingDraft/track.py` (quản lý track)
3. `pyJianYingDraft/video_segment.py`, `audio_segment.py`, `text_segment.py`, `effect_segment.py`
4. `pyJianYingDraft/keyframe.py`, `animation.py`
5. `pyJianYingDraft/metadata/*.py` (enum/type ID effect/font/transition)

Nguyên tắc sửa an toàn:
- Không đổi format output draft json nếu chưa test import vào CapCut/Jianying.
- Không đổi time-unit ngầm (seconds vs microseconds).
- Không hardcode metadata ID mới nếu chưa đồng bộ với nguồn metadata.

---

## 9) Quy tắc thêm feature mới (playbook)
1. Tạo file impl mới hoặc mở rộng file `*_impl.py` liên quan.
2. Reuse `get_or_create_draft()` để tránh diverge state model.
3. Trả response thống nhất: `{ "draft_id": ..., "draft_url": ... }`.
4. Thêm route ở `capcut_server.py`.
5. Thêm tool schema + dispatch ở `mcp_server.py`.
6. Nếu cần save asset mới, nối vào `save_draft_impl.py`.
7. Cập nhật docs: `README.md`, `MCP_Documentation_English.md`, `MCP_文档_中文.md`.

---

## 10) Known pitfalls
- Cache in-memory: không phù hợp multi-instance nếu không có external state.
- Đường dẫn Windows trong môi trường non-Windows có xử lý riêng, dễ bug path separator.
- Một số impl gọi network trực tiếp (`requests.get`), timeout/retry cần chú ý khi harden production.
- Metadata endpoint nhiều, nhưng chất lượng phụ thuộc data trong `pyJianYingDraft/metadata`.

---

## 11) Gợi ý đọc nhanh cho AI model mới vào
Checklist 15 phút:
1. Đọc `README.md` để hiểu mục tiêu sản phẩm.
2. Đọc `capcut_server.py` để thấy surface API.
3. Đọc `create_draft.py` + `draft_cache.py` để hiểu state model.
4. Đọc `add_video_track.py`, `add_text_impl.py`, `add_subtitle_impl.py` để nắm pattern mutate.
5. Đọc `save_draft_impl.py` để nắm finalize/output pipeline.
6. Đọc `mcp_server.py` để map API parity với MCP.

Sau checklist này mới bắt đầu sửa feature; giảm nguy cơ phá compatibility.

---

## 12) File reference quan trọng
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

## 13) Hướng dẫn MCP-first cho AI orchestration
Với bài toán dựng/chỉnh video, AI agent cần ưu tiên dùng năng lực CapCut có sẵn qua API của repo, thay vì tự viết logic xử lý media ngoài luồng.

Ưu tiên:
1. MCP tools trong `mcp_server.py`.
2. HTTP API tương đương trong `capcut_server.py`.
3. Chỉ viết code mới khi xác nhận thiếu capability.

Ví dụ thực tế:
- Add text layer có style: gọi `add_text` với tham số font/size/color/border/background/transform.
- Add subtitle theo SRT + style: gọi `add_subtitle`.
- Làm animation theo thời gian: gọi `add_video_keyframe`.
- Thêm effect/sticker/transition: dùng `add_effect` / `add_sticker` / params transition của `add_video`.

Lý do: giữ tương thích model draft nội bộ, metadata ID, pipeline save, và import behavior ở CapCut/Jianying.
