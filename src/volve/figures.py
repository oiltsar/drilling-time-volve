"""Графики отчёта. Каждый возвращает fig; заголовок графика — вывод."""
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from volve import analysis as A
from volve import npt
from volve.viz import ACCENT, CALM, GREY, INK, LIGHT, WARN

PROGRAMS = ["бурение 2007–2009", "бурение 2013–2014", "КРС 2008–2016", "ликвидация 2016"]


def _pct(x):
    return f"{x:.1f}".replace(".", ",") + "%"


def _num(x, digits=0):
    return f"{x:,.{digits}f}".replace(",", " ").replace(".", ",")


def balance(ops):
    """Баланс календарного времени по станкам и этапам."""
    rows = [("Разведка · ППБУ Treasure Prospect, 1992–1993", ops[ops.rig == "TREASURE PROSPECT"]),
            ("Разведка · ППБУ Byford Dolphin, 1997–1998", ops[ops.rig == "BYFORD DOLPHIN"])]
    dev = ops[ops.scope == A.DEVELOPMENT]
    names = {"бурение 2007–2009": "Эксплуатация · бурение 2007–2009", "бурение 2013–2014": "Эксплуатация · бурение 2013–2014",
             "КРС 2008–2016": "Эксплуатация · КРС 2008–2016", "ликвидация 2016": "Эксплуатация · ликвидация 2016"}
    rows += [(names[p], dev[dev.program == p]) for p in PROGRAMS]
    fig, ax = plt.subplots(figsize=(10, 4.2))
    for i, (name, d) in enumerate(rows[::-1]):
        h = d.hours.sum()
        pv = d[d.time_class == "productive"].hours.sum() / h * 100
        n = d[d.time_class == "npt"].hours.sum() / h * 100
        w = d[d.time_class == "weather"].hours.sum() / h * 100
        ax.barh(i, pv, color=LIGHT)
        ax.barh(i, n, left=pv, color=ACCENT)
        ax.barh(i, w, left=pv + n, color=WARN)
        ax.text(pv / 2, i, f"ПВ {_pct(pv)}", ha="center", va="center", color=INK, fontsize=9)
        ax.text(pv + n / 2, i, _pct(n), ha="center", va="center", color="white", fontsize=9, fontweight="bold")
        ax.text(101, i, f"{_num(h / 24)} сут · НПВ {_num(d[d.time_class == 'npt'].hours.sum() / (h / 24), 1)} ч/сут · метео {_pct(w)}",
                va="center", fontsize=9, color=INK)
    ax.set_yticks(range(len(rows)), [r[0] for r in rows[::-1]])
    ax.set_xlim(0, 100)
    ax.xaxis.set_visible(False)
    ax.spines["bottom"].set_visible(False)
    ax.set_title("В эксплуатационном бурении НПВ вдвое ниже, чем в разведке, но держится на 13–17%\n", fontsize=12)
    ax.text(0, 1.02, "Баланс календарного времени: ПВ, НПВ (оранжевый), простой по метеоусловиям (тёмный)",
            transform=ax.transAxes, fontsize=9, color=WARN)
    return fig


def structure(ops, title):
    """Структура НПВ: виды и причины внутри видов, % календарного времени."""
    total = ops.hours.sum()
    c = A.causes(ops)
    c["pct"] = c.hours / total * 100
    kind_tot = c.groupby("npt_kind").pct.sum().sort_values(ascending=False)
    kind_tot = kind_tot[kind_tot >= 0.05]
    rows = []
    for kind, tot in kind_tot.items():
        rows.append((kind, tot, True))
        sub = c[c.npt_kind == kind].sort_values("pct", ascending=False)
        small = sub[sub.pct < 0.1]
        for r in sub[sub.pct >= 0.1].itertuples():
            rows.append((r.npt_cause, r.pct, False))
        if small.pct.sum() >= 0.05 and len(sub) > len(small):
            rows.append(("прочее", small.pct.sum(), False))
    fig, ax = plt.subplots(figsize=(10, 0.27 * len(rows) + 1.2))
    top_kind = kind_tot.index[0]
    y, current = 0, None
    ticks, labels = [], []
    for name, val, is_kind in rows:
        if is_kind:
            current = name
            y -= 0.5
            ax.text(0, y, f"{name.upper()} — {_pct(val)} календарного времени, {_num(val / 100 * total)} ч",
                    fontsize=9, fontweight="bold", va="center", color=ACCENT if name == top_kind else INK)
        else:
            ax.barh(y, val, color=ACCENT if current == top_kind else GREY, height=0.7)
            ax.text(val + 0.05, y, _pct(val), va="center", fontsize=8.5)
            ticks.append(y)
            labels.append(name)
        y -= 1
    ax.set_yticks(ticks, labels, fontsize=8.5)
    ax.xaxis.set_visible(False)
    ax.spines["bottom"].set_visible(False)
    ax.set_xlim(left=0)
    ax.tick_params(axis="y", pad=4)
    ax.set_title(title + "\n", fontsize=12)
    return fig


def dynamics(ops, min_hours=500):
    """НПВ станка по кварталам, эксплуатационное бурение."""
    q = A.quarterly(ops)
    q = q[q["часы"] >= min_hours]
    rep = q[npt.REPAIR] / q["часы"] * 100
    rest = q["НПВ, %"] - rep
    fig, ax = plt.subplots(figsize=(10, 4))
    x = np.arange(len(q))
    ax.bar(x, rep, color=ACCENT, label="ремонт бурового оборудования")
    ax.bar(x, rest, bottom=rep, color=GREY, label="остальное НПВ")
    for i, v in enumerate(q["НПВ, %"]):
        ax.text(i, v + 1, f"{v:.0f}", ha="center", fontsize=9)
    labels = [f"{p.quarter} кв.\n{p.year}" for p in q.index]
    ax.set_xticks(x, labels, fontsize=8)
    gaps = [i for i in range(1, len(q)) if (q.index[i] - q.index[i - 1]).n > 1]
    for g in gaps:
        ax.axvline(g - 0.5, color=CALM, lw=1, ls=(0, (2, 3)))
    ax.yaxis.set_visible(False)
    ax.legend(loc="upper right", fontsize=9)
    ax.set_title("Два провала: I квартал 2008 года (39%) и запуск после перерыва в 2013-м (68%)\n", fontsize=12)
    ax.text(0, 1.02, "НПВ, % календарного времени СПБУ Mærsk Inspirer по кварталам (кварталы от 500 ч работы; пунктир — перерыв в работах)",
            transform=ax.transAxes, fontsize=9, color=WARN)
    return fig


def repeats_timeline(ops, events, top=7):
    """Лента отказов по узлам: каждая точка — событие, размер — часы НПВ."""
    dev = ops[ops.scope == A.DEVELOPMENT].sort_values("t_start")
    clock = pd.Series(dev.hours.cumsum().to_numpy() / 24, index=dev.t_start.to_numpy())
    clock = clock[~clock.index.duplicated()]
    ev = events[(events.scope == A.DEVELOPMENT) & events.npt_kind.isin([npt.REPAIR, npt.SERVICE])].copy()
    ev["day"] = clock.reindex(ev.start).to_numpy()
    rep, _ = A.repeats(ev)
    rep = rep[rep.npt_cause != "узел не указан"].head(top)
    fig, ax = plt.subplots(figsize=(10, 0.55 * len(rep) + 1.6))
    for i, r in enumerate(rep[::-1].itertuples()):
        e = ev[ev.npt_cause == r.npt_cause]
        ax.scatter(e.day, [i] * len(e), s=np.clip(e.hours, 0.5, None) * 6, color=ACCENT if i == len(rep) - 1 else GREY,
                   alpha=0.55, linewidths=0)
        ax.text(clock.max() * 1.01, i, f"{r.events} отказов · {_num(r.hours)} ч", va="center", fontsize=9)
    ax.set_yticks(range(len(rep)), rep.npt_cause[::-1])
    year_start = dev.groupby(dev.t_start.dt.year).t_start.min()
    busy = dev.groupby(dev.t_start.dt.year).hours.sum() / 24 >= 60
    shown = [(clock[t], y) for y, t in year_start.items() if busy[y]]
    ax.set_xticks([t for t, _ in shown], [str(y) for _, y in shown], fontsize=9)
    ax.set_xlabel("наработка станка; отмечено начало работ в годы, когда станок отработал больше 60 суток", fontsize=9)
    ax.set_xlim(0, clock.max() * 1.01)
    ax.set_title("Одни и те же узлы отказывают из года в год: трубный манипулятор — 224 раза за девять лет\n", fontsize=12)
    ax.text(0, 1.03, "Каждая точка — событие НПВ, площадь точки — часы. СПБУ Mærsk Inspirer, 2007–2016",
            transform=ax.transAxes, fontsize=9, color=WARN)
    return fig


def rates(ops, events, causes):
    """НПВ узла на 1000 часов работы станка по периодам."""
    dev = ops[ops.scope == A.DEVELOPMENT]
    ev = events[events.scope == A.DEVELOPMENT]
    fig, axes = plt.subplots(1, len(causes), figsize=(10, 3.2), sharey=True)
    short = ["2007–09", "2013–14", "2016"]
    titles = {"трубный манипулятор и ключи": "трубный манипулятор", "насосы и циркуляционная система": "насосы, циркуляция",
              "ПВО, райзер и устьевое оборудование": "ПВО и устье"}
    periods = ["бурение 2007–2009", "бурение 2013–2014", "ликвидация 2016"]
    for ax, cause in zip(axes, causes):
        r = A.failure_rate(dev, ev, cause, periods)["НПВ, ч на 1000 ч"]
        worse = r.iloc[1] > r.iloc[0]
        ax.bar(range(3), r, color=[GREY, ACCENT if worse else WARN, GREY], width=0.7)
        for i, v in enumerate(r):
            ax.text(i, v + 0.8, f"{v:.0f}", ha="center", fontsize=9)
        ax.set_xticks(range(3), short, fontsize=9)
        ax.set_title(titles.get(cause, cause), fontsize=10, fontweight="normal")
        ax.yaxis.set_visible(False)
    fig.suptitle("Снижение видно только по трубному манипулятору, и к 2016 году отказы вернулись", x=0.01, ha="left", fontsize=12,
                 fontweight="bold", y=1.08)
    fig.text(0.01, 0.98, "Часы НПВ узла на 1000 часов работы станка: бурение 2007–2009, бурение 2013–2014, ликвидация 2016. Оранжевый — стало хуже",
             fontsize=9, color=WARN)
    return fig


def plan(plan_df):
    """План НПВ на скважину по накопленной статистике и факт."""
    p = plan_df.reset_index(drop=True)
    fig, ax = plt.subplots(figsize=(10, 4))
    x = np.arange(len(p))
    ax.bar(x, p.fact, color=[GREY if w else ACCENT for w in p.within], width=0.65)
    ax.step(np.r_[x - 0.5, x[-1] + 0.5], np.r_[p.p80, p.p80.iloc[-1]], where="post", color=INK, lw=1.4)
    ax.step(np.r_[x - 0.5, x[-1] + 0.5], np.r_[p.p50, p.p50.iloc[-1]], where="post", color=INK, lw=1, ls=(0, (2, 2)))
    for i, v in enumerate(p.fact):
        ax.text(i, v + 1, f"{v:.0f}", ha="center", fontsize=9)
    ax.text(len(p) - 0.45, p.p80.iloc[-1], "граница P80", fontsize=8.5, va="center")
    ax.text(len(p) - 0.45, p.p50.iloc[-1], "ожидание P50", fontsize=8.5, va="center")
    ax.set_xticks(x, [w.replace("15/9-", "") for w in p.wellbore], rotation=45, ha="right", fontsize=8.5)
    ax.set_xlim(-0.6, len(p) + 1.3)
    ax.yaxis.set_visible(False)
    n_out = int((~p.within).sum())
    ax.set_title(f"План НПВ по накопленной статистике выдержали {len(p) - n_out} скважин из {len(p)}\n", fontsize=12)
    ax.text(0, 1.02, "НПВ скважины, % времени строительства. Линии — план, посчитанный только по скважинам, законченным раньше",
            transform=ax.transAxes, fontsize=9, color=WARN)
    return fig


def risk(risk_df, n_wells, label_top=8):
    """Карта рисков на одну скважину."""
    r = risk_df[risk_df.npt_kind != npt.UNKNOWN].copy()
    fig, ax = plt.subplots(figsize=(10, 5.2))
    top = r.head(label_top)
    ax.scatter(r.probability * 100, r.p50, s=r.expected_h * 28 + 12, color=GREY, alpha=0.5, linewidths=0)
    ax.scatter(top.probability.head(3) * 100, top.p50.head(3), s=top.expected_h.head(3) * 28 + 12, color=ACCENT, alpha=0.8, linewidths=0)
    short = {"крепление: негерметичность, недоспуск, повторный спуск": "брак при креплении",
             "энергетика, гидравлика, системы управления": "энергетика и управление",
             "оборудование крепления и заканчивания": "оборудование крепления"}
    offsets = {"насосы и циркуляционная система": (14, -4, "left"), "ГИС и канатная техника": (-14, -4, "right"),
               "трубный манипулятор и ключи": (0, -30, "center"), "энергетика, гидравлика, системы управления": (-12, 2, "right"),
               "оборудование крепления и заканчивания": (0, -18, "center")}
    for t in top.itertuples():
        dx, dy, ha = offsets.get(t.npt_cause, (0, 14, "center"))
        ax.annotate(f"{short.get(t.npt_cause, t.npt_cause)} · {t.expected_h:.0f} ч", (t.probability * 100, t.p50), fontsize=8.5,
                    xytext=(dx, dy), textcoords="offset points", ha=ha, va="center")
    ax.set_xlabel("вероятность: доля скважин, где причина дала НПВ, %")
    ax.set_ylabel("тяжесть: медиана часов НПВ на скважину, где причина была")
    ax.spines["left"].set_visible(True)
    ax.set_xlim(0, 105)
    ax.set_ylim(0, r.p50.max() * 1.15)
    ax.set_title("Карта рисков на следующую скважину: что закладывать в план\n", fontsize=12)
    ax.text(0, 1.02, f"По {n_wells} стволам эксплуатационного бурения. Площадь круга — ожидаемые часы НПВ на скважину",
            transform=ax.transAxes, fontsize=9, color=WARN)
    return fig


def scopes(ops):
    """Виды НПВ: разведка против эксплуатационного бурения, % календарного времени."""
    k = A.kinds(ops, "scope").T
    k = k / ops.groupby("scope").hours.sum() * 100
    k = k.drop(index=npt.UNKNOWN).sort_values(A.EXPLORATION)
    fig, ax = plt.subplots(figsize=(10, 4.2))
    y = np.arange(len(k))
    ax.barh(y + 0.2, k[A.EXPLORATION], height=0.38, color=GREY, label="разведочное бурение, 1992–1998")
    ax.barh(y - 0.2, k[A.DEVELOPMENT], height=0.38, color=ACCENT, label="эксплуатационное бурение, 2007–2016")
    for i, (a, b) in enumerate(zip(k[A.EXPLORATION], k[A.DEVELOPMENT])):
        ax.text(a + 0.1, i + 0.2, _pct(a), va="center", fontsize=9)
        ax.text(b + 0.1, i - 0.2, _pct(b), va="center", fontsize=9)
    ax.set_yticks(y, k.index)
    ax.xaxis.set_visible(False)
    ax.spines["bottom"].set_visible(False)
    ax.legend(loc="lower right", fontsize=9)
    ax.set_title("Геологию разведки учли: аварии и осложнения ушли, главным стало оборудование\n", fontsize=12)
    ax.text(0, 1.02, "Виды НПВ, % календарного времени", transform=ax.transAxes, fontsize=9, color=WARN)
    return fig


def weather(ops):
    """Простой по метеоусловиям по месяцам."""
    m = ops.assign(month=ops.t_start.dt.month)
    share = m[m.time_class == "weather"].groupby("month").hours.sum().reindex(range(1, 13)).fillna(0) / m.groupby("month").hours.sum() * 100
    fig, ax = plt.subplots(figsize=(10, 3.2))
    ax.bar(share.index, share, color=[ACCENT if v >= 8 else GREY for v in share], width=0.7)
    for i, v in share.items():
        ax.text(i, v + 0.3, f"{v:.0f}", ha="center", fontsize=9)
    ax.set_xticks(range(1, 13), ["янв", "фев", "мар", "апр", "май", "июн", "июл", "авг", "сен", "окт", "ноя", "дек"])
    ax.yaxis.set_visible(False)
    ax.set_title("Метеопростои приходятся на октябрь — март: до 12% времени, летом около нуля\n", fontsize=12)
    ax.text(0, 1.02, "Простой по метеоусловиям, % календарного времени по месяцам, все станки 1992–2016",
            transform=ax.transAxes, fontsize=9, color=WARN)
    return fig
