"""
Alice no terminal (voz ou texto). Para a interface web, use o server.py.
"""
import re
import time

from brain.saida import forcar_utf8

forcar_utf8()

from brain.actions import Think
from brain.personality import Personality

TIMEOUT = 45  # segundos que ela continua ouvindo depois de ser chamada
CHAMADO = re.compile(r"^\W*alice\b[\s,.!?:;-]*", re.IGNORECASE)  # pega "Alice," "alice!" "Alice:"

# A voz é opcional: sem a chave do Murf, a Alice responde só no texto.
speak = None
try:
    from audio.speaker import Speak

    speak = Speak()
except Exception as e:
    print("Voz (Murf) desativada:", e)


def notificar(texto):
    print("\n" + texto)
    if speak:
        speak.enfileirar(texto)


brain = Think(Personality(), notificar=notificar)


def responder(pergunta, falar=True):
    """Mostra cada frase assim que o LLM a termina e já manda para a voz."""
    t0 = time.time()
    primeira = True
    try:
        for ev in brain.stream(pergunta):
            if ev["type"] == "sentence":
                if primeira:
                    print(f"(1ª frase em {time.time() - t0:.1f}s)")
                    primeira = False
                print("Alice:", ev["text"])
                if falar and speak:
                    speak.enfileirar(ev["text"])
            elif ev["type"] == "acao":
                print("Ação:", ev["acao"], ev["arg"] or "")
                print("  ->", brain.executar(ev["acao"], ev["arg"]))
    except Exception as e:  # ErroLLM já vem com a mensagem explicada
        print("Erro:", e)
    if falar and speak:
        speak.esperar()  # só volta a ouvir quando ela termina, para não se escutar


def modo_voz():
    from audio.listener import Listener  # carrega o Whisper só se for usar a voz

    mic = Listener()
    ativa = False
    ultimo_uso = 0.0
    print("Diga 'Alice' para chamar. Ctrl+C para sair.")

    while True:
        fala = mic.ouvir_som()
        if not fala:
            continue

        chamada = CHAMADO.match(fala)
        if chamada:
            ativa = True
            fala = fala[chamada.end():].strip()
        elif ativa and time.time() - ultimo_uso > TIMEOUT:
            ativa = False
            print("Modo passivo")

        if not ativa or not fala:
            ultimo_uso = time.time() if chamada else ultimo_uso
            continue

        responder(fala)
        ultimo_uso = time.time()


def modo_texto():
    falar = bool(speak) and input("Alice fala as respostas em voz alta? (s/n) ").strip().lower().startswith("s")
    print("Digite 'sair' para encerrar.")
    while True:
        pergunta = input("Você: ").strip()
        if pergunta.lower() in ("sair", "exit", "q"):
            break
        if pergunta:
            responder(pergunta, falar)


if __name__ == "__main__":
    brain.aquecer()
    escolha = input("Deseja conversar por texto ou fala? (t/f) ").strip().lower()
    try:
        modo_voz() if escolha.startswith("f") else modo_texto()
    except KeyboardInterrupt:
        print("\nAté mais!")