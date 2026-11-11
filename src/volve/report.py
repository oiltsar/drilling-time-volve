"""Собирает графики и витрины отчёта. Запуск: PYTHONPATH=src python src/volve/report.py"""
from pathlib import Path

import matplotlib
matplotlib.use("Agg")

from volve import analysis as A
from volve import figures as F
from volve import npt, viz

OUT = Path(__file__).resolve().parents[2] / "reports"
UNITS = ["трубный манипулятор и ключи", "верхний привод", "насосы и циркуляционная система",
         "ПВО, райзер и устьевое оборудование"]


def main():
    viz.setup()
    reports, ops = A.prepare()
    ev = npt.events(ops)
    dev = ops[ops.scope == A.DEVELOPMENT]
    wells = A.wells_table(ops)
    build = dev[dev.stage == "строительство"]
    risk = A.risk_map(build, ev[(ev.scope == A.DEVELOPMENT) & (ev.stage == "строительство")], list(wells.wellbore))
    plan = A.npt_plan(wells)

    for old in (OUT / "figures").glob("*.png"):
        old.unlink()
    figs = {
        "01_balance.png": F.balance(ops),
        "02_structure.png": F.structure(dev, "Больше половины НПВ эксплуатационного бурения — ремонт бурового оборудования"),
        "03_dynamics.png": F.dynamics(dev),
        "04_repeats.png": F.repeats_timeline(ops, ev),
        "05_rates.png": F.rates(ops, ev, UNITS),
        "06_plan.png": F.plan(plan),
        "07_risk.png": F.risk(risk, len(wells)),
        "08_scopes.png": F.scopes(ops),
        "09_weather.png": F.weather(ops),
    }
    for name, fig in figs.items():
        viz.save(fig, name)

    marts = OUT / "marts"
    marts.mkdir(parents=True, exist_ok=True)
    cols = ["wellbore", "scope", "rig_ru", "program", "stage", "campaign", "t_start", "t_end", "hours", "md", "hole_in",
            "activity_group", "activity", "state_detail", "time_class", "event", "npt_kind", "npt_cause", "npt_owner", "npt_source"]
    ops[cols].to_csv(marts / "operations.csv", index=False)
    ev.drop(columns="comment").to_csv(marts / "npt_events.csv", index=False)
    wells.to_csv(marts / "wells.csv", index=False)
    risk.to_csv(marts / "risk_map.csv", index=False)
    plan.to_csv(marts / "npt_plan.csv", index=False)
    A.quarterly(dev).to_csv(marts / "quarterly.csv")
    for old in ("campaigns.csv",):
        (marts / old).unlink(missing_ok=True)
    print("ok", OUT)


if __name__ == "__main__":
    main()
