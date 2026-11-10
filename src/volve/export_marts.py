"""Выгружает витрины в CSV для BI-системы (Yandex DataLens). Запуск: python src/volve/export_marts.py"""
from pathlib import Path

from volve import analysis as A

OUT = Path(__file__).resolve().parents[2] / "reports" / "marts"


def main():
    reports, ops, _ = A.load()
    ops = A.add_causes(A.add_campaigns(reports, ops))
    ops["cause_group"] = ops.cause.map(A.cause_group, na_action="ignore")
    ops["time_class_ru"] = ops.time_class.map(A.CLASS_RU)
    OUT.mkdir(parents=True, exist_ok=True)
    cols = ["wellbore", "campaign", "campaign_type", "era", "rig", "t_start", "t_end", "hours", "md", "hole_in",
            "activity_group", "activity", "time_class_ru", "cause", "cause_group"]
    ops[cols].to_csv(OUT / "operations.csv", index=False)
    A.campaigns(ops).to_csv(OUT / "campaigns.csv", index=False)
    A.events(ops).drop(columns="comment").to_csv(OUT / "npt_events.csv", index=False)
    print("ok", OUT)


if __name__ == "__main__":
    main()
