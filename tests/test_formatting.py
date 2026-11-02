from bot.formatting import markdown_to_html, split_text


def test_escapes_html() -> None:
    assert markdown_to_html("<script>&") == "&lt;script&gt;&amp;"


def test_basic_markdown() -> None:
    html = markdown_to_html("# Title\n**bold** *it* ~~no~~ `a<b`\n- item")
    assert html == "<b>Title</b>\n<b>bold</b> <i>it</i> <s>no</s> <code>a&lt;b</code>\n• item"


def test_code_block_is_not_formatted() -> None:
    html = markdown_to_html("```python\nx = **y** < 1\n```")
    assert html == '<pre><code class="language-python">x = **y** &lt; 1</code></pre>'


def test_links_only_http() -> None:
    assert markdown_to_html("[a](https://x.io/?q=1&b=2)") == (
        '<a href="https://x.io/?q=1&amp;b=2">a</a>'
    )
    assert markdown_to_html("[a](javascript:alert(1))") == "[a](javascript:alert(1))"


def test_snake_case_is_not_italic() -> None:
    assert markdown_to_html("2 * 3 * 4 and snake_case_name") == "2 * 3 * 4 and snake_case_name"


def test_split_short_text() -> None:
    assert split_text("hello") == ["hello"]


def test_split_respects_limit() -> None:
    text = "\n".join(f"line {i}" for i in range(500))
    chunks = split_text(text, limit=200)
    assert all(len(chunk) <= 200 for chunk in chunks)
    assert "\n".join(chunks) == text


def test_split_reopens_code_fence() -> None:
    text = "```py\n" + "\n".join(f"x = {i}" for i in range(100)) + "\n```"
    chunks = split_text(text, limit=200)
    assert len(chunks) > 1
    for chunk in chunks:
        assert chunk.count("```") == 2
    assert chunks[1].startswith("```py\n")


def test_split_hard_wraps_long_line() -> None:
    chunks = split_text("a" * 1000, limit=200)
    assert all(len(chunk) <= 200 for chunk in chunks)
    assert "".join(chunks).replace("\n", "") == "a" * 1000
