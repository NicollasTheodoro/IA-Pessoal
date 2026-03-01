from audio.listener import Listener
from audio.speaker import Speak
from brain.actions import Think
from brain.personality import Personality
import time


speak = Speak()
mic = Listener()
brain = Think(Personality())

ativa = False
ultimo_uso = 0
tempo_timeout = 45

case = input("deseja conversar por texto ou fala? (t/f)")

if "f" in case.lower():
    while True:
        pergunta = mic.ouvir_som()

        if not pergunta:
            continue

        if pergunta and pergunta.lower().startswith("alice"):
            ativa = True
            ultimo_uso = time.time()
            pergunta = pergunta.replace("alice", "", 1).strip()
            print("Áudio gravado!")
            print("Gerando resposta!!!")

        if not pergunta:
            continue

        if ativa:
            if time.time() - ultimo_uso > tempo_timeout:
                ativa = False
                print("Modo passivo")
                continue

            ultimo_uso = time.time()

            start = time.time()

            resposta = brain.generate(pergunta)
            print("LLM demorou:", time.time() - start)

            # if "faça" in resposta or "abra" in resposta or "abre" in resposta:
            #     resposta["tipo"] = resposta["acao"]
            
            if not resposta:
                print("Sem resposta válida")
                continue
                
            if resposta["tipo"] == "acao":
                if not resposta.get("resposta"):
                    resposta["resposta"] = "Claro!"
                speak.falar(resposta["resposta"])
                brain.comandos(resposta)
            
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