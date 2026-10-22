#!/usr/bin/env python3
"""life-kline：每天 30 秒自评，把日子画成一张 K 线图。

纯本地、零第三方依赖、零网络。
"""

from __future__ import annotations

import argparse
import sys
from datetime import date as Date, datetime
from pathlib import Path

from core import narrate, render, store
from core.aggregate import PERIODS, aggregate
from core.metrics import compute_stats, slice_days, suspension_gaps
from core.model import DataError, Day, build_day

VERSION = "0.1.0"

PERIOD_LABEL = {
    "day": "日线",
    "week": "周线",
    "month": "月线",
    "year": "年线",
}

ASK = Path(__file__).resolve().parent / "presets" / "ask.md"


def _path(args) -> Path:
    return Path(args.path).expanduser() if args.path else store.default_path()


def _pct(v: float) -> str:
    return f"{v * 100:.1f}%"


def _fmt_date(d: Date | None) -> str:
    return d.isoformat() if d else "—"


# ---------------------------------------------------------------- commands


def cmd_init(args) -> int:
    path, created = store.init_file(_path(args))
    if created:
        print(f"已创建 {path}，里面有一条样例和一条停牌日，可以直接改。")
        print("下一步：life-kline add")
    else:
        print(f"{path} 已存在，没有覆盖。")
    return 0


def _ask(prompt: str, default: str = "") -> str:
    try:
        raw = input(prompt).strip()
    except EOFError:
        return default
    return raw or default


def _ask_score(prompt: str, field_name: str) -> str:
    while True:
        raw = _ask(prompt)
        try:
            build_day("2000-01-01", {field_name: raw, **{k: raw for k in ("open", "high", "low", "close") if k != field_name}}, line=1)
            return raw
        except DataError as err:
            print(f"  {err.reason}，再试一次。", file=sys.stderr)


def cmd_add(args) -> int:
    path = _path(args)
    if not path.exists():
        store.init_file(path)
        print(f"没有数据文件，已创建 {path}。")

    raw_date = args.date or _ask("哪一天？（回车 = 今天）", datetime.now().date().isoformat())

    if args.open is not None or args.close is not None:
        scores = {
            "open": args.open or "",
            "high": args.high or "",
            "low": args.low or "",
            "close": args.close or "",
        }
    else:
        print("四个问题，30 秒。")
        scores = {
            "open": _ask_score("早上起来的时候，你的状态大概几分？（0–10）", "open"),
            "high": _ask_score("今天最好的那个时刻，能打到几分？", "high"),
            "low": _ask_score("今天最糟的那个时刻，掉到几分？", "low"),
            "close": _ask_score("现在，睡前，几分？", "close"),
        }

    volume = args.volume if args.volume is not None else _ask("成交量？记不住就回车跳过：")
    note = args.note if args.note is not None else _ask("备注（可空）：")
    tags = args.tags if args.tags is not None else _ask("标签，用分号分隔（可空）：")

    try:
        day = build_day(str(raw_date), scores, volume or "", note or "", tags or "", line=None)
    except DataError as err:
        print(err.render(), file=sys.stderr)
        return 2

    if store.find_day(path, day.date) is not None and not args.force:
        print(f"{day.date} 已经有记录了。要覆盖就加 --force。", file=sys.stderr)
        return 2

    store.append_day(path, day)
    if day.suspended:
        print(f"已把 {day.date} 记为停牌。")
    else:
        print(f"已记录 {day.date}：开 {day.open} 高 {day.high} 低 {day.low} 收 {day.close}。")
    return 0


def cmd_verify(args) -> int:
    path = _path(args)
    try:
        days = store.load(path)
    except FileNotFoundError as err:
        print(err, file=sys.stderr)
        return 2
    except DataError as err:
        print(err.render(), file=sys.stderr)
        return 2
    recorded = [d for d in days if not d.suspended]
    print(f"{path} 校验通过：{len(days)} 行，其中 {len(recorded)} 天有记录、{len(days) - len(recorded)} 天停牌。")
    return 0


def _stats_lines(stats) -> list[tuple[str, str]]:
    rows = [("有记录天数", f"{stats.recorded_days} 天")]
    rows.append(("停牌天数", f"{stats.suspended_days} 天"))
    rows.append(("停牌率", _pct(stats.suspension_rate)))
    if stats.daily_returns:
        avg = sum(stats.daily_returns) / len(stats.daily_returns)
        rows.append(("平均日收益率", _pct(avg)))
        rows.append(("最近一次日收益率", _pct(stats.daily_returns[-1])))
    else:
        rows.append(("日收益率", "样本不足，需要至少 2 天记录"))
    if stats.amplitudes:
        rows.append(("平均振幅", _pct(sum(stats.amplitudes) / len(stats.amplitudes))))
    else:
        rows.append(("振幅", "样本不足"))
    if stats.volatility is None:
        rows.append(("波动率（样本标准差 n-1）", "样本不足，需要至少 2 个收益率"))
    else:
        rows.append(("波动率（样本标准差 n-1）", _pct(stats.volatility)))
    rows.append(("最大回撤", f"{_pct(stats.max_drawdown)}（{_fmt_date(stats.max_drawdown_date)}）"))
    rows.append(("最长连阳", narrate.describe_streak(stats.longest_up, "up")))
    rows.append(("最长连阴", narrate.describe_streak(stats.longest_down, "down")))
    return rows


def cmd_stats(args) -> int:
    path = _path(args)
    try:
        days = store.load(path)
    except FileNotFoundError as err:
        print(err, file=sys.stderr)
        return 2
    except DataError as err:
        print(err.render(), file=sys.stderr)
        return 2

    days = slice_days(days, _parse_opt_date(args.start, "--from"), _parse_opt_date(args.end, "--to"))
    if not days:
        print("这个区间里没有数据。")
        return 0

    stats = compute_stats(days)
    print(narrate.render_narrative(stats, period="year"))
    print()
    for key, value in _stats_lines(stats):
        print(f"{key:<24}{value}")
    return 0


def cmd_gaps(args) -> int:
    path = _path(args)
    try:
        days = store.load(path)
    except FileNotFoundError as err:
        print(err, file=sys.stderr)
        return 2
    except DataError as err:
        print(err.render(), file=sys.stderr)
        return 2

    if not days:
        print("还没有任何记录。")
        return 0

    gaps = suspension_gaps(days)
    stats = compute_stats(days)
    recorded = stats.recorded_days
    total = stats.total_days

    print(f"区间 {_fmt_date(stats.first_recorded)} → {_fmt_date(stats.last_recorded)}，共 {total} 天")
    print(f"有记录 {recorded} 天　停牌 {len(gaps)} 天　停牌率 {_pct(stats.suspension_rate)}")
    print()

    if not gaps:
        print("这段时间一天没停牌。")
        return 0

    bar_width = 48
    filled = min(bar_width, round(stats.suspension_rate * bar_width))
    bar = "█" * filled + "░" * (bar_width - filled)
    print(f"停牌 {bar} {_pct(stats.suspension_rate)}   有记录 {_pct(1 - stats.suspension_rate)}")

    # 按连续停牌段聚合展示，比逐日罗列好读
    runs: list[list[Date]] = []
    for d in gaps:
        if runs and (d - runs[-1][-1]).days == 1:
            runs[-1].append(d)
        else:
            runs.append([d])
    runs.sort(key=len, reverse=True)
    print()
    print("最长的几段停牌：")
    for run in runs[:8]:
        if len(run) == 1:
            print(f"  {run[0].isoformat()}（1 天）")
        else:
            print(f"  {run[0].isoformat()} → {run[-1].isoformat()}（{len(run)} 天）")
    return 0


def cmd_chart(args) -> int:
    path = _path(args)
    try:
        days = store.load(path)
    except FileNotFoundError as err:
        print(err, file=sys.stderr)
        return 2
    except DataError as err:
        print(err.render(), file=sys.stderr)
        return 2

    if not days:
        print("数据文件是空的，先 life-kline add；这次先生成一张空图。")

    period = args.period
    candles = aggregate(days, period)
    if not candles:
        print("这个区间全是停牌，画不出 K 线；这次先生成一张空图。")

    stats = compute_stats(days)
    gaps = suspension_gaps(days)
    review = narrate.build(days, period=period)

    cards = [
        ("有记录天数", f"{stats.recorded_days}"),
        ("最长连阳", f"{stats.longest_up.length} 天" if stats.longest_up and stats.longest_up.length >= 2 else "—"),
        ("最大回撤", _pct(stats.max_drawdown)),
        ("停牌率", _pct(stats.suspension_rate)),
    ]

    extra_rows = [(k, v) for k, v in _stats_lines(stats)]

    payload = render.RenderInput(
        candles=candles,
        gap_dates=gaps,
        review=review,
        cards=cards,
        extra_rows=extra_rows,
        period_label=f"{PERIOD_LABEL[period]}　{_fmt_date(stats.first_recorded)} → {_fmt_date(stats.last_recorded)}　共 {len(candles)} 根",
        mask=args.mask,
    )
    out = Path(args.out).expanduser() if args.out else Path("life.html")
    store.write_text(out, render.render(payload))
    print(f"已生成 {out}" + ("（分享模式：只有形状，没有数字）" if args.mask else ""))
    return 0


# ---------------------------------------------------------------- helpers


def _parse_opt_date(raw: str | None, flag: str) -> Date | None:
    if not raw:
        return None
    try:
        return Date.fromisoformat(raw)
    except ValueError:
        raise SystemExit(f"{flag} 需要 ISO 日期（YYYY-MM-DD），实际是 `{raw}`") from None


class _OncePath(argparse.Action):
    """同时接受 `life-kline --path a.csv verify` 和 `life-kline verify --path a.csv`。

    顶层和每个子命令各挂了一份 `--path`，两份共用同一个 dest，
    所以重复写不算冲突，后写的生效（argparse 默认的 last-wins）。
    """

    def __call__(self, parser, namespace, values, option_string=None):
        setattr(namespace, self.dest, values)


PATH_HELP = "数据文件路径，默认 ~/life-kline.csv；放在子命令前后都行"

# 顶层那份要给 default=None，子命令那份要给 SUPPRESS。反过来会让
# `--path a.csv verify` 的 a.csv 被子命令的 None 默认值覆盖掉。
PATH_OPTION = dict(action=_OncePath, dest="path", metavar="CSV", help=PATH_HELP)


def build_parser() -> argparse.ArgumentParser:
    # argparse 只解析「子命令之前」的选项，所以顶层和每个子命令各挂一份 --path，
    # `life-kline --path a.csv verify` 和 `life-kline verify --path a.csv` 都能跑。
    # 两份共用 dest，默认值的给法见 PATH_OPTION 上面那段注释。
    parser = argparse.ArgumentParser(
        prog="life-kline",
        description="每天 30 秒自评，把日子画成一张 K 线图。",
        epilog="提示：--path 写在子命令前后都可以，例如 `life-kline --path a.csv verify` "
        "或 `life-kline verify --path a.csv`。",
    )
    parser.add_argument("--version", action="version", version=f"life-kline {VERSION}")
    parser.add_argument("--path", default=None, **PATH_OPTION)
    sub = parser.add_subparsers(dest="command", metavar="<命令>")

    def add_sub(name: str, help_text: str) -> argparse.ArgumentParser:
        p = sub.add_parser(name, help=help_text)
        p.add_argument("--path", default=argparse.SUPPRESS, **PATH_OPTION)
        return p

    p_init = add_sub("init", "初始化 CSV")
    p_init.set_defaults(func=cmd_init)

    p_add = add_sub("add", "记录一天")
    p_add.add_argument("--date")
    p_add.add_argument("--open")
    p_add.add_argument("--high")
    p_add.add_argument("--low")
    p_add.add_argument("--close")
    p_add.add_argument("--volume")
    p_add.add_argument("--note")
    p_add.add_argument("--tags")
    p_add.add_argument("--force", action="store_true", help="覆盖同一天的记录")
    p_add.set_defaults(func=cmd_add)

    p_chart = add_sub("chart", "生成单文件 HTML")
    p_chart.add_argument("--period", choices=PERIODS, default="day")
    p_chart.add_argument("--out", default="life.html")
    p_chart.add_argument("--mask", action="store_true", help="分享模式：只留形状，去掉数字")
    p_chart.set_defaults(func=cmd_chart)

    p_stats = add_sub("stats", "终端输出 7 个指标")
    p_stats.add_argument("--from", dest="start")
    p_stats.add_argument("--to", dest="end")
    p_stats.set_defaults(func=cmd_stats)

    p_gaps = add_sub("gaps", "列出停牌日与停牌率")
    p_gaps.set_defaults(func=cmd_gaps)

    p_verify = add_sub("verify", "只校验 CSV")
    p_verify.set_defaults(func=cmd_verify)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if not getattr(args, "func", None):
        parser.print_help()
        return 1
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
