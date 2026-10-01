# -*- coding: utf-8 -*-
#
#   foxbase_linux - núcleo do FoxBASE Linux
#
#   Copyright (c) 2026, Vilmar Catafesta <vcatafesta@gmail.com>
#   Assembled By Vilmar Catafesta for the VoidBR project.
#   Licença: MIT (veja /usr/share/licenses/foxbase-linux/LICENSE)
#
"""FoxBASE Linux — ambiente xBase em terminal, inspirado no FoxBASE+ para DOS.

Módulos:
    app.py      janela principal, menus, teclas globais e ações de banco
    command.py  Command Window: interpretador de comandos xBase
    expr.py     avaliador de expressões xBase (?, REPLACE, FOR)
    dbf.py      leitura/escrita direta de DBF (dBASE III / FoxBASE+)
    browser.py  BROWSE (grade de registros)
    editor.py   MODIFY COMMAND (editor de programas .prg)
    widgets.py  teclado, campo de edição, diálogos e tela EDIT
    runner.py   RUN / DO / F5: programas externos e Harbour (hbmk2)
    ui.py       cores, molduras e barra de menus (curses)
"""

APP_NAME = "foxbase-linux"
APP_VERSION = "0.1.0"
