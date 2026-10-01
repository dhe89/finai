import json

import requests
import streamlit as st

OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
DEFAULT_MODEL = "google/gemma-3-12b-it:free"
FALLBACK_MODELS = [DEFAULT_MODEL, "openrouter/free"]

SYSTEM_PROMPT = """Anda adalah FinAI, asisten Financial Intelligence untuk analisis data keuangan bank.

ATURAN WAJIB:
1. Jawab hanya berdasarkan EVIDENCE yang diberikan oleh Python. EVIDENCE adalah satu-satunya sumber fakta dan angka.
2. Jangan mengarang angka, periode, tren, penyebab, target, atau informasi lain yang tidak ada di EVIDENCE.
3. Jangan menebak maksud pengguna. Jika pertanyaan belum jelas, Python seharusnya sudah menghentikan permintaan sebelum sampai ke Anda. Jika masih ada ambiguitas, minta klarifikasi secara singkat.
4. Jangan mengubah periode yang ada di EVIDENCE dan jangan menggunakan periode dari percakapan sebelumnya sebagai fakta.
5. Pesan assistant sebelumnya hanya konteks percakapan, BUKAN sumber data. Jangan mengambil angka dari pesan tersebut.
6. Jika EVIDENCE tidak memuat data yang diperlukan, katakan bahwa data tersebut tidak tersedia. Jangan melakukan estimasi atau inferensi yang tidak didukung EVIDENCE.
7. Untuk pertanyaan sebab-akibat, jelaskan hanya faktor yang dapat didukung langsung oleh angka/kelompok data dalam EVIDENCE. Gunakan frasa seperti “berdasarkan data” bila menyimpulkan dari perubahan angka.
8. Jangan menampilkan proses berpikir internal, self-talk, langkah pencarian, atau kalimat seperti “mari kita cek”, “mungkin pengguna bermaksud”, “let's check”, atau dugaan typo.
9. Jangan memberikan informasi yang tidak diperlukan untuk menjawab pertanyaan.
10. Gunakan bahasa Indonesia yang ringkas, jelas, dan profesional.
11. Jika pertanyaan meminta satu angka, berikan angka tersebut terlebih dahulu. Tambahkan konteks hanya jika diperlukan.
12. Unit angka mengikuti EVIDENCE. Jangan mengubah satuan tanpa menyebutkannya.
13. OUTPUT HARUS HANYA JAWABAN FINAL untuk pengguna. Jangan pernah menampilkan reasoning, chain-of-thought, langkah analisis, pemeriksaan evidence, self-talk, draft, atau label seperti “Analysis”, “Thinking process”, “Let's check”, “Response”.
14. Jangan menulis ulang EVIDENCE atau isi prompt.

Format jawaban:
- Pertanyaan fakta sederhana: satu jawaban langsung.
- Perbandingan: nilai periode yang dibandingkan + perubahan jika dapat dihitung dari EVIDENCE.
- Analisis: kesimpulan singkat lalu faktor pendukung yang benar-benar ada di EVIDENCE.
"""


def get_api_key():
    try:
        key = st.secrets.get("OPENROUTER_API_KEY", "")
        if not key:
            key = st.secrets.get("api_key", "")
        return str(key).strip() if key else None
    except Exception:
        return None


def _clean_final_answer(content):
    """Fail closed when a model leaks reasoning into the visible content."""
    text = str(content or "").strip()
    if not text:
        return ""

    lowered = text.lower()
    reasoning_markers = [
        "here's a thinking process:", "here is a thinking process:",
        "thinking process:", "chain of thought:", "reasoning:",
        "let's analyze", "let's check", "mari kita cek", "langkah analisis:",
    ]
    if any(marker in lowered for marker in reasoning_markers):
        # Prefer an explicit final-answer section if the model supplied one.
        for final_marker in ["response:", "jawaban:", "final answer:", "jawaban akhir:"]:
            idx = lowered.rfind(final_marker)
            if idx >= 0:
                candidate = text[idx + len(final_marker):].strip(" :\n")
                if candidate:
                    return candidate
        # No trustworthy final section: do not expose the leaked reasoning.
        return ""

    return text


def chat(messages, model=DEFAULT_MODEL, timeout=45, evidence=None, financial_context=None):
    """Call an answer model using only deterministic Python evidence."""
    api_key = get_api_key()
    if not api_key:
        return {"ok": False, "error": "API key OpenRouter belum ditemukan di Streamlit Secrets."}
    if evidence is None:
        evidence = financial_context
    if evidence is None:
        return {"ok": False, "error": "Evidence keuangan belum tersedia."}

    evidence_json = json.dumps(evidence, ensure_ascii=False, allow_nan=False, separators=(",", ":"))
    system_content = SYSTEM_PROMPT + "\n\nEVIDENCE DARI PYTHON (SUMBER FAKTA SATU-SATUNYA):\n" + evidence_json
    user_messages = [m for m in messages if m.get("role") == "user"][-4:]
    payload_messages = [{"role": "system", "content": system_content}]
    payload_messages.extend(user_messages)
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        "HTTP-Referer": "https://demuy89.streamlit.app",
        "X-Title": "FinAI",
    }

    models = [model] if model else []
    for candidate in FALLBACK_MODELS:
        if candidate not in models:
            models.append(candidate)
    errors=[]
    for candidate in models:
        payload = {
            "model": candidate,
            "messages": payload_messages,
            "temperature": 0.0,
            "max_tokens": 350,
            "reasoning": {"exclude": True},
        }
        try:
            response = requests.post(OPENROUTER_URL, headers=headers, json=payload, timeout=timeout)
        except requests.RequestException as exc:
            errors.append(f"{candidate}: {exc}")
            continue
        if response.status_code != 200:
            try:
                err=response.json().get("error", {})
                msg=err.get("message") or response.text
            except Exception:
                msg=response.text
            errors.append(f"{candidate}: HTTP {response.status_code} {msg}")
            continue
        try:
            data=response.json(); choices=data.get("choices") or []
            if not choices:
                errors.append(f"{candidate}: empty choices"); continue
            message=choices[0].get("message") or {}
            content=message.get("content")
            if isinstance(content,list):
                content="".join(str(x.get("text","")) if isinstance(x,dict) else str(x) for x in content)
            cleaned=_clean_final_answer(content)
            if cleaned:
                return {"ok":True,"content":cleaned,"model":candidate}
            errors.append(f"{candidate}: empty final content")
        except Exception as exc:
            errors.append(f"{candidate}: {exc}")
    return {"ok":False,"error":"; ".join(errors[-3:]) or "Model tidak mengembalikan jawaban final yang dapat ditampilkan."}
