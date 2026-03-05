from audio.listener import Listener
from audio.speaker import Speak
from brain.actions import Think
from brain.personality import Personality
from core.controller import Controller
import time


speak = Speak()
brain = Think(Personality())
listener = Listener()  # sem callback aqui
controller = Controller(listener, brain)
# mic = Listener()


ativa = False
ultimo_uso = 0
tempo_timeout = 45

case = input("deseja conversar por texto ou fala? (t/f)")

if "f" in case.lower():
    while True:
        resposta = controller.talk_with_voice()

        if not resposta:
            continue

        if resposta["tipo"] == "acao":
            speak.falar(resposta.get("resposta", "Claro!"))
            brain.comandos(resposta)

        elif resposta["tipo"] == "fala":
            speak.falar(resposta["resposta"])
        # print(resposta)
        # brain.comandos(pergunta)  # ⚠️ IMPORTANTE (explico abaixo)
        # if resposta and resposta.strip():
        #         speak.falar(resposta)
        # else:
        #     print("Resposta vazia. Não enviando para TTS.")

case = input("deseja ouvir o que Alice fala? (y/n)")
if "y" in case:
    while True:
        pergunta = input("Entre com a pergunta")
        resposta = brain.generate(pergunta)

        resposta["resposta"] = "abrindo"

        if not resposta:
            print("Sem resposta válida")
            continue
        
        if  resposta["acao"] == "abrir_youtube":
            speak.falar(resposta["resposta"])
            brain.comandos(resposta)

        if  resposta["acao"] == "abrir_navegador":
            speak.falar(resposta["resposta"])
            brain.comandos(resposta)
            
        if  resposta["acao"] == "abrir_projeto":
            speak.falar(resposta["resposta"])
            brain.comandos(resposta)
        
        elif resposta["tipo"] == "fala":
             speak.falar(resposta["resposta"])
        print(resposta)


        # brain.comandos(pergunta)  # ⚠️ IMPORTANTE (explico abaixo)
        # if resposta and resposta.strip():
        #         speak.falar(resposta)
        # else:
        #     print("Resposta vazia. Não enviando para TTS.")

while True:
    pergunta = input("Entre com a pergunta")
    resposta = brain.generate(pergunta)
    if resposta and resposta.strip():
        print(resposta)
    else:
        print("Resposta vazia. Não enviando para TTS.")
    brain.comandos(pergunta)