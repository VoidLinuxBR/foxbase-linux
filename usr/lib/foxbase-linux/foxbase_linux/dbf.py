"""Leitura/escrita direta de arquivos DBF (dBASE III / FoxBASE+)."""

import os
import struct
from datetime import date, datetime
from pathlib import Path


class DBFError(Exception):
    pass


# Language driver ID (byte 29 do header) -> codepage
LDID_CODEPAGES = {
    0x01: "cp437",
    0x02: "cp850",
    0x03: "cp1252",
    0x57: "cp1252",
    0x58: "cp1252",
    0x59: "cp1252",
    0x64: "cp852",
    0x65: "cp866",
    0x66: "cp865",
    0x67: "cp861",
    0x6A: "cp737",
    0x6B: "cp857",
    0xC8: "cp1250",
    0xC9: "cp1251",
    0xCA: "cp1254",
    0xCB: "cp1253",
}
CODEPAGE_LDID = {"cp437": 0x01, "cp850": 0x02, "cp1252": 0x03}

# Sem language driver no header: usa FOXBASE_CODEPAGE ou cp850 (padrão BR).
DEFAULT_CODEPAGE = os.environ.get("FOXBASE_CODEPAGE", "cp850")

EDITABLE_TYPES = ("C", "N", "F", "D", "L")
VALID_CREATE_TYPES = ("C", "N", "D", "L")


def parse_date(text):
    """Aceita dd/mm/aaaa, dd/mm/aa, aaaammdd. Retorna date ou None."""
    text = str(text).strip()
    if not text or text.replace("/", "").strip() == "":
        return None
    if len(text) == 8 and text.isdigit():
        return datetime.strptime(text, "%Y%m%d").date()
    parts = text.replace("-", "/").replace(".", "/").split("/")
    if len(parts) != 3 or not all(p.strip().isdigit() for p in parts):
        raise DBFError(f"Invalid date: {text}")
    day, month, year = (int(p) for p in parts)
    if year < 100:
        year += 1900 if year >= 50 else 2000
    try:
        return date(year, month, day)
    except ValueError as exc:
        raise DBFError(f"Invalid date: {text}") from exc


class DBF:
    def __init__(self, filename):
        self.filename = Path(filename)
        self.fields = []
        self.records = []
        self.version = 0x03
        self.header_length = 0
        self.record_length = 0
        self.codepage = DEFAULT_CODEPAGE
        self._read()

    # ------------------------------------------------------------ create
    @classmethod
    def create(cls, filename, fields, allow_memo=False):
        """fields: lista de dicts {name, type, length, decimals}.

        allow_memo: aceita campos M já existentes (MODIFY STRUCTURE); o .DBT
        original continua sendo usado.
        """
        filename = Path(filename)
        if not fields:
            raise DBFError("Structure has no fields.")

        names = set()
        for field in fields:
            name = field["name"].upper()
            if not name or len(name) > 10:
                raise DBFError(f"Bad field name: {name!r}")
            if not (name[0].isalpha() and all(c.isalnum() or c == "_" for c in name)):
                raise DBFError(f"Bad field name: {name}")
            if name in names:
                raise DBFError(f"Duplicate field: {name}")
            names.add(name)
            field["name"] = name
            kind = field["type"].upper()
            field["type"] = kind
            if kind not in VALID_CREATE_TYPES and not (allow_memo and kind == "M"):
                raise DBFError(f"Bad field type: {kind}")
            if kind == "M":
                field["length"], field["decimals"] = 10, 0
            elif kind == "D":
                field["length"], field["decimals"] = 8, 0
            elif kind == "L":
                field["length"], field["decimals"] = 1, 0
            elif kind == "C":
                field["decimals"] = 0
                if not 1 <= field["length"] <= 254:
                    raise DBFError(f"Bad width for {name}")
            elif kind == "N":
                if not 1 <= field["length"] <= 19:
                    raise DBFError(f"Bad width for {name}")
                if field["decimals"] and field["decimals"] > field["length"] - 2:
                    raise DBFError(f"Bad decimals for {name}")

        header_length = 32 + 32 * len(fields) + 1
        record_length = 1 + sum(f["length"] for f in fields)
        today = date.today()

        header = bytearray(32)
        header[0] = 0x83 if any(f["type"] == "M" for f in fields) else 0x03
        header[1] = today.year - 1900
        header[2] = today.month
        header[3] = today.day
        struct.pack_into("<I", header, 4, 0)
        struct.pack_into("<H", header, 8, header_length)
        struct.pack_into("<H", header, 10, record_length)
        header[29] = CODEPAGE_LDID.get(DEFAULT_CODEPAGE, 0)

        data = bytearray(header)
        for field in fields:
            desc = bytearray(32)
            desc[0:len(field["name"])] = field["name"].encode("ascii")
            desc[11] = ord(field["type"])
            desc[16] = field["length"]
            desc[17] = field["decimals"]
            data += desc
        data += b"\x0D\x1A"

        try:
            filename.write_bytes(bytes(data))
        except OSError as exc:
            raise DBFError(str(exc)) from exc

        return cls(filename)

    # -------------------------------------------------------------- read
    def _read(self):
        with self.filename.open("rb") as f:
            header = f.read(32)
            if len(header) != 32:
                raise DBFError("Not a database file.")

            self.version = header[0]
            count = struct.unpack_from("<I", header, 4)[0]
            self.header_length = struct.unpack_from("<H", header, 8)[0]
            self.record_length = struct.unpack_from("<H", header, 10)[0]
            self.codepage = LDID_CODEPAGES.get(header[29], DEFAULT_CODEPAGE)

            if self.header_length < 33 or self.record_length < 1:
                raise DBFError("Not a database file.")

            self.fields.clear()
            offset = 1
            while f.tell() + 32 <= self.header_length:
                raw = f.read(32)
                if not raw or raw[0] == 0x0D:
                    break
                if len(raw) != 32:
                    raise DBFError("Invalid field descriptor.")
                name = raw[:11].split(b"\0", 1)[0].decode("ascii", errors="replace")
                self.fields.append({
                    "name": name.strip().upper(),
                    "type": chr(raw[11]).upper(),
                    "length": raw[16],
                    "decimals": raw[17],
                    "offset": offset,
                })
                offset += raw[16]

            if not self.fields:
                raise DBFError("Database has no fields.")

            f.seek(self.header_length)
            self.records.clear()

            for _ in range(count):
                raw = f.read(self.record_length)
                if len(raw) != self.record_length:
                    break
                values = []
                for field in self.fields:
                    chunk = raw[field["offset"]:field["offset"] + field["length"]]
                    text = chunk.decode(self.codepage, errors="replace")
                    if field["type"] == "C":
                        text = text.rstrip()
                    elif field["type"] in EDITABLE_TYPES:
                        text = text.strip()
                    # demais tipos (M, B, G...) ficam crus para preservar ponteiros
                    values.append(text)
                self.records.append({"deleted": raw[:1] == b"*", "values": values})

    # ------------------------------------------------------------- write
    def _encode(self, field, text):
        size = field["length"]
        if field["type"] in ("N", "F"):
            text = text.rjust(size)
        else:
            text = text.ljust(size)
        return text.encode(self.codepage, errors="replace")[:size].ljust(size, b" ")

    def save(self):
        today = date.today()
        try:
            with self.filename.open("r+b") as f:
                f.seek(1)
                f.write(bytes([today.year - 1900, today.month, today.day]))
                f.write(struct.pack("<I", self.record_count))
                f.seek(self.header_length)
                for record in self.records:
                    data = bytearray(b"*" if record["deleted"] else b" ")
                    for field, value in zip(self.fields, record["values"]):
                        data += self._encode(field, value)
                    f.write(data)
                f.write(b"\x1A")
                f.truncate()
        except OSError as exc:
            raise DBFError(str(exc)) from exc

    # ------------------------------------------------------------ values
    def field_index(self, name):
        name = name.strip().upper()
        for index, field in enumerate(self.fields):
            if field["name"] == name:
                return index
        return -1

    @staticmethod
    def display_width(field):
        if field["type"] == "D":
            return 10
        if field["type"] == "M":
            return 4
        return field["length"]

    @staticmethod
    def display_value(field, raw):
        kind = field["type"]
        if kind == "D":
            raw = raw.strip()
            if len(raw) == 8 and raw.isdigit():
                return f"{raw[6:8]}/{raw[4:6]}/{raw[0:4]}"
            return "  /  /    "
        if kind == "L":
            return raw.strip()[:1] if raw.strip() in ("T", "F", "Y", "N") else "?"
        if kind == "M":
            return "Memo" if raw.strip() not in ("", "0") else "memo"
        return raw

    def validate(self, field, text):
        """Converte texto digitado para o valor cru gravado no DBF."""
        kind = field["type"]
        text = "" if text is None else str(text)

        if kind == "C":
            return text[:field["length"]].rstrip()

        if kind in ("N", "F"):
            text = text.strip().replace(",", ".")
            if not text:
                return ""
            try:
                number = float(text)
            except ValueError as exc:
                raise DBFError(f"Not numeric: {text}") from exc
            dec = field["decimals"]
            out = f"{number:.{dec}f}" if dec else str(int(round(number)))
            if len(out) > field["length"]:
                raise DBFError(f"Numeric overflow in {field['name']}")
            return out

        if kind == "D":
            value = parse_date(text)
            return value.strftime("%Y%m%d") if value else ""

        if kind == "L":
            value = text.strip().upper()[:1]
            if value in ("T", "Y", "S"):
                return "T"
            if value in ("F", "N"):
                return "F"
            if value in ("", "?"):
                return ""
            raise DBFError("Logical must be T or F")

        raise DBFError(f"Field {field['name']} ({kind}) is read-only.")

    def typed_value(self, index, field_index):
        """Valor xBase tipado (str, número, date, bool) de um campo."""
        field = self.fields[field_index]
        raw = self.records[index]["values"][field_index]
        kind = field["type"]
        if kind == "C":
            return raw.ljust(field["length"])
        if kind in ("N", "F"):
            try:
                number = float(raw) if raw.strip() else 0.0
            except ValueError:
                number = 0.0
            return int(number) if not field["decimals"] else number
        if kind == "D":
            try:
                return parse_date(raw)
            except DBFError:
                return None
        if kind == "L":
            return raw.strip() in ("T", "Y")
        return raw

    def from_typed(self, field, value):
        if isinstance(value, bool):
            return self.validate(field, "T" if value else "F")
        if isinstance(value, date):
            if field["type"] == "D":
                return value.strftime("%Y%m%d")
            return self.validate(field, value.strftime("%d/%m/%Y"))
        if value is None:
            return ""
        return self.validate(field, str(value))

    # ----------------------------------------------------------- records
    @property
    def record_count(self):
        return len(self.records)

    def blank_values(self):
        return ["" for _ in self.fields]

    def append_blank(self):
        self.records.append({"deleted": False, "values": self.blank_values()})
        self.save()
        return len(self.records) - 1

    def delete(self, index):
        self.records[index]["deleted"] = True
        self.save()

    def recall(self, index):
        self.records[index]["deleted"] = False
        self.save()

    def pack(self):
        before = len(self.records)
        self.records = [r for r in self.records if not r["deleted"]]
        self.save()
        return before - len(self.records)

    def zap(self):
        self.records = []
        self.save()
