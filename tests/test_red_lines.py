"""三条诚实红线的结构级断言。

红线一 不预测：指标函数不接受「未来日期」参数、只输出过去。
红线二 不插值：任何地方都不出现填充/插值式的补齐逻辑。
红线三 不装客观：文案统一叫「状态」，且标注数据来源。
"""

from __future__ import annotations

import ast
import inspect
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from core import metrics  # noqa: E402


class TestNoPredictiveApi(unittest.TestCase):
    def test_metric_functions_take_no_future_date_parameter(self):
        """任何指标函数签名里都不许出现「未来/forecast/tomorrow」类参数。"""
        banned = ("future", "forecast", "predict", "tomorrow")
        allowed = {"days", "returns", "start", "end", "candles"}
        for name, func in vars(metrics).items():
            if not inspect.isfunction(func) or func.__module__ != metrics.__name__:
                continue
            params = set(inspect.signature(func).parameters)
            self.assertFalse({p.lower() for p in params} & set(banned), f"{name} 有可疑参数 {params}")
            self.assertTrue(params <= allowed | {"days", "returns", "data", "candles"}, f"{name}: {params}")

    def test_metrics_module_imports_nothing_from_disk(self):
        """metrics.py 不许碰文件：不能 import store / pathlib / os。"""
        tree = ast.parse((ROOT / "core" / "metrics.py").read_text(encoding="utf-8"))
        modules = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                modules.update(a.name.split(".")[0] for a in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                modules.add(node.module.split(".")[0])
        self.assertFalse(modules & {"store", "pathlib", "os", "io"}, modules)


class TestNoInterpolationCode(unittest.TestCase):
    def test_no_fill_forward_or_interpolate_helpers(self):
        """红线二：源码里不能有「向前填充 / 插值 / 补值」这类实现。"""
        banned = ("ffill", "fillna", "interpolate", "backfill", "bfill", "pad_series")
        offenders = []
        for path in sorted((ROOT / "core").glob("*.py")) + [ROOT / "cli.py"]:
            tree = ast.parse(path.read_text(encoding="utf-8"))
            for node in ast.walk(tree):
                names = []
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    names = [node.name]
                elif isinstance(node, ast.Name):
                    names = [node.id]
                elif isinstance(node, ast.Attribute):
                    names = [node.attr]
                for name in names:
                    if any(b in name.lower() for b in banned):
                        offenders.append(f"{path.name}: {name}")
        self.assertEqual(offenders, [], offenders)


class TestStoreDoesNotAggregate(unittest.TestCase):
    def test_store_has_no_aggregation_helpers(self):
        """职责边界：store.py 不许算聚合。"""
        tree = ast.parse((ROOT / "core" / "store.py").read_text(encoding="utf-8"))
        funcs = {n.name for n in ast.walk(tree) if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))}
        self.assertFalse({"aggregate", "to_week", "to_month", "to_year"} & funcs, funcs)

    def test_store_does_not_compute_metrics(self):
        source = (ROOT / "core" / "store.py").read_text(encoding="utf-8")
        self.assertNotIn("metrics", source)
        self.assertNotIn("Candle", source)


class TestHonestLanguage(unittest.TestCase):
    def test_self_assessment_is_labelled(self):
        """红线三：分数必须标「自评」，图例必须写数据来源。"""
        from tests.test_render import build_html

        html = build_html(mask=False)
        self.assertIn("自评", html)
        self.assertIn("数据来源", html)

    def test_state_not_index(self):
        from tests.test_render import build_html

        html = build_html(mask=False)
        self.assertIn("状态", html)
        for word in ("人生指数", "幸福度", "运势", "命运"):
            self.assertNotIn(word, html)


if __name__ == "__main__":
    unittest.main()
