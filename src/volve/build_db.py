"""Суточные буровые рапорты Volve (parquet) -> база DuckDB: reports, operations, wellbores.

Запуск: python src/volve/build_db.py
"""
from pathlib import Path

import duckdb
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
RAW = ROOT / "data" / "raw" / "ddr.parquet"
DB = ROOT / "data" / "processed" / "volve.duckdb"
MISSING = -999.99  # так в рапортах помечено «нет значения»


def num(v):
    """Число из строки рапорта; пусто и -999.99 -> None."""
    try:
        x = float(v)
    except (TypeError, ValueError):
        return None
    return None if x == MISSING else x


def first(lst):
    return dict(lst[0]) if lst is not None and len(lst) else {}


def ts(v):
    """Время в рапортах записано с норвежским часовым поясом; оставляем местное время буровой."""
    return pd.to_datetime(v, errors="coerce", utc=True).tz_convert("Europe/Oslo").tz_localize(None) if v else pd.NaT


def main():
    raw = pd.read_parquet(RAW)
    reports, ops = [], []
    for r in raw.itertuples(index=False):
        st, wb = first(r.statusInfo), first(r.wellboreInfo)
        rig = first(wb.get("rigAlias"))
        reports.append(dict(
            report_id=r.docName, wellbore=r.nameWellbore.replace("NO ", ""),
            day_start=ts(r.dTimStart), day_end=ts(r.dTimEnd),
            report_no=num(st.get("reportNo")), md=num(st.get("md")), tvd=num(st.get("tvd")),
            hole_in=num(st.get("diaHole")), dist_drill=num(st.get("distDrill")),
            md_csg_last=num(st.get("mdCsgLast")),
            spud=ts(wb.get("dTimSpud")), drill_complete=pd.to_datetime(wb.get("dateDrillComplete"), errors="coerce"),
            operator=wb.get("operator"), rig=rig.get("name"),
            summary=st.get("sum24Hr"), forecast=st.get("forecast24Hr"),
        ))
        for i, a in enumerate(r.activity if r.activity is not None else []):
            code = (a.get("proprietaryCode") or "").split(" -- ")
            ops.append(dict(
                report_id=r.docName, wellbore=r.nameWellbore.replace("NO ", ""), seq=i,
                t_start=ts(a.get("dTimStart")), t_end=ts(a.get("dTimEnd")), md=num(a.get("md")),
                phase=a.get("phase"), activity_group=code[0] or None,
                activity=code[1] if len(code) > 1 else None,
                state=a.get("state"), state_detail=a.get("stateDetailActivity"),
                comment=a.get("comments"),
            ))
    reports, ops = pd.DataFrame(reports), pd.DataFrame(ops)
    ops["hours"] = (ops.t_end - ops.t_start).dt.total_seconds() / 3600

    DB.parent.mkdir(parents=True, exist_ok=True)
    DB.unlink(missing_ok=True)
    con = duckdb.connect(str(DB))
    con.execute("CREATE TABLE reports AS SELECT * FROM reports")
    con.execute("CREATE TABLE operations AS SELECT * FROM ops")
    con.execute((ROOT / "sql" / "marts.sql").read_text(encoding="utf-8"))
    for t in ("reports", "operations", "wellbores", "ops_clean"):
        print(t, con.execute(f"SELECT count(*) FROM {t}").fetchone()[0])
    con.close()


if __name__ == "__main__":
    main()
