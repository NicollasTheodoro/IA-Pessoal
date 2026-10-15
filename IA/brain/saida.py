"""
Saída de texto (print) sempre em UTF-8.

No Windows, quando a saída NÃO é um console (ex.: o pet liga o server.py sem janela, ou o texto vai
para um arquivo/pipe), o Python usa a codificação do sistema (cp1252) e qualquer emoji num print
dá "UnicodeEncodeError: 'charmap' codec can't encode character". Isso derrubava, por exemplo, o
microfone (print("🎧 Ouvindo...")) e podia derrubar um lembrete com emoji.
Aqui a saída passa a ser UTF-8, e o que não couber vira '?' em vez de causar erro.
"""
import sys


def forcar_utf8():
    for nome in ("stdout", "stderr"):
        fluxo = getattr(sys, nome, None)  # None quando roda sem console (pythonw): print vira no-op, sem erro
        if fluxo is not None and hasattr(fluxo, "reconfigure"):
            try:
                fluxo.reconfigure(encoding="utf-8", errors="replace")
            except Exception:
                pass
