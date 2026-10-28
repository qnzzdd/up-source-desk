"""内容推断：字段抽取 + 置信度约束 + 信息不足时拒绝编造。

LLM 是可替换的适配器；未配置端点时返回 InformationInsufficient，不伪造结果。
"""
from __future__ import annotations

import hashlib
import json
import os
from dataclasses import dataclass, field
from typing import Any

import httpx

from app.policy import GroupPolicy, InferenceMode

SYSTEM_PROMPT = """你是一个内容摘要助手。你只能依据给定材料判断内容，不得补充材料中没有的信息。

规则：
1. 材料不足时，information_sufficiency 必须输出 "low"，possible_content 留空。
2. evidence 只能引用材料原文片段，不得改写或推测。
3. confidence 不得超过材料类型允许的上限。
4. 不得描述视频画面、剧情、结论，除非材料中明确写出。
5. worth_reading 只给判据（"若你需要 X"），不替用户做决定。

只输出 JSON，字段：subject_tags, possible_content, evidence, information_sufficiency, worth_reading, confidence。"""


@dataclass
class InferenceInput:
    target_type: str          # video | dynamic
    target_id: str
    title: str = ""
    desc: str = ""
    comments: list[str] = field(default_factory=list)
    image_text: str = ""
    mode: str = InferenceMode.TITLE.value

    def payload_text(self) -> str:
        parts = [f"标题：{self.title}" if self.title else ""]
        if self.desc:
            parts.append(f"简介：{self.desc[:300]}")
        if self.comments:
            parts.append("热评摘录：\n" + "\n".join(f"- {c[:120]}" for c in self.comments[:10]))
        if self.image_text:
            parts.append(f"图片文字：{self.image_text[:400]}")
        return "\n".join(p for p in parts if p)

    @property
    def input_hash(self) -> str:
        raw = json.dumps(
            {"t": self.title, "d": self.desc, "c": self.comments, "i": self.image_text},
            ensure_ascii=False,
            sort_keys=True,
        )
        return hashlib.sha256(raw.encode()).hexdigest()[:32]


@dataclass
class InferenceResult:
    subject_tags: list[str]
    possible_content: str
    evidence: list[str]
    information_sufficiency: str
    worth_reading: str
    confidence: float
    input_hash: str
    model: str = ""
    prompt_version: str = "v1"

    def as_payload(self) -> dict[str, Any]:
        return {
            "subject_tags": self.subject_tags,
            "possible_content": self.possible_content,
            "evidence": self.evidence,
            "information_sufficiency": self.information_sufficiency,
            "worth_reading": self.worth_reading,
            "confidence": round(self.confidence, 3),
            "model": self.model,
            "prompt_version": self.prompt_version,
        }


def insufficient(inp: InferenceInput, reason: str = "材料不足") -> InferenceResult:
    return InferenceResult(
        subject_tags=[],
        possible_content="",
        evidence=[reason],
        information_sufficiency="low",
        worth_reading="信息不足，未作判断",
        confidence=0.0,
        input_hash=inp.input_hash,
    )


def clamp(payload: dict, policy: GroupPolicy, inp: InferenceInput) -> InferenceResult:
    """把模型输出夹到策略允许的范围内。这是防幻觉的最后一道闸门。"""
    cap = policy.confidence_cap()
    tags = [str(t)[:20] for t in (payload.get("subject_tags") or [])][:5]
    evidence = [str(e)[:120] for e in (payload.get("evidence") or [])][:5]
    content = str(payload.get("possible_content") or "").strip()
    sufficiency = str(payload.get("information_sufficiency") or "low").lower()
    try:
        conf = float(payload.get("confidence") or 0.0)
    except (TypeError, ValueError):
        conf = 0.0

    # 无证据 → 强制降级为信息不足
    if not evidence or not content:
        return insufficient(inp, "模型未给出可引用的证据")

    conf = max(0.0, min(conf, cap))
    # 只有标题时措辞必须谨慎
    if InferenceMode(inp.mode) is InferenceMode.TITLE:
        sufficiency = "low" if conf <= 0.4 else "medium"

    return InferenceResult(
        subject_tags=tags,
        possible_content=content[:200],
        evidence=evidence,
        information_sufficiency=sufficiency,
        worth_reading=str(payload.get("worth_reading") or "")[:100],
        confidence=conf,
        input_hash=inp.input_hash,
        model=str(payload.get("_model") or ""),
    )


class LLMClient:
    """OpenAI 兼容端点。未配置时 enabled=False。"""

    def __init__(self) -> None:
        self.base = os.environ.get("UPSD_LLM_BASE", "").rstrip("/")
        self.key = os.environ.get("UPSD_LLM_KEY", "")
        self.model = os.environ.get("UPSD_LLM_MODEL", "")
        self.timeout = float(os.environ.get("UPSD_LLM_TIMEOUT", "60"))

    @property
    def enabled(self) -> bool:
        return all([self.base, self.key, self.model])

    def infer(self, inp: InferenceInput, policy: GroupPolicy) -> InferenceResult:
        if not self.enabled:
            return insufficient(inp, "未配置模型端点")
        if InferenceMode(policy.inference) is InferenceMode.NONE:
            return insufficient(inp, "该分组关闭了推断")
        text = inp.payload_text()
        if len(text.strip()) < 8:
            return insufficient(inp, "材料不足")

        body = {
            "model": self.model,
            "temperature": 0.2,
            "response_format": {"type": "json_object"},
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": f"置信度上限：{policy.confidence_cap()}\n\n{text}"},
            ],
        }
        with httpx.Client(timeout=self.timeout) as c:
            resp = c.post(
                f"{self.base}/chat/completions",
                headers={"Authorization": f"Bearer {self.key}"},
                json=body,
            )
            resp.raise_for_status()
            raw = resp.json()["choices"][0]["message"]["content"]
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError:
            return insufficient(inp, "模型输出不是合法 JSON")
        payload["_model"] = self.model
        return clamp(payload, policy, inp)
