"""验收判据 7、8、12（渲染面）：mask 去数字、单文件自包含、不说预测话术。"""

from __future__ import annotations

import re
import sys
import tempfile
import unittest
from datetime import date
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from core import render  # noqa: E402
from core.aggregate import aggregate  # noqa: E402
from core.metrics import compute_stats, suspension_gaps  # noqa: E402
from core.store import load  # noqa: E402

CSV = ROOT / "fixtures" / "full.csv"

PREDICTIVE = ("预测", "明天", "将持续", "建议", "运势", "命运", "指数", "大概率", "将会", "未来", "趋势")

# 合法的数字白名单：日期（含 ISO 与「10 月 22 日」）、版本号、单位
ALLOW_DATE = re.compile(r"\d{4}-\d{2}-\d{2}")
ALLOW_CN_DATE = re.compile(r"\d{1,2} 月 \d{1,2} 日")
ALLOW_VERSION = re.compile(r"\bv?\d+\.\d+(\.\d+)?\b")


def build_html(mask: bool = False, period: str = "day") -> str:
    days = load(CSV)
    stats = compute_stats(days)
    candles = aggregate(days, period)
    payload = render.RenderInput(
        candles=candles,
        gap_dates=suspension_gaps(days),
        review="这一天你记录了 12 天（共 77 天）。",
        cards=[("有记录天数", "12"), ("最长连阳", "3 天"), ("最大回撤", "70.0%"), ("停牌率", "84.4%")],
        extra_rows=[("波动率（样本标准差 n-1）", "60.1%")],
        period_label=f"日线　2026-10-18 → 2027-01-02　共 {len(candles)} 根",
        mask=mask,
    )
    return render.render(payload)


def text_nodes(html: str) -> list[str]:
    """取出 HTML 的文本节点（去掉标签与属性），只看用户肉眼可见的内容。"""
    body = html.split("<body>", 1)[1]
    without_titles = re.sub(r"<title>.*?</title>", "", body, flags=re.S)
    return [seg.strip() for seg in re.sub(r"<[^>]*>", "\n", without_titles).splitlines() if seg.strip()]


def svg_text_nodes(html: str) -> list[str]:
    svg = re.search(r"<svg.*?</svg>", html, flags=re.S).group(0)
    return [seg.strip() for seg in re.sub(r"<[^>]*>", "\n", svg).splitlines() if seg.strip()]


class TestMaskRemovesNumbers(unittest.TestCase):
    def test_mask_html_has_no_score_or_scale_numbers(self):
        """--mask 输出中不得出现任何分数/刻度数字（日期与版本号用白名单放行）。"""
        html = build_html(mask=True)
        offenders = []
        for node in text_nodes(html):
            stripped = ALLOW_DATE.sub("", node)
            stripped = ALLOW_CN_DATE.sub("", stripped)
            stripped = ALLOW_VERSION.sub("", stripped)
            if re.search(r"\d", stripped):
                offenders.append(node)
        self.assertEqual(offenders, [], "mask 版本里还有数字：" + str(offenders))

    def test_mask_svg_has_no_tick_labels(self):
        """坐标轴刻度、图例分数、max/min 具体值都不能有。"""
        svg = re.search(r"<svg.*?</svg>", build_html(mask=True), flags=re.S).group(0)
        self.assertEqual(svg_text_nodes(svg), [], "mask 的 SVG 里还有可见文字")

    def test_mask_keeps_same_candle_count(self):
        """形状没丢：K 线根数与 mask 前一致。"""
        def bodies(html: str) -> int:
            # 影线是 <line>，实体是 <rect>；成交量柱 opacity=0.45，先剔掉
            svg = re.search(r"<svg.*?</svg>", html, flags=re.S).group(0)
            svg = re.sub(r'<rect [^>]*opacity="0\.45"[^>]*/>', "", svg)
            return len(re.findall(r"<rect ", svg))

        self.assertEqual(bodies(build_html(mask=False)), bodies(build_html(mask=True)))
        self.assertEqual(bodies(build_html(mask=False)), 12)
        # 停牌那两天不产生柱体
        self.assertNotIn("2026-10-20", re.findall(r"<title>(.*?)</title>", build_html(mask=False))[0])

    def test_mask_has_watermark(self):
        html = build_html(mask=True)
        self.assertIn("形状可分享，数字只留给自己", html)

    def test_mask_hides_cards_and_details(self):
        html = build_html(mask=True)
        self.assertNotIn("排牌", html)
        self.assertNotIn("停牌率", html)
        self.assertNotIn("84.4%", html)
        self.assertNotIn("最大回撤", html)

    def test_mask_keeps_shape_via_polyline(self):
        """均线的形状（SVG 坐标）必须保留，相对关系还在。"""
        svg = re.search(r"<svg.*?</svg>", build_html(mask=True), flags=re.S).group(0)
        self.assertIn("<polyline", svg)


class TestRenderIsSelfContained(unittest.TestCase):
    def test_no_external_resources(self):
        html = build_html(mask=False)
        for pattern in ("http://", "https://", "<script src=", '<link rel="stylesheet"'):
            self.assertNotIn(pattern, html, f"出现外部资源引用：{pattern}")

    def test_no_script_tag_at_all(self):
        self.assertNotIn("<script", build_html(mask=False).lower())

    def test_no_external_in_mask_version(self):
        html = build_html(mask=True)
        for pattern in ("http://", "https://", "<script src=", '<link rel="stylesheet"'):
            self.assertNotIn(pattern, html)

    def test_uses_inline_svg_not_canvas(self):
        html = build_html(mask=False)
        self.assertIn("<svg", html)
        self.assertNotIn("<canvas", html.lower())

    def test_china_convention_red_up_green_down(self):
        """阳线红、阴线绿，别搞反。"""
        html = build_html(mask=False)
        self.assertEqual(render.PALETTE["up"], "#c0392b")
        self.assertEqual(render.PALETTE["down"], "#1e8449")
        self.assertIn(render.PALETTE["up"], html)
        self.assertIn(render.PALETTE["down"], html)

    def test_gap_is_visually_marked(self):
        html = build_html(mask=False)
        self.assertIn('stroke-dasharray="2 4"', html)  # 停牌虚线
        self.assertIn("停牌", html)


class TestNoPredictiveVocabulary(unittest.TestCase):
    def check(self, html: str):
        offenders = [w for w in PREDICTIVE if w in html]
        self.assertEqual(offenders, [], f"出现红线词汇：{offenders}")

    def test_chart_html_wording(self):
        self.check(build_html(mask=False))
        self.check(build_html(mask=True))

    def test_cli_terminal_output_wording(self):
        from tests.helpers import run_cli

        for args in (("stats",), ("gaps",), ("verify",)):
            code, out, err = run_cli(*args, path=CSV)
            self.assertEqual(code, 0, err)
            offenders = [w for w in PREDICTIVE if w in out]
            self.assertEqual(offenders, [], f"{args} 输出出现红线词汇：{offenders}")

    def test_streak_span_matches_length_in_stats_output(self):
        """user-visible：连阳那一行的日期跨度必须等于连阳天数。

        通用毛病是「跨度与根数不符」：3 根阳线报成 10 天跨度。

        fixtures/full.csv 手算：close 6 → 7 → 9 → 10，第一根阳线 10-23（收 7），
        之后 10-29（收 9）、10-31（收 10）——连阳 3 根；10-24~10-30 是停牌。
        """
        from tests.helpers import run_cli

        code, out, err = run_cli("stats", path=CSV)
        self.assertEqual(code, 0, err)
        line = next(l for l in out.splitlines() if l.startswith("最长连阳"))
        self.assertIn("10 月 23 日–10 月 31 日", line)
        self.assertNotIn("10 月 22 日", line)

        # 手算：3 根阳线（10-23 / 10-29 / 10-31），段内夹了 6 天停牌，
        # 所以日期跨度 = 3 + 6 = 9 天。旧实现从 10-22 起算，会报成 10 天。
        out_span = re.search(r"（(\d{1,2}) 月 (\d{1,2}) 日–(\d{1,2}) 月 (\d{1,2}) 日）", line)
        self.assertIsNotNone(out_span, f"连阳那一行没有日期区间：{line}")
        sm, sd, em, ed = (int(x) for x in out_span.groups())
        self.assertEqual((sm, sd), (10, 23), "起点应是第一根阳线 10-23")
        self.assertEqual((em, ed), (10, 31), "终点应是最后一根阳线 10-31")
        span_days = (date(2026, em, ed) - date(2026, sm, sd)).days + 1
        self.assertEqual(span_days, 9, f"3 根阳线 + 6 天停牌 = 9 天跨度，实际 {span_days}")

    def test_source_contains_no_predictive_words(self):
        """面向用户的文案里不许出现这些词。

        只检查「字符串字面量」——注释里出现这些词（比如解释为什么禁用它们）
        不算违规，因为用户永远看不到注释。
        """
        import ast

        offenders = []
        for path in sorted(ROOT.rglob("*.py")):
            rel = path.relative_to(ROOT)
            if ".git" in path.parts or rel.parts[0] == "tests":
                continue
            tree = ast.parse(path.read_text(encoding="utf-8"))
            # 只检查真正会被打印/渲染的字符串；docstring 是写给人看的注释
            docstrings = set()
            for node in ast.walk(tree):
                if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
                    if node.body and isinstance(node.body[0], ast.Expr) and isinstance(node.body[0].value, ast.Constant):
                        docstrings.add(id(node.body[0].value))
            for node in ast.walk(tree):
                if isinstance(node, ast.Constant) and isinstance(node.value, str) and id(node) not in docstrings:
                    for word in PREDICTIVE:
                        if word in node.value:
                            offenders.append(f"{rel}:{node.lineno} 出现「{word}」")
        self.assertEqual(offenders, [], "用户可见文案里出现红线词汇：" + str(offenders))

    def test_uses_word_state_not_index(self):
        html = build_html(mask=False)
        self.assertIn("状态", html)
        self.assertNotIn("人生指数", html)
        self.assertNotIn("幸福度", html)


class TestRenderNeverComputes(unittest.TestCase):
    def test_render_module_does_not_import_metrics(self):
        """render 不许算指标：它不能依赖 metrics / aggregate 的对外计算函数。"""
        import ast

        source = (ROOT / "core" / "render.py").read_text(encoding="utf-8")
        tree = ast.parse(source)
        modules = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module:
                modules.add(node.module)
            elif isinstance(node, ast.Import):
                modules.update(a.name for a in node.names)
        self.assertFalse({m for m in modules if m.endswith("metrics")}, modules)
        self.assertFalse({m for m in modules if m.endswith("narrate")}, modules)


if __name__ == "__main__":
    unittest.main()
