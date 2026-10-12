"""
Ações que a Alice pode executar no PC.

É uma lista fechada: o LLM só consegue chamar o que está em `self.registro`.
Para criar uma ação nova: escreva um método e registre-o no __init__.
O prompt da Alice é montado a partir deste registro, então não precisa editar mais nada.
"""
import os
import shutil
import subprocess
import threading
import unicodedata
import webbrowser
from datetime import datetime
from urllib.parse import quote_plus

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
    "proxima_musica": ["proxima", "pula", "pular", "avanca", "trocar a", "troca a", "passa a", "passar a", "next"],
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
    def __init__(self, notificar=None):
        # notificar(texto): chamado quando um lembrete dispara
        self.notificar = notificar or print
        # nome -> (descrição para o prompt, função, rótulo do argumento ou None)
        self.registro = {
            "abrir_navegador": ("abre o navegador", self.abrir_navegador, None),
            "abrir_youtube": ("abre o YouTube", self.abrir_youtube, None),
            "pesquisar_google": ("pesquisa algo no Google", self.pesquisar_google, "termo"),
            "tocar_musica": ("procura uma música ou vídeo no YouTube", self.tocar_musica, "nome"),
            "abrir_programa": ("abre um programa: " + ", ".join(PROGRAMAS), self.abrir_programa, "programa"),
            "abrir_projeto": ("abre a pasta do projeto da Alice", self.abrir_projeto, None),
            "pausar_midia": ("pausa ou retoma a música/vídeo", lambda: self._midia("playpause", "Pausei/retomei a mídia."), None),
            "proxima_musica": ("pula para a próxima música", lambda: self._midia("nexttrack", "Próxima faixa."), None),
            "volume_mais": ("aumenta o volume", lambda: self._volume("volumeup", "Volume aumentado."), None),
            "volume_menos": ("diminui o volume", lambda: self._volume("volumedown", "Volume diminuído."), None),
            "mutar": ("muta ou desmuta o som", lambda: self._volume("volumemute", "Alternei o mudo.", 1), None),
            "tirar_print": ("tira um print da tela", self.tirar_print, None),
            "anotar": ("salva uma anotação no bloco de notas da Alice", self.anotar, "texto"),
            "lembrete": ("avisa depois de alguns minutos", self.lembrete, "minutos|texto"),
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
        texto = texto.strip() or "hora do lembrete"
        timer = threading.Timer(minutos * 60, self.notificar, args=[f"Lembrete: {texto}"])
        timer.daemon = True
        timer.start()
        return f"Lembrete criado para daqui a {minutos:g} min: {texto}"