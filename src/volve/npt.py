"""Классификатор НПВ: вид (авария, осложнение, брак, ремонт, отказ сервиса, простой, инцидент) и причина.

В рапортах Volve вида НПВ нет: есть группа операции (interruption и код внутри неё),
отметка state / stateDetailActivity и комментарий супервайзера. Вид и причина
восстанавливаются в три шага:
  1) по коду операции и отметке (ловильные работы, перебуривание, поглощение, ГНВП, прихват);
  2) по ключевым словам комментария (узел оборудования, ожидание, инцидент);
  3) операция без причины внутри события наследует причину соседней операции этого события.
"""
import re

import pandas as pd

# Виды НПВ в порядке показа
ACCIDENT, TROUBLE, DEFECT = "авария", "осложнение", "брак"
REPAIR, SERVICE, IDLE, HSE = "ремонт бурового оборудования", "отказ оборудования сервисов", "простой", "инцидент"
UNKNOWN = "причина не указана"
KINDS = [REPAIR, SERVICE, TROUBLE, ACCIDENT, DEFECT, IDLE, HSE, UNKNOWN]
KIND_SHORT = {REPAIR: "ремонт", SERVICE: "отказ сервиса", TROUBLE: "осложнение", ACCIDENT: "авария",
              DEFECT: "брак", IDLE: "простой", HSE: "инцидент", UNKNOWN: "не указано"}

# Кто отвечает за вид НПВ
OWNER = {REPAIR: "буровой подрядчик", SERVICE: "сервисные подрядчики", TROUBLE: "скважина (геология и технология)",
         ACCIDENT: "скважина (геология и технология)", DEFECT: "качество работ", IDLE: "организация работ",
         HSE: "организация работ", UNKNOWN: "не указано"}

# Причина по коду операции группы interruption
CODE_RULES = {
    "fish": (ACCIDENT, "ловильные работы"),
    "sidetrack": (ACCIDENT, "перебуривание ствола"),
    "lost circulation": (TROUBLE, "поглощение"),
    "well control": (TROUBLE, "ГНВП"),
}
# Причина по отметке stateDetailActivity
DETAIL_RULES = {
    "stuck equipment": (ACCIDENT, "прихват"),
    "circulation loss": (TROUBLE, "поглощение"),
    "mud loss": (TROUBLE, "поглощение"),
    "kick": (TROUBLE, "ГНВП"),
    "injury": (HSE, "травма, падение предметов, остановка по безопасности"),
}

# Причина по тексту комментария. Порядок важен: первое совпадение побеждает.
TEXT_RULES = [
    (IDLE, "забастовка", r"strike"),
    (HSE, "травма, падение предметов, остановка по безопасности",
     r"injur|first aid|dropped object|\bdrops? incident|muster|gas alarm|fire alarm|man over ?board|time ?out for safety|"
     r"exhaust fumes|safety stand|\bh2s\b"),
    (IDLE, "ОЗЦ", r"^\W*(continued? )?(woc\b|w\.o\.c|wait(ed|ing)? (on|for) (the )?(cement|cmt))"),
    (ACCIDENT, "прихват", r"stuck|jarr(ed|ing)|free ?point|back ?off"),
    (ACCIDENT, "ловильные работы", r"\bfish|overshot|grapple|\bspear|junk|magnet|milled? on"),
    (TROUBLE, "поглощение", r"lost circ|losses|lost returns|\blcm\b|loss rate|mud loss"),
    (TROUBLE, "ГНВП", r"\bkick|well control|shut in well|kill(ed|ing)? (the )?well|influx|well flow"),
    (REPAIR, "краны и грузоподъёмные механизмы", r"\bcrane"),
    (REPAIR, "верхний привод", r"top ?drive|\btds\b|\bddm\b|dolly|\bibop\b|saver sub|wash ?pipe|swivel"),
    (REPAIR, "трубный манипулятор и ключи",
     r"roughneck|\bprs\b|pipe handling|rack(er|ing)|\bura\b|elevator|\btongs?\b|cat ?walk|finger ?board|\bhts\b|"
     r"\birn\b|\bps-? ?21|\bps-? ?30|power slips|pipe ?deck machine|\bpdm\b|conveyer|conveyor|eagle|stand ?lift"),
    (REPAIR, "лебёдка и талевая система",
     r"draw ?works|crown|travell?ing block|drill ?line|fast[- ]line|dead ?line|slip(ped)? and cut|compensator|\bbrake|sheave"),
    (REPAIR, "насосы и циркуляционная система",
     r"mud pump|\bmp ?#? ?\d|\bpump|stand ?pipe|shaker|flow ?line|\bhose|liner wash|pulsation|rupture dis[ck]|"
     r"mud system|centrifuge|degasser"),
    (REPAIR, "ПВО, райзер и устьевое оборудование",
     r"\bbop\b|annular|wellhead|riser|diverter|x-?mas|\bxmt\b|\brams?\b|\bsstt\b|lmrp|\blmpr\b|tension(er|ing)? cyl|"
     r"choke|kill line|\bpod\b|koomey|wear ?bushing|seal assembly|slip joint"),
    (REPAIR, "краны и грузоподъёмные механизмы", r"tugger|winch|gantry|man ?rider|sling"),
    (REPAIR, "энергетика, гидравлика, системы управления",
     r"hydraulic|\bhpu\b|power|generator|electric|\bplc\b|software|control system|\bvicis\b|\bscr\b|black ?out|"
     r"\bcomputer|\bdrillview|cyber"),
    (SERVICE, "телесистема, ВЗД и РУС",
     r"\bmwd\b|\blwd\b|\bgmwd\b|mud motor|\bmotor\b|\brss\b|power ?drive|auto ?trak|on ?trak|gyro|\bsurvey|"
     r"no signal|decod|pulser|teleco|sonic ?vision|stetho"),
    (SERVICE, "ГИС и канатная техника",
     r"wire ?line|\bw/?l\b|lubricator|tractor|\bcable|logging|tool ?string|\bmdt\b|\brft\b|\bvsp\b|schlumb|"
     r"western|atlas|\bccl\b|grease head|stuffing box"),
    (SERVICE, "оборудование крепления и заканчивания",
     r"liner hanger|hanger|\brtts\b|packer|\bplug\b|screen|perforat|\bguns?\b|\btcp\b|\bdhsv\b|scsssv|tubing|"
     r"running tool|\bpbr\b|whipstock|\bmill|cutter|casing torque|\bjam\b|thread|\bdope|\bmcbv\b|setting tool|"
     r"tie-?back|\bswedge|\besp\b"),
    (SERVICE, "цементирование", r"cement|\bcmt\b|\bwoc\b|squeeze"),
    (SERVICE, "вывоз и закачка шлама", r"skip|cuttings|slurry|\bcri\b"),
    (TROUBLE, "затяжки, посадки, проработки",
     r"overpull|tight|pack(ed|ing)? ?off|\bream|wash(ed)? down|took weight|stood up|hang(ing)? up|unable to pass|"
     r"work(ed)? (pipe|string|assembly)|cavings|\bfill\b|stall"),
    (IDLE, "ожидание материалов, персонала, судна",
     r"wait(ed|ing)? (for|on) .{0,40}(boat|vessel|equipment|personnel|tools?|helicopter|parts?|arriv|crew|chemical|"
     r"material|supply|schlumberger|baker|halliburton)|boat|vessel|helicopter"),
    (IDLE, "ожидание решений и согласований",
     r"instruction|\btown\b|decision|discuss|evaluat|meeting with|onshore|procedure|formulated plan|waited prior"),
    (REPAIR, "обслуживание и осмотры вне графика",
     r"maintenance|maintanence|housekeeping|house-keeping|\bservice|inspect|\bndt\b|\bdnv\b|derrick|scaffold|clean"),
    (REPAIR, "утечки и уплотнения", r"leak|\bseal"),
    (IDLE, "ожидание прочее", r"wait|w\.o\.|suspend|stand ?by|shut ?down"),
]
TEXT_RULES = [(kind, cause, re.compile(pattern)) for kind, cause, pattern in TEXT_RULES]

# Коды interruption, которые сами задают вид, когда текст причины не дал
CODE_FALLBACK = {
    "repair": (REPAIR, "узел не указан"),
    "maintain": (REPAIR, "обслуживание и осмотры вне графика"),
    "wait": (IDLE, "ожидание прочее"),
    "rig up/down": (REPAIR, "узел не указан"),
}


# Плановые операции, неудача которых означает переделку работы (брак)
DEFECT_BY_ACTIVITY = {
    "casing": "крепление: негерметичность, недоспуск, повторный спуск",
    "bop/wellhead equipment": "устьевое оборудование: повторная установка и опрессовка",
    "bop activities": "устьевое оборудование: повторная установка и опрессовка",
    "rig up/down": "испытание пласта: повторный спуск компоновки",
    "drill stem test": "испытание пласта: повторный спуск компоновки",
    "squeeze": "цементные мосты и изоляция: повтор",
    "cement plug": "цементные мосты и изоляция: повтор",
    "cut": "резка и извлечение колонн: повтор",
    "perforate": "перфорация: повтор",
    "wire line": "канатные работы: повтор",
    "completion string": "спуск компоновки заканчивания: повтор",
}
MEANWHILE = re.compile(r"\bmeanwhile|\bmeanwhlie|\bsimultaneously|\bin parallel|\bat the same time|\bwhile waiting", re.I)
# Слова, по которым видно, что в операции описан сам отказ, а не работа после него
FAILURE = re.compile(
    r"repair|trouble|fail|problem|leak|broke|broken|damag|chang(ed|ing)? out|replac|unable|not work|not function|"
    r"malfunction|fault|\bwait|stuck|\blost\b|investigat|inspect|could not|did not|no success|negative|\bneg\b|"
    r"shut ?down|suspend|stopped|halted|burst|worn|wash(ed)? out|modif|adjust|reset|re-?boot|calibrat|strike|"
    r"overpull|tight|pack|alarm|injur|dropped|time ?out|attempt")
WAIT_START = re.compile(r"^\W*(continued? )?(to )?(wait|w\.?o\.? |waiting|woc\b|stand ?by)")


def main_clause(comment):
    """Часть комментария до «meanwhile»: попутные работы причиной НПВ не являются."""
    text = (comment or "").lower().replace("\n", " ")
    m = MEANWHILE.search(text)
    return text[:m.start()] if m and m.start() > 2 else text


def match_text(text):
    for kind, cause, pattern in TEXT_RULES:
        if pattern.search(text):
            return kind, cause
    return None, None


def classify_row(row):
    """Вид и причина НПВ одной операции. Возвращает (вид, причина, источник, надёжность)."""
    if row.activity_group == "interruption" and row.activity in CODE_RULES:
        return (*CODE_RULES[row.activity], "код операции", True)
    if row.state_detail in DETAIL_RULES:
        return (*DETAIL_RULES[row.state_detail], "отметка рапорта", True)
    text = main_clause(row.comment)
    kind, cause = match_text(text)
    planned = row.activity_group != "interruption"
    failed = row.state_detail == "operation failed" or row.state == "fail"
    if planned and failed and row.activity in DEFECT_BY_ACTIVITY and kind not in (ACCIDENT, TROUBLE, HSE):
        return DEFECT, DEFECT_BY_ACTIVITY[row.activity], "отметка рапорта", True
    if kind is None:
        return None, None, None, False
    if WAIT_START.search(text) and kind not in (IDLE, HSE):
        # ждали ремонта узла — причина узел; ждали чего-то ещё — простой
        if not re.search(r"repair|trouble|fix|fault|fail", text):
            k2, c2 = match_text(re.sub(r"\bpump|\btown\b", " ", text[:60]))
            idle = [(k, c) for k, c, p in TEXT_RULES if k == IDLE and p.search(text)]
            kind, cause = idle[0] if idle else ((k2, c2) if k2 else (IDLE, "ожидание прочее"))
    return kind, cause, "комментарий", bool(FAILURE.search(text))


def add_npt(ops):
    """Добавляет к операциям НПВ событие, вид, причину и источник разметки."""
    o = ops.sort_values(["wellbore", "t_start", "seq"]).copy()
    npt = o.time_class == "npt"
    n = o[npt]

    # Событие: подряд идущие операции НПВ на одном стволе, перерыв не больше часа
    new = (n.wellbore != n.wellbore.shift()) | ((n.t_start - n.t_end.shift()).dt.total_seconds() > 3600)
    o.loc[npt, "event"] = new.cumsum()

    res = n.apply(classify_row, axis=1, result_type="expand")
    res.columns = ["npt_kind", "npt_cause", "npt_source", "strong"]
    weak = res[~res.strong.astype(bool)].copy()
    res.loc[weak.index, ["npt_kind", "npt_cause", "npt_source"]] = None
    o.loc[npt, ["npt_kind", "npt_cause", "npt_source"]] = res[["npt_kind", "npt_cause", "npt_source"]]

    # Операция без описанного отказа наследует причину события: от предыдущей операции, затем от следующей
    n = o[npt]
    filled = n.groupby("event")[["npt_kind", "npt_cause"]].transform(lambda s: s.ffill().bfill())
    inherited = n.npt_kind.isna() & filled.npt_kind.notna()
    o.loc[npt, ["npt_kind", "npt_cause"]] = filled
    o.loc[inherited[inherited].index, "npt_source"] = "соседняя операция события"

    # В событии отказ не описан нигде: берём упоминание узла в комментарии
    rest = npt & o.npt_kind.isna()
    w = weak[weak.npt_kind.notna() & rest.reindex(weak.index)]
    o.loc[w.index, ["npt_kind", "npt_cause"]] = w[["npt_kind", "npt_cause"]]
    o.loc[w.index, "npt_source"] = "комментарий"

    # Остаток: вид по коду interruption и отметке рапорта
    rest = npt & o.npt_kind.isna()
    for code, (kind, cause) in CODE_FALLBACK.items():
        m = rest & (o.activity_group == "interruption") & (o.activity == code)
        o.loc[m, ["npt_kind", "npt_cause", "npt_source"]] = [kind, cause, "код операции"]
    rest = npt & o.npt_kind.isna()
    m = rest & (o.state_detail == "equipment failure")
    o.loc[m, ["npt_kind", "npt_cause", "npt_source"]] = [REPAIR, "узел не указан", "отметка рапорта"]
    rest = npt & o.npt_kind.isna()
    m = rest & ((o.state_detail == "operation failed") | (o.state == "fail"))
    o.loc[m, ["npt_kind", "npt_cause", "npt_source"]] = [DEFECT, "повторные работы без описания", "отметка рапорта"]
    rest = npt & o.npt_kind.isna()
    o.loc[rest, ["npt_kind", "npt_cause", "npt_source"]] = [UNKNOWN, UNKNOWN, "нет"]
    o["npt_owner"] = o.npt_kind.map(OWNER)
    return o


def events(ops):
    """События НПВ: одна строка на событие, вид и причина — по наибольшему времени внутри события."""
    n = ops[ops.time_class == "npt"]
    top = (n.groupby(["event", "npt_kind", "npt_cause"]).hours.sum().reset_index()
           .sort_values("hours").groupby("event").tail(1).set_index("event")[["npt_kind", "npt_cause"]])
    first = n.sort_values("t_start").groupby("event").first()
    longest = n.loc[n.groupby("event").hours.idxmax()].set_index("event").comment
    ev = pd.DataFrame({
        "wellbore": first.wellbore, "scope": first.scope, "stage": first.stage, "start": n.groupby("event").t_start.min(),
        "end": n.groupby("event").t_end.max(), "hours": n.groupby("event").hours.sum(),
        "hole_in": first.hole_in, "comment": longest,
    }).join(top)
    return ev.reset_index()
