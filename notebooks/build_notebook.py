"""Собирает notebooks/analysis.ipynb из ячеек ниже. Запуск: python notebooks/build_notebook.py"""
from pathlib import Path

import nbformat as nbf

cells = []
md = lambda t: cells.append(nbf.v4.new_markdown_cell(t.strip()))
code = lambda t: cells.append(nbf.v4.new_code_cell(t.strip()))

md("""
# НПВ при строительстве скважин Volve: классификация, повторяемость, план

Расчёты к [README](../README.md). Порядок тот же: баланс времени, виды и причины НПВ, динамика,
повторяемость отказов, план НПВ на скважину и карта рисков, затем отдельно разведка.
""")
code("""
import sys
sys.path.insert(0, "../src")

import matplotlib.pyplot as plt
import pandas as pd

from volve import analysis as A
from volve import figures as F
from volve import npt, viz

viz.setup()
pd.set_option("display.float_format", "{:,.1f}".format)
pd.set_option("display.max_colwidth", 140)

reports, ops = A.prepare()
ev = npt.events(ops)
dev = ops[ops.scope == A.DEVELOPMENT]
expl = ops[ops.scope == A.EXPLORATION]
print(f"рапортов {len(reports):,}, операций {len(ops):,}, стволов {ops.wellbore.nunique()}, суток станка {ops.hours.sum() / 24:,.0f}")
""")

md("""
## 1. Объект: одна площадь, три станка, два разных вида работ

Разведочные стволы 15/9-19 бурили с двух ППБУ в 1992–1998 годах. Эксплуатационные стволы 15/9-F бурила одна СПБУ
в 2007–2016 годах. Дальше они считаются раздельно.
""")
code("""
display(ops.groupby(["scope", "rig_ru"]).agg(стволов=("wellbore", "nunique"), начало=("t_start", "min"), конец=("t_end", "max"),
                                             суток=("hours", lambda s: s.sum() / 24)))
display(A.balance(ops, "program"))
F.balance(ops); plt.show()
""")

md("""
## 2. Учёт НПВ в рапортах и его проверка

НПВ — операции группы `interruption` (кроме метео), операции с отметкой `fail` и операции с отметкой
`stateDetailActivity`, отличной от `success`. Последние записаны под плановыми кодами (спуск колонны, СПО),
но это работы после отказа: подъём хвостовика труболовкой, повторный спуск, смена телесистемы.
""")
code("""
n = ops[ops.time_class == "npt"]
hidden = n[~((n.activity_group == "interruption") | (n.state == "fail"))]
print(f"НПВ всего {n.hours.sum():,.0f} ч, из них под плановыми кодами {hidden.hours.sum():,.0f} ч ({hidden.hours.sum() / n.hours.sum():.0%})")
print(f"код interruption/other: {n[(n.activity_group == 'interruption') & (n.activity == 'other')].hours.sum() / n.hours.sum():.0%} НПВ")
display((n.groupby("npt_source").hours.sum() / n.hours.sum() * 100).sort_values(ascending=False).to_frame("% НПВ"))
vague = n[n.npt_cause.isin(["узел не указан", "повторные работы без описания", "ожидание прочее", npt.UNKNOWN])]
print(f"без конкретной причины осталось {vague.hours.sum():,.0f} ч ({vague.hours.sum() / n.hours.sum():.1%} НПВ)")
""")
code("""
# Выборочная проверка разметки: 30 операций, вероятность выбора пропорциональна часам
check = n.sample(30, weights=n.hours, random_state=3)[["wellbore", "hours", "npt_kind", "npt_cause", "npt_source", "comment"]]
check.assign(comment=check.comment.str.replace("\\n", " ").str[:130])
""")

md("## 3. Эксплуатационное бурение: виды и причины НПВ")
code("""
k = dev[dev.time_class == "npt"].groupby("npt_kind").hours.sum().sort_values(ascending=False)
display(pd.DataFrame({"часы": k, "% НПВ": k / k.sum() * 100, "% календарного времени": k / dev.hours.sum() * 100}))
display((A.kinds(dev, "program").T / dev.groupby("program").hours.sum() * 100).round(1))
print("доля НПВ и 95% интервал:", [round(v, 1) for v in A.share_ci(dev)])
F.structure(dev, "Больше половины НПВ эксплуатационного бурения — ремонт бурового оборудования"); plt.show()
""")
code("""
# Крупнейшие события НПВ эксплуатационного бурения
de = ev[ev.scope == A.DEVELOPMENT]
print(f"событий {len(de)}, медиана {de.hours.median():.2f} ч, дольше суток {(de.hours >= 24).sum()} — {de[de.hours >= 24].hours.sum() / de.hours.sum():.0%} НПВ")
top = de.sort_values("hours", ascending=False).head(15)
top.assign(comment=top.comment.str.replace("\\n", " ").str[:120])[["wellbore", "start", "hours", "npt_kind", "npt_cause", "comment"]]
""")

md("## 4. Динамика по кварталам")
code("""
q = A.quarterly(dev)
display(q[q["часы"] >= 500][["часы", "НПВ, %", "метео, %"]])
F.dynamics(dev); plt.show()
""")

md("""
## 5. Повторяемость отказов

Вопрос: видно ли по данным, что с повторяющимися отказами работали. Мерило — часы НПВ узла на 1000 часов работы станка.
""")
code("""
rep, _ = A.repeats(de[de.npt_kind.isin([npt.REPAIR, npt.SERVICE])])
display(rep[["npt_kind", "npt_cause", "events", "hours", "median_h", "max_h", "first", "last"]].head(10))
F.repeats_timeline(ops, ev); plt.show()
""")
code("""
from volve.report import UNITS
periods = ["бурение 2007–2009", "бурение 2013–2014", "ликвидация 2016"]
for unit in UNITS:
    print(unit); display(A.failure_rate(dev, de, unit, periods))
F.rates(ops, ev, UNITS); plt.show()
""")
code("""
# Сквозная проблема: колонна-надставка (tie-back) 10 3/4"
nd = dev[dev.time_class == "npt"]
tb = nd[nd.event.isin(nd[nd.comment.str.contains("tie-?back|tieback", case=False, na=False)].event.unique())]
print(f"событий {tb.event.nunique()}, часов {tb.hours.sum():,.0f}")
tb.groupby("wellbore").agg(начало=("t_start", "min"), часов=("hours", "sum")).sort_values("начало")
""")

md("""
## 6. План НПВ на скважину и карта рисков

Проверка «как было бы»: перед каждой скважиной план считается только по скважинам, законченным раньше.
""")
code("""
wells = A.wells_table(ops)
display(wells)
plan = A.npt_plan(wells)
display(plan)
F.plan(plan); plt.show()
""")
code("""
build = dev[dev.stage == "строительство"]
risk = A.risk_map(build, ev[(ev.scope == A.DEVELOPMENT) & (ev.stage == "строительство")], list(wells.wellbore))
display(risk.head(15))
print(f"НПВ на скважину: среднее {wells.npt_h.mean():.0f} ч, медиана {wells.npt_h.median():.0f} ч, P80 {wells.npt_h.quantile(0.8):.0f} ч")
F.risk(risk, len(wells)); plt.show()
""")

md("## 7. Разведка отдельно")
code("""
k = expl[expl.time_class == "npt"].groupby("npt_kind").hours.sum().sort_values(ascending=False)
display(pd.DataFrame({"часы": k, "% календарного времени": k / expl.hours.sum() * 100}))
xe = ev[ev.scope == A.EXPLORATION].sort_values("hours", ascending=False).head(10)
display(xe.assign(comment=xe.comment.str.replace("\\n", " ").str[:120])[["wellbore", "start", "hours", "npt_kind", "npt_cause", "comment"]])
F.scopes(ops); plt.show()
""")

md("## 8. Метеопростои")
code("""
F.weather(ops); plt.show()
""")

nb = nbf.v4.new_notebook(cells=cells, metadata={"kernelspec": {"name": "python3", "display_name": "Python 3"}})
nbf.write(nb, Path(__file__).with_name("analysis.ipynb"))
print("ok")
