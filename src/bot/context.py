from bot.providers.base import ChatMessage

CHARS_PER_TOKEN = 3
MESSAGE_OVERHEAD = 4


def estimate_tokens(text: str) -> int:
    return len(text) // CHARS_PER_TOKEN + MESSAGE_OVERHEAD


def fit_context(messages: list[ChatMessage], budget: int) -> tuple[list[ChatMessage], bool]:
    kept = list(messages)
    total = sum(estimate_tokens(m.content) for m in kept)
    while len(kept) > 1 and (total > budget or kept[0].role != "user"):
        total -= estimate_tokens(kept.pop(0).content)
    return kept, len(kept) < len(messages)
