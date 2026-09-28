"""设置服务：schema 驱动读写、审计回滚、档案（.env）管理、连接探测、备份。"""

from __future__ import annotations

import shutil
import time
from pathlib import Path
from typing import TYPE_CHECKING, Any

import httpx

from app.domain import settings_schema as schema
from app.domain.errors import NotFoundError, ValidationAppError
from app.storage.stats_repo import SettingsRepo

if TYPE_CHECKING:
    from app.services.state import AppState


class ProfileStore:
    """服务档案：base_url/type 进 settings，密钥只进 .env（界面可读回明文）。"""

    def __init__(self, env_path: Path) -> None:
        self.env_path = env_path

    def _read_env(self) -> dict[str, str]:
        result: dict[str, str] = {}
        if not self.env_path.exists():
            return result
        for line in self.env_path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            result[key.strip()] = value.strip()
        return result

    def _write_env(self, values: dict[str, str]) -> None:
        lines = [f"{key}={value}" for key, value in sorted(values.items())]
        self.env_path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    @staticmethod
    def key_name(profile: str) -> str:
        safe = "".join(ch if ch.isalnum() else "_" for ch in profile).upper()
        return f"PA_KEY_{safe}"

    def get_key(self, profile: str) -> str:
        return self._read_env().get(self.key_name(profile), "")

    def set_key(self, profile: str, value: str) -> None:
        values = self._read_env()
        values[self.key_name(profile)] = value
        self._write_env(values)

    def delete_key(self, profile: str) -> None:
        values = self._read_env()
        values.pop(self.key_name(profile), None)
        self._write_env(values)


class SettingsService:
    def __init__(self, state: AppState, repo: SettingsRepo, profiles: ProfileStore) -> None:
        self._state = state
        self._repo = repo
        self._profiles = profiles

    # ---------- 读 ----------

    def get(self, key: str, default: Any = None) -> Any:
        item = schema.find(key)
        stored = self._repo.get(key, None)
        if stored is None:
            return item.default if item is not None else default
        if item is not None and item.type == "csv" and isinstance(stored, str):
            return schema.coerce(key, stored)
        return stored

    def get_str(self, key: str, default: str = "") -> str:
        value = self.get(key, default)
        return str(value) if value is not None else default

    def get_int(self, key: str, default: int = 0) -> int:
        try:
            return int(self.get(key, default))
        except (TypeError, ValueError):
            return default

    def get_float(self, key: str, default: float = 0.0) -> float:
        try:
            return float(self.get(key, default))
        except (TypeError, ValueError):
            return default

    def get_bool(self, key: str, default: bool = False) -> bool:
        value = self.get(key, default)
        return bool(value)

    def get_list(self, key: str) -> list[str]:
        value = self.get(key, [])
        if isinstance(value, list):
            return [str(v) for v in value]
        if isinstance(value, str):
            return schema.coerce(key, value) if isinstance(schema.coerce(key, value), list) else []
        return []

    def values(self) -> dict[str, Any]:
        merged = schema.defaults()
        for key, value in self._repo.all().items():
            if key.startswith("profile_") or key == "profiles" or key in merged or schema.find(key):
                merged[key] = value
        return merged

    # ---------- 写 ----------

    def set(self, key: str, value: Any) -> Any:
        item = schema.find(key)
        if item is None and key not in ("profiles",):
            raise ValidationAppError(f"未知配置项：{key}")
        coerced = schema.coerce(key, value) if item is not None else value
        if not self.get_bool("audit_enabled", True):
            self._repo.set(key, coerced, action="update-noaudit")
        else:
            self._repo.set(key, coerced, action="update")
        self._after_change(key, coerced)
        return coerced

    def bulk_set(self, payload: dict[str, Any]) -> dict[str, Any]:
        return {key: self.set(key, value) for key, value in payload.items()}

    def _after_change(self, key: str, value: Any) -> None:
        state = self._state
        if key in ("rate_limit_per_minute", "min_interval_seconds"):
            from app.domain.rate_limit import RateConfig

            state.limiter.reconfigure(
                RateConfig(
                    per_minute=int(state.settings.get("rate_limit_per_minute", 20)),
                    min_interval=float(state.settings.get("min_interval_seconds", 3.0)),
                )
            )

    # ---------- schema / 审计 ----------

    def schema_payload(self) -> dict[str, Any]:
        payload = schema.schema_payload()
        payload["values"] = self.values()
        payload["danger_groups"] = ["G10"]
        return payload

    def audit(self, limit: int = 100) -> list[dict[str, Any]]:
        return self._repo.audit(limit)

    def rollback(self, audit_id: int) -> None:
        if not self._repo.rollback(audit_id):
            raise NotFoundError("审计记录不存在")
        row = next((r for r in self._repo.audit(500) if r["id"] == audit_id), None)
        if row is not None:
            self._after_change(str(row["key"]), row.get("before"))

    # ---------- 档案 ----------

    def list_profiles(self) -> list[dict[str, Any]]:
        profiles = self._repo.get("profiles", []) or []
        result: list[dict[str, Any]] = []
        for profile in profiles:
            item = dict(profile)
            key = self._profiles.get_key(str(item.get("name", "")))
            item["api_key"] = key
            item["api_key_set"] = bool(key)
            result.append(item)
        return result

    def save_profile(self, profile: dict[str, Any]) -> dict[str, Any]:
        name = str(profile.get("name", "")).strip()
        if not name:
            raise ValidationAppError("档案名称不能为空")
        base_url = str(profile.get("base_url", "")).strip()
        if not base_url.startswith(("http://", "https://")):
            raise ValidationAppError("base_url 必须以 http(s):// 开头")
        ptype = str(profile.get("type", "openai"))
        if ptype not in ("openai", "ollama", "lmstudio"):
            raise ValidationAppError("档案类型必须是 openai / ollama / lmstudio")
        profiles = [dict(p) for p in (self._repo.get("profiles", []) or [])]
        entry = {"name": name, "base_url": base_url, "type": ptype}
        profiles = [p for p in profiles if p.get("name") != name]
        profiles.append(entry)
        self._repo.set("profiles", profiles, action="profile-save")
        api_key = str(profile.get("api_key", "") or "")
        if api_key:
            self._profiles.set_key(name, api_key)
        return {
            **entry,
            "api_key": self._profiles.get_key(name),
            "api_key_set": bool(self._profiles.get_key(name)),
        }

    def delete_profile(self, name: str) -> None:
        profiles = [dict(p) for p in (self._repo.get("profiles", []) or [])]
        remaining = [p for p in profiles if p.get("name") != name]
        if len(remaining) == len(profiles):
            raise NotFoundError(f"档案不存在：{name}")
        self._repo.set("profiles", remaining, action="profile-delete")
        self._profiles.delete_key(name)

    def resolved_profile(self, usage: str) -> dict[str, Any] | None:
        """四用途绑定（支持 @follow 跟随）。"""
        key = f"profile_{usage}"
        name = self.get_str(key, "default")
        seen: set[str] = set()
        while name.startswith("@"):
            if name in seen:
                return None
            seen.add(name)
            follow = {"@vision": "vision", "@chat": "chat", "@enhance": "enhance"}.get(name)
            if follow is None:
                return None
            name = self.get_str(f"profile_{follow}", "default")
        profiles = self._repo.get("profiles", []) or []
        for profile in profiles:
            if profile.get("name") == name:
                result = dict(profile)
                result["api_key"] = self._profiles.get_key(name)
                return result
        for profile in profiles:
            if profile.get("name") == "default":
                result = dict(profile)
                result["api_key"] = self._profiles.get_key("default")
                return result
        return profiles[0] if profiles else None

    def model_for(self, usage: str) -> str:
        return self.get_str(f"{usage}_model", "")

    # ---------- 探测 / 备份 ----------

    def probe(self, base_url: str, api_key: str) -> dict[str, Any]:
        started = time.monotonic()
        url = base_url.rstrip("/") + "/models"
        try:
            response = httpx.get(
                url,
                headers={"Authorization": f"Bearer {api_key}"} if api_key else {},
                timeout=10.0,
            )
            latency = int((time.monotonic() - started) * 1000)
            if response.status_code >= 400:
                return {
                    "ok": False,
                    "latency_ms": latency,
                    "error": f"服务返回 {response.status_code}",
                }
            return {"ok": True, "latency_ms": latency, "error": ""}
        except httpx.HTTPError as exc:
            return {
                "ok": False,
                "latency_ms": int((time.monotonic() - started) * 1000),
                "error": f"连接失败：{exc.__class__.__name__}",
            }

    def backup(self) -> Path:
        backup_dir = self._state.data_dir / "backups"
        backup_dir.mkdir(parents=True, exist_ok=True)
        stamp = time.strftime("%Y%m%d-%H%M%S")
        target = backup_dir / f"library-{stamp}.db"
        shutil.copy2(self._state.db.path, target)
        retain = self.get_int("backup_retain", 7)
        backups = sorted(backup_dir.glob("library-*.db"))
        for old in backups[:-retain]:
            old.unlink(missing_ok=True)
        return target

    def profiles_payload(self) -> dict[str, Any]:
        return {
            "profiles": self.list_profiles(),
            "bindings": {
                k: self.get(k)
                for k in ("profile_vision", "profile_embed", "profile_chat", "profile_enhance")
            },
            "models": {k: self.get(k) for k in ("vision_model", "embed_model", "chat_model")},
        }
