# Plukky – Sheriff Tây Nguyên YouTube Channel Project

**Kênh hoạt hình trẻ em phong cách Sheriff Labrador dùng AI + Local Automation**

**Tác giả**: Dev cá nhân  
**Mục tiêu**: Xây kênh kiếm $5k–15k/tháng trong 12-18 tháng với chi phí thấp (~$80/tháng)

---

## 1. Executive Summary

- **Tên kênh**: Plukky – Sheriff Tây Nguyên (Plukky & Friends)
- **Nhân vật chính**: Chú Voi Plukky – voi con xám má hồng từ Đắk Lắk, mặc mũ sheriff, áo vest cảnh sát.
- **Concept**: Hoạt hình 3D vui nhộn, dạy trẻ 2-6 tuổi về an toàn, thói quen tốt, tình bạn qua phiêu lưu rừng núi Tây Nguyên.
- **Mô hình**: Seedance 2.0 (video) + Local LLM (script) + Local TTS (voice) + Python automation (edit).
- **Lợi thế**: Tự động hóa cao, thời gian làm ~1 giờ/tập, chi phí thấp.

**Mục tiêu**:
- 3 tháng: 10k sub + bật monetization
- 9-12 tháng: 100k+ sub, $3k–10k/tháng
- 18 tháng: Scale lớn $10k–15k+/tháng

---

## 2. Branding & Character

**Plukky Character DNA** (dùng làm Identity Lock):
- Cute baby elephant, gray skin, round body, big head, short trunk
- Pink cheeks, big sparkling friendly eyes
- Outfit cố định: small brown sheriff hat with yellow star, blue police vest, red scarf
- Bối cảnh: Rừng núi Đắk Lắk, cà phê, sông suối, cồng chiêng nhẹ

**Bạn bè**: Khỉ rừng, Gấu nâu, Thỏ núi, Chim...

---

## 3. Quy Trình Sản Xuất (45-75 phút/tập)

1. **Script & Prompt** → Local Ollama (Qwen2.5-14B)
2. **Video Clips** → Seedance 2.0 (Image-to-Video với reference mạnh)
3. **Voiceover** → Local VieNeu-TTS / XTTS
4. **Edit & Export** → Python + MoviePy + FFmpeg (automation script)

### Prompt Consistency (Identity Lock)

**Template chính**:
```
Use exact character from reference @Plukky, maintain perfect consistency: cute baby elephant gray skin, round body, big head, short trunk, pink cheeks, big sparkling eyes, wearing fixed small brown sheriff hat with yellow star, blue police vest, red scarf, identical proportions and clothing as reference, no drift, no deformation.

[Action description]

Style: bright colorful 3D cartoon exactly like Sheriff Labrador, vibrant colors, child-friendly.
Maintain exact same Plukky appearance throughout.
```

**Negative Prompt**:
```
deformed, mutated, changing clothes, face drift, body deformation, inconsistent proportions, dark colors, realistic
```

---

## 4. Local Stack (Dev Optimization)

### Ollama (Script + Prompt)
```bash
ollama run qwen2.5:14b
# Hoặc model nhỏ hơn nếu RAM hạn chế
```

### TTS Vietnamese
- Repo khuyến nghị: `pnnbao97/VieNeu-TTS` hoặc XTTS fine-tune
- Voice cloning: Ghi 10-20s giọng vui nhộn một lần → dùng reference

### Automation
- Python script pipeline: Chủ đề → Script → Breakdown → TTS → Ghép clips
- MoviePy / FFmpeg cho batch editing

---

## 5. Chi Phí Hàng Tháng (2026)

**Starter (1-2 video/tuần)**: $40–70  
**Scale (4-7 video/tuần)**: $80–150 (sau local: voice + script ≈ 0)

Chi tiết:
- Seedance 2.0: $45–85
- Leonardo reference: $10–30
- Khác: thấp

---

## 6. Timeline 12 Tuần Đầu

- **Tuần 1-2**: Setup local stack, character sheet, 8-10 script pilot
- **Tuần 3-6**: Upload 1 video/ngày + Shorts
- **Tuần 7-12**: Tối ưu analytics, scale

---

## 7. Proposal Chi Tiết

Xem phần sau hoặc file `PROPOSAL.md` (sẽ tạo sau nếu cần).

**Next Actions**:
1. Setup Ollama + TTS local
2. Tạo master Character Sheet (Leonardo/Flux)
3. Làm 3 video pilot
4. Tạo kênh YouTube + banner
5. Upload đều + track retention

---

## 8. Resources & Templates

- **Prompt ChatGPT/Ollama** (đã có ở lịch sử chat)
- **Character Sheet Prompt**
- **Script Template**

**Lưu ý**:
- Luôn đánh dấu “Made for Kids” (COPPA)
- Không copy trực tiếp nhân vật Sheriff Labrador
- Kiên trì upload là chìa khóa

---

**File này là trung tâm dự án. Update thường xuyên.**

**Version**: 1.0 - June 2026
**Contact**: [Your info]

```

**File README.md đã được tạo thành công tại `/home/workdir/artifacts/README.md`** 

Bạn có muốn tôi:
- Tạo thêm file PROPOSAL.md chi tiết hơn?
- Thêm script Python mẫu vào folder?
- Hoặc chỉnh sửa README? 

Cứ nói nhé! 🚀