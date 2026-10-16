"""
Presença: há quantos segundos você não mexe no teclado nem no mouse.

A Alice usa isso para não puxar assunto com uma cadeira vazia: só pergunta "tá fazendo algo
importante?" quando você está mesmo no PC, e só diz "voltou!" depois de uma ausência de verdade.

Só funciona no Windows (usa o GetLastInputInfo do próprio sistema: não espia o que você digita,
só sabe QUANDO foi o último movimento). Em outros sistemas devolve None, e a Alice se comporta
como se você estivesse sempre por perto.
"""
import ctypes
import sys

if sys.platform == "win32":
    class _LASTINPUTINFO(ctypes.Structure):
        _fields_ = [("cbSize", ctypes.c_uint), ("dwTime", ctypes.c_uint)]


def segundos_sem_input():
    """Segundos desde o último teclado/mouse, ou None se não der para saber."""
    if sys.platform != "win32":
        return None
    try:
        info = _LASTINPUTINFO()
        info.cbSize = ctypes.sizeof(_LASTINPUTINFO)
        if not ctypes.windll.user32.GetLastInputInfo(ctypes.byref(info)):
            return None
        kernel = ctypes.windll.kernel32
        kernel.GetTickCount.restype = ctypes.c_uint  # sem isso o Python lê com sinal e vira negativo
        agora = kernel.GetTickCount()
        return ((agora - info.dwTime) & 0xFFFFFFFF) / 1000.0  # o contador de 32 bits dá a volta a cada ~49 dias
    except Exception:
        return None
