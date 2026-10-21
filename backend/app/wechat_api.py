"""微信 iLink 协议适配，依据腾讯 openclaw-weixin 2.4.10 的公开实现。"""
from __future__ import annotations

import base64
import hashlib
import logging
import os
import secrets
import time
from functools import lru_cache
from urllib.parse import urlsplit

import httpx
from cryptography.fernet import Fernet, InvalidToken

from app.config import settings

API_BASE = "https://ilinkai.weixin.qq.com"
PROTOCOL_VERSION = "2.4.10"
CLIENT_VERSION = str((2 << 16) | (4 << 8) | 10)


class _HideWechatRequests(logging.Filter):
    def filter(self, record):
        # HTTPX 的 INFO 请求日志包含查询串，扫码值和配对数字不应进入日志。
        return "/ilink/bot/" not in record.getMessage()


logging.getLogger("httpx").addFilter(_HideWechatRequests())


class WechatError(RuntimeError):
    def __init__(self, message: str, *, expired: bool = False):
        super().__init__(message)
        self.expired = expired


def trusted_base(value: str) -> str:
    """只接受微信官方 HTTPS 域名，防止重定向泄露 Bot 凭证。"""
    parsed = urlsplit(value)
    try:
        valid = (parsed.scheme == "https" and parsed.hostname is not None
                 and parsed.hostname.endswith(".weixin.qq.com") and parsed.port in (None, 443)
                 and not parsed.username and not parsed.password and parsed.path in ("", "/")
                 and not parsed.query and not parsed.fragment)
    except ValueError:
        valid = False
    if not valid:
        raise WechatError("微信返回的服务地址无效，请稍后重新连接。")
    return f"https://{parsed.hostname}"


@lru_cache(maxsize=4)
def _cipher(directory: str, configured_key: str) -> Fernet:
    from pathlib import Path

    key = configured_key.encode()
    if not key:
        path = Path(directory) / "wechat.key"
        try:
            fd = os.open(str(path), os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        except FileExistsError:
            # 另一进程可能刚创建文件，等待一次很短的原子密钥写入。
            for _ in range(20):
                key = path.read_bytes().strip()
                if key:
                    break
                time.sleep(0.05)
        else:
            key = Fernet.generate_key()
            with os.fdopen(fd, "wb") as stream:
                stream.write(key)
                stream.flush()
                os.fsync(stream.fileno())
    try:
        return Fernet(key)
    except (ValueError, TypeError):
        raise WechatError("微信加密密钥无效，请检查服务配置。") from None


def seal(value: str) -> str:
    return _cipher(str(settings.data_dir), settings.wechat_encryption_key).encrypt(value.encode()).decode()


def unseal(value: str) -> str:
    if not value:
        return ""
    try:
        return _cipher(str(settings.data_dir), settings.wechat_encryption_key).decrypt(value.encode()).decode()
    except (InvalidToken, UnicodeError):
        raise WechatError("微信凭证无法解密，请恢复原加密密钥，或断开后重新扫码连接。") from None


def digest(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


class WechatAPI:
    def __init__(self):
        self.client = httpx.AsyncClient(timeout=15, follow_redirects=False)

    async def close(self):
        await self.client.aclose()

    async def request(self, method: str, endpoint: str, *, base: str = API_BASE,
                      token: str = "", body: dict | None = None, params: dict | None = None,
                      timeout: float = 15) -> dict:
        headers = {"iLink-App-Id": "bot", "iLink-App-ClientVersion": CLIENT_VERSION}
        if method == "POST":
            headers.update({"Content-Type": "application/json", "AuthorizationType": "ilink_bot_token",
                            "X-WECHAT-UIN": base64.b64encode(str(secrets.randbits(32)).encode()).decode()})
            if token:
                headers["Authorization"] = f"Bearer {token}"
                body = {**(body or {}), "base_info": {"channel_version": PROTOCOL_VERSION,
                                                       "bot_agent": "SayLedger/1.0"}}
        try:
            response = await self.client.request(method, trusted_base(base) + "/ilink/bot/" + endpoint,
                                                 headers=headers, json=body if method == "POST" else None,
                                                 params=params, timeout=timeout)
            response.raise_for_status()
            data = response.json()
            if not isinstance(data, dict):
                raise ValueError
        except httpx.TimeoutException:
            raise WechatError("微信连接超时，服务会自动重试。") from None
        except (httpx.HTTPError, ValueError):
            raise WechatError("暂时无法连接微信，请检查服务器网络后重试。") from None
        codes = [data.get("ret", 0), data.get("errcode", 0)]
        if any(code not in (0, None) for code in codes):
            expired = -14 in codes
            raise WechatError("微信登录已失效，请断开后重新扫码连接。" if expired
                              else "微信暂未接受请求，服务会自动重试。", expired=expired)
        return data

    async def qr(self) -> dict:
        data = await self.request("POST", "get_bot_qrcode", params={"bot_type": "3"},
                                  body={"local_token_list": []})
        if not all(isinstance(data.get(k), str) and 0 < len(data[k]) < 8192
                   for k in ("qrcode", "qrcode_img_content")):
            raise WechatError("微信未返回有效二维码，请稍后重试。")
        return data

    async def qr_status(self, base: str, qrcode: str, code: str = "") -> dict:
        params = {"qrcode": qrcode}
        if code:
            params["verify_code"] = code
        return await self.request("GET", "get_qrcode_status", base=base, params=params, timeout=40)

    async def updates(self, base: str, token: str, cursor: str) -> dict:
        return await self.request("POST", "getupdates", base=base, token=token,
                                  body={"get_updates_buf": cursor}, timeout=45)

    async def send(self, base: str, token: str, peer: str, context: str, client_id: str, text: str):
        if not context:
            raise WechatError("消息缺少回复上下文，请在微信里重新发送消息。")
        # 官方发送接口允许省略 ret；request 已校验 HTTP 状态及显式的非零业务错误码。
        await self.request("POST", "sendmessage", base=base, token=token, body={"msg": {
            "from_user_id": "", "to_user_id": peer, "client_id": client_id,
            "message_type": 2, "message_state": 2, "context_token": context,
            "item_list": [{"type": 1, "text_item": {"text": text}}],
        }})
