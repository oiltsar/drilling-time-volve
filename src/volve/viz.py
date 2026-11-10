"""Единый стиль графиков."""
import matplotlib.pyplot as plt

# Серый — основной цвет, один акцент на главную мысль
INK, GREY, LIGHT = "#151917", "#9aa09c", "#e1e4df"
ACCENT, WARN, CALM = "#e8590c", "#4f5753", "#b9beba"
BG = "#fcfcfb"
CLASS_COLORS = {"productive": GREY, "npt": ACCENT, "weather": WARN}
GROUP_COLORS = {"оборудование станка и подрядчиков": CALM, "осложнения в скважине": WARN, "забастовка": ACCENT,
                "ожидание и согласования": LIGHT, "не классифицировано": LIGHT}


def setup():
    plt.rcParams.update({
        "figure.facecolor": BG, "axes.facecolor": BG, "savefig.facecolor": BG, "figure.dpi": 110, "savefig.dpi": 160, "savefig.bbox": "tight", "font.family": "DejaVu Sans",
        "font.size": 10, "axes.titlesize": 12, "axes.titleweight": "bold", "axes.titlelocation": "left",
        "axes.spines.top": False, "axes.spines.right": False, "axes.edgecolor": GREY, "axes.labelcolor": INK,
        "xtick.color": INK, "ytick.color": INK, "axes.grid": False, "axes.spines.left": False, "xtick.major.size": 0, "ytick.major.size": 0,
        "axes.axisbelow": True, "legend.frameon": False,
    })


def save(fig, name):
    from pathlib import Path
    out = Path(__file__).resolve().parents[2] / "reports" / "figures" / name
    out.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out)
