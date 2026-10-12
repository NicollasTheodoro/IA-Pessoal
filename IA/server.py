"""
Servidor da interface web da Alice.

Estrutura esperada (rode a partir da pasta IA/, a mesma do app.py):

    IA/
      server.py
      static/index.html
      brain/  audio/

    pip install flask
    python server.py

Depois abra http://127.0.0.1:5000

Variáveis opcionais:
    ALICE_PORTA=5000          porta do servidor
    ALICE_ORIGENS=http://x    outras origens autorizadas a chamar a API (separadas por vírgula)
"""
import importlib.util
import json
import os
import threading
import time
from collections import deque
from urllib.parse import urlparse

from flask import Flask, Response, jsonify, request, send_from_directory, stream_with_context

from brain.actions import Think
from brain.personality import Personality

PASTA = os.path.dirname(os.path.abspath(__file__))
PORTA = int(os.getenv("ALICE_PORTA", "5000"))
ORIGENS = {o.strip().rstrip("/") for o in os.getenv("ALICE_ORIGENS", "").split(",") if o.strip()}

app = Flask(__name__, static_folder=os.path.join(PASTA, "static"))

# ---------------------------------------------------------------- voz (opcional)
# Se a chave do Murf não existir, a interface funciona só com texto.
speaker = None
try:
    from audio.speaker import Speak

    speaker = Speak()
except Exception as e:
    print("Voz (Murf) desativada:", e)

# ---------------------------------------------------------------- ouvido (opcional)
# Reconhecimento de voz pelo microfone do PC (Whisper), o mesmo do app.py. Só precisa de
# faster-whisper e sounddevice instalados. Não depende do navegador.
ouvido_ok = all(importlib.util.find_spec(m) for m in ("faster_whisper", "sounddevice"))
mic = None
lock_mic = threading.Lock()
cancelar_mic = threading.Event()


def carregar_mic():
    global mic
    if mic is None:
        from audio.listener import Listener

        mic = Listener()
    return mic


# ---------------------------------------------------------------- cérebro
avisos = deque(maxlen=50)  # lembretes que dispararam e a interface ainda não mostrou


def notificar(texto):
    """Chamado pela ação 'lembrete' quando o tempo acaba."""
    print(texto)
    avisos.append(texto)
    if speaker:
        speaker.enfileirar(texto)


personalidade = Personality()
brain = Think(personalidade, notificar=notificar)

# O Ollama e o histórico da Alice não são thread-safe: uma conversa por vez.
lock_chat = threading.Lock()
# Edições rápidas de traços/memória não precisam esperar a Alice terminar de falar.
lock_dados = threading.Lock()


def estado():
    return {
        "mood": personalidade.state,
        "traits": dict(personalidade.traits),
        "memory": dict(brain.memory.data),
    }


def corpo():
    return request.get_json(silent=True) or {}


def sse(evento, dados):
    return f"event: {evento}\ndata: {json.dumps(dados, ensure_ascii=False)}\n\n"


# ---------------------------------------------------------------- segurança
# O servidor só escuta em 127.0.0.1, mas o navegador deixa QUALQUER site tentar
# chamar localhost. Como a interface pode abrir programas no PC, só aceitamos
# chamadas vindas da própria interface.
@app.before_request
def proteger():
    if request.host.split(":")[0] not in ("127.0.0.1", "localhost"):
        return jsonify(error="Host não permitido."), 403
    if request.method in ("POST", "PUT", "DELETE"):
        origem = request.headers.get("Origin")
        if origem and urlparse(origem).netloc != request.host and origem.rstrip("/") not in ORIGENS:
            return jsonify(error="Origem não permitida."), 403


@app.after_request
def cors(resp):
    origem = (request.headers.get("Origin") or "").rstrip("/")
    if origem in ORIGENS:
        resp.headers["Access-Control-Allow-Origin"] = origem
        resp.headers["Access-Control-Allow-Headers"] = "Content-Type"
        resp.headers["Access-Control-Allow-Methods"] = "GET,POST,PUT,DELETE,OPTIONS"
    return resp


# ---------------------------------------------------------------- rotas
@app.get("/")
def index():
    return send_from_directory(app.static_folder, "index.html")


@app.get("/state")
def get_state():
    return jsonify({**estado(), "voz": speaker is not None, "ouvido": ouvido_ok, "modelo": brain.model})


@app.get("/actions")
def get_actions():
    return jsonify(acoes=brain.acoes.lista())


@app.get("/avisos")
def get_avisos():
    saida = []
    while avisos:
        saida.append(avisos.popleft())
    return jsonify(avisos=saida)


@app.post("/chat")
def chat():
    body = corpo()
    msg = (body.get("message") or "").strip()
    if not msg:
        return jsonify(error="Mensagem vazia."), 400

    falar = bool(body.get("speak")) and speaker is not None
    rodar = bool(body.get("run_actions"))

    def gerar():
        t0 = time.time()
        primeira = None
        teve_fala = False
        with lock_chat:
            if falar:
                speaker.parar()  # corta o que a Alice ainda estava dizendo
            try:
                for ev in brain.stream(msg):
                    if ev["type"] == "sentence":
                        teve_fala = True
                        if primeira is None:
                            primeira = round(time.time() - t0, 2)
                        if falar:
                            speaker.enfileirar(ev["text"])  # não trava: toca enquanto o LLM continua
                    elif ev["type"] == "acao":
                        ev = dict(ev, executada=rodar)
                        if rodar:
                            ev["resultado"] = brain.executar(ev["acao"], ev["arg"])
                    yield sse(ev["type"], ev)
            except Exception as e:  # ErroLLM (Ollama fora do ar, modelo ausente...) ou falha inesperada
                yield sse("erro", {"error": str(e) or e.__class__.__name__})
            else:
                if not teve_fala:
                    yield sse("erro", {"error": "A Alice não respondeu. Tente de novo."})
            yield sse("fim", {"timings": {"primeira": primeira, "total": round(time.time() - t0, 2)}, **estado()})
            if falar and teve_fala:
                speaker.esperar()  # a chamada só volta a ouvir quando a Alice termina de falar
                yield sse("falou", {})

    resp = Response(stream_with_context(gerar()), mimetype="text/event-stream")
    resp.headers["Cache-Control"] = "no-cache"
    resp.headers["X-Accel-Buffering"] = "no"
    return resp


@app.post("/ouvir")
def ouvir():
    """Escuta uma frase pelo microfone do PC. Devolve {"texto": ...} (None se ninguém falou)."""
    if not ouvido_ok:
        return jsonify(error="Microfone do PC indisponível: instale faster-whisper e sounddevice."), 501
    if not lock_mic.acquire(blocking=False):
        return jsonify(error="O microfone já está em uso."), 409
    try:
        cancelar_mic.clear()
        texto = carregar_mic().ouvir_som(espera_max=20, cancelar=cancelar_mic)
        return jsonify(texto=texto)
    except Exception as e:
        return jsonify(error=f"Erro no microfone: {e}"), 500
    finally:
        lock_mic.release()


@app.post("/ouvir/cancelar")
def ouvir_cancelar():
    cancelar_mic.set()
    return jsonify(ok=True)


@app.post("/stop")
def stop():
    if speaker:
        speaker.parar()
    return jsonify(ok=True)


@app.post("/action")
def action():
    body = corpo()
    nome = (body.get("acao") or "").strip().lower()
    if nome not in brain.acoes.registro:  # lista fechada: só o que existe em acoes.py
        return jsonify(error="Ação desconhecida."), 400
    resultado = brain.executar(nome, body.get("arg"))
    return jsonify(ok=True, resultado=resultado)


@app.put("/traits")
def set_traits():
    with lock_dados:
        try:
            for k, v in corpo().items():
                if k in personalidade.traits:
                    personalidade.traits[k] = int(v)
        except (TypeError, ValueError):
            return jsonify(error="Valor inválido."), 400
        personalidade._clamp()
        personalidade.update_emotions()
        personalidade.update_state()
    return jsonify(estado())


@app.route("/memory", methods=["PUT", "DELETE"])
def memory():
    body = corpo()
    key = (body.get("key") or "").strip()
    if not key:
        return jsonify(error="Chave vazia."), 400
    with lock_dados:
        if request.method == "PUT":
            brain.memory.store(key, body.get("value", ""))
        else:
            brain.memory.data.pop(key, None)
            brain.memory.save()
    return jsonify(memory=dict(brain.memory.data))


if __name__ == "__main__":
    def aquecer():
        with lock_chat:  # se o aquecimento rodar junto com a 1ª conversa, o Ollama recarrega o modelo duas vezes
            brain.aquecer()
        if ouvido_ok:
            try:
                with lock_mic:  # carrega o Whisper agora, para a 1ª chamada não esperar
                    carregar_mic()
            except Exception as e:
                print("Microfone do PC indisponível:", e)

    threading.Thread(target=aquecer, daemon=True).start()  # 1ª resposta bem mais rápida
    print(f"Alice no ar: http://127.0.0.1:{PORTA}")
    # 127.0.0.1: só o seu PC acessa. A interface pode disparar ações no computador.
    app.run(host="127.0.0.1", port=PORTA, debug=False, threaded=True)