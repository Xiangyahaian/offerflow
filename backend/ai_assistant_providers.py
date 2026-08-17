"""象遇 · 国内主流 OpenAI 兼容 API 预设。"""
from __future__ import annotations

from typing import Any, Dict, List

# 每项：id, label, base_url, models[{id, label}]
AI_ASSISTANT_PROVIDERS: List[Dict[str, Any]] = [
    {
        "id": "deepseek",
        "label": "DeepSeek",
        "base_url": "https://api.deepseek.com/v1",
        "models": [
            {"id": "deepseek-chat", "label": "DeepSeek Chat"},
            {"id": "deepseek-reasoner", "label": "DeepSeek Reasoner"},
        ],
    },
    {
        "id": "dashscope",
        "label": "通义千问 · 阿里云百炼",
        "base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1",
        "models": [
            {"id": "qwen-turbo", "label": "Qwen Turbo"},
            {"id": "qwen-plus", "label": "Qwen Plus"},
            {"id": "qwen-max", "label": "Qwen Max"},
            {"id": "qwen-long", "label": "Qwen Long"},
        ],
    },
    {
        "id": "zhipu",
        "label": "智谱 AI",
        "base_url": "https://open.bigmodel.cn/api/paas/v4",
        "models": [
            {"id": "glm-4-flash", "label": "GLM-4 Flash"},
            {"id": "glm-4-air", "label": "GLM-4 Air"},
            {"id": "glm-4-plus", "label": "GLM-4 Plus"},
        ],
    },
    {
        "id": "moonshot",
        "label": "Moonshot · Kimi",
        "base_url": "https://api.moonshot.cn/v1",
        "models": [
            {"id": "moonshot-v1-8k", "label": "Moonshot 8K"},
            {"id": "moonshot-v1-32k", "label": "Moonshot 32K"},
            {"id": "moonshot-v1-128k", "label": "Moonshot 128K"},
        ],
    },
    {
        "id": "doubao",
        "label": "豆包 · 火山方舟",
        "base_url": "https://ark.cn-beijing.volces.com/api/v3",
        "models": [
            {"id": "doubao-pro-32k", "label": "Doubao Pro 32K（请替换为方舟 Endpoint ID）"},
            {"id": "doubao-lite-32k", "label": "Doubao Lite 32K（请替换为方舟 Endpoint ID）"},
        ],
    },
    {
        "id": "baidu",
        "label": "百度千帆 · 文心",
        "base_url": "https://qianfan.baidubce.com/v2",
        "models": [
            {"id": "ernie-4.0-8k", "label": "ERNIE 4.0"},
            {"id": "ernie-3.5-8k", "label": "ERNIE 3.5"},
            {"id": "ernie-speed-8k", "label": "ERNIE Speed"},
        ],
    },
    {
        "id": "siliconflow",
        "label": "SiliconFlow",
        "base_url": "https://api.siliconflow.cn/v1",
        "models": [
            {"id": "deepseek-ai/DeepSeek-V3", "label": "DeepSeek V3"},
            {"id": "Qwen/Qwen2.5-72B-Instruct", "label": "Qwen2.5 72B"},
            {"id": "THUDM/glm-4-9b-chat", "label": "GLM-4 9B"},
        ],
    },
    {
        "id": "baichuan",
        "label": "百川智能",
        "base_url": "https://api.baichuan-ai.com/v1",
        "models": [
            {"id": "Baichuan4-Turbo", "label": "Baichuan4 Turbo"},
            {"id": "Baichuan3-Turbo", "label": "Baichuan3 Turbo"},
        ],
    },
    {
        "id": "minimax",
        "label": "MiniMax",
        "base_url": "https://api.minimax.chat/v1",
        "models": [
            {"id": "abab6.5s-chat", "label": "abab6.5s Chat"},
            {"id": "abab6.5g-chat", "label": "abab6.5g Chat"},
        ],
    },
    {
        "id": "stepfun",
        "label": "阶跃星辰 · Step",
        "base_url": "https://api.stepfun.com/v1",
        "models": [
            {"id": "step-2-16k", "label": "Step 2 16K"},
            {"id": "step-1-8k", "label": "Step 1 8K"},
        ],
    },
    {
        "id": "lingyi",
        "label": "零一万物",
        "base_url": "https://api.lingyiwanwu.com/v1",
        "models": [
            {"id": "yi-large", "label": "Yi Large"},
            {"id": "yi-medium", "label": "Yi Medium"},
            {"id": "yi-spark", "label": "Yi Spark"},
        ],
    },
    {
        "id": "openai",
        "label": "OpenAI 官方",
        "base_url": "https://api.openai.com/v1",
        "models": [
            {"id": "gpt-4o-mini", "label": "GPT-4o Mini"},
            {"id": "gpt-4o", "label": "GPT-4o"},
        ],
    },
    {
        "id": "custom",
        "label": "自定义 · OpenAI 兼容",
        "base_url": "",
        "models": [
            {"id": "custom-model", "label": "在下方填写模型名称"},
        ],
    },
]


def find_provider(provider_id: str) -> Dict[str, Any] | None:
    pid = (provider_id or "").strip().lower()
    for p in AI_ASSISTANT_PROVIDERS:
        if p["id"] == pid:
            return p
    return None
