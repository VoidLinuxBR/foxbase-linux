"""HELP (F1 no ponto): grade de tópicos como no FoxBASE+ 2.10.

A lista e a navegação seguem o original; os textos de ajuda são próprios do
foxbase-linux (descrevem o que está implementado aqui).
"""

import curses

from . import screen, ui
from .widgets import is_enter, read_key

TOPICS = [
    "<ALIAS>", "<HISTORY>", "<OPERATOR", "<PATH>", "<SCOPE>", "?", "@", "ABS()",
    "ACCEPT", "ALIAS()", "APPEND", "ASC()", "AT()", "AVERAGE", "BOF()", "BROWSE",
    "CALL", "CANCEL", "CHANGE", "CHR()", "CLEAR", "CLOSE", "CMONTH()", "COL()",
    "CONTINUE", "COPY", "COUNT", "CREATE", "CTOD()", "DATE()", "DAY()", "DBF()",
    "DELETE", "DELETED()", "DIMENSION", "DIR", "DISKSPACE", "DISPLAY", "DO", "DOW()",
    "DTOC()", "EDIT", "EJECT", "EOF()", "ERASE", "ERROR()", "EXIT", "EXP()",
    "FCOUNT()", "FIELD()", "FILE()", "FIND", "FKLABEL()", "FKMAX()", "FLOCK()", "FLUSH",
    "FOUND()", "GATHER", "GETENV()", "GO", "HELP", "IF", "IIF()", "INDEX",
    "INKEY()", "INPUT", "INSERT", "INT()", "ISALPHA()", "ISCOLOR()", "ISLOWER()", "ISUPPER()",
    "JOIN", "KEYBOARD", "LABEL", "LEFT()", "LEN()", "LIST", "LOAD", "LOCATE",
    "LOG()", "LOOP", "LOWER()", "LTRIM()", "LUPDATE()", "MACROS-&", "MAX()", "MENU",
    "MESSAGE()", "MIN()", "MOD()", "MODIFY", "MONTH()", "MULTIUSER", "NDX()", "NOTE",
    "ON", "OS()", "PACK", "PARAMETER", "PCOL()", "PRIVATE", "PROCEDURE", "PROW()",
    "PUBLIC", "QUIT", "READ", "READKEY()", "RECALL", "RECCOUNT", "RECNO()", "RECSIZE()",
    "REINDEX", "RELEASE", "RENAME", "REPLACE", "REPLICATE", "REPORT", "RESTORE", "RESUME",
    "RETRY", "RETURN", "RIGHT()", "ROUND()", "ROW()", "RTRIM()", "RUN/!", "SAVE",
    "SCATTER", "SEEK", "SELECT", "SELECT()", "SET", "SKIP", "SORT", "SPACE()",
    "SQRT()", "STORE", "STR()", "STUFF()", "SUBSTR()", "SUM", "SUSPEND", "SYS()",
    "TEXT", "TIME()", "TOTAL", "TRANSFORM", "TRIM()", "TYPE", "TYPE()", "UDF",
    "UNLOCK", "UPDATE", "UPDATED()", "UPPER()", "USE", "VAL()", "VERSION()", "WAIT",
    "YEAR()", "ZAP",
]

TEXTS = {
    "?": "? <exp list> / ?? <exp list>\n\n? avança uma linha e mostra as expressões;\n"
         "?? mostra na posição atual do cursor.",
    "APPEND": "APPEND [BLANK]\n\nAbre a tela de inclusão de registros. Enter no primeiro\n"
              "campo de um registro em branco encerra. APPEND BLANK inclui um\n"
              "registro vazio sem abrir a tela.",
    "AVERAGE": "AVERAGE [<exp list>] [<scope>] [FOR <cond>] [WHILE <cond>]",
    "BROWSE": "BROWSE\n\nGrade de registros com edição direta. F10 abre o menu\n"
              "(Bottom, Top, Record #, fiNd, Skip, Lock, Freeze); F1 mostra ou\n"
              "esconde a caixa de navegação.",
    "CHANGE": "CHANGE [<scope>] - igual ao EDIT.",
    "CLEAR": "CLEAR [ALL | MEMORY]",
    "CLOSE": "CLOSE DATABASES | ALL",
    "CONTINUE": "CONTINUE - continua o último LOCATE.",
    "COUNT": "COUNT [<scope>] [FOR <cond>] [WHILE <cond>]",
    "CREATE": "CREATE [<arquivo>]\n\nTela de definição da estrutura. ^Home abre o menu\n"
              "(Bottom, Top, Field #, Save, Abandon); ^End grava.",
    "DELETE": "DELETE [<scope>] [FOR <cond>] [WHILE <cond>] / DELETE FILE <arquivo>",
    "DIR": "DIR [<máscara>]",
    "DISPLAY": "DISPLAY [<scope>] [<campos>] [FOR] [WHILE] [OFF]\n"
               "DISPLAY STRUCTURE | MEMORY | STATUS",
    "DO": "DO <programa> - compila com o Harbour (hbmk2) e executa.",
    "EDIT": "EDIT [<n>] - tela de edição do registro atual.",
    "GO": "GO[TO] <n> | TOP | BOTTOM  (ou só o número do registro)",
    "HELP": "HELP [<tópico>]",
    "INSERT": "INSERT - no foxbase-linux, igual ao APPEND.",
    "LIST": "LIST [<scope>] [<campos>] [FOR] [WHILE] [OFF]\n"
            "LIST STRUCTURE | MEMORY | STATUS",
    "LOCATE": "LOCATE [<scope>] FOR <cond> [WHILE <cond>]",
    "MODIFY": "MODIFY STRUCTURE | MODIFY COMMAND <arquivo>",
    "PACK": "PACK - remove os registros marcados.",
    "QUIT": "QUIT - encerra o foxbase-linux.",
    "RECALL": "RECALL [<scope>] [FOR <cond>] [WHILE <cond>]",
    "RELEASE": "RELEASE <variáveis> | ALL",
    "REPLACE": "REPLACE <campo> WITH <exp> [, ...] [<scope>] [FOR] [WHILE]",
    "RUN/!": "RUN <comando> / ! <comando> - executa no shell.",
    "SET": "SET TALK | DELETED | EXACT | CENTURY | SAFETY ... ON/OFF\n"
           "SET DATE AMERICAN | BRITISH | FRENCH | GERMAN | ITALIAN | ANSI\n"
           "SET DECIMALS TO <n> / SET DEFAULT TO <pasta>",
    "SKIP": "SKIP [<n>]",
    "STORE": "STORE <exp> TO <variáveis>  /  <var> = <exp>",
    "SUM": "SUM [<exp list>] [<scope>] [FOR <cond>] [WHILE <cond>]",
    "USE": "USE [<arquivo>]",
    "WAIT": "WAIT [<mensagem>]",
    "ZAP": "ZAP - apaga todos os registros (pergunta antes com SET SAFETY ON).",
}

COLS = 8
CELL = 9
STRIDE = 10


def _topic_page(app, topic):
    stdscr = app.stdscr
    h, _ = stdscr.getmaxyx()
    screen.clear(stdscr)
    text = TEXTS.get(topic)
    if text is None:
        text = f"No HELP on {topic} in foxbase-linux."
    lines = text.split("\n")
    lines[0] = "Format:   " + lines[0]
    for i, line in enumerate(lines):
        ui.put(stdscr, 1 + i, 7, line)
    screen.status_bar(stdscr, "HELP", topic.strip("<>"), "")
    screen.messages(stdscr, "UpLevel: PgUp,←,◄┘  Exit: Esc", "")
    curses.curs_set(0)
    stdscr.refresh()
    ch = None
    while ch is None or ch == curses.KEY_RESIZE:
        ch = read_key(stdscr)
    return ch != 27


def show_help(app, topic=""):
    stdscr = app.stdscr
    index = 0
    if topic:
        wanted = topic.strip().upper()
        matches = [t for t in TOPICS if t.strip("<>()").startswith(wanted)]
        if matches:
            if not _topic_page(app, matches[0]):
                return
            index = TOPICS.index(matches[0])
    search = ""
    while True:
        h, w = stdscr.getmaxyx()
        screen.clear(stdscr)
        rows = h - 3
        top = max(0, index // COLS - rows + 1)
        for i, name in enumerate(TOPICS):
            r = i // COLS - top
            if r < 0 or r >= rows:
                continue
            c = (i % COLS) * STRIDE
            attr = curses.color_pair(ui.C_REVERSE) if i == index else 0
            ui.put(stdscr, r, c, name[:CELL].ljust(CELL), attr)
            if i % COLS < COLS - 1:
                ui.put(stdscr, r, c + CELL, "│")
        screen.status_bar(stdscr, "HELP", "", app.rec_info())
        screen.messages(stdscr,
                        "MoveBar: ←,→,↑,↓  NameSearch: <char>  PickTopic: ◄┘  "
                        "UpLevel: PgUp  Exit: Esc", "Select HELP Topic")
        curses.curs_set(0)
        stdscr.refresh()
        ch = read_key(stdscr)
        if ch is None or ch == curses.KEY_RESIZE:
            continue
        if ch in (27, curses.KEY_PPAGE):
            return
        if ch == curses.KEY_LEFT:
            index = max(0, index - 1)
        elif ch == curses.KEY_RIGHT:
            index = min(len(TOPICS) - 1, index + 1)
        elif ch == curses.KEY_UP:
            index = max(0, index - COLS)
        elif ch == curses.KEY_DOWN:
            index = min(len(TOPICS) - 1, index + COLS)
        elif is_enter(ch):
            search = ""
            if not _topic_page(app, TOPICS[index]):
                return
        elif isinstance(ch, str):
            search += ch.upper()
            for i, name in enumerate(TOPICS):
                if name.strip("<").startswith(search):
                    index = i
                    break
            else:
                curses.beep()
                search = ""
