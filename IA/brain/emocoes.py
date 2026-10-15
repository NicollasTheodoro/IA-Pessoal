"""
Motor de emoções da Alice: decide QUAL expressão mostrar e QUANDO trocar.

Quem desenha (interface web e desktop pet) só recebe eventos e mostra o sprite certo.
Tudo aqui é Python puro, sem relógio nem sorteio escondidos (ambos podem ser injetados),
então dá para testar.

COMO A EXPRESSÃO MUDA (por isso parece natural):
  1. Reação a você: ao receber sua mensagem ela já reage (oi -> animada, elogio -> tímida/apaixonada,
     xingamento -> irritada, pergunta -> ideia...).
  2. Durante a resposta: cada FRASE pode ter a sua emoção (tag <emo:nome> do modelo ou, se faltar,
     palavras e pontuação da própria frase). A troca acontece quando a frase começa a ser falada.
  3. Parada, ela "vive": a cada poucos segundos passa para uma emoção vizinha da atual
     (grafo VIZINHAS), influenciada pelos traços (carinho, energia, sarcasmo, paciência), pelo
     estado de humor, pela hora do dia e por quanto tempo você ficou sem falar com ela:
        ~1:40 sem você  -> mais tédio e confusão
        ~4:20           -> espreguiça/boceja e fica sonolenta
        ~10:00          -> dorme (metade do tempo, de madrugada)
     Ao interagir de novo, ela acorda espreguiçando antes de reagir.
  4. Cutucões (clique no pet): 1 -> simpática, 2 -> confusa, 3 -> tímida/desconfiada, 4+ -> irritada.
  5. Eventos: lembrete -> ideia; ação que deu certo -> às vezes comemora; falhou -> confusa.

Eventos publicados (para o cliente pedir com eventos(desde)):
    {"tipo": "emocao", "nome": "feliz", "dur": 8.2, "fonte": "ocioso"}
    {"tipo": "fala",   "texto": "...",  "emocao": "feliz", "dur": 3.1}
    {"tipo": "aviso",  "texto": "Lembrete: ..."}
"""
import random
import re
import threading
import time
import unicodedata
from collections import deque
from datetime import datetime

from . import vocabulario as vc

# --------------------------------------------------------------------------- catálogo
# sprite: arquivo em static/pet/<sprite>.png (10 imagens, várias emoções compartilham a mesma pose)
# mov:    movimento que o cliente aplica sobre o sprite (veja MOVIMENTOS)
# part:   partículas flutuantes (emoji) que o cliente solta de vez em quando
# hold:   quanto tempo (min, max em segundos) a emoção costuma durar quando ela está parada
EMOCOES = {
    "neutra":        dict(rotulo="Neutra",        sprite="seria",         mov="respirar",   part=[],             cor="#ff5c93", hold=(9, 20)),
    "desconfiada":   dict(rotulo="Desconfiada",   sprite="seria",         mov="inclinar",   part=[],             cor="#9b8cc4", hold=(4, 9)),
    "feliz":         dict(rotulo="Animada",       sprite="piscadinha",    mov="pular_leve", part=["✨"],         cor="#ffd95a", hold=(6, 12)),
    "brincalhona":   dict(rotulo="Brincalhona",   sprite="piscadinha",    mov="balancar",   part=["♪"],          cor="#ff9ad5", hold=(4, 9)),
    "vitoria":       dict(rotulo="Vitoriosa",     sprite="vitoria",       mov="pular",      part=["🎉", "✨"],    cor="#ffd95a", hold=(4, 8)),
    "apaixonada":    dict(rotulo="Apaixonada",    sprite="encantada",     mov="balancar",   part=["♥"],          cor="#ff7ab8", hold=(6, 12)),
    "ideia":         dict(rotulo="Ideia!",        sprite="ideia",         mov="pular_leve", part=["💡"],         cor="#7ad7ff", hold=(4, 8)),
    "irritada":      dict(rotulo="Irritada",      sprite="irritada",      mov="tremer",     part=[],             cor="#ff7a45", hold=(6, 12)),
    "entediada":     dict(rotulo="Entediada",     sprite="entediada",     mov="respirar",   part=[],             cor="#8f86a8", hold=(7, 16)),
    "confusa":       dict(rotulo="Confusa",       sprite="entediada",     mov="inclinar",   part=["❓"],         cor="#a8a0c8", hold=(3, 7)),
    "sonolenta":     dict(rotulo="Sonolenta",     sprite="sonolenta",     mov="cochilar",   part=[],             cor="#6f78c9", hold=(7, 15)),
    "dormindo":      dict(rotulo="Dormindo",      sprite="sonolenta",     mov="cochilar",   part=["💤"],         cor="#4f5aa8", hold=(3600, 3600)),
    "espreguicando": dict(rotulo="Espreguiçando", sprite="espreguicando", mov="esticar",    part=[],             cor="#ffb07a", hold=(3.5, 5)),
    "timida":        dict(rotulo="Tímida",        sprite="timida",        mov="encolher",   part=[],             cor="#ffa6c9", hold=(5, 10)),
    "choramingando": dict(rotulo="Chorosa",       sprite="timida",        mov="tremer_leve", part=["💧"],        cor="#8ab6ff", hold=(5, 9)),
    "carente":       dict(rotulo="Carente",       sprite="timida",        mov="balancar",   part=["♥"],          cor="#b79bff", hold=(6, 12)),
    # só aparece enquanto o microfone está aberto (ouvindo(True)); não entra no sorteio nem nas frases
    "ouvindo":       dict(rotulo="Ouvindo",       sprite="seria",         mov="inclinar",   part=["🎧"],         cor="#5fd0c0", hold=(90, 90)),
}
# o que o cliente deve implementar para cada "mov":
MOVIMENTOS = ("respirar", "inclinar", "pular_leve", "pular", "balancar", "tremer", "tremer_leve",
              "cochilar", "esticar", "encolher")

# nomes que o modelo ou o usuário podem usar -> emoção do catálogo
ALIAS = {
    "animada": "feliz", "alegre": "feliz", "contente": "feliz", "empolgada": "ideia", "surpresa": "ideia",
    "brava": "irritada", "braba": "irritada", "raiva": "irritada", "nervosa": "irritada", "irritado": "irritada",
    "apaixonado": "apaixonada", "encantada": "apaixonada", "fofa": "apaixonada", "amor": "apaixonada",
    "sonolento": "sonolenta", "sono": "sonolenta", "cansada": "sonolenta",
    "tedio": "entediada", "desinteressada": "entediada", "entediado": "entediada",
    "triste": "choramingando", "chorando": "choramingando", "choramingo": "choramingando",
    "envergonhada": "timida", "tímida": "timida", "vergonha": "timida",
    "orgulhosa": "vitoria", "comemorando": "vitoria", "vitoriosa": "vitoria", "vitória": "vitoria",
    "piscadinha": "brincalhona", "zoando": "brincalhona", "travessa": "brincalhona", "sapeca": "brincalhona",
    "sarcastica": "desconfiada", "sarcástica": "desconfiada", "seria": "neutra", "séria": "neutra",
    "neutral": "neutra", "excited": "feliz", "irritated": "irritada", "needy": "carente",
    "carinhosa": "carente", "pensativa": "confusa", "duvida": "confusa", "dúvida": "confusa",
    "escutando": "ouvindo", "atenta": "ouvindo",
    "bocejo": "espreguicando", "bocejando": "espreguicando", "espreguicando": "espreguicando",
}
BASE_DO_ESTADO = {"neutral": "neutra", "excited": "feliz", "irritated": "irritada", "needy": "carente"}

# como ela "está" (vai para o prompt: o texto da resposta combina com a expressão)
HUMOR_PROMPT = {
    "neutra": "tranquila", "desconfiada": "desconfiada e meio sarcástica", "feliz": "animada",
    "brincalhona": "brincalhona, com vontade de zoar", "vitoria": "radiante, comemorando",
    "apaixonada": "derretida e fofa", "ideia": "empolgada com uma ideia", "irritada": "irritada, curta e seca",
    "entediada": "entediada e desinteressada", "confusa": "confusa", "sonolenta": "com sono, devagar",
    "dormindo": "grogue, acabou de ser acordada", "espreguicando": "bocejando, acabou de acordar",
    "timida": "tímida e envergonhada", "choramingando": "chorosa e manhosa", "carente": "carente, pedindo atenção",
    "ouvindo": "atenta, ouvindo você",
}

# ----------------------------------------------------------------------- ociosidade natural
# De cada emoção, para quais ela costuma ir quando está parada (peso relativo).
VIZINHAS = {
    "neutra":        {"neutra": 3, "desconfiada": 3, "feliz": 3, "entediada": 2, "ideia": 2, "brincalhona": 2, "confusa": 1, "timida": 1},
    "desconfiada":   {"neutra": 3, "entediada": 2, "confusa": 2, "brincalhona": 2, "irritada": 1, "ideia": 1},
    "feliz":         {"brincalhona": 3, "neutra": 3, "ideia": 2, "vitoria": 1, "apaixonada": 1, "timida": 1},
    "brincalhona":   {"feliz": 3, "neutra": 2, "desconfiada": 2, "vitoria": 1, "ideia": 1, "timida": 1},
    "vitoria":       {"feliz": 4, "brincalhona": 2, "neutra": 2, "apaixonada": 1},
    "apaixonada":    {"timida": 3, "feliz": 3, "neutra": 2, "carente": 1, "brincalhona": 1},
    "ideia":         {"feliz": 3, "neutra": 3, "brincalhona": 2, "desconfiada": 1, "vitoria": 1},
    "irritada":      {"desconfiada": 3, "neutra": 2, "entediada": 2, "irritada": 1, "choramingando": 0.5},
    "entediada":     {"neutra": 2, "confusa": 2, "sonolenta": 2, "desconfiada": 2, "espreguicando": 1.5, "entediada": 1},
    "confusa":       {"neutra": 3, "desconfiada": 2, "entediada": 2, "ideia": 2, "timida": 1},
    "sonolenta":     {"sonolenta": 2, "entediada": 2, "espreguicando": 2, "neutra": 1},
    "espreguicando": {"neutra": 3, "feliz": 3, "sonolenta": 1, "brincalhona": 1},
    "timida":        {"neutra": 3, "feliz": 2, "apaixonada": 1, "carente": 1, "choramingando": 0.5},
    "choramingando": {"carente": 2, "timida": 2, "neutra": 2, "entediada": 1},
    "carente":       {"timida": 2, "apaixonada": 2, "neutra": 2, "choramingando": 1, "feliz": 1},
    "dormindo":      {"dormindo": 1},
}
# peso geral (variedade), somado ao do grafo
BASE = {"neutra": 3, "desconfiada": 1.2, "feliz": 1.5, "brincalhona": 1.2, "vitoria": 0.4, "apaixonada": 0.5,
        "ideia": 0.9, "irritada": 0.25, "entediada": 1.2, "confusa": 0.7, "sonolenta": 0.6, "timida": 0.6,
        "choramingando": 0.15, "carente": 0.5, "espreguicando": 0.3}
NAO_SORTEIA = {"dormindo", "ouvindo"}  # dormindo só pela escada do sono; ouvindo só com o microfone aberto

T_TEDIO, T_BOCEJO, T_SONO, T_DORME = 100, 260, 330, 600  # segundos sem interação
FATOR_NOITE = 0.5  # de madrugada o sono vem na metade do tempo

# --------------------------------------------------------------------------- vocabulário
def _norm(t):
    t = unicodedata.normalize("NFD", (t or "").lower())
    return "".join(c for c in t if unicodedata.category(c) != "Mn")


def _p(expr):
    return re.compile(expr)


# Reação à mensagem do usuário (primeira que casar). Cada item: (padrão, {emoção: peso})
USUARIO = [
    (_p(r"\b(vagabund\w*|idiota|burr[ao]|inutil|cala a boca|odeio|te odeio|insuportavel|irritante|chata|"
        r"vai embora|incompetente|imbecil|lixo|estupida|bobona)\b"),
     {"irritada": 4, "desconfiada": 1, "choramingando": 1}),
    (_p(r"\b(amo voce|te amo|linda|lindo|fofa|fofo|maravilhosa|incrivel|perfeita|voce e demais|gosto de voce|"
        r"parabens|orgulho de voce|querida|meu bem)\b"),
     {"timida": 3, "apaixonada": 3, "feliz": 2}),
    (_p(r"\b(obrigad[oa]|valeu|vlw|brigad[oa]|agradeco|te devo)\b"),
     {"timida": 3, "feliz": 3, "apaixonada": 1}),
    (_p(r"\b(tchau|ate mais|ate logo|flw|falou|fui)\b"),
     {"brincalhona": 3, "timida": 2, "feliz": 1}),
    (_p(r"\b(boa noite|vou dormir|vou deitar|to com sono|estou com sono|sono)\b"),
     {"sonolenta": 3, "espreguicando": 1}),
    (_p(r"\b(oi+|ola|opa|e ai|eai|bom dia|boa tarde|salve|hey|hello|fala ai)\b"),
     {"feliz": 4, "brincalhona": 2, "timida": 1}),
    (_p(r"\b(k{3,}|kk+|haha+|rsrs+|hehe|piada|engracad[oa])\b"),
     {"brincalhona": 4, "feliz": 2}),
    (_p(r"\b(triste|chorei|chorando|deprimid[oa]|sozinh[oa]|ansios[oa]|mal hoje|dia ruim|cansad[oa] de tudo|saudade)\b"),
     {"carente": 3, "choramingando": 2, "timida": 1}),
    (_p(r"\b(consegui|passei|deu certo|ganhei|fui aprovad[oa]|terminei|acabei)\b"),
     {"vitoria": 3, "feliz": 2, "apaixonada": 1}),
]
# frases do vocabulario.py do projeto (elogios e ofensas que já faziam os traços mudarem)
_BOM = [_norm(w) for w in vc.goodWords]
_RUIM = [_norm(w) for w in vc.badWords]
COMANDO = _p(r"^(abre|abrir|pesquisa|pesquisar|toca|tocar|pausa|pausar|anota|anotar|lembra|me lembra|me avisa|agenda|"
             r"agendar|mostra|mostrar|tira|tirar|registra|registrar|pula|pular|volta|voltar|aumenta|diminui|muta|"
             r"liga|desliga|procura|busca|cancela|coloca|poe)\b")
PERGUNTA = _p(r"(\?\s*$|^(como|por que|porque|quando|onde|quem|qual|quais|o que|que horas|quanto|sera que|voce sabe|"
              r"vai chover|tem como)\b)")

# Emoção de UMA FRASE da Alice (primeira que casar)
FRASE = [
    ("brincalhona", _p(r"\b(k{3,}|kk+|haha+|rsrs+|hehe|zoeira|brincadeira|pegadinha|brinca\w*)\b")),
    ("irritada", _p(r"\b(chega|que saco|nao aguento|para com isso|insuportavel|irritante|cansei|odeio|ridicul\w*|"
                    r"idiota|burr[ao]|ai que raiva)\b")),
    ("choramingando", _p(r"\b(sinto muito|que triste|ah nao|buaa+|snif|chorand\w*|chorar|saudade|abandon\w*)\b")),
    ("apaixonada", _p(r"\b(amo|adoro|fofo|fofa|querid[oa]|lind[oa]|coracao|carinho|meu bem|amor)\b")),
    ("timida", _p(r"\b(desculpa|foi mal|perdao|vergonha|ai que|sem graca|obrigad[oa])\b")),
    ("sonolenta", _p(r"\b(sono|sonolent\w*|bocej\w*|cansad[oa]|zzz|dormir|soneca)\b")),
    ("vitoria", _p(r"\b(consegui|conseguimos|pronto|prontinho|feito|deu certo|ganhamos|ganhei|parabens|uhul|"
                   r"arrasou|mandou bem)\b")),
    ("ideia", _p(r"\b(ideia|que tal|ja sei|olha so|dica|sugiro|experimenta|descobri|lembrei)\b")),
    ("confusa", _p(r"\b(nao entendi|como assim|hein|confus[oa]|nao sei|sei la|que\?|hã)\b")),
    ("entediada", _p(r"\b(tanto faz|que tedio|entediad[oa]|chato|ai ai|enfim|blz)\b")),
    ("desconfiada", _p(r"\b(duvido|serio\?|hmm+|sera que|suspeito|estranho|mentira|ta bom ne|conta outra)\b")),
    ("feliz", _p(r"\b(oba|legal|otimo|maravilh\w*|adorei|show|bora|com certeza|feliz|animad[oa]|bom dia)\b")),
]


def normalizar_nome(nome):
    """'Animada', 'feliz', 'excited'... -> nome do catálogo (ou None)."""
    n = (nome or "").strip().lower()
    n = ALIAS.get(n, ALIAS.get(_norm(n), _norm(n)))
    return n if n in EMOCOES else None


def catalogo():
    """O que as interfaces precisam para desenhar (sem os tempos internos)."""
    return {k: {c: v[c] for c in ("rotulo", "sprite", "mov", "part", "cor")} for k, v in EMOCOES.items()}


# --------------------------------------------------------------------------- motor
class Emocoes:
    def __init__(self, personalidade=None, agora=time.time, rng=None, ritmo=1.0):
        """
        personalidade: objeto com .traits (dict) e .state (opcional).
        agora: função que devolve segundos (injetável nos testes).
        ritmo: multiplica o tempo de cada expressão quando ela está parada.
               1 = normal, 2 = mais calma, 0.6 = mais agitada, 0 = parada (só reage).
        """
        self.p = personalidade
        self.agora = agora
        self.rng = rng or random.Random()
        self.ritmo = float(ritmo)
        self._lock = threading.RLock()
        self._eventos = deque(maxlen=300)
        self._id = 0

        t = self.agora()
        self.atual = "neutra"
        self.desde = t
        self.ate = t + self.rng.uniform(*EMOCOES["neutra"]["hold"])
        self.ultima_interacao = t
        self.ultimo_bocejo = t - 10_000
        self.ocupado_ate = 0.0        # enquanto ela fala, não troca sozinha
        self.bloqueio_ate = 0.0       # acordando: espera o espreguiçar terminar
        self.fila = []                # [(emoção, duração|None, fonte)] aplicadas quando ficar livre
        self.recentes = deque(maxlen=3)
        self.toques = []
        self._frases = 0              # frases da resposta atual (para variar emoções longas)
        self._thread = None

    # ---------------------------------------------------------------- barramento
    def _emitir(self, ev):
        with self._lock:
            self._id += 1
            ev = {"id": self._id, "t": round(self.agora(), 2), **ev}
            self._eventos.append(ev)
            return ev

    def eventos(self, desde=0):
        """(lista de eventos com id > desde, id do último evento)."""
        with self._lock:
            return [e for e in self._eventos if e["id"] > desde], self._id

    def estado(self):
        with self._lock:
            c = EMOCOES[self.atual]
            return {"nome": self.atual, "rotulo": c["rotulo"], "sprite": c["sprite"], "mov": c["mov"],
                    "part": list(c["part"]), "cor": c["cor"],
                    "restante": max(0.0, round(self.ate - self.agora(), 1)), "ritmo": self.ritmo}

    def humor_para_prompt(self):
        return f"{EMOCOES[self.atual]['rotulo']} ({HUMOR_PROMPT[self.atual]})"

    # ---------------------------------------------------------------- núcleo
    def definir(self, nome, dur=None, fonte="auto", forcar=False, respeitar_bloqueio=True, bloquear=False):
        """Troca a emoção e avisa os clientes. `forcar` publica mesmo se for a mesma (reanima)."""
        nome = normalizar_nome(nome)
        if not nome:
            return False
        with self._lock:
            agora = self.agora()
            if respeitar_bloqueio and agora < self.bloqueio_ate:
                self.fila.append((nome, dur, fonte))
                return False
            if dur is None:
                dur = self._duracao(nome)
            mudou = nome != self.atual
            self.atual, self.desde, self.ate = nome, agora, agora + dur
            if bloquear:  # a próxima da fila só entra depois desta terminar (ex.: o bocejo inteiro)
                self.bloqueio_ate = self.ate
            self.recentes.append(nome)
            if mudou or forcar:
                self._emitir({"tipo": "emocao", "nome": nome, "dur": round(dur, 1), "fonte": fonte})
            return True

    def _duracao(self, nome):
        lo, hi = EMOCOES[nome]["hold"]
        if nome == "dormindo":
            return lo
        escala = self.ritmo if self.ritmo > 0 else 1.0
        return self.rng.uniform(lo, hi) * escala

    def interagir(self):
        """Marca que o usuário apareceu. Devolve True se ela estava dormindo/ausente e vai acordar."""
        with self._lock:
            agora = self.agora()
            ocioso = agora - self.ultima_interacao
            ontem = datetime.fromtimestamp(self.ultima_interacao).date() != datetime.fromtimestamp(agora).date()
            acordando = self.atual == "dormindo" or (ontem and ocioso > 4 * 3600) or ocioso > 6 * 3600
            self.ultima_interacao = agora
            if acordando:
                self.definir("espreguicando", 3.5, "acordou", forcar=True, respeitar_bloqueio=False)
                self.bloqueio_ate = agora + 2.8
                self.ultimo_bocejo = agora
            return acordando

    # ---------------------------------------------------------------- reações a eventos
    def on_usuario(self, texto):
        """Chame ao receber a mensagem do usuário (antes de o modelo responder)."""
        with self._lock:
            self._frases = 0
            acordou = self.interagir()
            emo = self._reacao_usuario(texto)
            if acordou:
                self.fila.append((emo, None, "usuario"))
            else:
                self.definir(emo, self.rng.uniform(5, 9), "usuario", forcar=True)
            return emo

    def _reacao_usuario(self, texto):
        t = _norm(texto).strip()
        if any(w in t for w in _RUIM):
            return self._sortear(self._ajustar_reacao({"irritada": 4, "desconfiada": 1, "choramingando": 1}))
        if any(w in t for w in _BOM):
            return self._sortear(self._ajustar_reacao({"timida": 3, "apaixonada": 3, "feliz": 2}))
        for padrao, pesos in USUARIO:
            if padrao.search(t):
                return self._sortear(self._ajustar_reacao(pesos))
        if COMANDO.search(t):
            return self._sortear({"ideia": 3, "feliz": 2, "neutra": 1})
        if PERGUNTA.search(t):
            return self._sortear({"ideia": 3, "confusa": 1, "neutra": 2, "desconfiada": 1})
        return self._sortear(self._pesos_base(excluir={"espreguicando", "sonolenta", "choramingando"}))

    def _ajustar_reacao(self, pesos):
        """Os traços inclinam a reação: com pouca paciência o 'oi' vem seco, com muito carinho vem derretido."""
        t = self._traits()
        w = dict(pesos)
        if t["paciencia"] <= 2 and "irritada" not in w:
            w["desconfiada"] = w.get("desconfiada", 0) + 1.5
        if t["carinho"] >= 8 and "apaixonada" in w:
            w["apaixonada"] *= 1.8
        if t["sarcasmo"] >= 7 and "feliz" in w:
            w["brincalhona"] = w.get("brincalhona", 0) + 1.5
        return w

    def escolher_frase(self, texto, tag=None):
        """Emoção de uma frase da resposta: tag do modelo > palavras da frase > deriva da atual."""
        with self._lock:
            self._frases += 1
            emo = normalizar_nome(tag) if tag else None
            if emo in (None, "dormindo", "ouvindo"):
                emo = self._emocao_da_frase(texto)
            if emo is None:
                emo = self._deriva()
            return emo

    def _emocao_da_frase(self, texto):
        t = _norm(texto)
        for nome, padrao in FRASE:
            if padrao.search(t):
                return nome
        fim = t.strip()
        if fim.endswith("!") and self.rng.random() < 0.6:
            return "feliz"
        if (fim.endswith("...") or fim.endswith("…")) and self.rng.random() < 0.6:
            return "entediada"
        if fim.endswith("?") and self.rng.random() < 0.5:
            return "ideia"
        return None

    def _deriva(self):
        """Sem pista na frase: fica na atual, mas respostas compridas ganham uma variação sutil."""
        base = self.atual if self.atual not in ("dormindo", "espreguicando", "ouvindo") else self._baseline()
        if self._frases >= 2 and self.rng.random() < 0.45:
            viz = {k: v for k, v in VIZINHAS.get(base, {}).items() if k != base and k not in ("sonolenta", "espreguicando")}
            if viz:
                return self._sortear(viz)
        return base

    def emitir_fala(self, texto, emocao):
        """Chame quando a frase COMEÇA a ser falada (ou quando chega, se não há voz)."""
        with self._lock:
            agora = self.agora()
            dur = min(14.0, max(1.8, len(texto) / 14.0 + 1.2))
            self.ocupado_ate = max(self.ocupado_ate, agora) + dur
            self.atual, self.desde = emocao, agora
            self.ate = self.ocupado_ate + self.rng.uniform(4, 8)
            self.recentes.append(emocao)
            self._emitir({"tipo": "fala", "texto": texto, "emocao": emocao, "dur": round(dur, 1)})

    def on_fim_resposta(self):
        with self._lock:
            self.ate = max(self.ate, self.ocupado_ate + self.rng.uniform(5, 9))

    def on_acao(self, ok):
        with self._lock:
            if not ok:
                self.fila.append(("confusa", 5, "acao"))
            elif self.rng.random() < 0.35:
                self.fila.append(("vitoria", 5, "acao"))

    def on_aviso(self, texto):
        """Um lembrete disparou: ela acorda (se precisar), tem uma 'ideia' e mostra o aviso."""
        with self._lock:
            acordou = self.interagir()
            if acordou:
                self.fila.append(("ideia", 8, "aviso"))
            else:
                self.definir("ideia", 8, "aviso", forcar=True)
            self._emitir({"tipo": "aviso", "texto": texto})

    def on_toque(self):
        """Clique/cutucão no pet. Quanto mais ela é cutucada em seguida, mais se irrita."""
        with self._lock:
            agora = self.agora()
            self.toques = [t for t in self.toques if agora - t < 6] + [agora]
            n = len(self.toques)
            t = self._traits()
            if self.interagir():
                self.fila.append((self._sortear({"confusa": 2, "timida": 2, "feliz": 1}), None, "toque"))
                return
            if n >= 4 or (n == 3 and t["paciencia"] <= 2):
                pesos = {"irritada": 4, "desconfiada": 1, "choramingando": 1}
            elif n == 3:
                pesos = {"timida": 2, "desconfiada": 3, "irritada": 1}
            elif n == 2:
                pesos = {"confusa": 3, "timida": 2, "feliz": 1}
            else:
                pesos = {"feliz": 3, "brincalhona": 2, "timida": 2}
                if t["carinho"] >= 8:
                    pesos["apaixonada"] = 3
            self.definir(self._sortear(pesos), self.rng.uniform(4, 7), "toque", forcar=True)

    def ouvindo(self, ativo, entendeu=True):
        """Microfone aberto (ativo=True) ou fechado. Aberto, ela fica atenta e não troca sozinha;
        ao fechar sem ter entendido nada, fica confusa por um instante."""
        with self._lock:
            agora = self.agora()
            if ativo:
                self.ultima_interacao = agora
                self.fila.clear()  # reações antigas já não fazem sentido
                self.bloqueio_ate = 0.0
                self.definir("ouvindo", 90, "ouvindo", forcar=True, respeitar_bloqueio=False)
                self.ocupado_ate = agora + 90
            elif self.atual == "ouvindo":
                self.ocupado_ate = 0.0
                self.ate = agora + 1.0
                if not entendeu:
                    self.fila.append(("confusa", 4, "ouvindo"))

    def dormir(self):
        with self._lock:
            self.definir("dormindo", fonte="manual", respeitar_bloqueio=False, forcar=True)

    def acordar(self):
        with self._lock:
            self.ultima_interacao = self.agora()
            self.definir("espreguicando", 3.5, "manual", forcar=True, respeitar_bloqueio=False, bloquear=True)
            self.fila.append(("neutra", None, "manual"))

    # ---------------------------------------------------------------- vida própria
    def tick(self):
        """Chame ~2x por segundo. Retorna True se trocou de emoção por conta própria."""
        with self._lock:
            agora = self.agora()
            if agora < self.ocupado_ate:
                return False
            if self.fila and agora >= self.bloqueio_ate:
                nome, dur, fonte = self.fila.pop(0)
                self.definir(nome, dur, fonte, forcar=True, respeitar_bloqueio=False)
                return True
            if agora >= self.ate and agora >= self.bloqueio_ate:
                return self._proxima(agora)
            return False

    def _proxima(self, agora):
        if self.atual == "dormindo":
            self.ate = agora + 60  # continua dormindo até alguém aparecer
            return False
        ocioso = agora - self.ultima_interacao
        f = FATOR_NOITE if self._de_noite() else 1.0
        if self.ritmo == 0:  # modo foco: não faz nada sozinha
            self.ate = agora + 30
            return False
        if ocioso >= T_DORME * f and self.atual in ("sonolenta", "espreguicando", "entediada"):
            return self.definir("dormindo", fonte="ocioso")
        if ocioso >= T_BOCEJO * f and agora - self.ultimo_bocejo > 600 and self.atual != "espreguicando":
            self.ultimo_bocejo = agora
            self.fila.append(("sonolenta", None, "ocioso"))
            return self.definir("espreguicando", fonte="ocioso", bloquear=True)
        if ocioso >= T_SONO * f and self.atual not in ("sonolenta", "espreguicando"):
            return self.definir("sonolenta", fonte="ocioso")
        alvo = self._sortear(self._pesos_idle(ocioso, f))
        if alvo == self.atual:  # fica mais um tempo igual, sem evento
            self.ate = agora + self._duracao(alvo)
            return False
        return self.definir(alvo, fonte="ocioso")

    # ---------------------------------------------------------------- pesos
    def _traits(self):
        t = {"carinho": 5, "energia": 5, "sarcasmo": 5, "paciencia": 5}
        if self.p is not None:
            t.update(getattr(self.p, "traits", {}) or {})
        return t

    def _baseline(self):
        estado = getattr(self.p, "state", "neutral") if self.p is not None else "neutral"
        return BASE_DO_ESTADO.get(estado, "neutra")

    def _de_noite(self):
        h = datetime.fromtimestamp(self.agora()).hour
        return h >= 23 or h < 6

    def _mult(self):
        """Multiplicadores por emoção vindos dos traços e do humor geral."""
        t, m = self._traits(), {}

        def mul(nomes, f):
            for n in nomes:
                m[n] = m.get(n, 1.0) * f

        if t["energia"] >= 7:
            mul(("feliz", "brincalhona", "vitoria", "ideia"), 1.8)
            mul(("sonolenta", "entediada"), 0.4)
        elif t["energia"] <= 3:
            mul(("sonolenta", "entediada"), 1.8)
            mul(("feliz", "brincalhona", "vitoria"), 0.5)
        if t["carinho"] >= 8:
            mul(("apaixonada", "timida", "carente"), 2.2)
            mul(("desconfiada",), 0.6)
        elif t["carinho"] <= 3:
            mul(("apaixonada", "carente"), 0.3)
            mul(("desconfiada", "entediada"), 1.6)
        if t["sarcasmo"] >= 7:
            mul(("desconfiada", "brincalhona"), 1.8)
        if t["paciencia"] <= 2:  # o padrão é 3: só abaixo disso ela fica estourada
            mul(("irritada",), 4.0)
            mul(("desconfiada",), 1.3)
        elif t["paciencia"] >= 7:
            mul(("irritada",), 0.3)
        estado = getattr(self.p, "state", "neutral") if self.p is not None else "neutral"
        if estado == "excited":
            mul(("feliz", "vitoria", "brincalhona"), 1.6)
        elif estado == "irritated":
            mul(("irritada",), 5.0)
            mul(("desconfiada",), 1.5)
        elif estado == "needy":
            mul(("carente", "choramingando", "timida"), 3.0)
        return m

    def _pesos_base(self, excluir=()):
        m = self._mult()
        return {k: v * m.get(k, 1.0) for k, v in BASE.items() if k not in excluir}

    def _pesos_idle(self, ocioso, f):
        m = self._mult()
        base = BASE
        viz = VIZINHAS.get(self.atual, {})
        w = {}
        for k in BASE:
            if k in NAO_SORTEIA:
                continue
            w[k] = (viz.get(k, 0) + 0.25 * base[k]) * m.get(k, 1.0)
        if ocioso >= T_TEDIO * f:  # sem ninguém por perto: tédio e dúvida
            for k, x in (("entediada", 2.5), ("confusa", 1.8), ("desconfiada", 1.5), ("sonolenta", 1.6),
                         ("feliz", 0.5), ("brincalhona", 0.6), ("vitoria", 0.2)):
                w[k] *= x
        t, estado = self._traits(), (getattr(self.p, "state", "neutral") if self.p is not None else "neutral")
        if t["paciencia"] > 2 and estado != "irritated":
            w["irritada"] *= 0.3  # sem motivo, quase nunca estoura sozinha
        if estado != "needy":
            w["choramingando"] *= 0.4
        if ocioso < 45 and self.atual not in ("sonolenta", "entediada"):
            w["espreguicando"] = 0  # só se espreguiça quem já está parada há um tempo
        if ocioso < 120:
            w["sonolenta"] *= 0.25
        if self._de_noite():
            w["sonolenta"] *= 2.0
        for r in self.recentes:  # evita repetir as últimas
            if r in w:
                w[r] *= 0.2
        return {k: v for k, v in w.items() if v > 0}

    def _sortear(self, pesos):
        itens = [(k, v) for k, v in pesos.items() if v > 0]
        if not itens:
            return "neutra"
        total = sum(v for _, v in itens)
        x = self.rng.random() * total
        for k, v in itens:
            x -= v
            if x <= 0:
                return k
        return itens[-1][0]

    # ---------------------------------------------------------------- thread
    def iniciar(self, passo=0.5):
        """Liga a vida própria em segundo plano."""
        if self._thread:
            return

        def loop():
            while True:
                time.sleep(passo)
                try:
                    self.tick()
                except Exception as e:  # nunca derruba o servidor
                    print("Erro no motor de emoções:", e)

        self._thread = threading.Thread(target=loop, daemon=True)
        self._thread.start()
