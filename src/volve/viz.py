"""Единый стиль графиков."""
import matplotlib.pyplot as plt

INK, GREY, LIGHT = "#1b1f24", "#8a9099", "#d9dde2"
ACCENT, WARN, CALM = "#c8452c", "#e0a030", "#2f6f9f"
CLASS_COLORS = {"productive": CALM, "npt": ACCENT, "weather": WARN}
GROUP_COLORS = {"оборудование станка и подрядчиков": CALM, "осложнения в скважине": ACCENT, "забастовка": WARN,
                "ожидание и согласования": GREY, "не классифицировано": LIGHT}


def setup():
    plt.rcParams.update({
        "figure.dpi": 110, "savefig.dpi": 160, "savefig.bbox": "tight", "font.family": "DejaVu Sans",
        "font.size": 10, "axes.titlesize": 12, "axes.titleweight": "bold", "axes.titlelocation": "left",
        "axes.spines.top": False, "axes.spines.right": False, "axes.edgecolor": GREY, "axes.labelcolor": INK,
        "xtick.color": INK, "ytick.color": INK, "axes.grid": True, "grid.color": LIGHT, "grid.linewidth": 0.6,
        "axes.axisbelow": True, "legend.frameon": False,
    })


def save(fig, name):
    from pathlib import Path
    out = Path(__file__).resolve().parents[2] / "reports" / "figures" / name
    out.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out)
