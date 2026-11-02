from bot.stats import StatsView, format_context, format_cost, render_stats
from bot.storage import ModelUsage, UsageTotals


def test_format_cost() -> None:
    assert format_cost(UsageTotals()) == "$0.0000"
    assert format_cost(UsageTotals(requests=2, cost=0.5)) == "$0.5000"
    assert format_cost(UsageTotals(requests=2, cost=0.5, unpriced=1)) == "$0.5000 (+1 без цены)"
    assert format_cost(UsageTotals(requests=2, unpriced=2)) == "цена не задана"


def test_format_context() -> None:
    assert format_context(None, None) == "—"
    assert format_context(None, 128000) == "0 / 128 000"
    assert format_context(32000, 128000) == "32 000 / 128 000 (25.0%)"


def test_render_stats_escapes_model_names() -> None:
    totals = UsageTotals(requests=1, input_tokens=10, output_tokens=5, cost=0.001)
    view = StatsView(
        model="evil/<b>",
        context_used=15,
        context_limit=1000,
        session_messages=2,
        session=totals,
        today=totals,
        total=totals,
        by_model=[ModelUsage("evil/<b>", totals)],
    )
    text = render_stats(view)
    assert "evil/<b>" not in text
    assert "<code>evil/&lt;b&gt;</code>" in text
    assert "1.5%" in text
