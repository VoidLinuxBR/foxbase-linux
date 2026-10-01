import curses


C_BLUE = 1
C_MENU = 2
C_REVERSE = 3
C_STATUS = 4
C_BORDER = 5
C_WINDOW = 6
C_DISABLED = 7
C_HOTKEY = 8
C_ERROR = 9


def init_colors():
    curses.start_color()
    try:
        curses.use_default_colors()
    except curses.error:
        pass

    curses.init_pair(C_BLUE, curses.COLOR_WHITE, curses.COLOR_BLUE)
    curses.init_pair(C_MENU, curses.COLOR_BLACK, curses.COLOR_CYAN)
    curses.init_pair(C_REVERSE, curses.COLOR_BLACK, curses.COLOR_WHITE)
    curses.init_pair(C_STATUS, curses.COLOR_BLACK, curses.COLOR_CYAN)
    curses.init_pair(C_BORDER, curses.COLOR_WHITE, curses.COLOR_BLUE)
    curses.init_pair(C_WINDOW, curses.COLOR_WHITE, curses.COLOR_BLUE)
    curses.init_pair(C_DISABLED, curses.COLOR_CYAN, curses.COLOR_BLUE)
    curses.init_pair(C_HOTKEY, curses.COLOR_RED, curses.COLOR_CYAN)
    curses.init_pair(C_ERROR, curses.COLOR_WHITE, curses.COLOR_RED)


def clear(stdscr):
    stdscr.bkgd(" ", curses.color_pair(C_BLUE))
    stdscr.erase()


def put(stdscr, y, x, text, attr=0):
    h, w = stdscr.getmaxyx()
    if y < 0 or y >= h or x < 0 or x >= w:
        return
    text = str(text)[:max(0, w - x)]
    if not attr & curses.A_COLOR:
        attr |= curses.color_pair(C_BLUE)
    try:
        stdscr.addstr(y, x, text, attr)
    except curses.error:
        # escrever na última célula da tela gera erro, mas o texto sai
        pass


def fill(stdscr, y, x, width, char=" ", attr=0):
    put(stdscr, y, x, char * max(0, width), attr)


def box(stdscr, y, x, h, w, title=None, attr=None, clear=False):
    if h < 2 or w < 2:
        return

    attr = attr or curses.color_pair(C_BORDER)

    put(stdscr, y, x, "┌" + "─" * (w - 2) + "┐", attr)
    for row in range(y + 1, y + h - 1):
        put(stdscr, row, x, "│", attr)
        if clear:
            fill(stdscr, row, x + 1, w - 2)
        put(stdscr, row, x + w - 1, "│", attr)
    put(stdscr, y + h - 1, x, "└" + "─" * (w - 2) + "┘", attr)

    if title:
        title = f" {title} "[:max(0, w - 4)]
        put(stdscr, y, x + max(1, (w - len(title)) // 2), title,
            curses.color_pair(C_BORDER) | curses.A_BOLD)


def centered(stdscr, y, text, attr=0):
    _, w = stdscr.getmaxyx()
    put(stdscr, y, max(0, (w - len(text)) // 2), text, attr)


class MenuBar:
    """Barra de menus estilo FoxBASE/FoxPro DOS.

    menus: [(nome, [(rótulo, ação, tecla_atalho_texto), ...]), ...]
    """

    def __init__(self, app, menus):
        self.app = app
        self.menus = menus
        self.active = False
        self.index = 0
        self.item = 0

    def _menu_x(self, index):
        x = 1
        for i in range(index):
            x += len(self.menus[i][0]) + 2
        return x

    def draw(self, stdscr):
        _, width = stdscr.getmaxyx()
        fill(stdscr, 0, 0, width, " ", curses.color_pair(C_MENU))

        for idx, (name, _) in enumerate(self.menus):
            x = self._menu_x(idx)
            if self.active and idx == self.index:
                put(stdscr, 0, x - 1, f" {name} ",
                    curses.color_pair(C_REVERSE) | curses.A_BOLD)
            else:
                put(stdscr, 0, x, name[0], curses.color_pair(C_HOTKEY) | curses.A_BOLD)
                put(stdscr, 0, x + 1, name[1:], curses.color_pair(C_MENU))

    def open(self, index=None):
        self.active = True
        if index is not None:
            self.index = index
        self.item = 0

    def close(self):
        self.active = False

    def popup(self, stdscr):
        if not self.active:
            return

        _, items = self.menus[self.index]
        x = self._menu_x(self.index) - 1
        _, sw = stdscr.getmaxyx()

        label_w = max(len(it[0]) for it in items)
        key_w = max((len(it[2]) if len(it) > 2 else 0) for it in items)
        width = label_w + key_w + 6
        x = min(x, max(0, sw - width - 1))

        box(stdscr, 1, x, len(items) + 2, width, clear=True)

        for row, it in enumerate(items):
            label = it[0]
            hot = it[2] if len(it) > 2 else ""
            text = " " + label.ljust(label_w + 2) + hot.rjust(key_w) + " "
            attr = (curses.color_pair(C_REVERSE) if row == self.item
                    else curses.color_pair(C_BLUE))
            put(stdscr, 2 + row, x + 1, text.ljust(width - 2), attr)

    def key(self, ch):
        """Retorna a ação escolhida (callable) ou None."""
        if ch in (27, curses.KEY_F10):
            self.close()
            return None

        if ch == curses.KEY_LEFT:
            self.index = (self.index - 1) % len(self.menus)
            self.item = 0
            return None

        if ch == curses.KEY_RIGHT:
            self.index = (self.index + 1) % len(self.menus)
            self.item = 0
            return None

        items = self.menus[self.index][1]

        if ch == curses.KEY_UP:
            self.item = (self.item - 1) % len(items)
            return None

        if ch == curses.KEY_DOWN:
            self.item = (self.item + 1) % len(items)
            return None

        if ch in (10, 13, curses.KEY_ENTER):
            action = items[self.item][1]
            self.close()
            return action

        if isinstance(ch, str):
            letter = ch.upper()
            for row, it in enumerate(items):
                if it[0][:1].upper() == letter:
                    self.item = row
                    self.close()
                    return it[1]

        return None
