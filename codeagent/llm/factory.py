from __future__ import annotations

from codeagent.config import Settings
from codeagent.llm.openai_compatible import OpenAICompatibleClient


def create_llm(settings: Settings) -> OpenAICompatibleClient:
    if not settings.api_key:
        raise ValueError("缺少 API key：请在 .env 中设置对应的密钥变量")
    if not settings.base_url:
        raise ValueError(f"未知 LLM_PROVIDER={settings.provider!r}，且未设置 LLM_BASE_URL")
    if not settings.model:
        raise ValueError("未设置模型名：请配置 DEEPSEEK_MODEL 或 LLM_MODEL")
    return OpenAICompatibleClient(
        api_key=settings.api_key,
        base_url=settings.base_url,
        model=settings.model,
    )
