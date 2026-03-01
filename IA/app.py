from audio.listener import Listener
from audio.speaker import Speak
from brain.actions import Think
import time


speak = Speak()
mic = Listener()
brain = Think(None)

case = input("deseja conversar por texto ou fala? (t/f)")

if "f" in case.lower():
    while True:
        pergunta = mic.ouvir_som()

        print("Áudio gravado!")
        print("Gerando resposta!!!")

        start = time.time()
        resposta = brain.generate(pergunta)
        print("LLM demorou:", time.time() - start)

        # if "faça" in resposta or "abra" in resposta or "abre" in resposta:
        #     resposta["tipo"] = resposta["acao"]
        
        if not resposta:
            print("Sem resposta válida")
            continue
            
        if  resposta["acao"] == "abrir_youtube":
            speak.falar("Claro, abrindo!")
            brain.comandos("abra o youtube")

        if  resposta["acao"] == "abrir_navegador":
            speak.falar("Claro, abrindo!")
            brain.comandos("abra o navegador")
        
        elif resposta["tipo"] == "fala":
             start = time.time()
             speak.falar(resposta["resposta"])
             print("Murf demorou:", time.time() - start)

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

        if not resposta:
            print("Sem resposta válida")
            continue
        
        if resposta["tipo"] == "acao":
             brain.comandos(resposta["acao"])
        
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