"""
Tudo do desktop pet que NÃO depende de Qt (por isso dá para testar sem abrir janela):
conversa com o servidor, fila de expressões, balão de fala, movimentos, partículas,
física de queda, passeio e configuração. A janela está em pet.py.
"""
import json
import math
import os
import subprocess
import sys
import time
import urllib.error
import urllib.request
from collections import deque
from dataclasses import dataclass

SPRITE_PX = 320  # tamanho original dos sprites (static/pet/*.png)


# ======================================================================== servidor
class ErroServidor(Exception):
    """O servidor respondeu com erro (ex.: 501 'microfone indisponível'); .status e a mensagem dele."""

    def __init__(self, status, mensagem):
        super().__init__(mensagem)
        self.status = status


class Cliente:
    """Fala com o server.py da Alice (mesmos endpoints que a interface web usa)."""

    def __init__(self, base="http://127.0.0.1:5000", timeout=3.0):
        self.base = base.rstrip("/")
        self.timeout = timeout

    def _req(self, metodo, caminho, corpo=None, timeout=None):
        dados = json.dumps(corpo).encode("utf-8") if corpo is not None else (b"{}" if metodo == "POST" else None)
        req = urllib.request.Request(self.base + caminho, data=dados, method=metodo,
                                     headers={"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=timeout or self.timeout) as r:
                return json.loads(r.read().decode("utf-8") or "{}")
        except urllib.error.HTTPError as e:
            try:
                msg = json.loads(e.read().decode("utf-8")).get("error") or str(e)
            except Exception:
                msg = str(e)
            raise ErroServidor(e.code, msg) from None

    def no_ar(self):
        try:
            self._req("GET", "/pet/catalogo", timeout=1.5)
            return True
        except Exception:
            return False

    def catalogo(self):
        return self._req("GET", "/pet/catalogo")

    def eventos(self, desde=None):
        """(eventos novos, id do último, estado atual). Com desde=None só devolve o estado."""
        j = self._req("GET", "/pet/eventos" + ("" if desde is None else f"?desde={int(desde)}"))
        return j["eventos"], j["ultimo"], j["atual"]

    def toque(self):
        return self._req("POST", "/pet/toque")

    def definir(self, nome, dur=10):
        return self._req("POST", "/pet/definir", {"nome": nome, "dur": dur})

    def ritmo(self, valor):
        return self._req("POST", "/pet/ritmo", {"ritmo": valor})

    def dormir(self):
        return self._req("POST", "/pet/dormir")

    def acordar(self):
        return self._req("POST", "/pet/acordar")

    # --- voz: o microfone é o do PC (Whisper no servidor), o pet só comanda e mostra
    def ouvir(self, espera=10):
        """Abre o microfone até a pessoa falar e ficar em silêncio. Devolve {'texto': ... ou None}. Bloqueia."""
        return self._req("POST", f"/ouvir?espera={float(espera)}", timeout=float(espera) + 60)

    def ouvir_cancelar(self):
        return self._req("POST", "/ouvir/cancelar")

    def ouvir_estado(self):
        return self._req("GET", "/ouvir/estado", timeout=1.5)

    def ouvir_preparar(self):
        return self._req("POST", "/ouvir/preparar")

    def parar_fala(self):
        return self._req("POST", "/stop")

    def adiar(self, texto, minutos=10):
        return self._req("POST", "/agenda", {"quando": f"daqui a {int(minutos)} minutos", "texto": texto})

    def conversar(self, mensagem, falar=True, acoes=True, timeout=600):
        """Gera (evento, dados) do stream SSE do /chat até o fim da resposta."""
        corpo = json.dumps({"message": mensagem, "speak": falar, "run_actions": acoes}).encode("utf-8")
        req = urllib.request.Request(self.base + "/chat", data=corpo, method="POST",
                                     headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=timeout) as r:
            evento, dados = None, []
            for bruto in r:
                linha = bruto.decode("utf-8").rstrip("\r\n")
                if linha.startswith("event:"):
                    evento = linha[6:].strip()
                elif linha.startswith("data:"):
                    dados.append(linha[5:].strip())
                elif linha == "":
                    if evento and dados:
                        yield evento, json.loads("\n".join(dados))
                    evento, dados = None, []


def garantir_servidor(cliente, server_py, cwd, espera=45):
    """Se o servidor não estiver no ar, liga (sem janela de console). Devolve o Popen ou None."""
    if cliente.no_ar():
        return None
    flags = 0x08000000 if os.name == "nt" else 0  # CREATE_NO_WINDOW
    proc = subprocess.Popen([sys.executable, server_py], cwd=cwd, creationflags=flags,
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    fim = time.time() + espera
    while time.time() < fim:
        if proc.poll() is not None:
            raise RuntimeError("O servidor da Alice fechou ao iniciar. Rode 'python IA/server.py' para ver o erro.")
        if cliente.no_ar():
            return proc
        time.sleep(0.4)
    proc.terminate()
    raise RuntimeError("O servidor da Alice não respondeu a tempo.")


# ======================================================================== configuração
PADRAO = {"escala": 0.7, "x": None, "y": None, "topo": True, "passear": True, "acoes": True,
          "servidor": "http://127.0.0.1:5000",
          "voz": True,        # a Alice fala as respostas em voz alta
          "chamada": False,   # depois que ela responde, abre o microfone de novo sozinha
          "olhar": True,      # vira para o lado do mouse
          "espera": 10,       # segundos esperando você começar a falar, antes de desistir
          "preparar_ouvido": True}  # carrega o Whisper ao abrir o pet (o 1º clique no microfone não espera)


def caminho_config():
    return os.path.join(os.path.expanduser("~"), ".alice_pet.json")


def carregar_config(caminho=None):
    cfg = dict(PADRAO)
    try:
        with open(caminho or caminho_config(), encoding="utf-8") as f:
            salvo = json.load(f)
        cfg.update({k: v for k, v in salvo.items() if k in PADRAO})
    except (OSError, ValueError):
        pass
    cfg["escala"] = min(2.0, max(0.3, float(cfg["escala"] or 0.7)))
    return cfg


def salvar_config(cfg, caminho=None):
    try:
        with open(caminho or caminho_config(), "w", encoding="utf-8") as f:
            json.dump({k: cfg.get(k) for k in PADRAO}, f, indent=2)
        return True
    except OSError:
        return False


# ======================================================================== layout
@dataclass
class Layout:
    sprite_w: int
    sprite_h: int
    janela_w: int
    janela_h: int
    margem: int      # espaço embaixo dos pés (sombra)
    balao_h: int     # espaço em cima da cabeça (balão de fala)


def layout(escala):
    s = max(96, int(SPRITE_PX * escala))
    balao_h, margem = 140, 12
    return Layout(s, s, max(s + 80, 360), s + balao_h + margem, margem, balao_h)


# ======================================================================== fila de expressões
class FilaExpressao:
    """
    Evita o pisca-pisca: eventos de fala/emoção entram numa fila e cada um fica na tela um
    tempo mínimo (uma frase fica o tempo dela, até 6 s). Igual à fila da interface web.
    """

    def __init__(self, maximo=6):
        self.itens = deque()
        self.maximo = maximo
        self.ocupado_ate = 0.0

    def push(self, ev):
        if ev.get("tipo") in ("fala", "emocao"):
            self.itens.append(ev)
            while len(self.itens) > self.maximo:
                self.itens.popleft()

    def limpar(self):
        self.itens.clear()
        self.ocupado_ate = 0.0

    def proximo(self, agora):
        if not self.itens or agora < self.ocupado_ate:
            return None
        ev = self.itens.popleft()
        espera = max(1.2, min(float(ev.get("dur", 0)), 6.0)) if ev["tipo"] == "fala" else 0.6
        self.ocupado_ate = agora + espera
        return ev


# ======================================================================== balão de fala
def quebrar(texto, largura, medir, max_linhas=5):
    """Quebra o texto em linhas que cabem em `largura` (medir(str) -> pixels)."""
    linhas, atual = [], ""
    for palavra in texto.split():
        teste = (atual + " " + palavra).strip()
        if atual and medir(teste) > largura:
            linhas.append(atual)
            atual = palavra
        else:
            atual = teste
    if atual:
        linhas.append(atual)
    if len(linhas) > max_linhas:
        linhas = linhas[:max_linhas]
        ultima = linhas[-1].rstrip(" .,;!?")
        while len(ultima) > 1 and medir(ultima + "…") > largura:
            ultima = ultima[:-1].rstrip()
        linhas[-1] = ultima + "…"
    return linhas


class Balao:
    def __init__(self):
        self.texto, self.tipo, self.nasceu, self.ate = "", "fala", 0.0, 0.0

    def mostrar(self, texto, dur, agora, tipo="fala"):
        self.texto, self.tipo, self.nasceu, self.ate = texto, tipo, agora, agora + dur

    def fechar(self):
        self.ate = 0.0

    def visivel(self, agora):
        return bool(self.texto) and agora < self.ate

    def alpha(self, agora):
        """Aparece em 0,15 s e some suavemente no último meio segundo."""
        if not self.visivel(agora):
            return 0.0
        entra = min(1.0, (agora - self.nasceu) / 0.15)
        sai = min(1.0, (self.ate - agora) / 0.5)
        return max(0.0, min(entra, sai))


# ======================================================================== movimento do sprite
def transformar(mov, t):
    """
    Espelha os movimentos da interface web. Devolve (dx, dy, sx, sy, rot):
    dx/dy como fração do tamanho do sprite (dy<0 = para cima), sx/sy = escala, rot em graus.
    A origem da rotação/escala é o pé do sprite (centro da base).
    """
    tau = 2 * math.pi
    s = lambda per: math.sin(tau * t / per)               # -1..1  # noqa: E731
    u = lambda per: (1 - math.cos(tau * t / per)) / 2      # 0..1   # noqa: E731
    if mov == "respirar":
        return 0, 0, 1 + 0.012 * u(3.4), 1 + 0.026 * u(3.4), 0
    if mov == "inclinar":
        return 0, 0, 1, 1, 3 * s(3.2)
    if mov == "pular_leve":
        return 0, -0.05 * u(1.0), 1, 1, 0
    if mov == "pular":
        p = u(0.6)
        return 0, -0.13 * p, 1.03 - 0.06 * p, 0.96 + 0.08 * p, 0
    if mov == "balancar":
        return 0, 0, 1, 1, 4 * s(1.7)
    if mov == "tremer":
        return 0.016 * s(0.14), 0, 1, 1, 0
    if mov == "tremer_leve":
        return 0.007 * s(0.2), 0, 1, 1, 0
    if mov == "cochilar":
        return 0, 0.015 + 0.01 * s(3.8), 1, 1, 1.5 + 2.5 * s(3.8)
    if mov == "esticar":
        return 0, 0, 1, 1 + 0.07 * u(1.5), 0
    if mov == "encolher":
        return 0, 0.015 + 0.005 * s(2.4), 0.957 - 0.012 * s(2.4), 0.957 - 0.012 * s(2.4), 0
    return 0, 0, 1, 1, 0


# ======================================================================== partículas
class Particulas:
    VIDA = 2.3

    def __init__(self, rng):
        self.rng = rng
        self.chars = []
        self.proxima = 0.0
        self.lista = []  # (ch, nasceu, x0, y0, dx)

    def configurar(self, chars, agora):
        self.chars = list(chars or [])
        self.proxima = agora + 0.25

    def atualizar(self, agora):
        if self.chars and agora >= self.proxima:
            self.lista.append((self.rng.choice(self.chars), agora, self.rng.uniform(0.2, 0.8),
                               self.rng.uniform(0.04, 0.3), self.rng.uniform(-0.1, 0.1)))
            self.proxima = agora + self.rng.uniform(1.2, 1.8)
        self.lista = [p for p in self.lista if agora - p[1] < self.VIDA]

    def desenho(self, agora):
        """[(caractere, x, y, alpha, escala)] com x/y em fração do sprite (y=0 topo)."""
        saida = []
        for ch, nasceu, x0, y0, dx in self.lista:
            k = (agora - nasceu) / self.VIDA
            alpha = k / 0.15 if k < 0.15 else (1 - k) / 0.85
            saida.append((ch, x0 + dx * k, y0 - 0.2 * k, max(0.0, min(1.0, alpha)), 0.6 + 0.55 * k))
        return saida


# ======================================================================== física e passeio
class Fisica:
    """Queda com quique quando a Alice é solta no ar."""
    G = 2600.0  # px/s²

    def __init__(self):
        self.vy = 0.0
        self.caindo = False

    def soltar(self):
        self.caindo, self.vy = True, 0.0

    def parar(self):
        self.caindo, self.vy = False, 0.0

    def passo(self, y, chao, dt):
        """Devolve (novo_y, tocou_o_chao, velocidade_do_impacto)."""
        if not self.caindo:
            return y, False, 0.0
        self.vy += self.G * dt
        y += self.vy * dt
        if y < chao:
            return y, False, 0.0
        impacto = self.vy
        if impacto > 420:
            self.vy = -impacto * 0.25
        else:
            self.vy, self.caindo = 0.0, False
        return chao, True, impacto


@dataclass
class Salto:
    x0: float
    x1: float
    chao: float
    t0: float
    dur: float
    altura: float

    def pos(self, agora):
        """(x, y, terminou). x suaviza no começo e no fim; y é uma parábola."""
        u = max(0.0, min(1.0, (agora - self.t0) / self.dur))
        e = u * u * (3 - 2 * u)
        return self.x0 + (self.x1 - self.x0) * e, self.chao - 4 * self.altura * u * (1 - u), u >= 1.0


class Passeio:
    """Decide quando ela dá um pulinho para outro ponto da tela (só quando está disposta)."""
    ENERGICAS = {"feliz", "brincalhona", "vitoria", "ideia", "apaixonada"}
    QUIETAS = {"dormindo", "sonolenta", "espreguicando", "irritada", "entediada", "choramingando", "timida", "carente"}

    def __init__(self, rng, agora):
        self.rng = rng
        self.proximo = agora + rng.uniform(12, 30)

    def decidir(self, agora, emocao, livre, x, tela_x0, tela_x1, largura, chao, ativo=True):
        if not ativo or not livre or emocao in self.QUIETAS or agora < self.proximo:
            return None
        energica = emocao in self.ENERGICAS
        self.proximo = agora + (self.rng.uniform(15, 45) if energica else self.rng.uniform(45, 120))
        espaco_esq, espaco_dir = x - tela_x0, (tela_x1 - largura) - x
        for _ in range(8):
            dist = self.rng.uniform(120, 420)
            destino = x + (dist if self.rng.random() < 0.5 else -dist)
            if tela_x0 <= destino <= tela_x1 - largura:
                break
        else:  # sem espaço para o lado sorteado: vai para o lado que tem espaço
            destino = x + min(self.rng.uniform(120, 420), espaco_dir) if espaco_dir > espaco_esq else x - min(self.rng.uniform(120, 420), espaco_esq)
        if abs(destino - x) < 40:
            return None
        return Salto(x, destino, chao, agora, self.rng.uniform(0.55, 0.9), self.rng.uniform(40, 90) if energica else 28)


def pop(u):
    """Escala (sx, sy) do 'pulinho' ao trocar de expressão; u vai de 0 a 1 em ~0,32 s."""
    if u >= 1:
        return 1.0, 1.0
    u = max(0.0, u)
    if u < 0.55:
        k = u / 0.55
        return 0.9 + 0.17 * k, 1.08 - 0.12 * k
    k = (u - 0.55) / 0.45
    return 1.07 - 0.07 * k, 0.96 + 0.04 * k


# ======================================================================== voz (botão de microfone)
# Estados do que o pet mostra no botão:
#   parado -> (clique) -> preparando|ouvindo -> gravando (detectou voz) -> transcrevendo -> pensando -> falando -> parado
ESTADOS_VOZ = ("parado", "preparando", "ouvindo", "gravando", "transcrevendo", "pensando", "falando")


def acao_clique_mic(estado):
    """O que um clique no microfone faz em cada estado."""
    if estado == "parado":
        return "iniciar"        # começa a ouvir; ao detectar que você parou de falar, envia sozinho
    if estado in ("pensando", "falando"):
        return "interromper"    # cala a Alice e já abre o microfone para você falar
    return "cancelar"           # estava ouvindo/preparando/transcrevendo: desiste


def estado_do_servidor(est):
    """Traduz /ouvir/estado para o estado do botão (None se o microfone está fechado)."""
    if not est.get("ativo"):
        return None
    if est.get("carregando") or not est.get("pronto"):
        return "preparando"     # primeira vez: o Whisper ainda está carregando
    return {"gravando": "gravando", "transcrevendo": "transcrevendo"}.get(est.get("estado"), "ouvindo")


class Chamada:
    """Modo chamada: ela volta a ouvir sozinha depois de responder, até a pessoa ficar muda."""
    MAX_VAZIOS = 2

    def __init__(self):
        self.ativa, self.vazios = False, 0

    def ligar(self):
        self.ativa, self.vazios = True, 0

    def desligar(self):
        self.ativa, self.vazios = False, 0

    def ouviu(self, texto):
        self.vazios = 0 if texto else self.vazios + 1

    def continuar(self):
        return self.ativa and self.vazios < self.MAX_VAZIOS

    def encerrou_por_silencio(self):
        return self.ativa and self.vazios >= self.MAX_VAZIOS


def escala_nivel(volume, limiar=0.01):
    """Volume RMS do microfone -> 0..1 para o anel (raiz: voz baixa ainda mexe o anel)."""
    if volume <= 0:
        return 0.0
    return min(1.0, (volume / (max(limiar, 1e-4) * 8)) ** 0.5)


def suavizar(anterior, novo, subida=0.55, descida=0.12):
    """Sobe rápido e desce devagar, como um medidor de volume."""
    k = subida if novo > anterior else descida
    return anterior + (novo - anterior) * k


# ======================================================================== geometria dos botões
def botoes(lay):
    """Botões desenhados junto aos pés dela (lado oposto ao rabo): {nome: (cx, cy, raio)} na janela."""
    r = max(14, int(lay.sprite_w * 0.065))
    cx = lay.janela_w / 2 - lay.sprite_w * 0.40
    cy = lay.janela_h - lay.margem - lay.sprite_h * 0.13
    return {"mic": (cx, cy, r), "texto": (cx + 2.3 * r, cy + 0.15 * r, r * 0.78)}


def dentro_circulo(c, x, y, folga=2):
    cx, cy, r = c
    return math.hypot(x - cx, y - cy) <= r + folga


def dentro_rect(rc, x, y):
    x0, y0, w, h = rc
    return x0 <= x <= x0 + w and y0 <= y <= y0 + h


def botao_em(lay, x, y):
    """Qual botão está nesse ponto da janela ('mic', 'texto') ou None."""
    for nome, c in botoes(lay).items():
        if dentro_circulo(c, x, y):
            return nome
    return None


# ======================================================================== lembretes no balão
def eh_lembrete(texto):
    return texto.strip().lstrip("⏰").strip().lower().startswith("lembrete")


def limpar_lembrete(texto):
    """'⏰ Lembrete atrasado: beber água' -> 'beber água'."""
    t = texto.strip().lstrip("⏰").strip()
    for pre in ("Lembrete atrasado:", "Lembrete:"):
        if t.lower().startswith(pre.lower()):
            return t[len(pre):].strip()
    return t


def rects_aviso(x, y, larg, alt):
    """Botões 'Ok' e '+10 min' na faixa de baixo do balão de lembrete: {nome: (x, y, w, h)}."""
    h, w_ok, w_mais, folga = 22, 44, 76, 8
    topo = y + alt - h - 6
    total = w_ok + folga + w_mais
    x0 = x + (larg - total) / 2
    return {"ok": (x0, topo, w_ok, h), "mais": (x0 + w_ok + folga, topo, w_mais, h)}


# ======================================================================== olhar
def virar_para(cursor_x, centro_x, atual, margem=140):
    """
    Os sprites olham para a ESQUERDA da tela (rabo à direita). Espelhar (True) faz ela olhar para a
    direita. Só vira quando o mouse passa de `margem` px do centro (evita ficar piscando de lado).
    """
    if cursor_x > centro_x + margem:
        return True
    if cursor_x < centro_x - margem:
        return False
    return atual
