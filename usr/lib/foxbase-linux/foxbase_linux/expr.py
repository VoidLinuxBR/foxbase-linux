"""Avaliador de expressões xBase (?, ??, STORE, REPLACE, FOR/WHILE).

Os números carregam largura e casas decimais (classe Num), como no FoxBASE+:
'? 5' mostra "5", '? x' (variável) mostra em 10 posições, um campo N(10,2)
mostra em 10 posições com 2 casas, '? 10/3' mostra " 3.33".
"""

import re
from datetime import date, datetime, timedelta

from . import settings
from .dbf import DBFError, parse_date


class ExprError(Exception):
    pass


class Num(float):
    """Número com largura e decimais de exibição."""

    def __new__(cls, value, width=10, dec=0):
        obj = super().__new__(cls, value)
        obj.width = max(1, int(width))
        obj.dec = max(0, int(dec))
        return obj

    def text(self):
        if self.dec:
            out = f"{float(self):.{self.dec}f}"
        else:
            out = str(int(round(float(self))))
        return out.rjust(self.width)


def num(value, width=10, dec=0):
    if isinstance(value, Num):
        return value
    return Num(value, width, dec)


TOKEN_RE = re.compile(
    r"""
    \s*(?:
      (?P<num>\d+(?:\.\d*)?|\.\d+)
    | (?P<str>"[^"]*"|'[^']*'|\[[^\]]*\])
    | (?P<log>\.(?:T|F|Y|N|AND|OR|NOT)\.)
    | (?P<name>[A-Za-z_][A-Za-z0-9_]*(?:->[A-Za-z_][A-Za-z0-9_]*)?)
    | (?P<op><>|<=|>=|!=|==|\*\*|[-+*/^(),=<>#$!%])
    )""",
    re.VERBOSE | re.IGNORECASE,
)


def tokenize(text):
    pos = 0
    tokens = []
    text = text.rstrip()
    while pos < len(text):
        if not text[pos:].strip():
            break
        match = TOKEN_RE.match(text, pos)
        if not match or match.end() == pos:
            raise ExprError("Syntax error.")
        pos = match.end()
        kind = match.lastgroup
        tokens.append((kind, match.group(kind)))
    return tokens


def format_value(value):
    """Valor como sai no ? / STORE."""
    if isinstance(value, bool):
        return ".T." if value else ".F."
    if isinstance(value, date):
        return settings.fmt_date(value)
    if value is None:
        return settings.blank_date()
    if isinstance(value, Num):
        return value.text()
    if isinstance(value, (int, float)):
        return num(value).text()
    return str(value)


def type_letter(value):
    if isinstance(value, bool):
        return "L"
    if isinstance(value, (int, float)):
        return "N"
    if isinstance(value, date) or value is None:
        return "D"
    return "C"


def _str_of_number(value, length=10, decimals=0):
    text = f"{value:.{decimals}f}" if decimals else str(int(round(value)))
    if len(text) > length:
        return "*" * length
    return text.rjust(length)


class Evaluator:
    def __init__(self, app):
        self.app = app

    # ------------------------------------------------------------ parser
    def evaluate(self, text):
        self.tokens = tokenize(text)
        self.pos = 0
        if not self.tokens:
            raise ExprError("Missing expression.")
        value = self._or()
        if self.pos < len(self.tokens):
            raise ExprError("Syntax error.")
        return value

    def evaluate_list(self, text):
        """Lista separada por vírgulas (para ?)."""
        self.tokens = tokenize(text)
        self.pos = 0
        values = []
        if not self.tokens:
            return values
        while True:
            values.append(self._or())
            if self._accept("op", ","):
                continue
            break
        if self.pos < len(self.tokens):
            raise ExprError("Syntax error.")
        return values

    def check(self, text):
        """Valida a sintaxe sem avaliar (usado antes de imprimir com ?)."""
        tokens = tokenize(text)
        depth = 0
        expect_operand = True
        for kind, value in tokens:
            if kind == "op" and value == "(":
                depth += 1
                expect_operand = True
            elif kind == "op" and value == ")":
                depth -= 1
                expect_operand = False
            elif kind == "op" and value == ",":
                expect_operand = True
            elif kind == "op" or (kind == "log" and value.upper() in (".AND.", ".OR.")):
                if expect_operand and value not in ("-", "+", "!"):
                    raise ExprError("Missing operand.")
                expect_operand = True
            elif kind == "log" and value.upper() == ".NOT.":
                expect_operand = True
            else:
                expect_operand = False
        if tokens and expect_operand:
            raise ExprError("Missing operand.")
        if depth:
            raise ExprError("Unbalanced parenthesis.")

    def _peek(self):
        return self.tokens[self.pos] if self.pos < len(self.tokens) else (None, None)

    def _accept(self, kind, value=None):
        tk, tv = self._peek()
        if tk == kind and (value is None or tv.upper() == value):
            self.pos += 1
            return tv
        return None

    def _or(self):
        left = self._and()
        while self._accept("log", ".OR."):
            right = self._and()
            left = self._bool(left) or self._bool(right)
        return left

    def _and(self):
        left = self._not()
        while self._accept("log", ".AND."):
            right = self._not()
            left = self._bool(left) and self._bool(right)
        return left

    @staticmethod
    def _bool(value):
        if not isinstance(value, bool):
            raise ExprError("Not a Logical expression.")
        return value

    def _not(self):
        if self._accept("log", ".NOT.") or self._accept("op", "!"):
            return not self._bool(self._not())
        return self._compare()

    def _compare(self):
        left = self._additive()
        tk, tv = self._peek()
        if tk == "op" and tv in ("=", "==", "<>", "!=", "#", "<", ">", "<=", ">=", "$"):
            self.pos += 1
            right = self._additive()
            if tv == "$":
                if not (isinstance(left, str) and isinstance(right, str)):
                    raise ExprError("Operator/operand type mismatch.")
                return left in right
            if type_letter(left) != type_letter(right):
                raise ExprError("Operator/operand type mismatch.")
            if isinstance(left, str):
                if tv == "==":
                    return left.rstrip() == right.rstrip()
                if not settings.on("EXACT"):
                    left = left[:len(right)]
                else:
                    left, right = left.rstrip(), right.rstrip()
            if left is None or right is None:
                left = left or date.min
                right = right or date.min
            ops = {
                "=": lambda a, b: a == b, "==": lambda a, b: a == b,
                "<>": lambda a, b: a != b, "!=": lambda a, b: a != b,
                "#": lambda a, b: a != b, "<": lambda a, b: a < b,
                ">": lambda a, b: a > b, "<=": lambda a, b: a <= b,
                ">=": lambda a, b: a >= b,
            }
            return ops[tv](left, right)
        return left

    def _additive(self):
        left = self._term()
        while True:
            if self._accept("op", "+"):
                left = self._add(left, self._term())
            elif self._accept("op", "-"):
                left = self._sub(left, self._term())
            else:
                return left

    def _term(self):
        left = self._power()
        while True:
            if self._accept("op", "*"):
                a, b = self._num(left), self._num(self._power())
                left = Num(float(a) * float(b), a.width + b.width + 1, a.dec + b.dec)
            elif self._accept("op", "/"):
                a, b = self._num(left), self._num(self._power())
                if float(b) == 0:
                    raise ExprError("Division by zero.")
                dec = max(a.dec, settings.state["DECIMALS"])
                left = Num(float(a) / float(b), max(a.width, b.width) + dec + 1, dec)
            elif self._accept("op", "%"):
                a, b = self._num(left), self._num(self._power())
                left = Num(float(a) % float(b), max(a.width, b.width), max(a.dec, b.dec))
            else:
                return left

    def _power(self):
        left = self._unary()
        while self._accept("op", "^") or self._accept("op", "**"):
            a, b = self._num(left), self._num(self._unary())
            left = Num(float(a) ** float(b), 10, settings.state["DECIMALS"])
        return left

    def _unary(self):
        if self._accept("op", "-"):
            a = self._num(self._unary())
            return Num(-float(a), a.width + 1, a.dec)
        if self._accept("op", "+"):
            return self._num(self._unary())
        return self._primary()

    def _primary(self):
        tk, tv = self._peek()
        if tk is None:
            raise ExprError("Missing operand.")
        self.pos += 1

        if tk == "num":
            dec = len(tv.split(".", 1)[1]) if "." in tv else 0
            return Num(float(tv), len(tv), dec)
        if tk == "str":
            return tv[1:-1]
        if tk == "log":
            up = tv.upper()
            if up in (".T.", ".Y."):
                return True
            if up in (".F.", ".N."):
                return False
            raise ExprError("Missing operand.")
        if tk == "op" and tv == "(":
            value = self._or()
            if not self._accept("op", ")"):
                raise ExprError("Unbalanced parenthesis.")
            return value
        if tk == "name":
            if self._accept("op", "("):
                args = []
                if not self._accept("op", ")"):
                    while True:
                        args.append(self._or())
                        if self._accept("op", ","):
                            continue
                        if not self._accept("op", ")"):
                            raise ExprError("Unbalanced parenthesis.")
                        break
                return self._call(tv.upper(), args)
            return self._field(tv)
        raise ExprError("Missing operand.")

    # ----------------------------------------------------------- helpers
    @staticmethod
    def _num(value):
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise ExprError("Operator/operand type mismatch.")
        return num(value)

    def _add(self, a, b):
        if isinstance(a, str) and isinstance(b, str):
            return a + b
        if (isinstance(a, date) or a is None) and isinstance(b, (int, float)) \
                and not isinstance(b, bool):
            return a + timedelta(days=int(b)) if a else None
        a, b = self._num(a), self._num(b)
        return Num(float(a) + float(b), max(a.width, b.width) + 1, max(a.dec, b.dec))

    def _sub(self, a, b):
        if isinstance(a, str) and isinstance(b, str):
            return a.rstrip() + b + " " * (len(a) - len(a.rstrip()))
        if isinstance(a, date) and isinstance(b, date):
            return Num((a - b).days, 10)
        if (isinstance(a, date) or a is None) and isinstance(b, (int, float)) \
                and not isinstance(b, bool):
            return a - timedelta(days=int(b)) if a else None
        a, b = self._num(a), self._num(b)
        return Num(float(a) - float(b), max(a.width, b.width) + 1, max(a.dec, b.dec))

    def field_value(self, dbf, index, fi):
        field = dbf.fields[fi]
        value = dbf.typed_value(index, fi)
        if field["type"] in ("N", "F"):
            return Num(value, field["length"], field["decimals"])
        if field["type"] == "M":
            return dbf.read_memo(dbf.records[index]["values"][fi])
        return value

    def _field(self, name):
        dbf = self.app.current_dbf
        if "->" in name:
            name = name.split("->", 1)[1]
        if dbf:
            fi = dbf.field_index(name)
            if fi >= 0:
                if dbf.record_count and not self.app.eof:
                    rec = min(self.app.current_record, dbf.record_count - 1)
                    return self.field_value(dbf, rec, fi)
                field = dbf.fields[fi]
                return {
                    "C": " " * field["length"],
                    "N": Num(0, field["length"], field["decimals"]),
                    "D": None, "L": False,
                }.get(field["type"], "")
        if name.upper() in self.app.memvars:
            return self.app.memvars[name.upper()]
        raise ExprError("Variable not found.")

    def _call(self, name, args):
        app = self.app
        dbf = app.current_dbf

        def arg(i, default=None):
            return args[i] if len(args) > i else default

        def n10(value, dec=0):
            return Num(value, 10, dec)

        if name == "RECNO":
            if not dbf:
                return n10(0)
            return n10(dbf.record_count + 1 if app.eof else app.current_record + 1)
        if name == "RECCOUNT":
            return n10(dbf.record_count if dbf else 0)
        if name == "RECSIZE":
            return n10(dbf.record_length if dbf else 0)
        if name == "FCOUNT":
            return n10(len(dbf.fields) if dbf else 0)
        if name == "FIELD":
            i = int(self._num(arg(0, 1)))
            return dbf.fields[i - 1]["name"] if dbf and 0 < i <= len(dbf.fields) else ""
        if name == "EOF":
            return not dbf or app.eof
        if name == "BOF":
            return not dbf or app.bof
        if name == "FOUND":
            return bool(app.found)
        if name == "DELETED":
            return bool(dbf and dbf.record_count and not app.eof
                        and dbf.records[app.current_record]["deleted"])
        if name == "DBF":
            return str(dbf.filename) if dbf else ""
        if name == "DATE":
            return date.today()
        if name == "TIME":
            return datetime.now().strftime("%H:%M:%S")
        if name in ("UPPER", "LOWER", "TRIM", "RTRIM", "LTRIM", "ALLTRIM"):
            text = arg(0)
            if not isinstance(text, str):
                raise ExprError("Operator/operand type mismatch.")
            if name == "UPPER":  # como no original: só letras ASCII
                return "".join(c.upper() if c.isascii() else c for c in text)
            if name == "LOWER":
                return "".join(c.lower() if c.isascii() else c for c in text)
            return {
                "TRIM": text.rstrip, "RTRIM": text.rstrip, "LTRIM": text.lstrip, "ALLTRIM": text.strip,
            }[name]()
        if name == "LEN":
            if not isinstance(arg(0), str):
                raise ExprError("Operator/operand type mismatch.")
            return n10(len(arg(0)))
        if name == "AT":
            return n10(str(arg(1, "")).find(str(arg(0, ""))) + 1)
        if name == "SUBSTR":
            text, start = str(arg(0, "")), int(self._num(arg(1, 1)))
            length = arg(2)
            text = text[max(0, start - 1):]
            return text[:int(length)] if length is not None else text
        if name == "LEFT":
            return str(arg(0, ""))[:int(self._num(arg(1, 0)))]
        if name == "RIGHT":
            n = int(self._num(arg(1, 0)))
            return str(arg(0, ""))[-n:] if n else ""
        if name == "SPACE":
            return " " * int(self._num(arg(0, 0)))
        if name == "REPLICATE":
            return str(arg(0, "")) * int(self._num(arg(1, 0)))
        if name == "STR":
            return _str_of_number(float(self._num(arg(0, 0))), int(arg(1, 10)), int(arg(2, 0)))
        if name == "VAL":
            text = str(arg(0, "")).strip()
            match = re.match(r"[-+]?\d*\.?\d*", text)
            try:
                value = float(match.group(0)) if match and match.group(0) not in ("", "-", "+", ".") else 0.0
            except ValueError:
                value = 0.0
            return n10(value, settings.state["DECIMALS"])
        if name == "INT":
            return n10(int(float(self._num(arg(0, 0)))))
        if name == "ROUND":
            a = self._num(arg(0, 0))
            places = int(arg(1, 0))
            return Num(round(float(a), places), a.width, max(0, places))
        if name == "ABS":
            a = self._num(arg(0, 0))
            return Num(abs(float(a)), a.width, a.dec)
        if name in ("MAX", "MIN"):
            a, b = arg(0), arg(1)
            return (max if name == "MAX" else min)(a, b)
        if name == "MOD":
            a, b = self._num(arg(0, 0)), self._num(arg(1, 1))
            return Num(float(a) % float(b), max(a.width, b.width), max(a.dec, b.dec))
        if name == "SQRT":
            return n10(float(self._num(arg(0, 0))) ** 0.5, settings.state["DECIMALS"])
        if name == "DTOC":
            return format_value(arg(0))
        if name == "DTOS":
            value = arg(0)
            return value.strftime("%Y%m%d") if isinstance(value, date) else " " * 8
        if name == "CTOD":
            try:
                return parse_date(str(arg(0, "")))
            except DBFError:
                return None
        if name in ("DAY", "MONTH", "YEAR"):
            value = arg(0)
            if not isinstance(value, date):
                return Num(0, 3 if name != "YEAR" else 5)
            return Num(getattr(value, name.lower()), 3 if name != "YEAR" else 5)
        if name == "DOW":
            value = arg(0)
            return Num((value.isoweekday() % 7) + 1 if isinstance(value, date) else 0, 3)
        if name == "CDOW":
            value = arg(0)
            return value.strftime("%A") if isinstance(value, date) else ""
        if name == "CMONTH":
            value = arg(0)
            return value.strftime("%B") if isinstance(value, date) else ""
        if name == "CHR":
            return chr(int(self._num(arg(0, 32))))
        if name == "ASC":
            text = str(arg(0, ""))
            return n10(ord(text[0]) if text else 0)
        if name == "ISALPHA":
            return str(arg(0, ""))[:1].isalpha()
        if name == "ISUPPER":
            return str(arg(0, ""))[:1].isupper()
        if name == "ISLOWER":
            return str(arg(0, ""))[:1].islower()
        if name == "IIF":
            return arg(1) if arg(0) else arg(2)
        if name == "TYPE":
            try:
                return type_letter(self.app.command.evaluator.evaluate(str(arg(0, ""))))
            except ExprError:
                return "U"
        if name == "VERSION":
            return "FoxBASE+ 2.10"
        if name == "OS":
            return "Linux"
        raise ExprError("Unrecognized phrase/keyword.")
