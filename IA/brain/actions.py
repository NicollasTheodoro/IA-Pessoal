from ollama import chat
import pyautogui as py
import time
import json
import os
import re

api_key = os.getenv("MURF_API_KEY")


class Think:
    def __init__(self, personalidade):
        self.personalidade = personalidade
        self.history = []
        self.model='qwen2.5:7b'
        self.messages=[
            {'role': 'system', 'content': """
            Você é Alice, uma assistente virtual com personalidade viva.
            Nunca use emojis

            Sempre responda em JSON no formato:

            {
            "tipo": "fala" ou "acao",
            "acao": "nome_da_acao" ou null,
            "resposta": "texto que deve ser falado"
            }
             
            As ações possíveis são:
            - abrir_navegador
            - abrir_youtube
             """
             }
        ]   
    
    

    def generate(self, user_input):

        def extrair_json(texto):
            match = re.search(r'\{.*\}', texto, re.DOTALL)
            if match:
                return json.loads(match.group())
            return None
    
        self.history.append(user_input)
        # resposta = self.personalidade.generate(user_input) | Deixando de lado momentâneamente para testes.
        self.messages.append({'role': 'user', 'content': user_input})

        response = chat(
            model=self.model,
            messages=self.messages,
            options={
                "num_predict": 100,
                "temperature": 0.6,
                "top_p": 0.9
                }
        )

        raw_content = response['message']['content'] # resposta = response['message']['content']

        raw_content = raw_content.replace("```json", "").replace("```", "").strip()

        try:
            print("RAW RESPONSE:", raw_content)

            dados = extrair_json(raw_content)
            if not dados:
                print("JSON inválido")
                return None

        except json.JSONDecodeError:
            print("Erro ao decodificar JSON:")
            return None
        self.messages.append({'role': 'assistant', 'content': raw_content})


        self.history.append(dados["resposta"])
        return dados
    

    def abrir_programa(self, nome):
        py.hotkey("win")
        time.sleep(0.7)
        py.write(nome, interval=0.05)
        py.press("enter")


    def comandos(self, user_input):
        if not user_input:
            print("Input vazio em comandos()")
            return
        
        user_input = user_input.lower()
        print("DEBUG:", user_input)

        if "abra o navegador" in user_input or "abre o navegador" in user_input:
            self.abrir_programa("Opera")

        elif "abra o youtube" in user_input or "abre o youtube" in user_input:
            self.abrir_programa("Opera")
            time.sleep(2)
            py.write("https://www.youtube.com", interval=0.05)
            py.press("enter")
    




    # teste

# mensagem = "Olá, Alice! Pode abrir o youtube, por favor?"
# brain = Think(personalidade=None)
# resposta = brain.generate(mensagem)
# print(resposta)
# brain.comandos("Olá!")