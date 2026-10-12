import os
import time

from ollama import chat

from brain.acoes import Acoes
from brain.memory import PersistentMemory
from brain.prompt_builder import build_system_prompt
from brain.stream import StreamParser

# Troque o modelo sem mexer no código:  set ALICE_MODELO=qwen2.5:3b
MODELO = os.getenv("ALICE_MODELO", "qwen2.5:7b")
MAX_MENSAGENS = 8  # só as últimas 8 mensagens vão para o modelo (menos contexto = mais rápido)
KEEP_ALIVE = "30m"  # mantém o modelo carregado na memória entre as falas
OPCOES = {
    "num_predict": 160,   # respostas curtas: são faladas em voz alta
    "temperature": 0.7,
    "top_p": 0.9,
    "num_ctx": 3072,      # contexto menor também gasta menos memória
}

# Padrão: roda o modelo na CPU (num_gpu=0). Placas antigas ou integradas (ex.: GT 740, Intel UHD)
# derrubam o Ollama quando o prompt é grande. Se você tiver uma placa NVIDIA moderna:
#   $env:ALICE_GPU="999"   usa a GPU para todas as camadas do modelo
#   $env:ALICE_BATCH="128" (opcional) lê o prompt em blocos menores, se a GPU ainda travar
OPCOES["num_gpu"] = int(os.getenv("ALICE_GPU", "0"))
if os.getenv("ALICE_BATCH"):
    OPCOES["num_batch"] = int(os.getenv("ALICE_BATCH"))
# Opções que mudam como o modelo é CARREGADO: o aquecimento precisa usar as mesmas,
# senão o Ollama descarrega e recarrega o modelo na primeira fala.
CARGA = {k: OPCOES[k] for k in ("num_ctx", "num_batch", "num_gpu") if k in OPCOES}


class ErroLLM(Exception):
    """Erro com mensagem já explicada para o usuário."""


class Think:
    def __init__(self, personalidade, notificar=None, modelo=MODELO):
        self.personalidade = personalidade
        self.model = modelo
        self.messages = []
        self.memory = PersistentMemory()
        self.acoes = Acoes(notificar)

    # ------------------------------------------------------------------
    def stream(self, user_input):
        """Gera eventos conforme o modelo escreve (veja brain/stream.py)."""
        self.personalidade.update_from_interaction(user_input)
        sistema = build_system_prompt(self.personalidade, self.memory.data, self.acoes.descricoes())
        msgs = [
            {"role": "system", "content": sistema},
            *self.messages,
            {"role": "user", "content": user_input},
        ]

        parser = StreamParser()
        teve_acao = False
        tags = []  # só as tags que valeram: é o que vai para o histórico

        def tratar(ev):
            nonlocal teve_acao
            if ev["type"] == "acao":
                if not self.acoes.permitida(ev["acao"], user_input):
                    print(f"Ação ignorada (você não pediu): {ev['acao']}")
                    return {"type": "acao_ignorada", "acao": ev["acao"], "arg": ev["arg"]}
                teve_acao = True
                tags.append(f"<acao:{ev['acao']}" + (f"|{ev['arg']}" if ev["arg"] else "") + ">")
            elif ev["type"] == "memoria":
                tags.append(f"<memoria:{ev['chave']}|{ev['valor']}>")
            return self._tratar(ev)

        for token in self._chat_stream(msgs):
            for ev in parser.feed(token):
                yield tratar(ev)
        for ev in parser.flush():
            yield tratar(ev)

        if not parser.falas and teve_acao:
            yield {"type": "sentence", "text": "Pronto."}
            parser.falas.append("Pronto.")

        if parser.falas:  # só entra no histórico se a Alice realmente respondeu
            # Sem as tags ignoradas: senão o modelo aprende com os próprios erros e repete.
            resposta = " ".join(parser.falas + tags)
            self.messages += [
                {"role": "user", "content": user_input},
                {"role": "assistant", "content": resposta},
            ]
            self.messages = self.messages[-MAX_MENSAGENS:]

    def executar(self, acao, arg=None):
        return self.acoes.executar(acao, arg)

    def aquecer(self):
        """Carrega o modelo na memória antes da primeira fala (a 1ª resposta fica bem mais rápida)."""
        try:
            chat(
                model=self.model,
                messages=[{"role": "user", "content": "oi"}],
                options={"num_predict": 1, **CARGA},
                keep_alive=KEEP_ALIVE,
            )
        except Exception as e:
            print("Aquecimento do modelo falhou:", self._explicar(e))

    # ------------------------------------------------------------------
    def _tratar(self, ev):
        if ev["type"] == "memoria":
            self.memory.store(ev["chave"], ev["valor"])
            print(f"Memória salva: {ev['chave']} = {ev['valor']}")
        return ev

    def _chat_stream(self, msgs):
        for tentativa in (1, 2):
            recebeu = False
            try:
                for chunk in chat(
                    model=self.model,
                    messages=msgs,
                    stream=True,
                    options=OPCOES,
                    keep_alive=KEEP_ALIVE,
                ):
                    recebeu = True
                    yield chunk["message"]["content"]
                return
            except Exception as e:
                print(f"[Ollama] erro real (tentativa {tentativa}): {e!r}")  # a mensagem amigável abaixo é só um palpite
                if recebeu or tentativa == 2:
                    raise ErroLLM(self._explicar(e)) from e
                print("Ollama falhou, tentando de novo:", e)
                time.sleep(1.5)  # dá tempo do Ollama subir o runner de novo

    def _explicar(self, e):
        t = str(e).lower()
        if "not found" in t and "model" in t:
            return f"O modelo {self.model} não está instalado. Rode: ollama pull {self.model}"
        if isinstance(e, ConnectionError) or "connection refused" in t or "failed to connect" in t:
            return "Não consegui conectar no Ollama. Ele está aberto?"
        if "forcibly closed" in t or "runner" in t or "status code: 500" in t or "terminated" in t:
            return (
                "O Ollama travou ao rodar o modelo (quase sempre falta de memória). "
                "Feche programas pesados, reinicie o Ollama ou use um modelo menor, "
                "por exemplo: set ALICE_MODELO=qwen2.5:3b"
            )
        return f"Erro no modelo: {e}"