"""Расчёты: загрузка, этапы работ, баланс времени, динамика, повторяемость отказов, карта рисков, план НПВ."""
from pathlib import Path

import duckdb
import numpy as np
import pandas as pd

from volve import npt

ROOT = Path(__file__).resolve().parents[2]
DB = ROOT / "data" / "processed" / "volve.duckdb"

EXPLORATION, DEVELOPMENT = "разведочное бурение", "эксплуатационное бурение"
CAMPAIGN_GAP_DAYS = 30  # перерыв в рапортах дольше — новый заход станка на ствол
STAGE = {"drilling": "строительство", "completion": "строительство", "formation evaluation": "строительство",
         "moving": "строительство", "workover": "КРС", "plug abandon": "ликвидация"}
RIG_RU = {"MÆRSK INSPIRER": "СПБУ Mærsk Inspirer", "BYFORD DOLPHIN": "ППБУ Byford Dolphin",
          "TREASURE PROSPECT": "ППБУ Treasure Prospect"}


def load():
    """Операции и рапорты из базы. Рапорт с датой раньше 1990 года — ошибка в исходнике, отбрасываем."""
    con = duckdb.connect(str(DB), read_only=True)
    reports = con.execute("SELECT * FROM reports WHERE day_start >= DATE '1990-01-01'").df()
    ops = con.execute("SELECT * FROM ops_clean WHERE t_start >= DATE '1990-01-01'").df()
    con.close()
    return reports, ops


def prepare():
    """Полная подготовка: этапы работ и разметка НПВ."""
    reports, ops = load()
    return reports, npt.add_npt(add_stages(reports, ops))


def add_stages(reports, ops):
    """Заход — непрерывная серия рапортов на стволе. Этап захода — по плановым операциям с наибольшим временем."""
    r = reports.sort_values(["wellbore", "day_start"]).copy()
    gap = r.groupby("wellbore").day_start.diff().dt.days.fillna(0)
    r["campaign"] = (gap > CAMPAIGN_GAP_DAYS).groupby(r.wellbore).cumsum()
    o = ops.merge(r[["report_id", "campaign"]], on="report_id")
    planned = o[o.activity_group != "interruption"]
    dominant = (planned.groupby(["wellbore", "campaign", "activity_group"]).hours.sum().reset_index()
                .sort_values("hours").groupby(["wellbore", "campaign"]).tail(1))
    dominant["stage"] = dominant.activity_group.map(STAGE)
    o = o.merge(dominant[["wellbore", "campaign", "stage"]], on=["wellbore", "campaign"], how="left")
    o["stage"] = o.stage.fillna("строительство")
    o["scope"] = np.where(o.t_start < "2000-01-01", EXPLORATION, DEVELOPMENT)
    o["rig_ru"] = o.rig.map(RIG_RU)
    year = o.t_start.dt.year
    o["program"] = np.select(
        [o.scope == EXPLORATION, (o.stage == "строительство") & (year <= 2009), (o.stage == "строительство") & (year >= 2013),
         o.stage == "КРС", (o.stage == "ликвидация") & (year >= 2016)],
        ["разведка 1992–1998", "бурение 2007–2009", "бурение 2013–2014", "КРС 2008–2016", "ликвидация 2016"],
        default="бурение " + np.where(year <= 2009, "2007–2009", "2013–2014"))
    return o


def balance(ops, by):
    """Баланс календарного времени: часы, доля НПВ и метео, НПВ в часах на сутки."""
    g = ops.groupby(by, sort=False)
    out = pd.DataFrame({
        "сутки": g.hours.sum() / 24,
        "ПВ, ч": ops[ops.time_class == "productive"].groupby(by).hours.sum(),
        "НПВ, ч": ops[ops.time_class == "npt"].groupby(by).hours.sum(),
        "метео, ч": ops[ops.time_class == "weather"].groupby(by).hours.sum(),
    }).fillna(0)
    total = out["сутки"] * 24
    out["НПВ, %"] = out["НПВ, ч"] / total * 100
    out["метео, %"] = out["метео, ч"] / total * 100
    out["НПВ, ч/сут"] = out["НПВ, ч"] / out["сутки"]
    return out


def kinds(ops, by=None):
    """Часы НПВ по видам (и по разрезу by)."""
    n = ops[ops.time_class == "npt"]
    keys = ([by] if isinstance(by, str) else list(by or [])) + ["npt_kind"]
    return n.groupby(keys).hours.sum().unstack("npt_kind").reindex(columns=npt.KINDS).fillna(0)


def causes(ops):
    """Причины НПВ внутри видов: часы, число событий, доля."""
    n = ops[ops.time_class == "npt"]
    out = n.groupby(["npt_kind", "npt_cause"]).agg(hours=("hours", "sum"), events=("event", "nunique")).reset_index()
    out["share"] = out.hours / out.hours.sum() * 100
    return out.sort_values("hours", ascending=False)


def quarterly(ops):
    """НПВ станка по кварталам: календарные часы, НПВ по видам, доля."""
    q = ops.assign(quarter=ops.t_start.dt.to_period("Q"))
    total = q.groupby("quarter").hours.sum()
    k = kinds(q, "quarter").reindex(total.index).fillna(0)
    k["часы"] = total
    k["НПВ, %"] = k[npt.KINDS].sum(axis=1) / total * 100
    k["метео, %"] = q[q.time_class == "weather"].groupby("quarter").hours.sum().reindex(total.index).fillna(0) / total * 100
    return k


def repeats(events, min_hours=0.0):
    """Повторяемость отказов: по каждой причине события пронумерованы по времени.

    `after3` — часы на четвёртом и следующих случаях той же причины: это время, потерянное уже после того,
    как повторяемость стала видна по накопленной статистике.
    """
    e = events[events.hours >= min_hours].sort_values("start").copy()
    e["n"] = e.groupby("npt_cause").cumcount() + 1
    out = e.groupby(["npt_kind", "npt_cause"]).agg(
        events=("hours", "size"), hours=("hours", "sum"), median_h=("hours", "median"), max_h=("hours", "max"),
        first=("start", "min"), last=("start", "max")).reset_index()
    out["after3"] = e[e.n > 3].groupby("npt_cause").hours.sum().reindex(out.npt_cause).fillna(0).to_numpy()
    return out.sort_values("hours", ascending=False), e


def failure_rate(ops, events, cause, periods):
    """Отказы узла на 1000 часов работы станка по периодам (program)."""
    hours = ops.groupby("program").hours.sum()
    ev = events[events.npt_cause == cause].merge(
        ops[["event", "program"]].drop_duplicates("event"), on="event")
    g = ev.groupby("program").agg(events=("hours", "size"), npt_h=("hours", "sum"))
    out = pd.DataFrame({"часы станка": hours}).join(g).fillna(0).reindex(periods)
    out["отказов на 1000 ч"] = out.events / out["часы станка"] * 1000
    out["НПВ, ч на 1000 ч"] = out.npt_h / out["часы станка"] * 1000
    return out


def risk_map(ops, events, wells):
    """Карта рисков на одну скважину: вероятность причины (доля скважин, где она была) и тяжесть (часы на случай)."""
    ev = events[events.wellbore.isin(wells)]
    per_well = ev.groupby(["npt_kind", "npt_cause", "wellbore"]).hours.sum().reset_index()
    out = per_well.groupby(["npt_kind", "npt_cause"]).agg(
        wells=("wellbore", "nunique"), hours=("hours", "sum"),
        p50=("hours", "median"), p90=("hours", lambda s: s.quantile(0.9))).reset_index()
    out["probability"] = out.wells / len(wells)
    out["expected_h"] = out.hours / len(wells)
    return out.sort_values("expected_h", ascending=False)


def wells_table(ops):
    """Скважины эксплуатационного бурения в порядке начала строительства: сутки, проходка, НПВ."""
    b = ops[(ops.scope == DEVELOPMENT) & (ops.stage == "строительство")]
    g = b.groupby("wellbore")
    out = pd.DataFrame({
        "start": g.t_start.min(), "days": g.hours.sum() / 24, "md": g.md.max(),
        "npt_h": b[b.time_class == "npt"].groupby("wellbore").hours.sum(),
        "wow_h": b[b.time_class == "weather"].groupby("wellbore").hours.sum(),
    }).fillna(0).sort_values("start")
    out["npt_share"] = out.npt_h / (out.days * 24) * 100
    out["program"] = np.where(out.start.dt.year <= 2009, "бурение 2007–2009", "бурение 2013–2014")
    return out.reset_index()


def npt_plan(wells, min_history=3, min_days=10):
    """План НПВ на следующую скважину по накопленной статистике (проверка «как было бы»).

    Перед каждой скважиной берём уже законченные: медиана их доли НПВ — ожидание (P50),
    80-й перцентиль — граница, за которую выходить нельзя (P80). Сравниваем с фактом.
    """
    w = wells[wells.days >= min_days].reset_index(drop=True)
    rows = []
    for i in range(min_history, len(w)):
        hist = w.npt_share.iloc[:i]
        rows.append(dict(wellbore=w.wellbore[i], start=w.start[i], days=w.days[i], fact=w.npt_share[i],
                         p50=hist.median(), p80=hist.quantile(0.8), history=i))
    out = pd.DataFrame(rows)
    out["within"] = out.fact <= out.p80
    return out


def share_ci(ops, n_boot=5000, seed=42):
    """Доля НПВ и 95% интервал: бутстрэп по суткам станка."""
    d = ops.assign(day=ops.t_start.dt.floor("D"), n=np.where(ops.time_class == "npt", ops.hours, 0.0))
    d = d.groupby(["wellbore", "day"]).agg(h=("hours", "sum"), n=("n", "sum"))
    rng = np.random.default_rng(seed)
    h, n = d.h.to_numpy(), d.n.to_numpy()
    idx = rng.integers(0, len(h), size=(n_boot, len(h)))
    boot = n[idx].sum(axis=1) / h[idx].sum(axis=1)
    return n.sum() / h.sum() * 100, np.quantile(boot, 0.025) * 100, np.quantile(boot, 0.975) * 100
