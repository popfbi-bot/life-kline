"""life-kline 核心逻辑。

只依赖 Python 标准库；不做网络访问；除 store.py 外不碰磁盘。
"""

__all__ = ["model", "store", "aggregate", "metrics", "narrate", "render"]
