<div align="center">

# 🔵 foxbase-linux

**FoxBASE Linux - ambiente xBase em terminal inspirado no FoxBASE+ para DOS (DBF, BROWSE, PRG)**

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg?style=for-the-badge)](LICENSE)

</div>

---

**FoxBASE Linux** — reprodução em terminal (curses) do **FoxBASE+ 2.10** para DOS.
O comportamento foi comparado tela a tela com o FoxBASE+ original rodando no DOSBox:
linha de comandos (ponto), mensagens, formatos de saída, BROWSE, EDIT/APPEND,
CREATE/MODIFY STRUCTURE, MODIFY COMMAND e HELP. Por cima fica a barra de menus do
foxbase-linux (F12 ou Alt+letra), que só executa comandos do original.

## Dependências

- Python 3.9+ (só biblioteca padrão)
- Harbour com `hbmk2` (opcional — só para `DO programa`)

## Uso

```bash
foxbase-linux                   # abre na pasta atual
foxbase-linux clientes.dbf      # já abre o DBF (USE)
foxbase-linux programa.prg      # já abre o programa (MODIFY COMMAND)
foxbase-linux --version
```

Sem instalar, direto do repositório: `./usr/bin/foxbase-linux`.
Terminal mínimo: 80x24 (o original usava 80x25).

### Codepage

O codepage vem do *language driver* do header do DBF. Se o arquivo não
declara nenhum (comum em DBFs de Clipper/FoxBASE), usa `cp850` (acentos pt_BR).
Para mudar: `FOXBASE_CODEPAGE=cp437 foxbase-linux`.

## A tela de comandos

Como no original: o ponto fica sempre logo acima da barra de status
(`Command Line ║<C:>║CLIENTES ║Rec: 1/6 ║ ║`) e a saída rola para cima;
`?` começa em linha nova e `??` escreve onde o cursor está. Comandos que precisam
de um banco sem nenhum aberto perguntam `No database in USE.  Enter file name:`.
↑↓ recuperam comandos anteriores. Ao sair do EDIT/APPEND/HELP a tela continua
visível acima do ponto; BROWSE, CREATE, MODIFY STRUCTURE e MODIFY COMMAND limpam.

### Teclas de função (as do original)

```text
F1  HELP              F6  display status
F2  central           F7  display memory
F3  list              F8  display
F4  dir               F9  append
F5  display structure F10 edit
F12 / Alt+letra: menu do foxbase-linux       Ins: modo de inserção
```

## Telas cheias

Todas têm a caixa de navegação do original no topo (F1 mostra/esconde), a barra de
status (modo, arquivo, registro, `Ins`, `Del`) e as mensagens nas duas últimas
linhas. Digitar sobrescreve (Ins alterna) e o campo cheio passa para o próximo.

**BROWSE:** "View and edit fields."; começa com o registro atual no topo; F10 ou
^Home abre o menu **Bottom, Top, Record #, fiNd, Skip, Lock, Freeze**; ↓ no último
registro pergunta "Add new records? (Y/N)"; ^←/^→ rolam as colunas; ^U marca
exclusão; ^Y apaga o campo; ^End grava e sai; Esc sai.

**EDIT / CHANGE / APPEND:** nome do campo na coluna 0, valor na 11. ↑↓/Enter mudam
de campo, PgUp/PgDn de registro (passar do último sai em EOF, PgUp no primeiro sai);
data inválida: "Invalid date. (press SPACE)"; ^U marca exclusão; ^Home edita memo;
^End grava e sai; Esc sai. No APPEND, Enter no primeiro campo de um registro em
branco encerra.

**CREATE / MODIFY STRUCTURE:** "Bytes remaining", campos numerados em duas colunas
(field name, type, width, dec); o tipo pela barra de espaço (Character, Numeric,
Date, Logical, Memo) ou pela letra; mensagens de ajuda de cada coluna; ^N insere,
^U remove; ^Home abre o menu **Bottom, Top, Field #, Save, Abandon**; ^End grava
("Press ENTER to confirm.  Any other key to resume."); Esc pergunta "Are you sure
you want to abandon the operation? (Y/N)". Depois do CREATE: "Input data records
now? (Y/N)". O MODIFY STRUCTURE guarda o original em `.BAK`; se algum campo mudou
de nome, pergunta "Should data be COPIED from backup for all fields? (Y/N)".

**MODIFY COMMAND:** "Edit: arquivo" na linha 0; ^W ou ^End grava; Esc sai
("Abort editing? (Y/N):" se alterado); ^N insere linha, ^Y apaga linha, ^T apaga
palavra, Home/End palavra, ^←/^→ início/fim da linha, ^KF procura, ^KL procura de
novo, ^KR lê arquivo, ^KW grava em arquivo, ^KB reformata o parágrafo.

## Comandos (aceitam abreviação de 4 letras: `BROW`, `DISP STRU`, `APPE BLAN`)

```text
USE [arquivo]   CLOSE DATABASES   CREATE [arquivo]   MODIFY STRUCTURE
BROWSE   EDIT / CHANGE [n]   APPEND [BLANK]   INSERT
LIST / DISPLAY [escopo] [campos/expressões] [FOR cond] [WHILE cond] [OFF]
LIST / DISPLAY STRUCTURE | MEMORY | STATUS
GO[TO] n | TOP | BOTTOM   n   SKIP [n]   LOCATE [escopo] FOR cond   CONTINUE
REPLACE campo WITH expr [, ...] [escopo] [FOR] [WHILE]
DELETE / RECALL [escopo] [FOR] [WHILE]   DELETE FILE arq   PACK   ZAP
COUNT / SUM / AVERAGE [expressões] [escopo] [FOR] [WHILE]
? expr[, expr]   ?? expr   STORE expr TO var[, var]   var = expr   RELEASE
MODIFY COMMAND arq   DO arq   RUN cmd / ! cmd   DIR [máscara]   WAIT [msg]
SET TALK|DELETED|EXACT|CENTURY|SAFETY|HEADING... ON/OFF
SET DATE AMERICAN|BRITISH|FRENCH|GERMAN|ITALIAN|ANSI   SET DECIMALS TO n
SET DEFAULT TO pasta   CLEAR [ALL|MEMORY]   HELP [tópico]   QUIT
```

Escopo: `ALL`, `NEXT n`, `RECORD n`, `REST`. Datas no formato do `SET DATE`
(padrão AMERICAN, mm/dd/aa, como no original).

### Expressões

Operadores `+ - * / % ^`, comparações `= == <> # < > <= >=`, `$` (contido),
`.AND. .OR. .NOT.`, literais `'texto'`, `"texto"`, `[texto]`, `.T.`/`.F.`.
Os números saem com a largura do original (`? 5` → `5`, variável → 10 posições,
campo → largura do campo, `? 10/3` → ` 3.33`).

Funções: `RECNO() RECCOUNT() RECSIZE() FCOUNT() FIELD() EOF() BOF() FOUND()
DELETED() DBF() DATE() TIME() UPPER() LOWER() TRIM() RTRIM() LTRIM() ALLTRIM()
LEN() AT() SUBSTR() LEFT() RIGHT() SPACE() REPLICATE() STR() VAL() INT() ROUND()
ABS() MAX() MIN() MOD() SQRT() DTOC() DTOS() CTOD() DAY() MONTH() YEAR() DOW()
CDOW() CMONTH() CHR() ASC() ISALPHA() ISUPPER() ISLOWER() IIF() TYPE() VERSION() OS()`.

## Diferenças conhecidas em relação ao original

- Caminhos de arquivo do Linux no lugar de `C:\` (`<C:>` fica na barra de status).
- Linha 0 com a barra de menus do foxbase-linux; por isso a área de comandos tem
  uma linha a menos que a do original.
- Textos do HELP são próprios (descrevem o que está implementado aqui).
- `DO` compila o programa com o Harbour em vez de interpretar.
- Ainda não implementados: índices (INDEX/SEEK/FIND), várias áreas (SELECT),
  relatórios e etiquetas, @...SAY/GET e programação na linha de comandos.

Em `/usr/share/foxbase-linux/exemplos/` há um `clientes.dbf` e um `ola.prg` prontos.

## Instalação

```bash
git clone https://github.com/voidlinuxbr/foxbase-linux.git
cd foxbase-linux/pkgfile && pkgmake
```

## Créditos

Vilmar Catafesta <vcatafesta@gmail.com> — https://voidbr.org — Licença MIT.
