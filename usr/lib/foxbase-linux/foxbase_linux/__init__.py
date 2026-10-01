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
    structure.py CREATE / MODIFY STRUCTURE (tela de estrutura)
    form.py     EDIT / CHANGE / APPEND (tela de registro)
    browser.py  BROWSE (grade com edição direta)
    fieldedit.py edição de um campo (sobrescrever/inserir, data, número)
    screen.py   caixa de ajuda, barra de status e linha de mensagens
    editor.py   MODIFY COMMAND (editor de programas .prg)
    widgets.py  teclado, linha de edição e diálogos
    runner.py   RUN / DO / F5: programas externos e Harbour (hbmk2)
    ui.py       cores, molduras e barra de menus (curses)
"""

APP_NAME = "foxbase-linux"
APP_VERSION = "0.2.0"
