"""Расчёты для анализа времени: загрузка, кампании, причины потерь, события, бутстрэп."""
import re
from pathlib import Path

import duckdb
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
DB = ROOT / "data" / "processed" / "volve.duckdb"

CAMPAIGN_GAP_DAYS = 30  # перерыв в рапортах дольше — новая кампания на стволе
CAMPAIGN_RU = {"drilling": "бурение", "completion": "заканчивание", "workover": "ремонт скважины",
               "plug abandon": "ликвидация", "interruption": "аварийная", "formation evaluation": "исследования",
               "moving": "переезд"}
CLASS_RU = {"productive": "работа по программе", "npt": "непроизводительное время", "weather": "ожидание погоды"}

# Причина потери по тексту комментария. Порядок важен: первое совпадение побеждает.
TEXT_RULES = [
    ("забастовка", r"strike"),
    ("верхний привод", r"top ?drive|\btds\b|\bddm\b|dolly"),
    ("ПВО и устьевое оборудование", r"\bbop\b|annular|wellhead|riser|diverter|x-?mas|xmt|\brams?\b|sstt|lmrp|tension cyl|dhsv"),
    ("трубный манипулятор и ключи", r"roughneck|\bprs\b|pipe handling|racker|elevator|\btong|catwalk|finger ?board|\bhts\b"),
    ("лебёдка и талевая система", r"draw ?works|crown|travell?ing block|drill ?line|slip and cut|compensator|brake"),
    ("насосы и циркуляционная система", r"mud pump|\bpump|stand ?pipe|shaker|flow ?line|wash ?pipe|\bhose"),
    ("кран", r"\bcrane"),
    ("гидравлика, энергетика, автоматика", r"hydraulic|\bhpu\b|power|generator|electric|\bplc\b|software|control system"),
    ("канатная техника и геофизика", r"wire ?line|lubricator|tractor|\bcable|logging tool|toolstring"),
    ("забойное оборудование", r"\bmwd\b|\blwd\b|\bmotor\b|\bbha\b|\bbit\b|rss|powerdrive|autotrak"),
    ("осложнения в стволе", r"stuck|jarr|overpull|tight|pack(ed)? ?off|losses|lost circ|\bkick|cement"),
    ("обслуживание станка", r"maintenance|housekeeping|\bservice"),
    ("утечки и уплотнения", r"leak|seal"),
    ("ожидание и согласования", r"wait|w\.o\.|\bwoc\b|suspend|stand ?by|evaluat|discuss|\btown\b"),
]
CODE_CAUSE = {"fish": "ловильные работы", "sidetrack": "перебуривание ствола", "lost circulation": "поглощение",
              "well control": "газонефтеводопроявление", "maintain": "обслуживание станка"}


def load():
    """Операции и рапорты из базы. Рапорты с датой раньше 1990 года — ошибка в исходнике, отбрасываем."""
    con = duckdb.connect(str(DB), read_only=True)
    reports = con.execute("SELECT * FROM reports WHERE day_start >= DATE '1990-01-01'").df()
    ops = con.execute("SELECT * FROM ops_clean WHERE t_start >= DATE '1990-01-01'").df()
    wellbores = con.execute("SELECT * FROM wellbores").df()
    con.close()
    return reports, ops, wellbores


def add_campaigns(reports, ops):
    """Кампания — непрерывная серия рапортов на стволе. Тип кампании — группа операций с наибольшим временем."""
    r = reports.sort_values(["wellbore", "day_start"]).copy()
    gap = r.groupby("wellbore").day_start.diff().dt.days.fillna(0)
    r["campaign"] = (gap > CAMPAIGN_GAP_DAYS).groupby(r.wellbore).cumsum()
    o = ops.merge(r[["report_id", "campaign"]], on="report_id")
    dominant = (o.groupby(["wellbore", "campaign", "activity_group"]).hours.sum().reset_index()
                .sort_values("hours").groupby(["wellbore", "campaign"]).tail(1)
                .rename(columns={"activity_group": "campaign_type"})[["wellbore", "campaign", "campaign_type"]])
    o = o.merge(dominant, on=["wellbore", "campaign"])
    o["campaign_type"] = o.campaign_type.map(CAMPAIGN_RU)
    o["era"] = np.where(o.t_start < "2000-01-01", "разведка 1992–1998", "разработка 2007–2016")
    return o


def cause(row):
    """Причина непроизводительного времени: сначала по коду операции, затем по тексту комментария."""
    if row.activity_group == "interruption" and row.activity in CODE_CAUSE:
        return CODE_CAUSE[row.activity]
    text = (row.comment or "").lower()
    for name, pattern in TEXT_RULES:
        if re.search(pattern, text):
            return name
    return "не классифицировано"


def add_causes(ops):
    o = ops.copy()
    npt = o.time_class == "npt"
    o.loc[npt, "cause"] = o[npt].apply(cause, axis=1)
    return o


def events(ops):
    """Событие — подряд идущие операции НПВ на одном стволе (перерыв не больше часа)."""
    n = ops[ops.time_class == "npt"].sort_values(["wellbore", "t_start"]).copy()
    new = (n.wellbore != n.wellbore.shift()) | ((n.t_start - n.t_end.shift()).dt.total_seconds() > 3600)
    n["event"] = new.cumsum()
    return (n.groupby("event").agg(wellbore=("wellbore", "first"), start=("t_start", "min"), hours=("hours", "sum"),
                                   cause=("cause", lambda s: s.value_counts().index[0]),
                                   campaign_type=("campaign_type", "first"),
                                   comment=("comment", lambda c: c.loc[n.loc[c.index, "hours"].idxmax()]))
            .reset_index())


def daily(ops):
    """Сутки × ствол: всего часов и часов НПВ. Единица повторной выборки для бутстрэпа."""
    d = ops.assign(day=ops.t_start.dt.floor("D"), npt_h=np.where(ops.time_class == "npt", ops.hours, 0.0),
                   wow_h=np.where(ops.time_class == "weather", ops.hours, 0.0))
    return d.groupby(["wellbore", "day"]).agg(hours=("hours", "sum"), npt=("npt_h", "sum"), wow=("wow_h", "sum"),
                                              era=("era", "first"), campaign_type=("campaign_type", "first"),
                                              hole_in=("hole_in", "first")).reset_index()


def npt_share_ci(days, n_boot=5000, seed=42):
    """Доля НПВ и 95% интервал бутстрэпом по суткам (сутки внутри ствола зависимы, поэтому интервал — нижняя оценка разброса)."""
    rng = np.random.default_rng(seed)
    h, n = days.hours.to_numpy(), days.npt.to_numpy()
    idx = rng.integers(0, len(h), size=(n_boot, len(h)))
    boot = n[idx].sum(axis=1) / h[idx].sum(axis=1)
    return n.sum() / h.sum(), np.quantile(boot, 0.025), np.quantile(boot, 0.975)


def diff_ci(a, b, n_boot=5000, seed=42):
    """Разность долей НПВ двух групп суток и её 95% интервал."""
    rng = np.random.default_rng(seed)
    out = []
    for d in (a, b):
        h, n = d.hours.to_numpy(), d.npt.to_numpy()
        idx = rng.integers(0, len(h), size=(n_boot, len(h)))
        out.append(n[idx].sum(axis=1) / h[idx].sum(axis=1))
    diff = out[0] - out[1]
    return a.npt.sum() / a.hours.sum() - b.npt.sum() / b.hours.sum(), np.quantile(diff, 0.025), np.quantile(diff, 0.975)


EQUIPMENT = ["верхний привод", "трубный манипулятор и ключи", "ПВО и устьевое оборудование",
             "насосы и циркуляционная система", "канатная техника и геофизика", "забойное оборудование",
             "гидравлика, энергетика, автоматика", "лебёдка и талевая система", "кран", "утечки и уплотнения",
             "обслуживание станка"]
WELL = ["перебуривание ствола", "ловильные работы", "поглощение", "осложнения в стволе", "газонефтеводопроявление"]


def cause_group(c):
    if c in EQUIPMENT:
        return "оборудование станка и подрядчиков"
    if c in WELL:
        return "осложнения в скважине"
    if c == "забастовка":
        return "забастовка"
    if c == "ожидание и согласования":
        return "ожидание и согласования"
    return "не классифицировано"


def campaigns(ops):
    """Сводка по кампаниям: длительность, глубина, доли времени."""
    g = ops.groupby(["wellbore", "campaign", "campaign_type", "era"])
    out = g.agg(start=("t_start", "min"), end=("t_end", "max"), hours=("hours", "sum"), max_md=("md", "max")).reset_index()
    for cls in ("npt", "weather"):
        part = ops[ops.time_class == cls].groupby(["wellbore", "campaign"]).hours.sum().rename(cls + "_hours")
        out = out.merge(part, on=["wellbore", "campaign"], how="left")
    out = out.fillna({"npt_hours": 0, "weather_hours": 0})
    out["days"] = out.hours / 24
    out["npt_share"] = out.npt_hours / out.hours
    return out
