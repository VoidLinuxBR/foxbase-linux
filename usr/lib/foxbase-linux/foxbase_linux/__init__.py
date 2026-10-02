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
    app.py       janela principal (ponto), menus e telas cheias
    console.py   área de saída da linha de comandos, como no original
    command.py   interpretador de comandos xBase e formatos de saída
    expr.py      avaliador de expressões (números com largura/decimais)
    settings.py  estado dos SET (DATE, CENTURY, TALK, DELETED...)
    dbf.py       leitura/escrita de DBF (dBASE III / FoxBASE+) e memo .DBT
    browser.py   BROWSE
    form.py      EDIT / CHANGE / APPEND
    structure.py CREATE / MODIFY STRUCTURE
    editor.py    MODIFY COMMAND e edição de memo
    helpview.py  HELP
    fieldedit.py edição de um campo (sobrescrever/inserir, data, número)
    screen.py    caixas de navegação, barra de status, mensagens, menus de opção
    widgets.py   teclado e linha de edição
    runner.py    RUN / DO: programas externos e Harbour (hbmk2)
    harbour.py   ponte com o Harbour (hbrun + bridge.prg) para comandos/funções
    ui.py        cores, molduras e barra de menus (curses)
"""

APP_NAME = "foxbase-linux"
APP_VERSION = "0.4.2"
