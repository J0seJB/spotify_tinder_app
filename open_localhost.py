#!/usr/bin/env python3
"""Inicia el backend FastAPI del proyecto y abre la URL en el navegador."""
from __future__ import annotations

import os
import socket
import subprocess
import sys
import time
import webbrowser
from pathlib import Path

PROJECT_DIR = Path(__file__).resolve().parent
HOST = "127.0.0.1"
PORT = 8000
URL = f"http://{HOST}:{PORT}"


def is_port_open(host: str, port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(1)
        return sock.connect_ex((host, port)) == 0


def start_server() -> None:
    if is_port_open(HOST, PORT):
        print(f"El servidor ya está disponible en {URL}")
        return

    print("Iniciando servidor...")
    cmd = [sys.executable, "-m", "uvicorn", "api:app", "--host", HOST, "--port", str(PORT)]

    if os.name == "nt":
        subprocess.Popen(
            cmd,
            cwd=str(PROJECT_DIR),
            creationflags=subprocess.CREATE_NEW_CONSOLE,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    else:
        subprocess.Popen(
            cmd,
            cwd=str(PROJECT_DIR),
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )

    for _ in range(25):
        if is_port_open(HOST, PORT):
            print(f"Servidor listo en {URL}")
            return
        time.sleep(0.5)

    raise RuntimeError("No se pudo iniciar el servidor en el puerto 8000")


def open_browser() -> None:
    opened = webbrowser.open(URL, new=0, autoraise=True)
    if opened:
        print(f"Se abrió la pestaña en el navegador: {URL}")
    else:
        print(f"No se pudo abrir el navegador automáticamente. Abre esta URL manualmente: {URL}")


if __name__ == "__main__":
    try:
        start_server()
        open_browser()
    except Exception as exc:
        print(f"Error: {exc}")
        sys.exit(1)
