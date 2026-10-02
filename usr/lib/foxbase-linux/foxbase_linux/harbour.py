"""Ponte com o Harbour: comandos e funções que o foxbase-linux não tem
(ALERT(), ACHOICE(), MEMOEDIT(), @...SAY, hb_*() ...) são executados por um
processo hbrun que fica rodando com o bridge.prg.

O processo usa o mesmo terminal: durante a chamada ele desenha direto na tela
(a tela atual do foxbase-linux é repassada antes, para o ALERT aparecer por
cima dela) e lê o teclado. O que o '?' escreve volta por um arquivo
(SET ALTERNATE) e entra na tela de comandos; o banco, o registro atual e as
variáveis de memória são sincronizados nos dois sentidos a cada comando.
"""

import atexit
import curses
import errno
import os
import select
import re
import shutil
import subprocess
import tempfile
import time
from datetime import date
from pathlib import Path

from . import screen, settings, ui
from .expr import Num, type_letter

# codepage do DBF -> codepage do Harbour
START_TIMEOUT = 15  # segundos para o hbrun compilar o bridge e abrir a FIFO

HB_CODEPAGES = {"cp850": "PT850", "cp437": "EN", "cp1252": "PTISO"}
HB_DATE = {"AMERICAN": "mm/dd/yy", "ANSI": "yy.mm.dd", "BRITISH": "dd/mm/yy",
           "FRENCH": "dd/mm/yy", "GERMAN": "dd.mm.yy", "ITALIAN": "dd-mm-yy"}


def _keypad(cap):
    try:
        seq = curses.tigetstr(cap)
        if seq:
            os.write(1, seq)
    except (curses.error, OSError):
        pass


def bridge_source():
    here = Path(__file__).resolve().parent
    for candidate in (here.parent.parent.parent / "share" / "foxbase-linux" / "bridge.prg",
                      Path("/usr/share/foxbase-linux/bridge.prg")):
        if candidate.exists():
            return candidate
    return None


class HarbourBridge:
    def __init__(self, app):
        self.app = app
        self.proc = None
        self.tmp = None
        self.wfd = None
        self.rfd = None
        self.error = ""
        self.error_shown = False
        self.failed = False  # não tenta iniciar de novo a cada comando

    # ---------------------------------------------------------- processo
    @staticmethod
    def available():
        return bool(shutil.which("hbrun")) and bridge_source() is not None

    def _start(self):
        """Inicia o hbrun com o bridge.prg. Nunca bloqueia: se o hbrun não
        abrir a FIFO em START_TIMEOUT segundos (erro de compilação, versão
        antiga do Harbour...), desiste e guarda a mensagem em self.error."""
        if self.proc and self.proc.poll() is None:
            return True
        if not self.available() or self.failed:
            return False
        self.stop()
        self.error = ""
        screen.message(self.app.stdscr, "Please wait ...", 2)
        self.app.stdscr.refresh()
        self.tmp = tempfile.mkdtemp(prefix="foxbase-hb-")
        fin = os.path.join(self.tmp, "in")
        fout = os.path.join(self.tmp, "out")
        os.mkfifo(fin)
        os.mkfifo(fout)
        self.log_path = os.path.join(self.tmp, "hbrun.log")
        try:
            log = open(self.log_path, "wb")
            self.proc = subprocess.Popen(
                [shutil.which("hbrun"), str(bridge_source()), fin, fout],
                stdout=None, stderr=log, cwd=os.getcwd())
            log.close()
            # leitura: abre já (não bloqueia); escrita: espera o hbrun abrir a FIFO
            self.rfd = os.open(fout, os.O_RDONLY | os.O_NONBLOCK)
            deadline = time.monotonic() + START_TIMEOUT
            while True:
                try:
                    self.wfd = os.open(fin, os.O_WRONLY | os.O_NONBLOCK)
                    break
                except OSError as exc:
                    if exc.errno != errno.ENXIO:
                        raise
                if self.proc.poll() is not None or time.monotonic() > deadline:
                    self._fail_start()
                    return False
                time.sleep(0.05)
            os.set_blocking(self.wfd, True)
        except OSError as exc:
            self.error = f"Harbour bridge: {exc}"
            self.stop()
            return False
        self.rbuf = b""
        atexit.register(self.stop)
        return True

    def _fail_start(self):
        if self.proc and self.proc.poll() is None:
            self.proc.kill()
        self.error = "Harbour bridge failed to start (hbrun)." + self._log_tail()
        self.failed = True
        self.stop()

    def _log_tail(self):
        try:
            text = Path(self.log_path).read_text(errors="replace")
        except (OSError, AttributeError):
            return ""
        lines = [l for l in text.splitlines()
                 if l.strip() and "not found" not in l.lower()]
        return ("\n" + "\n".join(lines[-4:])) if lines else ""

    def stop(self):
        proc = getattr(self, "proc", None)
        if proc and proc.poll() is None:
            try:
                os.write(self.wfd, b"QUIT\n")
                proc.wait(timeout=2)
            except (OSError, subprocess.TimeoutExpired, AttributeError, TypeError):
                proc.kill()
        for name in ("wfd", "rfd"):
            fd = getattr(self, name, None)
            if fd is not None:
                try:
                    os.close(fd)
                except OSError:
                    pass
            setattr(self, name, None)
        self.proc = None
        if getattr(self, "tmp", None):
            shutil.rmtree(self.tmp, ignore_errors=True)
            self.tmp = None

    def _read_reply(self):
        """Lê até 'END'. Retorna as linhas ou None se o hbrun morreu."""
        reply = []
        while True:
            while b"\n" in self.rbuf:
                line, self.rbuf = self.rbuf.split(b"\n", 1)
                text = line.decode("latin-1")
                if text == "END":
                    return reply
                reply.append(text)
            ready, _, _ = select.select([self.rfd], [], [], 0.2)
            if ready:
                chunk = os.read(self.rfd, 65536)
                if chunk:
                    self.rbuf += chunk
                    continue
            if self.proc.poll() is not None:
                return None

    # ------------------------------------------------------------ chamada
    def _codepage(self):
        db = self.app.current_dbf
        return db.codepage if db else "cp850"

    def _enc(self, text):
        """Texto do foxbase-linux -> bytes do codepage, levados como latin-1."""
        cp = self._codepage()
        return str(text).encode(cp, errors="replace").decode("latin-1")

    def _dec(self, text):
        return text.encode("latin-1").decode(self._codepage(), errors="replace")

    def run(self, command, targets=()):
        """Executa a linha no Harbour. Retorna a lista de erros do Harbour
        ([] se deu certo) ou None se o Harbour não está disponível."""
        app = self.app
        stdscr = app.stdscr
        if not self._start():
            if self.error and not self.error_shown:
                self.error_shown = True
                return [self.error]
            return None
        h, w = stdscr.getmaxyx()
        alt = os.path.join(self.tmp, "alt.txt")
        try:
            os.remove(alt)
        except OSError:
            pass

        db = app.current_dbf
        lines = [f"CP {HB_CODEPAGES.get(self._codepage(), 'PT850')}"]
        lines.append(f"DBF {self._enc(db.filename) if db else ''}")
        if db:
            lines.append(f"REC {app.current_record + 1} {1 if app.eof else 0}")
        fmt = HB_DATE[settings.state["DATE"]]
        if settings.on("CENTURY"):
            fmt = fmt.replace("yy", "yyyy")
        lines.append(f"DATE {fmt}")
        lines.append(f"DEC {settings.state['DECIMALS']}")
        for name, value in app.memvars.items():
            lines.append(self._var_line(name, value))
        for name in targets:
            if name.upper() not in app.memvars:
                lines.append(f"VAR {name.upper()} U ")
        stdscr.refresh()
        for row, text in enumerate(ui.snapshot(range(h))):
            lines.append(f"SCR {row} {self._enc(text)}")
        lines.append(f"POS {h - 4} 0")
        lines.append(f"OUT {alt}")
        lines.append(f"CMD {self._enc(command)}")
        lines.append("END")
        _keypad("rmkx")  # setas no modo normal (ESC [ C), que o Harbour entende
        try:
            os.write(self.wfd, ("\n".join(lines) + "\n").encode("latin-1"))
            reply = self._read_reply()
        except OSError:
            reply = None
        if reply is None:
            _keypad("smkx")
            stdscr.clear()
            self.error = "Harbour bridge stopped." + self._log_tail()
            self.stop()
            return [self.error]
        _keypad("smkx")
        stdscr.clear()  # o Harbour desenhou direto no terminal: redesenha tudo
        return self._apply(reply, alt, h)

    @staticmethod
    def _var_line(name, value):
        kind = type_letter(value)
        if kind == "N":
            text = repr(float(value))
        elif kind == "D":
            text = value.strftime("%Y%m%d") if value else ""
        elif kind == "L":
            text = "T" if value else "F"
        else:
            text = str(value).replace("\\", "\\\\").replace("\n", "\\n")
        return f"VAR {name} {kind} {text}"

    def _apply(self, reply, alt, h):
        app = self.app
        console = app.console
        screen_rows = {}
        errors = []
        new_vars = {}
        dbf_path, rec = None, None
        for line in reply:
            key, _, arg = line.partition(" ")
            if key == "ERR":
                errors.append(self._dec(arg))
            elif key == "DBF":
                dbf_path = self._dec(arg)
            elif key == "REC":
                parts = arg.split()
                rec = (int(parts[0]), parts[1] == "1")
            elif key == "VAR":
                name, kind, value = (arg.split(" ", 2) + ["", ""])[:3]
                new_vars[name.upper()] = self._var_value(kind, self._dec(value))
            elif key == "SCR":
                row, _, text = arg.partition(" ")
                screen_rows[int(row)] = self._dec(text)

        # banco e registro: o Harbour pode ter aberto outro banco ou alterado dados
        if dbf_path:
            if not app.current_dbf or Path(dbf_path).resolve() != \
                    Path(app.current_dbf.filename).resolve():
                app.open_dbf(dbf_path)
            else:
                app.reload_dbf()
            if rec and app.current_dbf:
                count = app.current_dbf.record_count
                app.current_record = max(0, min(rec[0] - 1, count - 1))
                app.eof = rec[1] or count == 0
        elif dbf_path is not None and app.current_dbf:
            app.close_dbf()
        app.memvars.clear()
        app.memvars.update(new_vars)

        # tela desenhada pelo Harbour (@...SAY, CLS): fica acima do ponto
        if screen_rows:
            top = app.top_row()
            console.lines = [screen_rows.get(r, "") for r in range(top, h - 3)]
            console.col = 0
        # saída do ? / ?? / LIST do Harbour
        try:
            data = Path(alt).read_bytes().replace(b"\x1a", b"").replace(b"\r", b"")
        except OSError:
            data = b""
        if data:
            console.out(data.decode(self._codepage(), errors="replace"))
        return errors

    @staticmethod
    def _var_value(kind, value):
        if kind == "N":
            try:
                number = float(value)
            except ValueError:
                number = 0.0
            dec = len(value.split(".", 1)[1]) if "." in value else 0
            return Num(number, 10, min(dec, settings.state["DECIMALS"]) if dec else 0)
        if kind == "D":
            return date(int(value[:4]), int(value[4:6]), int(value[6:8])) \
                if re.fullmatch(r"\d{8}", value) else None
        if kind == "L":
            return value == "T"
        return value.replace("\\n", "\n").replace("\\\\", "\\")
