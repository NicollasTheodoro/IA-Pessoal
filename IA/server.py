"""
Servidor da interface web da Alice.

Coloque este arquivo ao lado do app.py (pasta IA/) e a interface em IA/static/index.html.
Rode a partir da RAIZ do repositório, para o memory.json ser o mesmo do app.py:

    pip install flask
    python IA/server.py

Depois abra http://127.0.0.1:5000
"""
import os
import threading
import time

from flask import Flask, jsonify, request, send_from_directory

from brain.actions import Think
from brain.personality import Personality

PASTA = os.path.dirname(os.path.abspath(__file__))
app = Flask(__name__, static_folder=os.path.join(PASTA, "static"))

personalidade = Personality()
brain = Think(personalidade)

# A voz é opcional: se a chave do Murf não existir, a interface funciona só com texto.
speaker = None
try:
    from audio.speaker import Speak

    speaker = Speak()
except Exception as e:
    print("Voz (Murf) desativada:", e)

# Ollama e o estado da Alice não são thread-safe: uma conversa por vez.
lock = threading.Lock()

ACOES_PERMITIDAS = {"abrir_navegador", "abrir_youtube", "abrir_projeto"}


def estado():
    return {
        "mood": personalidade.state,
        "traits": dict(personalidade.traits),
        "memory": dict(brain.memory.data),
    }


def em_segundo_plano(fn, *args):
    threading.Thread(target=fn, args=args, daemon=True).start()


@app.after_request
def cors(resp):
    resp.headers["Access-Control-Allow-Origin"] = "*"
    resp.headers["Access-Control-Allow-Headers"] = "Content-Type"
    resp.headers["Access-Control-Allow-Methods"] = "GET,POST,PUT,DELETE,OPTIONS"
    return resp


@app.get("/")
def index():
    return send_from_directory(app.static_folder, "index.html")


@app.get("/state")
def get_state():
    return jsonify(estado(), voz=speaker is not None)


@app.post("/chat")
def chat():
    body = request.get_json(force=True) or {}
    msg = (body.get("message") or "").strip()
    if not msg:
        return jsonify(error="Mensagem vazia."), 400

    t0 = time.time()
    try:
        with lock:
            dados = brain.generate(msg)
    except Exception as e:  # ex.: Ollama fora do ar, JSON sem o campo "resposta"
        return jsonify(error=f"Erro no cérebro da Alice: {e}", **estado()), 500
    llm = round(time.time() - t0, 2)

    if not dados or not dados.get("resposta"):
        return jsonify(error="A Alice não devolveu um JSON válido. Tente de novo.", **estado()), 502

    if body.get("speak") and speaker:
        em_segundo_plano(speaker.falar, dados["resposta"])  # não trava a resposta
    if body.get("run_actions") and dados.get("tipo") == "acao":
        em_segundo_plano(brain.comandos, dados)

    return jsonify(
        reply=dados["resposta"],
        tipo=dados.get("tipo", "fala"),
        acao=dados.get("acao"),
        memoria=dados.get("memoria"),
        timings={"llm": llm},
        **estado(),
    )


@app.post("/action")
def action():
    acao = (request.get_json(force=True) or {}).get("acao")
    if acao not in ACOES_PERMITIDAS:
        return jsonify(error="Ação desconhecida."), 400
    em_segundo_plano(brain.comandos, {"tipo": "acao", "acao": acao})
    return jsonify(ok=True)


@app.put("/traits")
def set_traits():
    with lock:
        for k, v in (request.get_json(force=True) or {}).items():
            if k in personalidade.traits:
                personalidade.traits[k] = int(v)
        personalidade._clamp()
        personalidade.update_emotions()
        personalidade.update_state()
    return jsonify(estado())


@app.route("/memory", methods=["PUT", "DELETE"])
def memory():
    body = request.get_json(force=True) or {}
    key = body.get("key")
    if not key:
        return jsonify(error="Chave vazia."), 400
    if request.method == "PUT":
        brain.memory.store(key, body.get("value", ""))
    else:
        brain.memory.data.pop(key, None)
        brain.memory.save()
    return jsonify(memory=dict(brain.memory.data))


if __name__ == "__main__":
    # 127.0.0.1: só o seu PC acessa. A interface pode disparar ações no computador.
    app.run(host="127.0.0.1", port=5000, debug=False)
