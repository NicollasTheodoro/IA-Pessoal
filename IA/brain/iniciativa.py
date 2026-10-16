"""
Iniciativa da Alice: ela puxa assunto sozinha, em vez de só responder.

O que ela faz (tudo com falas prontas no jeito dela, então é instantâneo e não disputa o Ollama):

  1. OI AO LIGAR     ao abrir o pet ela cumprimenta pela hora do dia, lembra da agenda de hoje ou da
                     chuva, e dispara o aquecimento do modelo (a 1ª conversa já sai rápida).
  2. SILÊNCIO        sem você falar com ela: ~7 min "tá fazendo algo importante?", ~25 min uma segunda
                     cutucada, ~60 min "bebe água, levanta". Só se você estiver no PC (veja presenca.py)
                     e cada pergunta espera mais que a anterior (não vira spam).
  3. EXPRESSÃO       quando ela muda de cara sozinha, às vezes comenta: espreguiçando -> "Nossa, que
                     cansaço", entediada -> "Que tédio...", sonolenta, carente, ideia...
  4. VOLTOU          você ficou longe do PC (15+ min) e voltou: "Voltou! Já tava com saudade."
  5. EXTRAS          "já almoçou?" / "já jantou?" (uma vez por dia, e ela anota o que você comeu),
                     "já passou da meia-noite, vai dormir" e reação aos cutucões no pet.

Regras para não ser chata: nível (0 desligada, 1 calma, 2 normal, 3 faladeira), intervalo mínimo
entre falas, nunca interrompe conversa, microfone aberto ou ela mesma falando, e fica quieta no
ritmo "Parada" (modo foco).

Tudo é Python puro: relógio, sorteio, presença e a saída da fala são injetáveis (por isso tem teste).
"""
import json
import os
import random
import threading
import time
from collections import deque
from datetime import datetime

from . import presenca as _presenca

NIVEIS = {0: "Desligada", 1: "Calma", 2: "Normal", 3: "Faladeira"}
FATOR = {1: 2.0, 2: 1.0, 3: 0.5}        # multiplica as esperas: menor = mais falante
PROB_NIVEL = {1: 0.6, 2: 1.0, 3: 1.4}   # multiplica a chance das falas de expressão

T_CHECKIN = (420, 1500, 3600)  # segundos de silêncio para a 1ª, 2ª e 3ª pergunta
GAP_GERAL = 60                 # mínimo entre duas falas de iniciativa
GAP_EXPRESSAO = 90             # mínimo entre dois comentários de expressão
PRESENTE_ATE = 180             # sem mexer no PC há menos disso = você está aí
AUSENTE_DE = 600               # sem mexer há 10+ min = você saiu
VOLTA_MIN = 900                # voltou depois de 15+ min: ela comenta
VOLTA_LONGA = 7200             # 2 h+: reação mais dramática
REINICIO_RAPIDO = 20 * 60      # ligou de novo em menos disso: "voltei, só reiniciei"
IDADE_MAX_EVENTO = 4.0         # só comenta a expressão se ela acabou de mudar
GAP_TOQUE = 6.0

# ============================================================================ falas
# Uma fala é (texto, emoção). Gênero neutro com você: ela nunca diz "sumido", "ocupado"...
SAUDACAO = {
    "manha": [("Bom dia! Dormiu bem?", "feliz"),
              ("Bom diaaa! Já tomou café ou vai me ignorar até o meio-dia?", "brincalhona"),
              ("Oi! Bom dia. Café primeiro, depois a gente conversa.", "feliz")],
    "tarde": [("Oi! Boa tarde.", "feliz"),
              ("Boa tarde! Como tá o dia?", "feliz"),
              ("Opa, boa tarde! Apareceu, hein.", "brincalhona")],
    "noite": [("Oi! Boa noite.", "feliz"),
              ("Boa noite! Como foi o dia?", "feliz"),
              ("Opa, boa noite. Veio me ver agora, é?", "brincalhona")],
    "madrugada": [("Nossa, ainda de pé a essa hora? Tá tudo bem?", "desconfiada"),
                  ("Oi... madrugada, é? Não vai dormir não?", "confusa")],
}
CONVITE = [("No que a gente trabalha hoje?", "ideia"), ("O que vai ser hoje?", "ideia"),
           ("Em que posso te atrapalhar hoje?", "brincalhona"), ("Bora fazer alguma coisa?", "feliz"),
           ("Me conta, qual é o plano?", "ideia")]
REINICIO = [("Voltei! Tava só dando um reset.", "brincalhona"),
            ("Pronto, reiniciei. Tava com saudade?", "brincalhona")]
SUMIU_DIAS = [("Olha quem apareceu! Faz {dias} dias que você não me liga.", "carente"),
              ("Nossa, {dias} dias sem falar comigo! Quase achei que tinha me trocado.", "choramingando")]

CHECKIN = [
    [  # 1ª pergunta
        [("Ei... sumiu.", "desconfiada"), ("Tá fazendo alguma coisa importante?", "confusa")],
        [("Oi? Tá muito silencioso por aí.", "confusa"), ("Tá fazendo algo importante?", "ideia")],
        [("Faz um tempinho que você não fala comigo.", "carente"),
         ("Tá no meio de alguma coisa importante?", "confusa")],
    ],
    [  # 2ª pergunta
        [("Continua em silêncio por aí...", "entediada"), ("Eu tô aqui se precisar de mim, viu?", "carente")],
        [("Ainda tá naquela coisa importante?", "desconfiada"),
         ("Se quiser uma pausa, é só falar comigo.", "feliz")],
        [("Psiu. Tá aí?", "brincalhona"), ("Se precisar de ajuda, me chama.", "feliz")],
    ],
    [  # 3ª pergunta (lembrete de saúde)
        [("Faz muito tempo que a gente não conversa.", "choramingando"),
         ("Bebe uma água e levanta dessa cadeira um pouquinho, vai.", "ideia")],
        [("Ei, faz tempão que você tá aí.", "desconfiada"),
         ("Estica as pernas, bebe água. Depois me conta o que tava fazendo.", "ideia")],
    ],
]
ACORDEI = [("Hmm... acordei sozinha.", "espreguicando")]

VOLTOU = {
    "curta": [[("Voltou! Já tava com saudade.", "apaixonada")],
              [("Ah, apareceu! Fiquei aqui sozinha.", "carente"), ("Mas tudo bem, eu me virei.", "brincalhona")],
              [("Olha quem voltou!", "feliz"), ("Demorou, hein.", "brincalhona")]],
    "longa": [[("Nossa, que demora! Achei que tinha me abandonado.", "choramingando"),
               ("Brincadeira... mais ou menos.", "brincalhona")],
              [("Voltou! Eu quase dormi de tanto esperar.", "espreguicando"),
               ("Me conta, onde você tava?", "ideia")]],
}
REFEICAO = {
    "almoco": [[("Ei, já almoçou?", "ideia"), ("Se já comeu, me conta o que foi que eu anoto.", "feliz")],
               [("Hora do almoço! Não vai me dizer que esqueceu de comer.", "desconfiada"),
                ("Quando comer, me conta que eu anoto pra você.", "feliz")]],
    "jantar": [[("Já jantou?", "ideia"), ("Me conta o que comeu que eu anoto.", "feliz")],
               [("Barriga roncando? Já é hora do jantar.", "brincalhona"),
                ("Depois me diz o que foi, que eu anoto.", "feliz")]],
}
MADRUGADA = [[("Já passou da meia-noite, hein.", "desconfiada"),
              ("Não vai dormir não? Amanhã você paga o preço.", "carente")],
             [("Ei, olha a hora! Tá tarde demais.", "confusa"),
              ("Vai dormir, vai. Eu fico aqui, prometo.", "carente")]]

# o que ela comenta quando muda de cara sozinha (emoção -> frases) e a chance de comentar
EXPRESSAO = {
    "espreguicando": ["Nossa, que cansaço.", "Aaah... preciso me esticar um pouco.", "Que preguiça, meu Deus.",
                      "Nossa, tô até estalando de tanto ficar parada."],
    "sonolenta": ["Hmm... tô com sono.", "Meus olhos estão pesando...",
                  "Se ninguém falar comigo eu vou apagar, hein."],
    "entediada": ["Que tédio...", "Alguém me dá o que fazer?",
                  "Já contei os ícones da sua tela duas vezes.", "Ai, ai... nada acontece por aqui."],
    "confusa": ["Hã? Pensei em alguma coisa e esqueci.", "Ué... o que eu ia falar mesmo?",
                "Tem alguma coisa estranha acontecendo aqui..."],
    "desconfiada": ["Hmm... tô de olho em você.", "Tá quieto demais por aqui. Desconfio.",
                    "Eu sei que tem coisa aí."],
    "feliz": ["Hoje tá um dia bom, hein!", "Tô de bom humor, nem sei por quê.", "Ai, que energia boa!"],
    "brincalhona": ["Hihi, pensei numa coisa engraçada.", "Se eu te contar o que pensei, você ri.",
                    "Tô com vontade de aprontar."],
    "vitoria": ["Uhul!", "Arrasei... em nada, mas arrasei."],
    "apaixonada": ["Ai, que dia lindo...", "Tô num clima romântico hoje.", "Suspiro..."],
    "ideia": ["Ah! Tive uma ideia!", "Ei, e se a gente fizesse alguma coisa divertida?", "Lembrei de uma coisa!"],
    "irritada": ["Que saco.", "Hmpf.", "Tô de mau humor, nem vem."],
    "timida": ["Ai... do nada fiquei com vergonha.", "Tô com vergonha, não olha."],
    "choramingando": ["Snif... ninguém liga pra mim.", "Tô meio tristinha, viu?"],
    "carente": ["Me dá um pouquinho de atenção?", "Tô com saudade de conversar.", "Ei... vem cá conversar comigo?"],
    "dormindo": ["Vou tirar uma soneca... me chama depois. Zzz.", "Tô apagando... zzz."],
}
PROB_EXPRESSAO = {"espreguicando": 0.9, "sonolenta": 0.5, "entediada": 0.35, "confusa": 0.3, "desconfiada": 0.25,
                  "feliz": 0.25, "brincalhona": 0.25, "vitoria": 0.5, "apaixonada": 0.4, "ideia": 0.45,
                  "irritada": 0.35, "timida": 0.4, "choramingando": 0.5, "carente": 0.55, "dormindo": 0.7}

TOQUE = {
    1: ["Oi?", "Hm? Me chamou?", "Tô aqui."],
    2: ["Ei, que foi?", "Tá me cutucando por quê?"],
    3: ["Ei, para com isso.", "Tá me deixando sem graça..."],
    4: ["Chega! Para de me cutucar!", "Eu mordo, hein!"],
}
PROB_TOQUE = {1: 0.35, 2: 0.6, 3: 0.9, 4: 1.0}
ACORDOU_TOQUE = [("Ei... eu tava dormindo!", "espreguicando"), ("Quem me acordou?", "confusa")]


def periodo(hora):
    if 5 <= hora < 12:
        return "manha"
    if 12 <= hora < 18:
        return "tarde"
    if 18 <= hora < 24:
        return "noite"
    return "madrugada"


def _partes(opcao):
    """Uma fala ou uma lista de falas -> lista de (texto, emoção)."""
    return [opcao] if isinstance(opcao, tuple) else list(opcao)


class Iniciativa:
    def __init__(self, emo, dizer, agenda=None, clima=None, ocupado=None, historico=None, ao_abrir=None,
                 presenca=_presenca.segundos_sem_input, arquivo=None, agora=None, rng=None, nivel=2):
        """
        emo:       o motor de emoções (brain/emocoes.py); a iniciativa lê os eventos e a ociosidade dele.
        dizer:     função(texto, emoção, voz) que mostra e fala (o servidor liga na voz e no pet).
        ocupado:   função() -> True se há conversa, microfone ou voz em andamento (ela espera).
        historico: função(texto) para guardar o que ela disse no histórico (a resposta do usuário faz sentido).
        ao_abrir:  função() chamada depois do oi inicial (aquece o modelo).
        presenca:  função() -> segundos sem teclado/mouse, ou None se não sabe.
        """
        self.emo, self._dizer = emo, dizer
        self.agenda, self.clima = agenda, clima
        self._ocupado = ocupado or (lambda: False)
        self._historico, self._ao_abrir, self._presenca = historico, ao_abrir, presenca
        self.agora = agora or emo.agora
        self.rng = rng or random.Random()
        self.arquivo = arquivo
        self._lock = threading.RLock()
        self._thread = None
        self.nivel = 2
        self.voz = True
        self.configurar(nivel=nivel)

        t = self.agora()
        self._estado = self._carregar()
        self._visto_antes = self._estado.get("visto")   # quando a Alice esteve no ar pela última vez
        self._ultimo_save = 0.0
        self._recentes = {}
        _, self._desde_ev = emo.eventos(10 ** 12)       # só eventos NOVOS contam
        self._ultima_fala = self._ultima_expr = self._abriu_em = -1e9
        self._vi = emo.ultima_interacao
        self._base_silencio = t
        self._n_checkin = 0
        self._pico_ausencia = 0.0
        self._pendente_volta = 0.0
        self._toque = None
        self._ultimo_toque = -1e9

    # ---------------------------------------------------------------- configuração
    def configurar(self, nivel=None, voz=None):
        if nivel is not None:
            n = int(nivel)
            if n not in NIVEIS:
                raise ValueError("Nível de iniciativa inválido (use 0, 1, 2 ou 3).")
            self.nivel = n
        if voz is not None:
            self.voz = bool(voz)

    def estado(self):
        return {"nivel": self.nivel, "nome": NIVEIS[self.nivel], "voz": self.voz, "perguntas": self._n_checkin}

    def _fator(self):
        return FATOR.get(self.nivel, 1.0)

    # ---------------------------------------------------------------- persistência
    def _carregar(self):
        try:
            with open(self.arquivo, encoding="utf-8") as f:
                j = json.load(f)
            return j if isinstance(j, dict) else {}
        except (OSError, ValueError, TypeError):
            return {}

    def _salvar(self):
        if not self.arquivo:
            return
        try:
            os.makedirs(os.path.dirname(self.arquivo) or ".", exist_ok=True)
            tmp = self.arquivo + ".tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(self._estado, f, ensure_ascii=False)
            os.replace(tmp, self.arquivo)
        except OSError:
            pass

    def _guardar_visto(self, agora):
        if agora - self._ultimo_save >= 60:
            self._ultimo_save = agora
            manter = {datetime.fromtimestamp(agora - k * 86400).strftime("%Y-%m-%d") for k in (0, 1)}  # hoje e ontem
            self._estado["visto"] = agora
            self._estado["dias"] = {d: v for d, v in self._estado.get("dias", {}).items() if d in manter}
            self._salvar()

    def _feito_hoje(self, chave, agora, noite=False):
        d = datetime.fromtimestamp(agora)
        if noite and d.hour < 6:  # a "noite" que começou ontem
            d = datetime.fromtimestamp(agora - 86400)
        return self._estado.get("dias", {}).get(d.strftime("%Y-%m-%d"), []), d.strftime("%Y-%m-%d"), chave

    def _marcar(self, chave, agora, noite=False):
        lista, dia, _ = self._feito_hoje(chave, agora, noite)
        self._estado.setdefault("dias", {})[dia] = lista + [chave]
        self._salvar()

    # ---------------------------------------------------------------- escolha e fala
    def _escolher(self, chave, opcoes):
        """Sorteia sem repetir as últimas 2 (por categoria). Devolve lista de falas."""
        rec = self._recentes.setdefault(chave, deque(maxlen=2))
        livres = [i for i in range(len(opcoes)) if i not in rec] or list(range(len(opcoes)))
        i = self.rng.choice(livres)
        rec.append(i)
        return _partes(opcoes[i])

    def _frase(self, chave, frases):
        """Como _escolher, mas para uma lista de frases simples (texto). Devolve o texto."""
        return self._escolher(chave, [(f, "") for f in frases])[0][0]

    def _falar(self, partes, categoria, historico=False, voz=None):
        agora = self.agora()
        self._ultima_fala = agora
        if categoria == "expressao":
            self._ultima_expr = agora
        voz = self.voz if voz is None else voz
        for texto, emocao in partes:
            try:
                self._dizer(texto, emocao, voz)
            except Exception as e:  # uma falha na voz nunca derruba a vida própria dela
                print("Iniciativa: erro ao falar:", e)
        if historico and self._historico:
            try:
                self._historico(" ".join(f"<emo:{e}> {t}" for t, e in partes))
            except Exception as e:
                print("Iniciativa: erro no histórico:", e)
        return partes

    # ---------------------------------------------------------------- 1. oi ao ligar
    def abrir(self, forcar=False):
        """O oi inicial. Devolve as falas (ou None se não falou). Ignora conversa em andamento (é a 1ª fala)."""
        agora = self.agora()
        with self._lock:
            if not forcar and (self.nivel == 0 or agora - self._abriu_em < 300):
                return None
            self._abriu_em = agora
            self.emo.interagir()                 # você a ligou: ela acorda, e a escada do sono recomeça
            self._vi = self.emo.ultima_interacao
            self._base_silencio = agora
            self._n_checkin = 0
            partes = self._montar_abertura(agora)
            self._falar(partes, "abertura", historico=True)
        if self._ao_abrir:
            try:
                self._ao_abrir()
            except Exception as e:
                print("Iniciativa: aquecimento falhou:", e)
        return partes

    def _montar_abertura(self, agora):
        now = datetime.fromtimestamp(agora)
        visto = self._visto_antes
        if visto and 0 <= agora - visto < REINICIO_RAPIDO:
            return self._escolher("reinicio", REINICIO)
        partes = []
        if visto:
            dias = (now.date() - datetime.fromtimestamp(visto).date()).days
            if dias >= 2:
                f = self._escolher("sumiu", SUMIU_DIAS)
                partes += [(t.replace("{dias}", str(dias)), e) for t, e in f]
        partes += self._escolher("saud_" + periodo(now.hour), SAUDACAO[periodo(now.hour)])
        ctx = self._contexto_do_dia(now)
        if ctx and self.rng.random() < 0.85:
            partes.append(ctx)
        if len(partes) < 3 and self.rng.random() < 0.7:
            partes += self._escolher("convite", CONVITE)
        return partes

    def _contexto_do_dia(self, now):
        """Uma coisa útil sobre hoje: agenda > chuva > calor. None se não tiver nada."""
        try:
            if self.agenda:
                hoje = []
                for i in self.agenda.pendentes():
                    dt = datetime.fromisoformat(i["quando"])
                    if dt.date() == now.date() and dt >= now.replace(second=0, microsecond=0):
                        hoje.append((dt, i["texto"]))
                if len(hoje) == 1:
                    return (f"Hoje, às {hoje[0][0]:%H:%M}, você tem: {hoje[0][1]}.", "ideia")
                if hoje:
                    return (f"Hoje você tem {len(hoje)} coisas na agenda. A próxima é {hoje[0][1]}, às {hoje[0][0]:%H:%M}.", "ideia")
            d = getattr(self.clima, "dados", None) if self.clima else None
            if d:
                if (d.get("chuva") or 0) >= 60:
                    return (f"Vai chover hoje, {d['chuva']}% de chance. Leva guarda-chuva se for sair.", "ideia")
                if (d.get("max") or 0) >= 33:
                    return (f"Hoje vai fazer {d['max']} graus. Bebe bastante água.", "ideia")
        except Exception as e:
            print("Iniciativa: contexto do dia indisponível:", e)
        return None

    # ---------------------------------------------------------------- cutucão
    def on_toque(self):
        """O servidor avisa que cutucaram o pet; a reação sai no próximo tick (não atrasa a resposta do clique)."""
        with self._lock:
            self._toque = (self.agora(), len(self.emo.toques), self.emo.atual)

    def _reagir_toque(self, agora):
        t, n, emo_atual = self._toque
        self._toque = None
        if agora - t > 3 or agora - self._ultimo_toque < GAP_TOQUE:
            return False
        n = max(1, min(n, 4))
        if emo_atual == "espreguicando":  # o toque a acordou
            partes = self._escolher("toque_acordou", ACORDOU_TOQUE)
        else:
            if self.rng.random() >= PROB_TOQUE[n]:
                return False
            texto = self._frase(f"toque{n}", TOQUE[n])
            emocao = "irritada" if n >= 4 else (emo_atual if emo_atual in EXPRESSAO else "confusa")
            partes = [(texto, emocao)]
        self._ultimo_toque = agora
        self._falar(partes, "toque")
        return True

    # ---------------------------------------------------------------- vida própria
    def tick(self):
        """Chame ~2x por segundo. Devolve True se ela falou algo."""
        with self._lock:
            agora = self.agora()
            self._guardar_visto(agora)
            evs, self._desde_ev = self.emo.eventos(self._desde_ev)
            idle = self._ler_presenca()
            self._acompanhar_ausencia(agora, idle)
            if self.emo.ultima_interacao != self._vi:  # você falou/cutucou/abriu o mic: recomeça a contagem
                self._vi = self.emo.ultima_interacao
                self._n_checkin = 0
                self._pendente_volta = 0.0
            if self.nivel == 0 or self.emo.ritmo == 0 or not self._livre(agora):
                self._toque = None
                return False
            if self._toque and self._reagir_toque(agora):
                return True
            if self._pendente_volta:
                return self._falar_volta(agora)
            presente = idle is None or idle < PRESENTE_ATE
            if not presente or agora - self._ultima_fala < GAP_GERAL * self._fator():
                return False
            return (self._tentar_madrugada(agora) or self._tentar_refeicao(agora)
                    or self._tentar_checkin(agora) or self._tentar_expressao(agora, evs))

    def _ler_presenca(self):
        try:
            return self._presenca()
        except Exception:
            return None

    def _livre(self, agora):
        """Não fala por cima de conversa, microfone, voz ou dela mesma falando."""
        return not (self._ocupado() or agora < self.emo.ocupado_ate or self.emo.atual == "ouvindo")

    def _acompanhar_ausencia(self, agora, idle):
        if idle is None:
            return
        if idle >= AUSENTE_DE:
            self._pico_ausencia = max(self._pico_ausencia, idle)
        elif idle < 30 and self._pico_ausencia:
            pico, self._pico_ausencia = self._pico_ausencia, 0.0
            self._base_silencio = agora   # acabou de chegar: a contagem do silêncio recomeça
            self._n_checkin = 0
            if pico >= VOLTA_MIN:
                self._pendente_volta = pico

    def _silencio(self, agora):
        return agora - max(self.emo.ultima_interacao, self._base_silencio)

    # ---------------------------------------------------------------- 4. voltou
    def _falar_volta(self, agora):
        pico, self._pendente_volta = self._pendente_volta, 0.0
        self.emo.interagir()   # ela acorda (se dormia) e a escada do sono recomeça
        self._vi = self.emo.ultima_interacao
        partes = self._escolher("volta_longa" if pico >= VOLTA_LONGA else "volta_curta",
                                VOLTOU["longa" if pico >= VOLTA_LONGA else "curta"])
        self._falar(partes, "volta", historico=True)
        return True

    # ---------------------------------------------------------------- 2. silêncio
    def _tentar_checkin(self, agora):
        n = self._n_checkin
        if n >= len(T_CHECKIN) or self._silencio(agora) < T_CHECKIN[n] * self._fator():
            return False
        self._n_checkin += 1
        self._falar(self._montar_checkin(n), "checkin", historico=True)
        return True

    def _montar_checkin(self, n):
        partes = self._escolher(f"checkin{n}", CHECKIN[n])
        if self.emo.atual == "dormindo":
            partes = list(ACORDEI) + partes
        return partes

    # ---------------------------------------------------------------- 5. extras
    def _tentar_refeicao(self, agora):
        h = datetime.fromtimestamp(agora).hour
        refeicao = "almoco" if 12 <= h < 14 else ("jantar" if 19 <= h < 22 else None)
        if not refeicao or self._silencio(agora) < 45:
            return False
        if refeicao in self._feito_hoje(refeicao, agora)[0]:
            return False
        self._marcar(refeicao, agora)
        self._falar(self._escolher("ref_" + refeicao, REFEICAO[refeicao]), "refeicao", historico=True)
        return True

    def _tentar_madrugada(self, agora):
        d = datetime.fromtimestamp(agora)
        if not (d.hour == 0 and d.minute >= 30 or 1 <= d.hour < 5):
            return False
        if "madrugada" in self._feito_hoje("madrugada", agora, noite=True)[0]:
            return False
        self._marcar("madrugada", agora, noite=True)
        self._falar(self._escolher("madrugada", MADRUGADA), "madrugada", historico=True)
        return True

    # ---------------------------------------------------------------- 3. expressão
    def _tentar_expressao(self, agora, evs):
        """Ela acabou de mudar de cara por conta própria: às vezes comenta."""
        cand = None
        for e in evs:
            if e.get("tipo") == "emocao" and e.get("fonte") == "ocioso" and e.get("nome") in EXPRESSAO:
                cand = e
        if not cand or self.emo.atual != cand["nome"] or agora - cand["t"] > IDADE_MAX_EVENTO:
            return False
        if agora - self._ultima_expr < GAP_EXPRESSAO * self._fator():
            return False
        nome = cand["nome"]
        h = datetime.fromtimestamp(agora).hour
        noite = h >= 23 or h < 6
        p = PROB_EXPRESSAO[nome] * PROB_NIVEL.get(self.nivel, 1.0) * (0.5 if noite and nome != "dormindo" else 1.0)
        if self.rng.random() >= p:
            return False
        self._falar([(self._frase("exp_" + nome, EXPRESSAO[nome]), nome)], "expressao")
        return True

    # ---------------------------------------------------------------- teste manual
    def disparar(self, tipo, **kw):
        """Dispara uma iniciativa agora, sem esperar (para testar). Devolve as falas ou None se o tipo não existe."""
        with self._lock:
            if tipo == "abertura":
                return self.abrir(forcar=True)
            if tipo == "checkin":
                n = max(0, min(int(kw.get("n", 0)), len(CHECKIN) - 1))
                return self._falar(self._montar_checkin(n), "checkin", historico=True)
            if tipo == "volta":
                return self._falar(self._escolher("volta_t", VOLTOU["curta"] + VOLTOU["longa"]), "volta", historico=True)
            if tipo in REFEICAO:
                return self._falar(self._escolher("ref_" + tipo, REFEICAO[tipo]), "refeicao", historico=True)
            if tipo == "madrugada":
                return self._falar(self._escolher("madrugada", MADRUGADA), "madrugada", historico=True)
            if tipo == "expressao":
                nome = kw.get("emocao") or self.rng.choice(list(EXPRESSAO))
                if nome not in EXPRESSAO:
                    return None
                return self._falar([(self._frase("exp_" + nome, EXPRESSAO[nome]), nome)], "expressao")
            return None

    # ---------------------------------------------------------------- thread
    def iniciar(self, passo=0.5):
        if self._thread:
            return

        def loop():
            while True:
                time.sleep(passo)
                try:
                    self.tick()
                except Exception as e:  # nunca derruba o servidor
                    print("Erro na iniciativa:", e)

        self._thread = threading.Thread(target=loop, daemon=True)
        self._thread.start()
