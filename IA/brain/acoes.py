"""
Ações que a Alice pode executar no PC.

É uma lista fechada: o LLM só consegue chamar o que está em `self.registro`.
Para criar uma ação nova: escreva um método e registre-o no __init__.
O prompt da Alice é montado a partir deste registro, então não precisa editar mais nada.
"""
import os
import re
import shutil
import subprocess
import threading
import unicodedata
import webbrowser
from collections import deque
from datetime import datetime, timedelta
from urllib.parse import quote_plus

from brain import nutricao, tempo

PROJETO = os.getenv("ALICE_PROJETO", r"D:\Aulas\Git\AulaCursoEmVideo\clonando-projeto-site\IA-Pessoal")
PASTA_DADOS = os.getenv("ALICE_DADOS", ".")

# Programas que a Alice pode abrir pelo nome. Edite à vontade. O valor pode ser:
#   - um comando do Windows ("calc", "notepad", "code")
#   - o caminho completo de um .exe
#   - um link de protocolo ("steam://...", "discord://"), que o Windows entrega ao programa certo
# DICA: para testar uma entrada, aperte Win+R, cole o valor e dê Enter. Se não abrir ali, não abre pela Alice.
PROGRAMAS = {
    "calculadora": "calc",
    "bloco de notas": "notepad",
    "explorador": "explorer",
    "vscode": "code",
    "paint": "mspaint",
    "gerenciador de tarefas": "taskmgr",
    "steam": "steam://open/main",
    "overwatch": "steam://rungameid/2357570",  # Overwatch 2 pela Steam. Pela Battle.net use: "battlenet://Pro"
    "opera": os.path.expandvars(
        r"%LOCALAPPDATA%\Programs\Opera\launcher.exe"  # se for o Opera GX: ...\Opera GX\launcher.exe
    ),
    "discord": "discord://",
    "cliente riot": "riotclient://",
    "valorant": "valorant://launch",
}


def _norm(texto):
    """minúsculas e sem acento, para comparar 'música' com 'musica'."""
    t = unicodedata.normalize("NFD", (texto or "").lower())
    return "".join(c for c in t if unicodedata.category(c) != "Mn")


# TRAVA DE SEGURANÇA: o modelo pequeno às vezes "inventa" ações sozinho (ex.: pausar a mídia
# depois de um "oi"). Uma ação só roda se a frase do usuário tiver pelo menos um destes trechos.
# Ao criar uma ação nova, adicione aqui as palavras que a pedem (sem acento, em minúsculas).
GATILHOS = {
    "abrir_navegador": ["navegador", "browser", "chrome", "internet", "google", "edge"],
    "abrir_youtube": ["youtube", "you tube", "iutube"],
    "pesquisar_google": ["pesquis", "busca", "procur", "google"],
    "tocar_musica": ["music", "toca", "tocar", "coloca", "bota", "video", "cancao", "ouvir", "escutar"],
    "abrir_programa": ["abr", "inicia", "execut", "calculadora", "bloco de notas", "paint", "vscode",
                       "explorador", "gerenciador"],
    "abrir_projeto": ["projeto", "pasta"],
    "pausar_midia": ["paus", "pare", "parar", "retom", "continu", "resum", "play",
                     "para a musica", "para o video", "para o som"],
    "proxima_musica": ["proxima", "proximo", "pula", "pular", "avanca", "trocar a", "troca a", "troca o", "passa a",
                       "passa o", "passar a", "passar o", "next", "skip"],
    "voltar_midia": ["volta", "voltar", "anterior", "retorna", "retornar"],
    "agendar": ["agend", "marca", "marcar", "lembr", "avis", "alarme", "compromisso", "reuniao", "me chama"],
    "cancelar_agenda": ["cancel", "apag", "remov", "tira", "esquec", "desmarc"],
    "registrar": ["regist", "anot", "comi", "comer", "almoc", "jant", "cafe da manha", "lanche", "treino", "treinei",
                  "corri", "corrida", "peso", "pesei", "estud", "ganhei", "recebi", "bico", "salario", "paguei", "gastei",
                  "malhei", "caminh", "kcal", "caloria"],
    "mostrar": ["mostr", "exib", "painel", "tela", "coloc", "deixa"],
    "clima": ["clima", "tempo", "temperatura", "chuv", "chov", "calor", "frio", "previsao", "guarda-chuva"],
    "volume_mais": ["volume", "aument", "sobe", "subir", "mais alto", "mais som"],
    "volume_menos": ["volume", "diminu", "baixa", "baixar", "abaixa", "abaixar", "menos som", "mais baixo"],
    "mutar": ["mut", "silenc", "sem som"],
    "tirar_print": ["print", "captura", "screenshot", "foto da tela"],
    "anotar": ["anot", "salva", "escrev", "registr", "nota"],
    "lembrete": ["lembr", "avis", "alarme", "timer", "cronometro", "daqui a", "minuto"],
}

# Os nomes dos programas de PROGRAMAS também contam como pedido ("quero jogar valorant", "steam").
GATILHOS["abrir_programa"] += [_norm(n) for n in PROGRAMAS] + ["jog"]


def _tecla(tecla, vezes=1):
    import pyautogui  # import tardio: só carrega se for usado

    pyautogui.press(tecla, presses=vezes)


class Acoes:
    def __init__(self, notificar=None, agenda=None, dados=None, clima=None, llm=None):
        # notificar(texto): chamado quando um lembrete dispara
        self.notificar = notificar or print
        self.agenda, self.dados, self.clima, self.llm = agenda, dados, clima, llm
        self.cards = deque(maxlen=20)  # recados que a Alice deixa na tela do painel
        self._card_id = 0
        # nome -> (descrição para o prompt, função, rótulo do argumento ou None)
        self.registro = {
            "abrir_navegador": ("abre o navegador", self.abrir_navegador, None),
            "abrir_youtube": ("abre o YouTube", self.abrir_youtube, None),
            "pesquisar_google": ("pesquisa algo no Google", self.pesquisar_google, "termo"),
            "tocar_musica": ("procura uma música ou vídeo no YouTube", self.tocar_musica, "nome"),
            "abrir_programa": ("abre um programa: " + ", ".join(PROGRAMAS), self.abrir_programa, "programa"),
            "abrir_projeto": ("abre a pasta do projeto da Alice", self.abrir_projeto, None),
            "pausar_midia": ("pausa ou retoma a música/vídeo", lambda: self._midia("playpause", "Pausei/retomei a mídia."), None),
            "proxima_musica": ("pula para o próximo vídeo do YouTube ou próxima música", self.pular, None),
            "voltar_midia": ("volta para o vídeo ou música anterior", lambda: self._midia("prevtrack", "Voltei uma faixa."), None),
            "volume_mais": ("aumenta o volume", lambda: self._volume("volumeup", "Volume aumentado."), None),
            "volume_menos": ("diminui o volume", lambda: self._volume("volumedown", "Volume diminuído."), None),
            "mutar": ("muta ou desmuta o som", lambda: self._volume("volumemute", "Alternei o mudo.", 1), None),
            "tirar_print": ("tira um print da tela", self.tirar_print, None),
            "anotar": ("salva uma anotação no bloco de notas da Alice", self.anotar, "texto"),
            "lembrete": ("avisa depois de alguns minutos", self.lembrete, "minutos|texto"),
            "agendar": ("agenda um aviso para um dia e hora (escreva o 'quando' como o usuário falou: amanhã 14:30, sexta 9h, dia 20 às 18h)", self.agendar, "quando|texto"),
            "cancelar_agenda": ("cancela um agendamento pelo texto dele", self.cancelar_agenda, "trecho do texto"),
            "registrar": ("guarda um registro nas planilhas: " + self._tabelas_desc(), self.registrar, "tabela|campo=valor;campo=valor"),
            "mostrar": ("deixa um recado ou informação na tela do painel", self.mostrar, "titulo|texto"),
            "clima": ("mostra o clima de hoje na tela do painel", self.mostrar_clima, None),
        }

    # ---------- usado pelo prompt e pelo servidor ----------
    def descricoes(self):
        linhas = []
        for nome, (desc, _, rotulo) in self.registro.items():
            uso = f"{nome}|{rotulo}" if rotulo else nome
            linhas.append(f"- {uso}: {desc}")
        return "\n".join(linhas)

    def lista(self):
        return [{"nome": n, "descricao": d, "arg": r} for n, (d, _, r) in self.registro.items()]

    def permitida(self, nome, texto):
        """True se o usuário realmente pediu algo que combina com essa ação."""
        if nome not in self.registro:
            print(f"[Alice] o modelo inventou uma ação que não existe: {nome}")
            return False
        gatilhos = GATILHOS.get(nome)
        if gatilhos is None:
            print(f"[Alice] a ação '{nome}' não tem gatilhos em GATILHOS (acoes.py): ignorada por segurança.")
            return False
        t = _norm(texto)
        return any(g in t for g in gatilhos)

    def executar(self, nome, arg=None):
        nome = (nome or "").strip().lower()
        item = self.registro.get(nome)
        if not item:
            return f"Ação desconhecida: {nome}"
        _, fn, rotulo = item
        if rotulo and not (arg or "").strip():
            return f"A ação {nome} precisa de: {rotulo}"
        try:
            return fn(arg.strip()) if rotulo else fn()
        except Exception as e:
            return f"Falhou {nome}: {e}"

    # ---------- ações ----------
    # ---------- agenda, planilhas, painel ----------
    def _tabelas_desc(self):
        if not self.dados:
            return ""
        from brain.dados import TABELAS
        return "; ".join(f"{n} ({', '.join(c['nome'] for c in t['colunas'] if c['nome'] != 'data')})" for n, t in TABELAS.items())

    def agendar(self, arg):
        quando, _, texto = arg.partition("|")
        item, erro = self.agenda.adicionar_frase(quando, texto)
        if erro:
            return erro
        return f"Agendado para {tempo.bonito(datetime.fromisoformat(item['quando']))}: {item['texto']}"

    def cancelar_agenda(self, trecho):
        n = self.agenda.cancelar_por_texto(trecho)
        return f"Cancelei {n} agendamento(s)." if n else f"Não achei nenhum agendamento com '{trecho}'."

    def registrar(self, arg):
        tabela, _, resto = arg.partition("|")
        campos = {}
        for par in resto.split(";"):
            k, _, v = par.partition("=")
            if k.strip() and v.strip():
                campos[k.strip()] = v.strip()
        return self.registrar_campos(tabela, campos)

    def registrar_campos(self, tabela, campos):
        """Usado pela Alice (tag) e pelo formulário da interface. Para comida, calcula os macros."""
        campos = {k: v for k, v in campos.items() if str(v).strip() != ""}
        nome, t = self.dados._tabela(tabela)
        if nome == "alimentacao":
            campos = {nutricao._norm(k).replace(" ", "_"): v for k, v in campos.items()}
            for velho, novo in (("caloria", "kcal"), ("calorias", "kcal"), ("proteina", "proteina_g"),
                                ("carboidrato", "carbo_g"), ("carbo", "carbo_g"), ("gordura", "gordura_g")):
                if velho in campos:
                    campos.setdefault(novo, campos.pop(velho))
            alimento = campos.get("alimento")
            if not alimento:
                return "Qual alimento você comeu?"
            kcal = None
            if campos.get("kcal"):
                m = re.search(r"\d+(?:[.,]\d+)?", str(campos["kcal"]))
                kcal = float(m.group(0).replace(",", ".")) if m else None
            macros_dados = all(campos.get(k) for k in ("proteina_g", "carbo_g", "gordura_g"))
            if not (kcal and macros_dados):
                r, erro = nutricao.calcular(alimento, campos.get("quantidade", ""), campos.get("preparo", ""), kcal, self.llm)
                if erro:
                    return erro
                for k, v in r.items():
                    if v is not None and not campos.get(k):
                        campos[k] = v
        id_ = self.dados.inserir(nome, campos)
        mostra = ", ".join(f"{k}={v}" for k, v in campos.items() if k != "obs")
        return f"Registrado em {t['titulo']} (#{id_}): {mostra}"

    def cartao(self, titulo, texto):
        self._card_id += 1
        self.cards.append({"id": self._card_id, "titulo": titulo, "texto": texto, "hora": f"{datetime.now():%H:%M}"})

    def mostrar(self, arg):
        titulo, sep, texto = arg.partition("|")
        if not sep:
            titulo, texto = "Alice", titulo
        self.cartao(titulo.strip()[:40] or "Alice", texto.strip()[:300])
        return "Deixei na tela."

    def mostrar_clima(self):
        c = self.clima.dados if self.clima else None
        if not c:
            return "Ainda não consegui o clima (sem internet?)."
        self.cartao(f"{c['icone']} {c['temp']}°C em {c['cidade']}",
                    f"{c['descricao'].capitalize()}. Máx {c['max']}°C, mín {c['min']}°C, chuva {c['chuva']}%.")
        return f"{c['temp']}°C, {c['descricao']}, chance de chuva {c['chuva']}%."

    def pular(self):
        """ALICE_PULAR=tecla (padrão): tecla de mídia, funciona com o YouTube em segundo plano.
        ALICE_PULAR=youtube: atalho Shift+N, só funciona com a aba do YouTube em primeiro plano."""
        if os.getenv("ALICE_PULAR", "tecla").lower() == "youtube":
            import pyautogui

            pyautogui.hotkey("shift", "n")
            return "Pulei o vídeo."
        return self._midia("nexttrack", "Pulei para o próximo.")

    def abrir_navegador(self):
        webbrowser.open("https://www.google.com")
        return "Abri o navegador."

    def abrir_youtube(self):
        webbrowser.open("https://www.youtube.com")
        return "Abri o YouTube."

    def pesquisar_google(self, termo):
        webbrowser.open("https://www.google.com/search?q=" + quote_plus(termo))
        return f"Pesquisei no Google: {termo}"

    def tocar_musica(self, nome):
        webbrowser.open("https://www.youtube.com/results?search_query=" + quote_plus(nome))
        return f"Procurei no YouTube: {nome}"

    def _achar_programa(self, nome):
        """Aceita 'Steam', 'o discord', 'riot'... e devolve a chave de PROGRAMAS (ou None)."""
        alvo = _norm(nome).strip()
        if not alvo:
            return None
        for chave in PROGRAMAS:
            if _norm(chave) == alvo:
                return chave
        for chave in PROGRAMAS:
            c = _norm(chave)
            if c in alvo or alvo in c:
                return chave
        return None

    def abrir_programa(self, nome):
        chave = self._achar_programa(nome)
        if not chave:
            return f"Não conheço o programa '{nome}'. Disponíveis: {', '.join(PROGRAMAS)}"
        alvo = PROGRAMAS[chave]  # sempre vem da lista fechada acima
        try:
            if "://" in alvo or os.path.isfile(alvo):
                os.startfile(alvo)  # links (steam://, discord://) e caminhos de .exe
            elif shutil.which(alvo):
                subprocess.Popen(["cmd", "/c", "start", "", alvo])  # comandos como calc e notepad
            else:
                return (f"Não achei '{alvo}' no computador. Em PROGRAMAS (acoes.py), use o caminho "
                        f"completo do .exe ou um link como steam://... para abrir {chave}.")
        except OSError as e:
            return f"Não consegui abrir {chave}: {e}"
        return f"Abri {chave}."

    def abrir_projeto(self):
        if not os.path.exists(PROJETO):
            return f"Não achei a pasta do projeto: {PROJETO}"
        os.startfile(PROJETO)
        return "Abri a pasta do projeto."

    def _midia(self, tecla, msg):
        _tecla(tecla)
        return msg

    def _volume(self, tecla, msg, vezes=5):
        _tecla(tecla, vezes)
        return msg

    def tirar_print(self):
        import pyautogui

        pasta = os.path.join(PASTA_DADOS, "prints")
        os.makedirs(pasta, exist_ok=True)
        caminho = os.path.join(pasta, datetime.now().strftime("print_%Y%m%d_%H%M%S.png"))
        pyautogui.screenshot(caminho)
        return f"Print salvo em {caminho}"

    def anotar(self, texto):
        caminho = os.path.join(PASTA_DADOS, "notas.txt")
        with open(caminho, "a", encoding="utf-8") as f:
            f.write(f"[{datetime.now():%d/%m/%Y %H:%M}] {texto}\n")
        return "Anotado."

    def lembrete(self, arg):
        minutos_txt, _, texto = arg.partition("|")
        minutos = float(minutos_txt.replace(",", ".").strip())
        minutos = max(0.1, min(minutos, 720))  # entre 6 segundos e 12 horas
        item = self.agenda.adicionar(datetime.now() + timedelta(minutes=minutos), texto)
        return f"Lembrete criado para daqui a {minutos:g} min: {item['texto']}"

    def notas_recentes(self, n=8):
        """Últimas anotações (para a Alice saber o que você anotou)."""
        try:
            with open(os.path.join(PASTA_DADOS, "notas.txt"), encoding="utf-8") as f:
                return [l.strip()[:140] for l in f.readlines()[-n:] if l.strip()]
        except OSError:
            return []
