"""单文件 HTML + 内联 SVG。

职责边界：这里只负责「画」，不计算任何指标——所有数字都由调用方
（core.metrics / core.narrate）算好后传进来。

硬约束：
- 无外部资源：不出现 http(s):// / <script src= / <link rel="stylesheet">
- 阳线红、阴线绿（中国股市习惯）
- 停牌日在图上留空白间隔，并在下方浅色标注
"""

from __future__ import annotations

import html
from dataclasses import dataclass
from datetime import date as Date

from .model import Candle

MASK_WATERMARK = "life-kline · 形状可分享，数字只留给自己"

PALETTE = {
    "up": "#c0392b",
    "down": "#1e8449",
    "grid": "#e8e8e8",
    "text": "#3d3d3d",
    "muted": "#b0b0b0",
    "bg": "#fffdf9",
    "ma": "#8a6fbf",
}

CSS = """
:root{color-scheme:light}
*{box-sizing:border-box}
body{margin:0;padding:32px 20px 48px;background:%(bg)s;color:%(text)s;
font-family:-apple-system,BlinkMacSystemFont,"PingFang SC","Hiragino Sans GB","Microsoft YaHei",sans-serif;
line-height:1.65;-webkit-font-smoothing:antialiased}
main{max-width:860px;margin:0 auto}
h1{font-size:20px;font-weight:600;margin:0 0 4px;letter-spacing:.02em}
.sub{color:%(muted)s;font-size:13px;margin:0 0 20px}
.review{font-size:16px;margin:0 0 24px;padding:14px 16px;background:#f7f3ec;border-radius:8px}
.cards{display:grid;grid-template-columns:repeat(auto-fit,minmax(140px,1fr));gap:12px;margin:0 0 28px}
.card{padding:12px 14px;border:1px solid %(grid)s;border-radius:8px;background:#fff}
.card .k{font-size:12px;color:%(muted)s;margin:0 0 4px}
.card .v{font-size:20px;font-weight:600;margin:0;letter-spacing:.01em}
figure{margin:0 0 24px}
svg{width:100%%;height:auto;display:block}
.legend{font-size:12px;color:%(muted)s;margin-top:8px;display:flex;flex-wrap:wrap;gap:14px}
.legend b{font-weight:600}
.details{margin-top:8px;border-top:1px solid %(grid)s;padding-top:16px}
.details summary{cursor:pointer;font-size:14px;color:%(text)s;outline:none}
.details table{border-collapse:collapse;width:100%%;margin-top:12px;font-size:14px}
.details td{padding:6px 0;border-bottom:1px solid %(grid)s;vertical-align:top}
.details td:last-child{text-align:right;font-variant-numeric:tabular-nums}
footer{margin-top:28px;font-size:12px;color:%(muted)s}
.watermark{font-size:12px;color:%(muted)s;margin:16px 0 0}
""" % PALETTE


@dataclass
class RenderInput:
    candles: list[Candle]
    gap_dates: list[Date]
    review: str
    cards: list[tuple[str, str]]
    extra_rows: list[tuple[str, str]]
    period_label: str
    mask: bool = False
    source_note: str = "数据来源：你自己的每日自评（0–10），不采集任何外部数据"


def _esc(text: str) -> str:
    return html.escape(str(text), quote=True)


def _moving_average(candles: list[Candle], window: int = 5) -> list[float | None]:
    closes = [c.close for c in candles]
    out: list[float | None] = []
    for i in range(len(closes)):
        if i + 1 < window:
            out.append(None)
        else:
            chunk = closes[i + 1 - window : i + 1]
            out.append(sum(chunk) / window)
    return out


def _svg(input_: RenderInput) -> str:
    """画 K 线 + 5 日形状线 + 成交量。mask 模式下不输出任何刻度数字。"""
    candles = input_.candles
    width, height = 860, 420
    pad_l, pad_r, pad_t = 8, 8, 12
    price_h = 300
    vol_h = 70
    vol_top = pad_t + price_h + 18
    mask = input_.mask
    ma = _moving_average(candles, 5)

    if not candles:
        inner = (
            f'<text x="{width/2}" y="{height/2}" text-anchor="middle" '
            f'font-size="14" fill="{PALETTE["muted"]}">这段时间没有记录，图上什么都没有</text>'
        )
        return f'<svg viewBox="0 0 {width} {height}" role="img" aria-label="空图">{inner}</svg>'

    lows = [c.low for c in candles]
    highs = [c.high for c in candles]
    lo, hi = min(lows), max(highs)
    if hi - lo < 1e-9:
        lo, hi = lo - 1, hi + 1
    span = hi - lo

    def y_of(v: float) -> float:
        return pad_t + price_h - (v - lo) / span * price_h

    n = len(candles)
    slot = (width - pad_l - pad_r) / n
    body_w = max(2.0, min(slot * 0.62, 26.0))

    parts: list[str] = []
    # 网格：mask 模式不画刻度数字，仅保留极淡的水平参考线
    for i in range(5):
        y = pad_t + price_h * i / 4
        parts.append(
            f'<line x1="{pad_l}" y1="{y:.1f}" x2="{width-pad_r}" y2="{y:.1f}" '
            f'stroke="{PALETTE["grid"]}" stroke-width="1"/>'
        )

    max_vol = max((c.volume or 0) for c in candles) or 1

    for idx, c in enumerate(candles):
        cx = pad_l + slot * (idx + 0.5)
        rising = c.close >= c.open
        color = PALETTE["up"] if rising else PALETTE["down"]
        label = f"{c.key} 开{c.open:g} 高{c.high:g} 低{c.low:g} 收{c.close:g}"
        if mask:
            label = "一根 K 线"
        title_tag = "" if mask else f"<title>{_esc(label)}</title>"
        parts.append(f"<g>{title_tag}")
        # 影线
        parts.append(
            f'<line x1="{cx:.1f}" y1="{y_of(c.high):.1f}" x2="{cx:.1f}" y2="{y_of(c.low):.1f}" '
            f'stroke="{color}" stroke-width="1.2"/>'
        )
        top = y_of(max(c.open, c.close))
        bottom = y_of(min(c.open, c.close))
        h = max(1.2, bottom - top)
        parts.append(
            f'<rect x="{cx - body_w/2:.1f}" y="{top:.1f}" width="{body_w:.1f}" height="{h:.1f}" '
            f'fill="{color}" rx="1"/>'
        )
        parts.append("</g>")
        # 成交量柱
        if c.volume:
            vh = c.volume / max_vol * vol_h
            parts.append(
                f'<rect x="{cx - body_w/2:.1f}" y="{vol_top + vol_h - vh:.1f}" width="{body_w:.1f}" '
                f'height="{vh:.1f}" fill="{color}" opacity="0.45" rx="1"/>'
            )

    # 收尾：形状线画在 K 线之上但不遮挡——所以先画柱子，再画线
    seg: list[str] = []
    for idx, value in enumerate(ma):
        if value is None:
            continue
        cx = pad_l + slot * (idx + 0.5)
        seg.append(f"{cx:.1f},{y_of(value):.1f}")
    if seg:
        parts.append(
            f'<polyline points="{" ".join(seg)}" fill="none" stroke="{PALETTE["ma"]}" '
            f'stroke-width="1.4" opacity="0.85" stroke-linejoin="round"/>'
        )

    # 停牌：图上留空白间隔（按日期比例定位，和 K 线等距）
    gap_marks = [d for d in input_.gap_dates if candles[0].start <= d <= candles[-1].end]
    if gap_marks:
        for d in gap_marks:
            # 按日期比例大致定位到空白处
            total_days = (candles[-1].end - candles[0].start).days or 1
            ratio = (d - candles[0].start).days / total_days
            x = pad_l + ratio * (width - pad_l - pad_r)
            title_tag = "" if mask else f"<title>停牌 {d.isoformat()}</title>"
            parts.append(
                f'<line x1="{x:.1f}" y1="{pad_t}" x2="{x:.1f}" y2="{pad_t + price_h}" '
                f'stroke="{PALETTE["muted"]}" stroke-width="0.8" stroke-dasharray="2 4" opacity="0.5"/>{title_tag}'
            )

    # 基线（成交量区）
    parts.append(
        f'<line x1="{pad_l}" y1="{vol_top + vol_h}" x2="{width-pad_r}" y2="{vol_top + vol_h}" '
        f'stroke="{PALETTE["grid"]}" stroke-width="1"/>'
    )

    # 横轴标签：mask 模式不显示日期数值
    if not mask:
        for idx in {0, n // 2, n - 1}:
            c = candles[idx]
            cx = pad_l + slot * (idx + 0.5)
            anchor = "start" if idx == 0 else ("end" if idx == n - 1 else "middle")
            parts.append(
                f'<text x="{cx:.1f}" y="{vol_top + vol_h + 18}" font-size="11" fill="{PALETTE["muted"]}" '
                f'text-anchor="{anchor}">{_esc(c.key)}</text>'
            )

    return (
        f'<svg viewBox="0 0 {width} {height}" role="img" '
        f'aria-label="{"K 线形状图" if mask else "人生 K 线图"}">' + "".join(parts) + "</svg>"
    )


def render(input_: RenderInput) -> str:
    mask = input_.mask
    review_html = "" if mask else f'<p class="review">{_esc(input_.review)}</p>'
    sub_html = "" if mask else f'<p class="sub">{_esc(input_.period_label)}</p>'
    cards_html = ""
    if not mask:
        cards_html = '<section class="cards">' + "".join(
            f'<div class="card"><p class="k">{_esc(k)}</p><p class="v">{_esc(v)}</p></div>'
            for k, v in input_.cards
        ) + "</section>"

    rows_html = ""
    if not mask and input_.extra_rows:
        rows_html = (
            '<details class="details"><summary>其余指标</summary><table>'
            + "".join(f"<tr><td>{_esc(k)}</td><td>{_esc(v)}</td></tr>" for k, v in input_.extra_rows)
            + "</table></details>"
        )

    legend = (
        f'<div class="legend"><span>红 = 状态<b>上升</b>的日子</span>'
        f'<span>绿 = 状态<b>下降</b>的日子</span>'
        f'<span>虚线 = <b>停牌</b>（那天没记录）</span></div>'
    )
    if mask:
        legend = f'<div class="legend"><span>{_esc(MASK_WATERMARK)}</span></div>'
    else:
        legend += f'<div class="legend"><span>{_esc(input_.source_note)}</span>' \
                  f'<span>分数是你自己的自评，0–10</span></div>'

    watermark = f'<p class="watermark">{_esc(MASK_WATERMARK)}</p>' if mask else ""

    title = "人生 K 线（形状）" if mask else "人生 K 线"
    return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{_esc(title)}</title>
<style>{CSS}</style>
</head>
<body>
<main>
<h1>{_esc(title)}</h1>
{review_html}
{sub_html}
{cards_html}
<figure>
{_svg(input_)}
{legend}
</figure>
{rows_html}
<footer>分数是自评，不是测量。图只描述已经发生的事，不描述将要发生的事。</footer>
{watermark}
</main>
</body>
</html>
"""
