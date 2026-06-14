#!/usr/bin/env python3
"""
Plukky Episode Pipeline
=======================
Tự động sinh 1 tập hoạt hình từ 1 chủ đề -> prompt sẵn sàng cho Seedance 2.0.

Triết lý consistency: tất cả nhân vật & bối cảnh chỉ được mô tả MỘT lần
(canonical block trong bible.json). Mọi cảnh inject nguyên văn block đó theo ID.
LLM không bao giờ được tự mô tả lại nhân vật ở bước viết cảnh -> không thể drift.

Stack: litellm (chạy được với Ollama local, LiteLLM proxy, hoặc API bất kỳ).
  pip install litellm

Config qua env:
  LLM_MODEL     (default: ollama/qwen2.5:14b)
  LLM_API_BASE  (default: http://localhost:11434  — đổi sang proxy LiteLLM nếu cần)
  LLM_API_KEY   (optional)

Chạy:
  python plukky_pipeline.py "Plukky dạy bé không đi theo người lạ"
  python plukky_pipeline.py "..." --scenes 8 --out ./episodes
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import litellm  # type: ignore

litellm.suppress_debug_info = True

# --------------------------------------------------------------------------- #
# Config
# --------------------------------------------------------------------------- #

MODEL = os.getenv("LLM_MODEL", "ollama/qwen2.5:14b")
API_BASE = os.getenv("LLM_API_BASE", "http://localhost:11434")
API_KEY = os.getenv("LLM_API_KEY", "")

# Style toàn cục dán vào MỌI prompt Seedance (English — model video đọc tốt hơn)
GLOBAL_STYLE = (
    "bright colorful 3D cartoon style, soft rounded shapes, warm cinematic lighting, "
    "child-friendly, high detail, smooth animation, 1080p"
)

# Negative prompt toàn cục
NEGATIVE_PROMPT = (
    "deformed, mutated, changing clothes, face drift, body deformation, "
    "inconsistent proportions, extra limbs, dark gloomy colors, scary, realistic, "
    "text, watermark, logo, low quality, blurry"
)

# Tham số render mặc định cho Seedance
DEFAULT_DURATION = 8        # giây / cảnh
ASPECT_RATIO = "16:9"
RESOLUTION = "1080p"

# --------------------------------------------------------------------------- #
# Plukky DNA — SEED CỨNG, không cho AI generate (tránh lệch brand)
# --------------------------------------------------------------------------- #

PLUKKY_CANON = {
    "id": "plukky",
    "name": "Plukky",
    "role": "Nhân vật chính — chú voi sheriff nhí của núi rừng Đắk Lắk",
    "identity_lock": (
        "Plukky, a cute baby elephant: soft light-gray skin, round chubby body, "
        "big rounded head, short curled trunk, rosy pink cheeks, big sparkling "
        "friendly dark eyes, tiny ears. FIXED OUTFIT that never changes: a small "
        "brown sheriff hat with a single yellow star on the front, a blue police "
        "vest, a red scarf around the neck. Identical proportions, identical "
        "clothing and colors in every single shot."
    ),
    "reference_image_prompt": (
        "Character reference sheet of Plukky, a cute baby elephant mascot, front "
        "and side view, neutral A-pose, soft light-gray skin, round chubby body, "
        "short curled trunk, rosy pink cheeks, big sparkling eyes, wearing a small "
        "brown sheriff hat with a yellow star, blue police vest, red scarf. Bright "
        "3D cartoon style, clean white background, full body visible."
    ),
}

# --------------------------------------------------------------------------- #
# LLM helper — gọi + ép JSON + tự repair (Qwen local hay xì JSON hỏng)
# --------------------------------------------------------------------------- #


def _chat(system: str, user: str, temperature: float = 0.7) -> str:
    kwargs: dict[str, Any] = {
        "model": MODEL,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        "temperature": temperature,
    }
    if API_BASE:
        kwargs["api_base"] = API_BASE
    if API_KEY:
        kwargs["api_key"] = API_KEY
    resp = litellm.completion(**kwargs)
    return resp.choices[0].message.content or ""


def _extract_json(text: str) -> Any:
    """Bóc JSON ra khỏi text (xử fences, prose thừa)."""
    text = text.strip()
    text = re.sub(r"^```(?:json)?", "", text).strip()
    text = re.sub(r"```$", "", text).strip()
    # Thử parse thẳng
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    # Tìm khối {...} hoặc [...] lớn nhất
    for opener, closer in (("{", "}"), ("[", "]")):
        start = text.find(opener)
        end = text.rfind(closer)
        if start != -1 and end != -1 and end > start:
            try:
                return json.loads(text[start : end + 1])
            except json.JSONDecodeError:
                continue
    raise ValueError("Không parse được JSON từ output LLM.")


def llm_json(system: str, user: str, temperature: float = 0.7, retries: int = 2) -> Any:
    """Gọi LLM, ép trả JSON. Repair 1 lần nếu hỏng."""
    last_err: Exception | None = None
    raw = ""
    for attempt in range(retries + 1):
        try:
            if attempt == 0:
                raw = _chat(system, user, temperature)
            else:
                # repair pass: đưa lại output hỏng, bắt sửa thành JSON thuần
                repair_sys = "You fix malformed JSON. Output ONLY valid JSON, no prose, no code fences."
                raw = _chat(repair_sys, f"Fix this into valid JSON:\n\n{raw}", 0.0)
            return _extract_json(raw)
        except Exception as e:  # noqa: BLE001
            last_err = e
            time.sleep(0.5)
    raise RuntimeError(f"LLM JSON failed sau {retries + 1} lần: {last_err}\n--- raw ---\n{raw[:800]}")


# --------------------------------------------------------------------------- #
# State
# --------------------------------------------------------------------------- #


@dataclass
class Project:
    topic: str
    out_dir: Path
    n_scenes: int = 8
    script: dict = field(default_factory=dict)
    bible: dict = field(default_factory=lambda: {"characters": {}, "settings": {}})
    scenes: list[dict] = field(default_factory=list)

    def save(self, name: str, data: Any) -> None:
        self.out_dir.mkdir(parents=True, exist_ok=True)
        (self.out_dir / name).write_text(
            json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        print(f"  -> saved {self.out_dir / name}")


# --------------------------------------------------------------------------- #
# BƯỚC 2 — Sinh kịch bản từ chủ đề
# --------------------------------------------------------------------------- #

SYS_SCRIPT = """Bạn là biên kịch hoạt hình giáo dục cho trẻ 2-6 tuổi, kênh "Plukky - Sheriff Tây Nguyên".
Nhân vật chính: Plukky — chú voi con đội mũ sheriff, sống ở rừng núi Đắk Lắk (cà phê, sông suối, cồng chiêng nhẹ).

QUY TẮC AN TOÀN TRẺ EM (BẮT BUỘC — đây là content "Made for Kids"/COPPA):
- Tuyệt đối không bạo lực, không hù dọa, không hình ảnh đáng sợ, không nguy hiểm được tôn vinh.
- Không cô lập trẻ khỏi người lớn tin cậy; luôn có thông điệp tích cực, an toàn, tình bạn.
- Mỗi tập có MỘT bài học rõ ràng, lặp lại đơn giản, kết thúc ấm áp.
- Hành động trực quan, dễ dựng bằng video AI (mỗi cảnh là một hành động nhìn thấy được trong ~5-12 giây).

Trả về JSON THUẦN (không markdown), schema:
{
  "title": "tên tập (tiếng Việt)",
  "lesson": "bài học cho bé (1 câu)",
  "logline": "tóm tắt 1-2 câu",
  "scenes": [
    {
      "scene_number": 1,
      "beat": "chuyện gì xảy ra trong cảnh (tiếng Việt, súc tích)",
      "location_hint": "gợi ý bối cảnh",
      "characters_hint": "ai xuất hiện",
      "tone": "cảm xúc chủ đạo"
    }
  ]
}"""


def step2_generate_script(p: Project) -> dict:
    print("[2] Sinh kịch bản...")
    user = f"Chủ đề: {p.topic}\nSố cảnh mong muốn: khoảng {p.n_scenes} cảnh."
    script = llm_json(SYS_SCRIPT, user)
    p.script = script
    p.save("01_script.json", script)
    return script


# --------------------------------------------------------------------------- #
# BƯỚC 3 — Review + tự sửa kịch bản
# --------------------------------------------------------------------------- #

SYS_REVIEW = """Bạn là biên tập viên khó tính cho hoạt hình trẻ em "Made for Kids".
Chấm kịch bản theo: (1) an toàn trẻ em & COPPA, (2) bài học rõ ràng, (3) mạch truyện
mượt cho bé 2-6 tuổi, (4) tính khả thi để dựng bằng AI video (mỗi cảnh có hành động
trực quan rõ không).

Trả JSON THUẦN:
{
  "score": 0-10,
  "verdict": "pass" hoặc "revise",
  "issues": [{"scene_number": int|null, "type": "...", "severity": "low|med|high", "fix": "đề xuất sửa"}]
}"""

SYS_REVISE = """Bạn là biên kịch. Áp dụng các đề xuất sửa vào kịch bản và trả lại
kịch bản hoàn chỉnh ĐÚNG schema gốc (title, lesson, logline, scenes[...]).
Giữ nguyên những gì đã tốt. Trả JSON THUẦN."""


def step3_review_and_revise(p: Project) -> dict:
    print("[3] Review kịch bản...")
    review = llm_json(SYS_REVIEW, json.dumps(p.script, ensure_ascii=False), temperature=0.3)
    p.save("02_script_review.json", review)
    if review.get("verdict") == "pass":
        print(f"  -> pass (score {review.get('score')}), không cần sửa.")
        return p.script
    print(f"  -> revise (score {review.get('score')}), đang sửa...")
    user = (
        f"KỊCH BẢN GỐC:\n{json.dumps(p.script, ensure_ascii=False)}\n\n"
        f"ĐỀ XUẤT SỬA:\n{json.dumps(review.get('issues', []), ensure_ascii=False)}"
    )
    revised = llm_json(SYS_REVISE, user, temperature=0.5)
    p.script = revised
    p.save("03_script_revised.json", revised)
    return revised


# --------------------------------------------------------------------------- #
# BƯỚC 4 — Bóc tách nhân vật & bối cảnh lặp lại
# --------------------------------------------------------------------------- #

SYS_EXTRACT = """Bạn phân tích kịch bản hoạt hình và bóc ra DANH SÁCH nhân vật và bối cảnh
LẶP LẠI giữa các cảnh (những thứ cần giữ đồng nhất xuyên suốt).

Lưu ý: nhân vật chính "Plukky" LUÔN tồn tại, dùng đúng id "plukky" — đừng tạo id khác cho Plukky.

Trả JSON THUẦN:
{
  "characters": [{"id": "snake_case", "name": "...", "role": "...", "scenes": [1,2,...]}],
  "settings":   [{"id": "snake_case", "name": "...", "brief": "...", "scenes": [1,2,...]}]
}
id viết thường, không dấu, không khoảng trắng (vd: "khi_rung", "song_suoi")."""


def step4_extract_entities(p: Project) -> dict:
    print("[4] Bóc tách nhân vật & bối cảnh...")
    ents = llm_json(SYS_EXTRACT, json.dumps(p.script, ensure_ascii=False), temperature=0.3)
    # Đảm bảo Plukky luôn có trong danh sách characters
    char_ids = {c.get("id") for c in ents.get("characters", [])}
    if "plukky" not in char_ids:
        ents.setdefault("characters", []).insert(
            0, {"id": "plukky", "name": "Plukky", "role": PLUKKY_CANON["role"], "scenes": []}
        )
    p.save("04_entities.json", ents)
    return ents


# --------------------------------------------------------------------------- #
# BƯỚC 5 — Character bible (Identity Lock) cho từng nhân vật
# --------------------------------------------------------------------------- #

SYS_CHAR_BIBLE = """Bạn là character designer cho hoạt hình 3D trẻ em phong cách Plukky.
Cho MỘT nhân vật, viết "identity lock": mô tả hình ảnh CỐ ĐỊNH cực kỳ chi tiết bằng
TIẾNG ANH (loài/dáng, màu sắc, trang phục cố định, tỉ lệ, biểu cảm) để model video giữ
y hệt giữa các cảnh. Phong cách: bright 3D cartoon, child-friendly, bối cảnh Tây Nguyên.

Trả JSON THUẦN:
{
  "id": "...",
  "name": "...",
  "identity_lock": "mô tả hình ảnh cố định, TIẾNG ANH, rất chi tiết, nhấn 'fixed outfit', 'identical proportions'",
  "reference_image_prompt": "prompt TIẾNG ANH để tạo ảnh character sheet master (clean white background, full body)"
}"""


def step5_character_bible(p: Project, characters: list[dict]) -> dict:
    print("[5] Viết Identity Lock cho nhân vật...")
    for c in characters:
        cid = c["id"]
        if cid == "plukky":
            p.bible["characters"]["plukky"] = dict(PLUKKY_CANON)  # seed cứng
            print("  -> plukky: seed cứng từ brand spec")
            continue
        user = (
            f"Nhân vật cần thiết kế: {json.dumps(c, ensure_ascii=False)}\n\n"
            f"Bối cảnh chung của phim (để phối màu hợp): rừng núi Đắk Lắk, Tây Nguyên."
        )
        bible_entry = llm_json(SYS_CHAR_BIBLE, user, temperature=0.6)
        bible_entry["id"] = cid  # ép đúng id
        p.bible["characters"][cid] = bible_entry
        print(f"  -> {cid}: done")
    p.save("05_bible_characters.json", p.bible["characters"])
    return p.bible["characters"]


# --------------------------------------------------------------------------- #
# BƯỚC 6 — Setting bible cho từng bối cảnh
# --------------------------------------------------------------------------- #

SYS_SETTING_BIBLE = """Bạn là environment artist cho hoạt hình 3D trẻ em.
Cho MỘT bối cảnh, viết "identity lock" bằng TIẾNG ANH: mô tả môi trường CỐ ĐỊNH chi tiết
(thành phần, ánh sáng, bảng màu, không khí Tây Nguyên: rừng, cà phê, sông suối) để giữ
nhất quán giữa các cảnh. Bright 3D cartoon, child-friendly.

Trả JSON THUẦN:
{
  "id": "...",
  "name": "...",
  "identity_lock": "mô tả môi trường cố định, TIẾNG ANH, chi tiết, nhấn 'consistent lighting and color palette'",
  "reference_image_prompt": "prompt TIẾNG ANH tạo ảnh establishing shot của bối cảnh (no characters)"
}"""


def step6_setting_bible(p: Project, settings: list[dict]) -> dict:
    print("[6] Viết Identity Lock cho bối cảnh...")
    for s in settings:
        sid = s["id"]
        user = f"Bối cảnh cần thiết kế: {json.dumps(s, ensure_ascii=False)}"
        bible_entry = llm_json(SYS_SETTING_BIBLE, user, temperature=0.6)
        bible_entry["id"] = sid
        p.bible["settings"][sid] = bible_entry
        print(f"  -> {sid}: done")
    p.save("06_bible_settings.json", p.bible["settings"])
    return p.bible["settings"]


# --------------------------------------------------------------------------- #
# BƯỚC 7 — Viết script từng cảnh, gắn ID nhân vật/bối cảnh chính xác
# --------------------------------------------------------------------------- #

SYS_SCENE = """Bạn viết kịch bản chi tiết cho TỪNG CẢNH của hoạt hình trẻ em "Made for Kids".

CỰC KỲ QUAN TRỌNG: bạn CHỈ được THAM CHIẾU nhân vật/bối cảnh bằng ID có sẵn trong bible.
TUYỆT ĐỐI KHÔNG mô tả lại ngoại hình nhân vật hay bối cảnh (việc đó hệ thống tự ghép từ
canonical block). Bạn chỉ chọn ID đúng và mô tả HÀNH ĐỘNG.

Ràng buộc an toàn: không bạo lực, không đáng sợ, tích cực, phù hợp bé 2-6 tuổi.
Hành động phải dựng được trong 1 clip ~5-12 giây.

Trả JSON THUẦN:
{
  "scene_number": int,
  "setting_id": "id bối cảnh (1 cái, từ bible)",
  "character_ids": ["id nhân vật xuất hiện, từ bible"],
  "action": "mô tả hành động trực quan bằng TIẾNG ANH cho model video (chỉ hành động/camera, KHÔNG mô tả ngoại hình)",
  "dialogue_vi": "lời thoại tiếng Việt ngắn, ấm áp (có thể rỗng)",
  "camera": "góc máy đơn giản, vd: 'gentle slow zoom in', 'wide establishing shot'",
  "duration_sec": 6-12
}"""


def step7_scene_scripts(p: Project) -> list[dict]:
    print("[7] Viết script từng cảnh...")
    valid_chars = list(p.bible["characters"].keys())
    valid_settings = list(p.bible["settings"].keys())
    scenes_out: list[dict] = []
    for sc in p.script.get("scenes", []):
        user = (
            f"CẢNH:\n{json.dumps(sc, ensure_ascii=False)}\n\n"
            f"ID nhân vật hợp lệ: {valid_chars}\n"
            f"ID bối cảnh hợp lệ: {valid_settings}\n"
            f"Bài học của tập: {p.script.get('lesson', '')}"
        )
        scene = llm_json(SYS_SCENE, user, temperature=0.6)
        # Lọc ID rác cho chắc
        scene["character_ids"] = [c for c in scene.get("character_ids", []) if c in valid_chars] or ["plukky"]
        if scene.get("setting_id") not in valid_settings and valid_settings:
            scene["setting_id"] = valid_settings[0]
        scene["made_for_kids"] = True
        scenes_out.append(scene)
        print(f"  -> cảnh {scene.get('scene_number')}: {scene.get('character_ids')} @ {scene.get('setting_id')}")
    p.scenes = scenes_out
    p.save("07_scene_scripts.json", scenes_out)
    return scenes_out


# --------------------------------------------------------------------------- #
# BƯỚC 8 — Review liên kết giữa các cảnh + tự fix
# --------------------------------------------------------------------------- #

SYS_CONTINUITY = """Bạn kiểm tra TÍNH LIÊN TỤC giữa các cảnh hoạt hình.
Kiểm tra: (1) mọi setting_id/character_ids có hợp lệ không, (2) có cảnh nào mô tả hành động
mâu thuẫn với canonical (vd ngụ ý đổi trang phục, đổi ngoại hình) không, (3) chuyển cảnh có
mượt và mạch lạc với bài học không.

Trả JSON THUẦN:
{
  "ok": true|false,
  "issues": [{"scene_number": int, "problem": "...", "fix": "đề xuất sửa phần action/dialogue (KHÔNG đụng tới ngoại hình)"}]
}"""

SYS_SCENE_FIX = """Bạn sửa MỘT cảnh theo đề xuất. Vẫn CHỈ dùng ID có sẵn, KHÔNG mô tả ngoại hình.
Trả lại cảnh ĐÚNG schema gốc (scene_number, setting_id, character_ids, action, dialogue_vi, camera, duration_sec). JSON THUẦN."""


def step8_continuity_review(p: Project) -> list[dict]:
    print("[8] Review liên kết giữa các cảnh...")
    payload = {
        "scenes": p.scenes,
        "valid_characters": list(p.bible["characters"].keys()),
        "valid_settings": list(p.bible["settings"].keys()),
    }
    review = llm_json(SYS_CONTINUITY, json.dumps(payload, ensure_ascii=False), temperature=0.3)
    p.save("08_continuity_review.json", review)
    if review.get("ok"):
        print("  -> liên tục OK.")
        return p.scenes
    issues_by_scene: dict[int, list] = {}
    for iss in review.get("issues", []):
        issues_by_scene.setdefault(iss["scene_number"], []).append(iss)
    print(f"  -> {len(review.get('issues', []))} issue, đang fix...")
    valid_chars = list(p.bible["characters"].keys())
    valid_settings = list(p.bible["settings"].keys())
    for i, scene in enumerate(p.scenes):
        sn = scene.get("scene_number")
        if sn in issues_by_scene:
            user = (
                f"CẢNH:\n{json.dumps(scene, ensure_ascii=False)}\n\n"
                f"ĐỀ XUẤT SỬA:\n{json.dumps(issues_by_scene[sn], ensure_ascii=False)}\n\n"
                f"ID nhân vật hợp lệ: {valid_chars}\nID bối cảnh hợp lệ: {valid_settings}"
            )
            fixed = llm_json(SYS_SCENE_FIX, user, temperature=0.5)
            fixed["character_ids"] = [c for c in fixed.get("character_ids", []) if c in valid_chars] or ["plukky"]
            if fixed.get("setting_id") not in valid_settings and valid_settings:
                fixed["setting_id"] = valid_settings[0]
            fixed["made_for_kids"] = True
            p.scenes[i] = fixed
            print(f"  -> fixed cảnh {sn}")
    p.save("09_scene_scripts_fixed.json", p.scenes)
    return p.scenes


# --------------------------------------------------------------------------- #
# BƯỚC 9 — Ráp prompt Seedance (DETERMINISTIC, không gọi LLM)
# --------------------------------------------------------------------------- #


def step9_assemble_seedance(p: Project) -> list[dict]:
    """Lắp canonical block theo ID -> prompt + reference images. Deterministic = consistency tuyệt đối."""
    print("[9] Ráp prompt Seedance...")
    manifest: list[dict] = []
    for scene in p.scenes:
        char_ids = scene.get("character_ids", [])
        setting_id = scene.get("setting_id")

        # Canonical blocks (nguyên văn từ bible — KHÔNG sinh lại)
        char_blocks = [
            p.bible["characters"][cid]["identity_lock"]
            for cid in char_ids
            if cid in p.bible["characters"]
        ]
        setting_block = (
            p.bible["settings"].get(setting_id, {}).get("identity_lock", "")
            if setting_id
            else ""
        )

        # Reference images (ảnh master sheet — Seedance nhét tối đa 9)
        ref_images = [f"references/{cid}.png" for cid in char_ids if cid in p.bible["characters"]]
        if setting_id and setting_id in p.bible["settings"]:
            ref_images.append(f"references/{setting_id}.png")

        # Lắp positive prompt
        parts = [
            "Use the exact characters and setting from the reference images, "
            "maintain perfect consistency, no drift, no deformation.",
            "CHARACTERS: " + " | ".join(char_blocks) if char_blocks else "",
            "SETTING: " + setting_block if setting_block else "",
            "ACTION: " + scene.get("action", ""),
            f"CAMERA: {scene.get('camera', '')}" if scene.get("camera") else "",
            f"Style: {GLOBAL_STYLE}.",
            "Maintain exact same appearance, clothing and proportions for every character throughout.",
        ]
        positive = " ".join(part for part in parts if part).strip()

        manifest.append(
            {
                "scene_number": scene.get("scene_number"),
                "duration_sec": scene.get("duration_sec", DEFAULT_DURATION),
                "aspect_ratio": ASPECT_RATIO,
                "resolution": RESOLUTION,
                "reference_images": ref_images,
                "positive_prompt": positive,
                "negative_prompt": NEGATIVE_PROMPT,
                "dialogue_vi": scene.get("dialogue_vi", ""),
                "made_for_kids": True,
            }
        )

    p.save("10_seedance_manifest.json", manifest)

    # Bản đọc cho người (.txt)
    lines = [
        f"# {p.script.get('title', p.topic)}",
        f"# Bài học: {p.script.get('lesson', '')}",
        f"# MADE FOR KIDS = TRUE (bật flag này khi upload YouTube — COPPA)",
        "",
    ]
    for m in manifest:
        lines += [
            "=" * 70,
            f"CẢNH {m['scene_number']}  |  {m['duration_sec']}s  |  {m['aspect_ratio']} {m['resolution']}",
            f"Reference images: {', '.join(m['reference_images'])}",
            "",
            "POSITIVE:",
            m["positive_prompt"],
            "",
            "NEGATIVE:",
            m["negative_prompt"],
            "",
            f"Thoại (VI): {m['dialogue_vi']}",
            "",
        ]
    (p.out_dir / "seedance_prompts.txt").write_text("\n".join(lines), encoding="utf-8")
    print(f"  -> saved {p.out_dir / 'seedance_prompts.txt'}")
    return manifest


# --------------------------------------------------------------------------- #
# Orchestrator
# --------------------------------------------------------------------------- #


def run_pipeline(topic: str, out_dir: Path, n_scenes: int) -> Project:
    p = Project(topic=topic, out_dir=out_dir, n_scenes=n_scenes)
    print(f"\n=== PLUKKY PIPELINE: {topic} ===")
    print(f"Model: {MODEL} @ {API_BASE}\n")

    step2_generate_script(p)
    step3_review_and_revise(p)
    ents = step4_extract_entities(p)
    step5_character_bible(p, ents.get("characters", []))
    step6_setting_bible(p, ents.get("settings", []))
    step7_scene_scripts(p)
    step8_continuity_review(p)
    step9_assemble_seedance(p)

    # Lưu bible gộp (single source of truth)
    p.save("bible.json", p.bible)
    print("\n=== XONG ===")
    print(f"Artifacts: {p.out_dir}")
    print("Bước tiếp theo của mày:")
    print("  1. Tạo ảnh master từ reference_image_prompt trong bible.json (Leonardo/Flux)")
    print(f"     -> lưu vào {p.out_dir / 'references'}/<id>.png")
    print("  2. Feed seedance_prompts.txt / 10_seedance_manifest.json vào Seedance 2.0")
    print("  3. Ghép clip + TTS (MoviePy) — đánh dấu Made for Kids khi upload")
    return p


def main() -> None:
    ap = argparse.ArgumentParser(description="Plukky episode pipeline")
    ap.add_argument("topic", help="Chủ đề tập phim")
    ap.add_argument("--scenes", type=int, default=8, help="Số cảnh mong muốn")
    ap.add_argument("--out", default="./episodes", help="Thư mục output gốc")
    args = ap.parse_args()

    slug = re.sub(r"[^a-z0-9]+", "_", args.topic.lower())[:40].strip("_") or "episode"
    out_dir = Path(args.out) / slug

    try:
        run_pipeline(args.topic, out_dir, args.scenes)
    except Exception as e:  # noqa: BLE001
        print(f"\n[LỖI] {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()