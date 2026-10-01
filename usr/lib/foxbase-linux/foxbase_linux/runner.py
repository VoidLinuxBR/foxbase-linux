"""Execução de programas externos (RUN, DO, F5) fora do curses."""

import curses
import os
import shutil
import subprocess
import tempfile
from pathlib import Path


def run_in_terminal(app, argv, shell=False, cwd=None):
    """Suspende o curses, roda o comando no terminal real e volta."""
    stdscr = app.stdscr
    curses.def_prog_mode()
    curses.endwin()
    code = None
    try:
        print("\033[0m\033[2J\033[H", end="", flush=True)
        try:
            code = subprocess.call(argv, shell=shell, cwd=cwd)
        except OSError as exc:
            print(f"Error: {exc}")
        print("\n\033[7m Press Enter to return to FoxBASE+ \033[0m", end="", flush=True)
        try:
            input()
        except (EOFError, KeyboardInterrupt):
            pass
    finally:
        curses.reset_prog_mode()
        stdscr.clear()
        stdscr.refresh()
    return code


def find_hbmk2():
    return shutil.which("hbmk2")


def compile_and_run(app, prg_path):
    """Compila um .prg com hbmk2 e executa o binário no terminal."""
    prg_path = Path(prg_path).resolve()
    hbmk2 = find_hbmk2()
    if not hbmk2:
        if shutil.which("harbour"):
            app.command.write("hbmk2 not found (harbour alone cannot link executables).")
        else:
            app.command.write("Harbour (hbmk2) not found in PATH.")
        return False

    with tempfile.TemporaryDirectory(prefix="foxbase-") as tmp:
        exe = Path(tmp) / prg_path.stem
        app.command.write(f"Compiling {prg_path.name}...")
        result = subprocess.run(
            [hbmk2, "-quiet", f"-o{exe}", str(prg_path)],
            text=True,
            capture_output=True,
            cwd=tmp,
        )
        output = (result.stdout + result.stderr).rstrip()
        if output:
            app.command.write(output)
        if result.returncode != 0 or not exe.exists():
            app.command.write(f"Compilation failed ({result.returncode}).")
            return False

        code = run_in_terminal(app, [str(exe)], cwd=os.getcwd())
        app.command.write(f"{prg_path.name} finished (exit {code}).")
        return True
