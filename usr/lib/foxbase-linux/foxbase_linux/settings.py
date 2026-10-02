"""Estado dos comandos SET (como no FoxBASE+ 2.10) e formatação de datas."""

from datetime import date

# SET DATE: formato -> (ordem dos campos, separador)
DATE_FORMATS = {
    "AMERICAN": ("mdy", "/"),
    "ANSI": ("ymd", "."),
    "BRITISH": ("dmy", "/"),
    "FRENCH": ("dmy", "/"),
    "GERMAN": ("dmy", "."),
    "ITALIAN": ("dmy", "-"),
}
DATE_NAMES = {
    "AMERICAN": "American", "ANSI": "ANSI", "BRITISH": "British",
    "FRENCH": "French", "GERMAN": "German", "ITALIAN": "Italian",
}

# chaves ON/OFF de DISPLAY STATUS, na ordem e com o padrão do original
SWITCHES = [
    ("ALTERNATE", False), ("BELL", True), ("CARRY", False), ("CENTURY", False),
    ("CLEAR", True), ("COLOR", True), ("CONFIRM", False), ("CONSOLE", True),
    ("DEBUG", False), ("DELETED", False), ("DELIMITERS", False), ("DEVICE", "scrn"),
    ("DOHISTORY", False), ("ECHO", False), ("ESCAPE", True), ("EMS", False),
    ("EXACT", False), ("FIELDS", False), ("FIXED", False), ("HEADING", True),
    ("HISTORY", True), ("INTENSITY", True), ("MENU", True), ("PRINT", False),
    ("SAFETY", True), ("SCOREBOARD", True), ("STATUS", True), ("STEP", False),
    ("TALK", True), ("UNIQUE", False),
]

state = {name: value for name, value in SWITCHES}
state["DATE"] = "AMERICAN"
state["DECIMALS"] = 2
state["MARGIN"] = 0
state["MEMOWIDTH"] = 50
state["TYPEAHEAD"] = 20
state["HISTORY_N"] = 20


def on(name):
    return bool(state.get(name))


def date_layout():
    order, sep = DATE_FORMATS[state["DATE"]]
    return order, sep


def blank_date():
    order, sep = date_layout()
    year = "    " if on("CENTURY") else "  "
    parts = {"d": "  ", "m": "  ", "y": year}
    return sep.join(parts[c] for c in order)


def date_width():
    return 10 if on("CENTURY") else 8


def fmt_date(value):
    """date -> texto conforme SET DATE / SET CENTURY ('' ou None -> em branco)."""
    if not value:
        return blank_date()
    order, sep = date_layout()
    year = f"{value.year:04d}" if on("CENTURY") else f"{value.year % 100:02d}"
    parts = {"d": f"{value.day:02d}", "m": f"{value.month:02d}", "y": year}
    return sep.join(parts[c] for c in order)


def fmt_date_raw(raw):
    """aaaammdd do DBF -> texto exibido."""
    raw = (raw or "").strip()
    if len(raw) == 8 and raw.isdigit():
        try:
            return fmt_date(date(int(raw[:4]), int(raw[4:6]), int(raw[6:])))
        except ValueError:
            pass
    return blank_date()


def parse_display_date(text):
    """Texto no formato atual -> date (None se em branco). ValueError se inválida."""
    text = str(text).strip()
    order, sep = date_layout()
    if not text.replace(sep, "").replace("/", "").strip():
        return None
    if len(text) == 8 and text.isdigit() and sep not in text:
        return date(int(text[:4]), int(text[4:6]), int(text[6:]))
    for s in (sep, "/", "-", "."):
        if s in text:
            parts = [p.strip() for p in text.split(s)]
            break
    else:
        raise ValueError(text)
    if len(parts) != 3 or not all(p.isdigit() for p in parts):
        raise ValueError(text)
    values = dict(zip(order, (int(p) for p in parts)))
    year = values["y"]
    if year < 100:
        year += 1900
    return date(year, values["m"], values["d"])
