"""对话问答：问题解析 → 图库检索 → 摘要回答；失败返回引导语（软失败）。"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from app.ai.prompts import build_chat_parse_prompt, parse_chat_json
from app.domain.errors import NotFoundError
from app.services import search_svc

if TYPE_CHECKING:
    from app.services.state import AppState

QUESTION_LIMIT = 400
GUIDANCE = (
    "对话服务暂不可用，你可以改用「检索」页：输入关键词、标签、时间范围或分类筛选，"
    "同样可以找到想要的图片。"
)
ANSWER_GUIDANCE = (
    "我暂时无法直接回答，但根据关键词已为你筛出候选图片；"
    "若需要更精确的结果，可在检索页组合筛选条件。"
)


def _summaries(state: AppState, items: list[dict[str, Any]]) -> list[str]:
    lines = []
    for row in items[:12]:
        desc = str(row.get("description_manual") or row.get("description_ai") or "")
        category = str(row.get("category_manual") or row.get("category_ai") or "未分类")
        lines.append(f"#{row['id']} {row['filename']}｜分类:{category}｜{desc[:60]}")
    return lines


def ask(state: AppState, question: str) -> dict[str, Any]:
    question = str(question or "").strip()[:QUESTION_LIMIT]
    if not question:
        return {"answer": "请输入你想找的图片内容。", "items": [], "degraded": False}
    chat = state.get_chat()
    parsed: dict[str, Any] = {}
    if chat is None:
        # 无对话档案：降级为关键词检索（主链路不受影响）
        result = search_svc.search(state, {"q": question, "limit": 12})
        return {
            "answer": GUIDANCE,
            "items": result["items"],
            "degraded": True,
            "question": question,
        }
    try:
        categories = [str(row["name"]) for row in state.catalog.list_categories()]
        output = chat.complete(
            [{"role": "user", "content": build_chat_parse_prompt(question, categories)}]
        )
        state.images.add_token_usage(
            None, "chat", output.model, output.tokens_in, output.tokens_out
        )
        parsed = parse_chat_json(output.content) or {}
    except Exception:  # noqa: BLE001 — 对话失败返回引导语
        return {"answer": GUIDANCE, "items": [], "degraded": True, "question": question}

    keywords = [str(k) for k in parsed.get("keywords") or [] if str(k).strip()]
    params: dict[str, Any] = {
        "q": " ".join(keywords) or question,
        "limit": 24,
        "category": parsed.get("category") or None,
        "date_from": parsed.get("date_from") or None,
        "date_to": parsed.get("date_to") or None,
        "rating_min": parsed.get("rating_min") or None,
    }
    result = search_svc.search(state, params)
    items = result["items"]
    answer = ""
    need_answer = bool(parsed.get("need_answer"))
    if need_answer:
        try:
            summary = "\n".join(_summaries(state, items)) or "（没有匹配的图片）"
            reply = chat.complete(
                [
                    {"role": "system", "content": "根据图片库检索结果回答用户，简洁、用中文。"},
                    {"role": "user", "content": f"问题：{question}\n候选图片：\n{summary}"},
                ]
            )
            answer = reply.content.strip()
            state.images.add_token_usage(
                None, "chat", reply.model, reply.tokens_in, reply.tokens_out
            )
        except Exception:  # noqa: BLE001 — 第二段失败仍返回结果
            answer = ANSWER_GUIDANCE
    else:
        answer = ANSWER_GUIDANCE if items else "没有找到匹配的图片，换个说法试试？"
    _proposals_from(state, parsed)
    return {
        "answer": answer or ANSWER_GUIDANCE,
        "items": items,
        "degraded": False,
        "question": question,
        "parsed": {
            "keywords": keywords,
            "category": parsed.get("category"),
            "date_from": parsed.get("date_from"),
            "date_to": parsed.get("date_to"),
            "rating_min": parsed.get("rating_min"),
        },
    }


def _proposals_from(state: AppState, parsed: dict[str, Any]) -> None:
    """对话建议：写入提案队列，批准前库零变化。"""
    entity = parsed.get("suggest_entity")
    if isinstance(entity, dict) and entity.get("name"):
        state.catalog.add_proposal(
            "entity",
            {
                "name": str(entity["name"]),
                "category": str(entity.get("category", "")),
                "description": str(entity.get("description", "")),
                "aliases": [str(a) for a in entity.get("aliases", [])],
            },
            source="chat",
        )
    tag = parsed.get("suggest_tag")
    if isinstance(tag, str) and tag.strip():
        state.catalog.add_proposal("tag", {"tag": tag.strip()}, source="chat")


def list_proposals(state: AppState, status: str | None = None) -> list[dict[str, Any]]:
    return state.catalog.list_proposals(status)


def decide_proposal(state: AppState, proposal_id: int, decision: str) -> dict[str, Any]:
    if decision not in ("approved", "rejected"):
        from app.domain.errors import ValidationAppError

        raise ValidationAppError("decision 必须是 approved 或 rejected")
    proposal = state.catalog.decide_proposal(proposal_id, decision)
    if proposal is None:
        raise NotFoundError(f"提案不存在：{proposal_id}")
    if decision == "approved":
        payload = proposal.get("payload") or {}
        if proposal["type"] == "entity":
            name = str(payload.get("name", "")).strip()
            if name and state.entities.get_by_name(name) is None:
                entity_id = state.entities.add(
                    name,
                    str(payload.get("category", "")),
                    str(payload.get("description", "")),
                    [str(a) for a in payload.get("aliases", [])],
                )
                from app.services.entities_svc import embed_entity

                embed_entity(state, entity_id, state.get_embed())
        elif proposal["type"] == "tag":
            tag = str(payload.get("tag", "")).strip()
            if tag:
                state.db.execute("INSERT OR IGNORE INTO tags(name) VALUES(?)", (tag,))
    return proposal
