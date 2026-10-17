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

Acesso pelo celular (veja o LEIAME-CELULAR.md):
    ALICE_HOST=0.0.0.0        escuta na rede (padrão 127.0.0.1: só este PC)
    ALICE_TOKEN=uma-senha     OBRIGATÓRIA quando ALICE_HOST não for local. Fora do PC, toda chamada exige essa senha.
"""
from brain.saida import forcar_utf8

forcar_utf8()  # print com emoji não pode derrubar o servidor quando a saída não é um console UTF-8

import importlib.util
import json
import os
import hmac
import threading
import time
import urllib.request
from collections import deque
from urllib.parse import urlparse

from flask import Flask, Response, jsonify, request, send_from_directory, stream_with_context


from brain.actions import Think
from brain.emocoes import MOVIMENTOS, Emocoes, catalogo as catalogo_emocoes
from brain.iniciativa import Iniciativa
from brain.personality import Personality

PASTA = os.path.dirname(os.path.abspath(__file__))
PORTA = int(os.getenv("ALICE_PORTA", "5000"))
HOST = os.getenv("ALICE_HOST", "127.0.0.1")
TOKEN = os.getenv("ALICE_TOKEN", "")
NTFY = os.getenv("ALICE_NTFY", "")  # opcional: tópico do ntfy.sh para receber os lembretes como notificação no celular
LOCAIS = ("127.0.0.1", "::1")
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
lock_carga_mic = threading.Lock()
mic_carregando = False
cancelar_mic = threading.Event()


def carregar_mic():
    global mic
    with lock_carga_mic:  # duas chamadas ao mesmo tempo não carregam o Whisper duas vezes
        if mic is None:
            from audio.listener import Listener

            mic = Listener()
    return mic


def preparar_mic():
    """Carrega o Whisper em segundo plano, para o primeiro clique no microfone não esperar o modelo."""
    global mic_carregando
    if not ouvido_ok or mic is not None or mic_carregando:
        return
    mic_carregando = True

    def carga():
        global mic_carregando
        try:
            carregar_mic()
        except Exception as e:
            print("Não consegui preparar o microfone:", e)
        finally:
            mic_carregando = False

    threading.Thread(target=carga, daemon=True).start()


def estado_mic():
    """O que o pet precisa para desenhar o anel de volume: 'esperando', 'gravando', 'transcrevendo'..."""
    m = mic
    return {"ouvido": ouvido_ok, "pronto": m is not None, "carregando": mic_carregando,
            "ativo": lock_mic.locked(), "estado": m.estado if m else "parado",
            "nivel": round(m.nivel, 4) if m else 0.0, "limiar": round(m.limiar_atual, 4) if m else 0.01}


# ---------------------------------------------------------------- cérebro
avisos = deque(maxlen=50)  # lembretes que dispararam e a interface ainda não mostrou
emo = None  # motor de emoções (criado junto com o cérebro, mais abaixo)


def _push(texto):
    try:
        req = urllib.request.Request("https://ntfy.sh/" + NTFY, data=texto.encode("utf-8"), headers={"Title": "Alice"})
        urllib.request.urlopen(req, timeout=8).close()
    except Exception as e:
        print("Notificação no celular falhou:", e)


def notificar(texto):
    """Chamado quando um lembrete/agendamento dispara."""
    print(texto)
    avisos.append(texto)
    if emo:
        emo.on_aviso(texto)
    if NTFY:
        threading.Thread(target=_push, args=(texto,), daemon=True).start()
    if speaker:
        speaker.enfileirar(texto)


personalidade = Personality()
brain = Think(personalidade, notificar=notificar)
# Expressões: ritmo 1 = normal, 2 = mais calma, 0.6 = mais agitada, 0 = parada (só reage)
emo = Emocoes(personalidade, ritmo=float(os.getenv("ALICE_EMO_RITMO", "1") or 1))
brain.emocoes = emo
emo.iniciar()

# O Ollama e o histórico da Alice não são thread-safe: uma conversa por vez.
lock_chat = threading.Lock()
# Edições rápidas de traços/memória não precisam esperar a Alice terminar de falar.
lock_dados = threading.Lock()

# ---------------------------------------------------------------- iniciativa (ela puxa assunto)
# Veja brain/iniciativa.py. Nível: ALICE_INICIATIVA=0 desligada, 1 calma, 2 normal (padrão), 3 faladeira.
def _dizer_iniciativa(texto, emocao, voz=True):
    ao_falar = lambda: emo.emitir_fala(texto, emocao)  # noqa: E731
    if voz and speaker is not None:
        speaker.enfileirar(texto, ao_falar)  # a expressão muda quando a voz começa
    else:
        ao_falar()


def _ocupado():
    """Conversa, microfone ou voz em andamento: a Alice espera para puxar assunto."""
    voz_ocupada = speaker is not None and getattr(speaker, "ocupado", lambda: False)()
    return lock_chat.locked() or lock_mic.locked() or bool(voz_ocupada)


def _guardar_no_historico(texto):
    """O que ela disse por iniciativa entra no histórico, para a sua resposta fazer sentido."""
    if lock_chat.acquire(blocking=False):
        try:
            brain.messages.append({"role": "assistant", "content": texto})
            brain.messages[:] = brain.messages[-8:]
        finally:
            lock_chat.release()


def _aquecer_modelo():
    def go():
        with lock_chat:
            brain.aquecer()

    threading.Thread(target=go, daemon=True).start()


try:
    _nivel_ini = int(os.getenv("ALICE_INICIATIVA", "2"))
except ValueError:
    _nivel_ini = 2
ini = Iniciativa(emo, _dizer_iniciativa, agenda=brain.agenda, clima=brain.clima, ocupado=_ocupado,
                 historico=_guardar_no_historico, ao_abrir=_aquecer_modelo,
                 arquivo=os.path.join(os.getenv("ALICE_DADOS", "."), "dados", "iniciativa.json"),
                 nivel=_nivel_ini if _nivel_ini in (0, 1, 2, 3) else 2)


def estado():
    return {
        "mood": personalidade.state,
        "traits": dict(personalidade.traits),
        "memory": dict(brain.memory.data),
        "expressao": emo.estado(),
    }


def corpo():
    return request.get_json(silent=True) or {}


def sse(evento, dados):
    return f"event: {evento}\ndata: {json.dumps(dados, ensure_ascii=False)}\n\n"


# ---------------------------------------------------------------- segurança
# A interface pode abrir programas, tirar print e mexer nas suas planilhas. Por isso:
#  - do próprio PC (127.0.0.1): só aceita a interface (checa Host e Origin, contra sites maliciosos);
#  - de outro aparelho (celular): exige a senha ALICE_TOKEN em TODA chamada, menos a página inicial
#    (que não tem dado nenhum). Erros de senha seguidos bloqueiam o aparelho por 1 minuto.
falhas = {}  # ip -> (erros, bloqueado_até)


def _origem_ok():
    origem = request.headers.get("Origin")
    return not origem or urlparse(origem).netloc == request.host or origem.rstrip("/") in ORIGENS


@app.before_request
def proteger():
    if request.remote_addr in LOCAIS:
        if request.host.split(":")[0] not in ("127.0.0.1", "localhost"):
            return jsonify(error="Host não permitido."), 403
        if request.method in ("POST", "PUT", "DELETE") and not _origem_ok():
            return jsonify(error="Origem não permitida."), 403
        return None
    # --- aparelho remoto ---
    if request.method == "GET" and request.path == "/":
        return None
    if not TOKEN:
        return jsonify(error="Acesso remoto desativado (defina ALICE_TOKEN)."), 403
    erros, ate = falhas.get(request.remote_addr, (0, 0))
    if time.time() < ate:
        return jsonify(error="Muitas tentativas. Espere 1 minuto."), 429
    enviado = request.headers.get("X-Alice-Token", "")
    if not hmac.compare_digest(enviado.encode(), TOKEN.encode()):
        erros += 1
        falhas[request.remote_addr] = (0, time.time() + 60) if erros >= 8 else (erros, 0)
        return jsonify(error="Senha incorreta.", auth=True), 401
    falhas.pop(request.remote_addr, None)
    if request.method in ("POST", "PUT", "DELETE") and not _origem_ok():
        return jsonify(error="Origem não permitida."), 403
    return None


@app.after_request
def cors(resp):
    origem = (request.headers.get("Origin") or "").rstrip("/")
    if origem in ORIGENS:
        resp.headers["Access-Control-Allow-Origin"] = origem
        resp.headers["Access-Control-Allow-Headers"] = "Content-Type, X-Alice-Token"
        resp.headers["Access-Control-Allow-Methods"] = "GET,POST,PUT,DELETE,OPTIONS"
    return resp


# ---------------------------------------------------------------- rotas
@app.get("/")
def index():
    return send_from_directory(app.static_folder, "index.html")


@app.get("/state")
def get_state():
    return jsonify({**estado(), "voz": speaker is not None, "ouvido": ouvido_ok, "modelo": brain.model,
                    "visao": brain.visao.modo})


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
    emo.on_usuario(msg)  # ela já reage à sua mensagem, antes mesmo de o modelo responder

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
                        # cada frase leva a sua emoção; ela vira expressão quando a frase COMEÇA a ser falada
                        emocao = emo.escolher_frase(ev["text"], ev.get("emo"))
                        ev = dict(ev, emocao=emocao)
                        ao_falar = lambda t=ev["text"], e=emocao: emo.emitir_fala(t, e)  # noqa: E731
                        if falar:
                            speaker.enfileirar(ev["text"], ao_falar)  # não trava: toca enquanto o LLM continua
                        else:
                            ao_falar()
                    elif ev["type"] == "acao":
                        ev = dict(ev, executada=rodar)
                        if rodar:
                            ev["resultado"] = brain.executar(ev["acao"], ev["arg"])
                            emo.on_acao(not str(ev["resultado"]).startswith(("Falhou", "Não ", "Nao ")))
                    yield sse(ev["type"], ev)
            except Exception as e:  # ErroLLM (Ollama fora do ar, modelo ausente...) ou falha inesperada
                emo.on_acao(False)  # fica confusa
                yield sse("erro", {"error": str(e) or e.__class__.__name__})
            else:
                if not teve_fala:
                    yield sse("erro", {"error": "A Alice não respondeu. Tente de novo."})
            emo.on_fim_resposta()
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
    espera = max(3.0, min(request.args.get("espera", 20, type=float), 60.0))  # quanto espera a pessoa começar a falar
    emo.ouvindo(True)  # ela fica atenta (e não troca de expressão) enquanto o microfone está aberto
    entendeu = False
    try:
        cancelar_mic.clear()
        texto = carregar_mic().ouvir_som(espera_max=espera, cancelar=cancelar_mic)
        entendeu = bool(texto)
        return jsonify(texto=texto)
    except Exception as e:
        return jsonify(error=f"Erro no microfone: {e}"), 500
    finally:
        lock_mic.release()
        # cancelar de propósito não é "não entendi": só fica confusa se ninguém falou
        emo.ouvindo(False, entendeu or cancelar_mic.is_set())


@app.get("/ouvir/estado")
def ouvir_estado():
    return jsonify(estado_mic())


@app.post("/ouvir/preparar")
def ouvir_preparar():
    preparar_mic()
    return jsonify(estado_mic())


@app.post("/ouvir/cancelar")
def ouvir_cancelar():
    cancelar_mic.set()
    return jsonify(ok=True)


# ---------------------------------------------------------------- visão de tela (brain/visao.py)
@app.get("/tela/estado")
def tela_estado():
    return jsonify(brain.visao.estado())


@app.post("/tela/modo")
def tela_modo():
    """{"modo": "0|texto|modelo", "modelo": "qwen3-vl:2b"} troca sem reiniciar o servidor."""
    b = corpo()
    try:
        brain.visao.configurar(modo=b.get("modo"), modelo=b.get("modelo"))
    except ValueError as e:
        return jsonify(error=str(e)), 400
    return jsonify(brain.visao.estado())


@app.post("/tela/ver")
def tela_ver():
    """Mostra o que a Alice leria da tela agora (para testar). {"pergunta": "..."} é opcional."""
    r = brain.visao.ver(str(corpo().get("pergunta", "")))
    return jsonify(r)


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
    emo.on_acao(not str(resultado).startswith(("Falhou", "Não ", "Nao ")))
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


# ---------------------------------------------------------------- desktop pet e expressões
# A interface web e o pet (pet.py) leem os MESMOS eventos: expressão, fala (frase + emoção) e aviso.
@app.get("/pet/catalogo")
def pet_catalogo():
    return jsonify(emocoes=catalogo_emocoes(), movimentos=list(MOVIMENTOS), estado=emo.estado())


@app.get("/pet/eventos")
def pet_eventos():
    """?desde=<último id visto>. Sem 'desde' (primeira chamada) só devolve o estado atual e o id de agora."""
    desde = request.args.get("desde", type=int)
    evs, ultimo = emo.eventos(desde if desde is not None and desde >= 0 else 10**12)
    return jsonify(eventos=evs, ultimo=ultimo, atual=emo.estado())


@app.post("/pet/toque")
def pet_toque():
    emo.on_toque()
    ini.on_toque()  # a reação falada sai logo depois (thread da iniciativa)
    return jsonify(atual=emo.estado())


@app.post("/pet/definir")
def pet_definir():
    b = corpo()
    try:
        dur = float(b.get("dur") or 8)
    except (TypeError, ValueError):
        return jsonify(error="Duração inválida."), 400
    if not emo.definir(b.get("nome"), max(1.0, min(dur, 600.0)), "manual", forcar=True, respeitar_bloqueio=False):
        return jsonify(error="Emoção desconhecida."), 400
    return jsonify(atual=emo.estado())


@app.post("/pet/ritmo")
def pet_ritmo():
    try:
        emo.ritmo = max(0.0, min(float(corpo().get("ritmo")), 5.0))
    except (TypeError, ValueError):
        return jsonify(error="Ritmo inválido."), 400
    return jsonify(atual=emo.estado())


@app.post("/pet/dormir")
def pet_dormir():
    emo.dormir()
    return jsonify(atual=emo.estado())


@app.post("/pet/acordar")
def pet_acordar():
    emo.acordar()
    return jsonify(atual=emo.estado())


# ---------------------------------------------------------------- iniciativa: configuração e teste
@app.get("/pet/iniciativa")
def pet_iniciativa_get():
    return jsonify(ini.estado())


@app.post("/pet/iniciativa")
def pet_iniciativa_set():
    b = corpo()
    try:
        ini.configurar(nivel=b.get("nivel"), voz=b.get("voz"))
    except (TypeError, ValueError) as e:
        return jsonify(error=str(e)), 400
    return jsonify(ini.estado())


@app.post("/pet/iniciativa/abertura")
def pet_iniciativa_abertura():
    """O pet chama ao conectar: ela diz oi (uma vez a cada 5 min no máximo) e aquece o modelo."""
    partes = ini.abrir()
    return jsonify(falou=bool(partes), texto=[t for t, _ in partes or []])


@app.post("/pet/iniciativa/disparar")
def pet_iniciativa_disparar():
    """Para testar sem esperar: {"tipo": "abertura|checkin|volta|almoco|jantar|madrugada|expressao", "emocao": "...", "n": 0}"""
    b = corpo()
    try:
        partes = ini.disparar(str(b.get("tipo", "")), emocao=b.get("emocao"), n=b.get("n", 0))
    except (TypeError, ValueError) as e:
        return jsonify(error=str(e)), 400
    if partes is None:
        return jsonify(error="Tipo desconhecido."), 400
    return jsonify(texto=[t for t, _ in partes])


# ---------------------------------------------------------------- painel, agenda, planilhas
def _erro(fn):
    """Transforma ValueError (dado inválido) em resposta 400 legível."""
    from functools import wraps

    @wraps(fn)
    def w(*a, **k):
        try:
            return fn(*a, **k)
        except ValueError as e:
            return jsonify(error=str(e)), 400

    return w


@app.get("/painel")
def painel():
    return jsonify(
        agora=time.strftime("%Y-%m-%dT%H:%M:%S"),
        clima=brain.clima.dados,
        agenda=brain.agenda.pendentes(10),
        resumo=brain.dados.resumo(),
        cards=list(brain.acoes.cards),
    )


@app.delete("/cards/<int:cid>")
def apagar_card(cid):
    brain.acoes.cards = type(brain.acoes.cards)((c for c in brain.acoes.cards if c["id"] != cid), maxlen=20)
    return jsonify(ok=True)


@app.get("/agenda")
def get_agenda():
    return jsonify(agenda=brain.agenda.todos())


@app.post("/agenda")
def post_agenda():
    b = corpo()
    item, erro = brain.agenda.adicionar_frase(str(b.get("quando", "")), str(b.get("texto", "")))
    if erro:
        return jsonify(error=erro), 400
    return jsonify(item=item)


@app.put("/agenda/<int:iid>")
def put_agenda(iid):
    return jsonify(ok=brain.agenda.concluir(iid, bool(corpo().get("feito", True))))


@app.delete("/agenda/<int:iid>")
def del_agenda(iid):
    return jsonify(ok=brain.agenda.remover(iid))


@app.get("/tabelas")
def get_tabelas():
    return jsonify(tabelas=brain.dados.esquema())


@app.get("/tabelas/<nome>")
@_erro
def get_tabela(nome):
    return jsonify(linhas=brain.dados.listar(nome, request.args.get("limite", 300, type=int)))


@app.post("/tabelas/<nome>")
@_erro
def post_tabela(nome):
    msg = brain.acoes.registrar_campos(nome, corpo().get("valores") or {})
    if not msg.startswith("Registrado"):
        return jsonify(error=msg), 400
    return jsonify(ok=True, mensagem=msg)


@app.put("/tabelas/<nome>/<int:lid>")
@_erro
def put_tabela(nome, lid):
    return jsonify(ok=brain.dados.atualizar(nome, lid, corpo().get("valores") or {}))


@app.delete("/tabelas/<nome>/<int:lid>")
@_erro
def del_tabela(nome, lid):
    return jsonify(ok=brain.dados.remover(nome, lid))


@app.get("/grafico/<nome>")
@_erro
def grafico(nome):
    a = request.args
    return jsonify(brain.dados.grafico(nome, a.get("y"), a.get("agg"), a.get("periodo"), a.get("por"), a.get("dias", 120, type=int)))


@app.get("/export/<nome>")
@_erro
def exportar(nome):
    nome_ok, _ = brain.dados._tabela(nome)
    return Response(brain.dados.csv(nome_ok), mimetype="text/csv; charset=utf-8",
                    headers={"Content-Disposition": f"attachment; filename={nome_ok}.csv"})


if __name__ == "__main__":
    if HOST not in LOCAIS + ("localhost",) and not TOKEN:
        raise SystemExit("ALICE_HOST aberto para a rede exige ALICE_TOKEN (uma senha). Veja o LEIAME-CELULAR.md.")

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
    ini.iniciar()  # a vida própria (puxar assunto) só liga quando roda como programa, não nos testes
    print(f"Alice no ar: http://127.0.0.1:{PORTA}" + ("  (aberta para a rede, com senha)" if TOKEN and HOST not in LOCAIS else ""))
    # Por padrão 127.0.0.1: só o seu PC acessa. A interface pode disparar ações no computador.
    app.run(host=HOST, port=PORTA, debug=False, threaded=True)