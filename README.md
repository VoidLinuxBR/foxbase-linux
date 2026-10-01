<div align="center">

# 🔵 foxbase-linux

**FoxBASE Linux - ambiente xBase em terminal inspirado no FoxBASE+ para DOS (DBF, BROWSE, PRG)**

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg?style=for-the-badge)](LICENSE)

</div>

---

**FoxBASE Linux** — ambiente xBase em terminal, inspirado no FoxBASE+/FoxPro clássico para DOS:
barra de menus, Command Window, BROWSE, tela EDIT e editor de programas —
tudo em `curses`, sem GTK nem dependências externas.

## Dependências

- Python 3.9+ (só biblioteca padrão)
- Harbour com `hbmk2` (opcional — só para `DO prog` / F5 no editor)

## Uso

```bash
foxbase-linux                   # abre na pasta atual
foxbase-linux clientes.dbf      # já abre o DBF (USE)
foxbase-linux programa.prg      # já abre o programa no editor
foxbase-linux --version
```

Sem instalar, direto do repositório: `./usr/bin/foxbase-linux`.

Terminal mínimo: 80x24. O DBF é lido/gravado diretamente pelo programa.

### Codepage

O codepage vem do *language driver* do header do DBF. Se o arquivo não
declara nenhum (comum em DBFs de Clipper/FoxBASE), usa `cp850` (acentos pt_BR).
Para mudar: `FOXBASE_CODEPAGE=cp437 foxbase-linux`.

## Teclas

```text
F10       menu (setas, Enter, letra inicial, Esc)
F1        ajuda          F6  Command Window
F2        USE (abrir)    F7  editor de programa
F3        BROWSE         F9  APPEND (novo registro + EDIT)
F4        estrutura      Ctrl-Q sair
F5        compilar/rodar o programa do editor (Harbour)
```

**BROWSE:** ↑↓ PgUp PgDn Home End · ←→ rola colunas · Enter edita ·
Ctrl-T/Ctrl-U/Del marca/desmarca exclusão · F9/Ctrl-N novo registro · Esc sai

**EDIT:** ↑↓/Tab muda de campo · Enter (ou começar a digitar) edita ·
PgUp/PgDn registro anterior/próximo · Ctrl-W ou F2 grava · Esc cancela

**Editor:** setas, Home/End, PgUp/PgDn, Del, Backspace junta linhas,
Ctrl-Y apaga linha, Tab, F2 grava (pede nome se novo), F5 roda, Esc volta

**Command Window:** ↑↓ histórico, ←→ Home End Del para editar a linha

## Comandos (aceitam abreviação de 4 letras: `BROW`, `DISP STRU`, `APPE BLAN`)

```text
USE [arquivo]            CLOSE DATABASES          CREATE arquivo
BROWSE                   EDIT / CHANGE [n]        APPEND [BLANK]
LIST [FOR cond]          DISPLAY [ALL]            DISPLAY STRUCTURE
LIST MEMORY
GO n | GO TOP | GO BOTTOM | n                     SKIP [n]
LOCATE FOR cond          CONTINUE
REPLACE campo WITH expr [, campo WITH expr] [ALL] [FOR cond]
DELETE [ALL] [FOR cond]  RECALL [ALL] [FOR cond]  PACK   ZAP
COUNT [FOR cond]         SUM [campos] [FOR cond]
? expr[, expr]           ?? expr
STORE expr TO var        var = expr
MODIFY COMMAND arq       DO arq                   RUN cmd  /  ! cmd
DIR [máscara]            CD [pasta]               CLEAR [ALL]  HELP  QUIT
```

### Expressões

Operadores `+ - * /`, comparações `= == <> # < > <= >=`, `$` (contido),
`.AND. .OR. .NOT.`, literais `'texto'`, `"texto"`, `[texto]`, `.T.`/`.F.`.

Funções: `RECNO() RECCOUNT() EOF() BOF() DELETED() DBF() DATE() TIME()
UPPER() LOWER() TRIM() RTRIM() LTRIM() ALLTRIM() LEN() SUBSTR() LEFT() RIGHT()
SPACE() REPLICATE() STR() VAL() INT() ROUND() ABS() DTOC() DTOS() CTOD()
DAY() MONTH() YEAR() CHR() ASC() IIF()`.

Datas no formato `dd/mm/aaaa` (SET DATE BRITISH).

## Exemplo

```text
. CREATE clientes
    (campos: CODIGO,N,5  NOME,C,30  CIDADE,C,20  NASC,D  LIMITE,N,10,2  ATIVO,L)
. APPEND BLANK
. REPLACE codigo WITH 1, nome WITH 'João', nasc WITH CTOD('15/03/1980'), ativo WITH .T.
. LIST FOR cidade = 'Porto'
. ? nome, nasc + 30, limite * 2
. BROWSE
```

Em `/usr/share/foxbase-linux/exemplos/` há um `clientes.dbf` e um `ola.prg` prontos.

## Instalação

```bash
git clone https://github.com/voidlinuxbr/foxbase-linux.git
cd foxbase-linux/pkgfile && pkgmake
```

## Créditos

Vilmar Catafesta <vcatafesta@gmail.com> — https://voidbr.org — Licença MIT.
