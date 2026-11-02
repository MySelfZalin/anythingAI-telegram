from dataclasses import dataclass, field
from html import escape

from bot.storage import ModelUsage, UsageTotals


@dataclass(frozen=True)
class StatsView:
    model: str | None
    context_used: int | None
    context_limit: int | None
    session_messages: int
    session: UsageTotals
    today: UsageTotals
    total: UsageTotals
    by_model: list[ModelUsage] = field(default_factory=list)


def format_tokens(value: int) -> str:
    return f"{value:,}".replace(",", " ")


def format_cost(totals: UsageTotals) -> str:
    if totals.requests and totals.unpriced == totals.requests:
        return "цена не задана"
    cost = f"${totals.cost:.4f}"
    return f"{cost} (+{totals.unpriced} без цены)" if totals.unpriced else cost


def format_totals(totals: UsageTotals) -> str:
    return (
        f"{totals.requests} запр. · "
        f"⬆️ {format_tokens(totals.input_tokens)} · "
        f"⬇️ {format_tokens(totals.output_tokens)} · "
        f"{format_cost(totals)}"
    )


def format_context(used: int | None, limit: int | None) -> str:
    if limit is None:
        return "—"
    if used is None:
        return f"0 / {format_tokens(limit)}"
    return f"{format_tokens(used)} / {format_tokens(limit)} ({used / limit:.1%})"


def render_stats(view: StatsView) -> str:
    model = f"<code>{escape(view.model)}</code>" if view.model else "не выбрана"
    lines = [
        "📊 <b>Статистика</b>",
        "",
        f"🤖 Модель: {model}",
        f"🧠 Контекст: {format_context(view.context_used, view.context_limit)}",
        f"💬 Сообщений в сессии: {view.session_messages}",
        "",
        f"<b>Сессия:</b> {format_totals(view.session)}",
        f"<b>Сегодня (UTC):</b> {format_totals(view.today)}",
        f"<b>Всего:</b> {format_totals(view.total)}",
    ]
    if view.by_model:
        lines += ["", "<b>По моделям:</b>"]
        lines += [
            f"• <code>{escape(item.label)}</code>\n   {format_totals(item.totals)}"
            for item in view.by_model
        ]
    return "\n".join(lines)
