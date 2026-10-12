"""
Lê a resposta do LLM token por token e a transforma em eventos, para a Alice
começar a falar na primeira frase, sem esperar a resposta inteira.

Formato que o LLM usa (texto puro com tags opcionais):

    Abrindo, mas não some lá dentro. <acao:abrir_youtube>
    Anotado. <memoria:aniversario|3 de maio>
    Já pesquiso. <acao:pesquisar_google|receita de bolo>

Eventos gerados:
    {"type": "sentence", "text": "..."}
    {"type": "acao", "acao": "nome", "arg": "..." | None}
    {"type": "memoria", "chave": "...", "valor": "..."}
"""
import re

TAG = re.compile(r"<\s*(acao|memoria)\s*:\s*([^<>]*?)\s*>", re.IGNORECASE)
FIM_DE_FRASE = re.compile(r"(?<=[.!?…])\s+|\n+")
MIN_CHARS = 18  # frases menores se juntam à próxima (menos chamadas de voz)


class StreamParser:
    def __init__(self):
        self.buf = ""     # texto ainda não analisado (pode conter uma tag pela metade)
        self.pend = ""    # fala acumulada esperando a frase fechar
        self.carry = ""   # frase curta esperando juntar com a próxima
        self.falas = []   # tudo que já foi emitido como fala

    def feed(self, token):
        self.buf += token
        return self._processar(final=False)

    def flush(self):
        return self._processar(final=True)

    def _processar(self, final):
        eventos = []
        while self.buf:
            i = self.buf.find("<")
            if i == -1:
                self.pend += self.buf
                self.buf = ""
                break
            self.pend += self.buf[:i]
            self.buf = self.buf[i:]
            j = self.buf.find(">")
            if j == -1:
                if final:
                    self.buf = ""  # tag incompleta: descarta
                elif len(self.buf) > 160:  # não parece uma tag de verdade
                    self.pend += self.buf[0]
                    self.buf = self.buf[1:]
                    continue
                break
            tag, self.buf = self.buf[: j + 1], self.buf[j + 1:]
            ev = self._tag(tag)
            if ev:
                eventos.append(ev)
        eventos += self._frases(final)
        return eventos

    def _tag(self, tag):
        m = TAG.fullmatch(tag)
        if not m:
            return None
        tipo = m.group(1).lower()
        partes = [p.strip() for p in m.group(2).split("|")]
        if tipo == "acao" and partes[0]:
            return {"type": "acao", "acao": partes[0].lower(), "arg": "|".join(partes[1:]) or None}
        if tipo == "memoria" and len(partes) >= 2 and partes[0]:
            return {"type": "memoria", "chave": partes[0], "valor": "|".join(partes[1:])}
        return None

    def _frases(self, final):
        partes = FIM_DE_FRASE.split(self.pend)
        if final:
            frases, self.pend = partes, ""
        else:
            frases, self.pend = partes[:-1], partes[-1]
        saida = []
        for f in frases:
            texto = (self.carry + " " + f).strip()
            self.carry = ""
            if not texto:
                continue
            if len(texto) < MIN_CHARS and not final:
                self.carry = texto
                continue
            saida.append(self._fala(texto))
        if final and self.carry:
            saida.append(self._fala(self.carry))
            self.carry = ""
        return saida

    def _fala(self, texto):
        texto = texto.replace("*", "").strip()
        self.falas.append(texto)
        return {"type": "sentence", "text": texto}