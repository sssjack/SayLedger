"""语音模式：短语开关、语音合成、微信语音编码。

声音：默认晓伊（Edge，活泼可爱少女音），Edge 挂了自动切服务商的
shimmer 兜底；网页直接播 mp3，微信要转 SILK（带 STX 头）再走网关上传。
语音只用于聊天回复：备忘推送与周报推送（payload kind 为 memo/weekly）
保持文字，长文也不发语音。
"""
from __future__ import annotations

import asyncio
import hashlib
import io
import re
import secrets
import struct
import tempfile
import wave
from pathlib import Path
from typing import Any

from app.config import settings
from app.db import SessionLocal, VoiceSetting

DEFAULT_VOICE = "xiaoyi"
FALLBACK_VOICE = "shimmer"
# 网页与微信语音共用的长度上限：超过只发文字，避免几分钟的长语音。
MAX_VOICE_CHARS = 1000
MAX_TTS_CHARS = 2000

# Edge 声音：名字 -> (voice id, pitch)。pitch 只影响晓伊俏皮版。
EDGE_VOICES: dict[str, tuple[str, str]] = {
    "xiaoyi": ("zh-CN-XiaoyiNeural", "+0Hz"),
    "xiaoyi_cute": ("zh-CN-XiaoyiNeural", "+12Hz"),
    "xiaoxiao": ("zh-CN-XiaoxiaoNeural", "+0Hz"),
}


class VoiceError(Exception):
    pass


# ---------------------------------------------------------------- 设置

def get_voice_setting(db, user_id: int) -> dict[str, Any]:
    row = db.get(VoiceSetting, user_id)
    if row is None:
        return {"enabled": False, "voice": DEFAULT_VOICE}
    return {"enabled": bool(row.enabled), "voice": row.voice or DEFAULT_VOICE}


def set_voice_setting(db, user_id: int, enabled: bool | None = None,
                      voice: str | None = None) -> dict[str, Any]:
    """直接提交：网页流程在 prepare_chat 后会 rollback，设置不能依赖外层提交。"""
    row = db.get(VoiceSetting, user_id)
    if row is None:
        row = VoiceSetting(user_id=user_id, enabled=0, voice=DEFAULT_VOICE)
        db.add(row)
    if enabled is not None:
        row.enabled = 1 if enabled else 0
    if voice is not None:
        row.voice = voice
    db.commit()
    return {"enabled": bool(row.enabled), "voice": row.voice}


def get_voice_enabled_for_user(user_id: int) -> tuple[bool, str]:
    with SessionLocal() as db:
        setting = get_voice_setting(db, user_id)
    return setting["enabled"], setting["voice"]


# ---------------------------------------------------------------- 短语开关

_OFF_PATTERNS = ["不用语音", "不要语音", "别用语音", "关闭语音", "关掉语音",
                 "用文字", "改回文字", "换回文字", "文字对话", "文字模式"]
_ON_PATTERNS = ["发个语音试试", "用语音回答", "用语音回复", "用语音说", "以后用语音",
                "都用语音", "开启语音", "打开语音", "语音模式", "改成语音", "换成语音", "用语音"]
_LEAD_FILLERS = ["好了", "好吧", "好的", "嗯", "那么", "那就", "请"]
# 开关句里跟在短语后面的残余，出现这些只当开关、不当新问题。
_TAIL_FILLERS = {"跟我对话", "跟我说话", "跟我聊", "跟我聊天", "对话", "说话"}
_PUNCT = " \t，。！？!?,、；;：:"

_FILLER_CHARS = set("你我以后都") | set(_PUNCT)


def _strip_lead(text: str) -> str:
    changed = True
    while changed:
        changed = False
        text = text.lstrip(_PUNCT)
        for filler in _LEAD_FILLERS:
            if text.startswith(filler):
                text = text[len(filler):]
                changed = True
                break
        text = text.lstrip(_PUNCT)
    return text


def parse_voice_toggle(text: str) -> tuple[str | None, str | None]:
    """识别语音开关。返回 (动作, 继续处理的新文本)：

    - (\"on\"/\"off\", None)：整句只是开关，调用方直接回确认文案。
    - (\"on\"/\"off\", new_text)：开关 + 真问题，先改模式再用 new_text 继续走正常流程。
    - (None, text)：不是开关，原样处理。
    OFF 先于 ON 匹配，否则“不用语音”会被“用语音”误认成开启。
    """
    original = text.strip()
    s = _strip_lead(original)
    if s[:1] in ("你", "我"):
        s = _strip_lead(s[1:])
    for action, patterns in (("off", _OFF_PATTERNS), ("on", _ON_PATTERNS)):
        for pattern in patterns:
            idx = s.find(pattern)
            if idx < 0:
                continue
            before, after = s[:idx], s[idx + len(pattern):]
            # 规则 A：短语在句首（前面只剩你/我/以后/都这类填充词）。
            if before.strip("".join(_FILLER_CHARS)) == "":
                rest = after.lstrip(_PUNCT).lstrip("我").lstrip(_PUNCT)
                # “跟我对话吧，今天……”这类残余：先剥掉“跟我对话吧”这段填充，
                # 但填充词后必须紧跟吧/标点才剥，避免“对话记录”被误切。
                for filler in sorted(_TAIL_FILLERS, key=len, reverse=True):
                    if (rest.startswith(filler)
                            and (len(rest) == len(filler)
                                 or rest[len(filler)] in "吧啊了" + _PUNCT)):
                        rest = rest[len(filler):].lstrip("吧啊了" + _PUNCT)
                        break
                tail = rest.rstrip("吧啊了" + _PUNCT)
                if tail == "" or tail in _TAIL_FILLERS:
                    return action, None
                return action, rest
            # 规则 B：短语在句尾（后面只剩“我/吧/标点”），前面是真问题。
            tail = after.lstrip("我").strip(_PUNCT + "吧啊了")
            if tail == "":
                return action, before.strip(_PUNCT)
    return None, original


# ---------------------------------------------------------------- 合成

async def _edge_mp3(text: str, voice: str) -> bytes:
    import edge_tts

    voice_id, pitch = EDGE_VOICES[voice]
    communicate = edge_tts.Communicate(text, voice_id, pitch=pitch, receive_timeout=120)
    buffer = io.BytesIO()
    async for chunk in communicate.stream():
        if chunk.get("type") == "audio" and chunk.get("data"):
            buffer.write(chunk["data"])
    data = buffer.getvalue()
    if not data:
        raise VoiceError("Edge 没有返回音频")
    return data


def _apiyi_audio(text: str, voice: str, response_format: str) -> bytes:
    import httpx

    response = httpx.post(
        settings.ai_base_url + "/audio/speech",
        headers={"Authorization": "Bearer " + settings.ai_api_key},
        json={"model": "tts-1", "input": text, "voice": voice, "response_format": response_format},
        timeout=60)
    response.raise_for_status()
    if not response.content:
        raise VoiceError("服务商没有返回音频")
    return response.content


async def synthesize_mp3(text: str, voice: str = DEFAULT_VOICE) -> bytes:
    """网页播放用 mp3：Edge 优先，挂了切服务商 shimmer。"""
    if voice in EDGE_VOICES:
        try:
            return await _edge_mp3(text, voice)
        except Exception:
            pass
    return _apiyi_audio(text, FALLBACK_VOICE, "mp3")


def synthesize_mp3_sync(text: str, voice: str = DEFAULT_VOICE) -> bytes:
    return asyncio.run(synthesize_mp3(text, voice))


def mp3_to_pcm(mp3: bytes) -> tuple[bytes, int, int]:
    """mp3 -> (16bit 单声道 PCM, 采样率, 时长毫秒)。只给微信 SILK 用。"""
    import miniaudio

    with tempfile.TemporaryDirectory(prefix="sayledger-tts-") as directory:
        source = Path(directory) / "voice.mp3"
        source.write_bytes(mp3)
        decoded = miniaudio.decode_file(str(source))
    if decoded.nchannels == 2:
        samples = [(a + b) / 2 for a, b in zip(decoded.samples[0::2], decoded.samples[1::2])]
    else:
        samples = list(decoded.samples)
    rate = decoded.sample_rate
    if rate not in (8000, 12000, 16000, 24000):
        raise VoiceError(f"不支持的采样率 {rate}")
    pcm = struct.pack(f"<{len(samples)}h",
                      *(max(-32768, min(32767, int(v * 32767))) for v in samples))
    duration_ms = int(len(samples) / rate * 1000)
    if duration_ms <= 0:
        raise VoiceError("音频为空")
    return pcm, rate, duration_ms


def pcm_to_silk(pcm: bytes, rate: int = 24000) -> bytes:
    """PCM -> 微信 SILK（tencent=True 带 0x02 STX 头，微信客户端认这个）。"""
    import pilk_nogil

    with tempfile.TemporaryDirectory(prefix="sayledger-silk-") as directory:
        source = Path(directory) / "voice.pcm"
        target = Path(directory) / "voice.silk"
        source.write_bytes(pcm)
        pilk_nogil.encode(str(source), str(target), pcm_rate=rate, tencent=True)
        silk = target.read_bytes()
    if not silk.startswith(b"\x02#!SILK_V3"):
        raise VoiceError("SILK 编码结果不是微信格式")
    return silk


async def synthesize_pcm(text: str, voice: str = DEFAULT_VOICE) -> tuple[bytes, int, int]:
    """微信用 PCM：Edge mp3 转码优先，失败用服务商 pcm 直出。"""
    if voice in EDGE_VOICES:
        try:
            mp3 = await _edge_mp3(text, voice)
            return mp3_to_pcm(mp3)
        except Exception:
            pass
    pcm = _apiyi_audio(text, FALLBACK_VOICE, "pcm")
    return pcm, 24000, int(len(pcm) / 2 / 24000 * 1000)


def build_wechat_voice(text: str, voice: str = DEFAULT_VOICE) -> tuple[bytes, int]:
    """同步入口（投递循环里放线程池跑）：返回 (silk, 播放时长毫秒)。"""
    pcm, rate, duration_ms = asyncio.run(synthesize_pcm(text, voice))
    return pcm_to_silk(pcm, rate), duration_ms


def md5_hex(data: bytes) -> str:
    return hashlib.md5(data).hexdigest()


def random_aes_key() -> bytes:
    return secrets.token_bytes(16)
