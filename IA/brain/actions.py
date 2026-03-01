from ollama import chat
import pyautogui as py
import time
import json
import os
import re
from brain.prompt_builder import build_system_prompt
from brain.memory import PersistentMemory


api_key = os.getenv("MURF_API_KEY")


class Think:
    def __init__(self, personalidade):
        self.personalidade = personalidade
        self.history = []
        self.model='qwen2.5:7b'
        self.messages = []
        self.memory = PersistentMemory() 
    
    

    def generate(self, user_input):

        def extrair_json(texto):
            match = re.search(r'\{.*\}', texto, re.DOTALL)
            if match:
                return json.loads(match.group())
            return None
    
        self.history.append(user_input)
        self.personalidade.update_from_interaction(user_input)

        memories = self.memory.data
        system_prompt = build_system_prompt(self.personalidade, memories)

        self.messages = [msg for msg in self.messages if msg["role"] != "system"]
        self.messages.insert(0, {"role": "system", "content": system_prompt})
        # resposta = self.personalidade.generate(user_input) | Deixando de lado momentâneamente para testes.
        self.messages.append({'role': 'user', 'content': user_input})

        response = chat(
            model=self.model,
            messages=self.messages,
            options={
                "num_predict": 200,
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

            # ✅ Agora é seguro usar dados
            if dados.get("memoria") and dados["memoria"].get("salvar"):
                chave = dados["memoria"].get("chave")
                valor = dados["memoria"].get("valor")

                if chave and valor:
                    self.memory.store(chave, valor)
                    print(f"Memória salva: {chave} = {valor}")

            # if not dados:
            #     print("JSON inválido")
            #     return None

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


    def comandos(self, dados):
        if not isinstance(dados, dict):
            return

        if dados.get("tipo") != "acao":
            return

        acao = dados.get("acao")

        if acao == "abrir_navegador":
            self.abrir_programa("Opera")

        elif acao == "abrir_youtube":
            self.abrir_programa("Opera")
            time.sleep(2)
            py.write("https://www.youtube.com", interval=0.05)
            py.press("enter")

        elif acao == "abrir_projeto":
            caminho_projeto = r"D:\Aulas\Git\AulaCursoEmVideo\clonando-projeto-site\IA-Pessoal"
            os.startfile(caminho_projeto)

    




    # teste

# mensagem = "Olá, Alice! Pode abrir o youtube, por favor?"
# brain = Think(personalidade=None)
# resposta = brain.generate(mensagem)
# print(resposta)
# brain.comandos("Olá!")