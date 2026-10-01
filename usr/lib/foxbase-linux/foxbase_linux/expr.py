"""Avaliador simples de expressões xBase (para ?, ??, REPLACE)."""

import re
from datetime import date, datetime, timedelta

from .dbf import DBFError, parse_date


class ExprError(Exception):
    pass


TOKEN_RE = re.compile(
    r"""
    \s*(?:
      (?P<num>\d+(?:\.\d*)?|\.\d+)
    | (?P<str>"[^"]*"|'[^']*'|\[[^\]]*\])
    | (?P<log>\.(?:T|F|Y|N|AND|OR|NOT)\.)
    | (?P<name>[A-Za-z_][A-Za-z0-9_]*(?:->[A-Za-z_][A-Za-z0-9_]*)?)
    | (?P<op><>|<=|>=|!=|==|[-+*/(),=<>#$!])
    )""",
    re.VERBOSE | re.IGNORECASE,
)


def tokenize(text):
    pos = 0
    tokens = []
    text = text.rstrip()
    while pos < len(text):
        match = TOKEN_RE.match(text, pos)
        if not match or match.end() == pos:
            raise ExprError(f"Syntax error near: {text[pos:pos + 10]}")
        pos = match.end()
        kind = match.lastgroup
        value = match.group(kind)
        tokens.append((kind, value))
    return tokens


def format_value(value):
    if isinstance(value, bool):
        return ".T." if value else ".F."
    if isinstance(value, date):
        return value.strftime("%d/%m/%Y")
    if value is None:
        return "  /  /    "
    if isinstance(value, float):
        return f"{value:.2f}".rjust(10)
    if isinstance(value, int):
        return str(value).rjust(10)
    return str(value)


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
            raise ExprError(f"Unexpected: {self.tokens[self.pos][1]}")
        return value

    def evaluate_list(self, text):
        """Avalia lista separada por vírgulas (para ?)."""
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
            raise ExprError(f"Unexpected: {self.tokens[self.pos][1]}")
        return values

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
            left = bool(left) or bool(right)
        return left

    def _and(self):
        left = self._not()
        while self._accept("log", ".AND."):
            right = self._not()
            left = bool(left) and bool(right)
        return left

    def _not(self):
        if self._accept("log", ".NOT.") or self._accept("op", "!"):
            return not bool(self._not())
        return self._compare()

    def _compare(self):
        left = self._additive()
        tk, tv = self._peek()
        if tk == "op" and tv in ("=", "==", "<>", "!=", "#", "<", ">", "<=", ">=", "$"):
            self.pos += 1
            right = self._additive()
            if tv == "$":
                return str(left) in str(right)
            if isinstance(left, str) and isinstance(right, str):
                if tv == "=":  # comparação xBase (SET EXACT OFF)
                    return left.startswith(right)
                if tv == "==":
                    return left.rstrip() == right.rstrip()
            try:
                return {
                    "=": lambda a, b: a == b,
                    "==": lambda a, b: a == b,
                    "<>": lambda a, b: a != b,
                    "!=": lambda a, b: a != b,
                    "#": lambda a, b: a != b,
                    "<": lambda a, b: a < b,
                    ">": lambda a, b: a > b,
                    "<=": lambda a, b: a <= b,
                    ">=": lambda a, b: a >= b,
                }[tv](left, right)
            except TypeError as exc:
                raise ExprError("Data type mismatch.") from exc
        return left

    def _additive(self):
        left = self._term()
        while True:
            if self._accept("op", "+"):
                right = self._term()
                left = self._add(left, right)
            elif self._accept("op", "-"):
                right = self._term()
                left = self._sub(left, right)
            else:
                return left

    def _term(self):
        left = self._unary()
        while True:
            if self._accept("op", "*"):
                right = self._unary()
                left = self._num(left) * self._num(right)
            elif self._accept("op", "/"):
                right = self._num(self._unary())
                if right == 0:
                    raise ExprError("Division by zero.")
                left = self._num(left) / right
            else:
                return left

    def _unary(self):
        if self._accept("op", "-"):
            return -self._num(self._unary())
        if self._accept("op", "+"):
            return self._num(self._unary())
        return self._primary()

    def _primary(self):
        tk, tv = self._peek()
        if tk is None:
            raise ExprError("Missing expression.")
        self.pos += 1

        if tk == "num":
            return float(tv) if "." in tv else int(tv)
        if tk == "str":
            return tv[1:-1]
        if tk == "log":
            up = tv.upper()
            if up in (".T.", ".Y."):
                return True
            if up in (".F.", ".N."):
                return False
            raise ExprError(f"Unexpected: {tv}")
        if tk == "op" and tv == "(":
            value = self._or()
            if not self._accept("op", ")"):
                raise ExprError("Missing ).")
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
                            raise ExprError("Missing ).")
                        break
                return self._call(tv.upper(), args)
            return self._field(tv)
        raise ExprError(f"Unexpected: {tv}")

    # ----------------------------------------------------------- helpers
    @staticmethod
    def _num(value):
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise ExprError("Data type mismatch.")
        return value

    def _add(self, a, b):
        if a is None and isinstance(b, (int, float)):
            return None  # data vazia + n = data vazia
        if isinstance(a, str) and isinstance(b, str):
            return a + b
        if isinstance(a, date) and isinstance(b, (int, float)) and not isinstance(b, bool):
            return a + timedelta(days=int(b))
        return self._num(a) + self._num(b)

    def _sub(self, a, b):
        if isinstance(a, str) and isinstance(b, str):
            return a.rstrip() + b + " " * (len(a) - len(a.rstrip()))
        if isinstance(a, date) and isinstance(b, date):
            return (a - b).days
        if isinstance(a, date) and isinstance(b, (int, float)) and not isinstance(b, bool):
            return a - timedelta(days=int(b))
        return self._num(a) - self._num(b)

    def _field(self, name):
        dbf = self.app.current_dbf
        if "->" in name:
            name = name.split("->", 1)[1]
        if dbf and dbf.record_count and not self.app.eof:
            fi = dbf.field_index(name)
            if fi >= 0:
                rec = min(self.app.current_record, dbf.record_count - 1)
                return dbf.typed_value(rec, fi)
        elif dbf and dbf.field_index(name) >= 0:
            field = dbf.fields[dbf.field_index(name)]
            return {"C": " " * field["length"], "N": 0, "D": None, "L": False}.get(field["type"], "")
        if name.upper() in self.app.memvars:
            return self.app.memvars[name.upper()]
        raise ExprError(f"Variable not found: {name.upper()}")

    def _call(self, name, args):
        app = self.app
        dbf = app.current_dbf

        def arg(i, default=None):
            return args[i] if len(args) > i else default

        if name == "RECNO":
            return app.current_record + 1 if dbf else 0
        if name == "RECCOUNT":
            return dbf.record_count if dbf else 0
        if name == "EOF":
            return not dbf or app.eof
        if name == "BOF":
            return not dbf or app.current_record == 0
        if name == "DELETED":
            return bool(dbf and dbf.record_count and not app.eof
                        and dbf.records[app.current_record]["deleted"])
        if name == "DBF":
            return str(dbf.filename.name).upper() if dbf else ""
        if name == "DATE":
            return date.today()
        if name == "TIME":
            return datetime.now().strftime("%H:%M:%S")
        if name in ("UPPER", "LOWER", "TRIM", "RTRIM", "LTRIM", "ALLTRIM", "LEN"):
            text = arg(0)
            if not isinstance(text, str):
                raise ExprError("Data type mismatch.")
            return {
                "UPPER": text.upper,
                "LOWER": text.lower,
                "TRIM": text.rstrip,
                "RTRIM": text.rstrip,
                "LTRIM": text.lstrip,
                "ALLTRIM": text.strip,
                "LEN": lambda: len(text),
            }[name]()
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
            return _str_of_number(self._num(arg(0, 0)), int(arg(1, 10)), int(arg(2, 0)))
        if name == "VAL":
            try:
                return float(str(arg(0, "")).strip() or 0)
            except ValueError:
                return 0
        if name == "INT":
            return int(self._num(arg(0, 0)))
        if name == "ROUND":
            return round(self._num(arg(0, 0)), int(arg(1, 0)))
        if name == "ABS":
            return abs(self._num(arg(0, 0)))
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
                return 0
            return getattr(value, name.lower())
        if name == "CHR":
            return chr(int(self._num(arg(0, 32))))
        if name == "ASC":
            text = str(arg(0, ""))
            return ord(text[0]) if text else 0
        if name == "IIF":
            return arg(1) if arg(0) else arg(2)
        raise ExprError(f"Unrecognized function: {name}()")
