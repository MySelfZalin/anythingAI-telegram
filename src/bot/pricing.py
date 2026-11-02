from bot.config import ModelConfig
from bot.providers.base import Usage

TOKENS_PER_PRICE_UNIT = 1_000_000


def calculate_cost(usage: Usage, config: ModelConfig | None) -> float | None:
    if config is None or config.price_in is None or config.price_out is None:
        return None
    return (
        usage.input_tokens * config.price_in + usage.output_tokens * config.price_out
    ) / TOKENS_PER_PRICE_UNIT
