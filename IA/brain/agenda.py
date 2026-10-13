"""
Agenda e lembretes que sobrevivem a reinícios (salvos em dados/agenda.json).

Um item: {"id", "quando": "2026-10-15T14:30", "texto", "feito": bool, "avisado": bool}
Uma thread confere a cada 10 s e chama notificar(texto) quando chega a hora.
Se o PC estava desligado na hora marcada, o aviso sai assim que a Alice ligar ("atrasado").
"""
import json
import os
import threading
import time
from datetime import datetime, timedelta

from brain import tempo

_TOLERANCIA = timedelta(minutes=2)


class Agenda:
    def __init__(self, pasta, notificar=None):
        os.makedirs(pasta, exist_ok=True)
        self.arquivo = os.path.join(pasta, "agenda.json")
        self.notificar = notificar or print
        self._lock = threading.RLock()
        self.itens = self._carregar()
        threading.Thread(target=self._loop, daemon=True).start()

    # ---------- persistência ----------
    def _carregar(self):
        try:
            with open(self.arquivo, encoding="utf-8") as f:
                return json.load(f)
        except FileNotFoundError:
            return []
        except Exception as e:
            print("Não consegui ler a agenda:", e)
            return []

    def _salvar(self):
        tmp = self.arquivo + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(self.itens, f, indent=2, ensure_ascii=False)
        os.replace(tmp, self.arquivo)

    # ---------- uso ----------
    def adicionar(self, quando, texto):
        """quando: datetime. Devolve o item criado."""
        with self._lock:
            novo_id = max((i["id"] for i in self.itens), default=0) + 1
            item = {"id": novo_id, "quando": quando.strftime("%Y-%m-%dT%H:%M:%S"),
                    "texto": texto.strip()[:200] or "hora do lembrete", "feito": False, "avisado": False}
            self.itens.append(item)
            self._salvar()
            return item

    def adicionar_frase(self, frase, texto):
        """Aceita 'amanhã 14:30', 'sexta 9h', 'daqui a 20 minutos'... Devolve (item, erro)."""
        dt = tempo.interpretar(frase)
        if not dt:
            return None, f"Não entendi quando é '{frase}'. Tente 'amanhã 14:30' ou 'dia 20 às 18h'."
        if dt < datetime.now() - _TOLERANCIA:
            return None, f"{tempo.bonito(dt)} já passou."
        return self.adicionar(dt, texto), None

    def remover(self, item_id):
        with self._lock:
            antes = len(self.itens)
            self.itens = [i for i in self.itens if i["id"] != item_id]
            if len(self.itens) != antes:
                self._salvar()
                return True
            return False

    def concluir(self, item_id, feito=True):
        with self._lock:
            for i in self.itens:
                if i["id"] == item_id:
                    i["feito"] = feito
                    self._salvar()
                    return True
            return False

    def cancelar_por_texto(self, trecho):
        """Remove os itens pendentes cujo texto contém `trecho`. Devolve quantos."""
        trecho = tempo._norm(trecho).strip()
        if not trecho:
            return 0
        with self._lock:
            ids = [i["id"] for i in self.itens if not i["feito"] and trecho in tempo._norm(i["texto"])]
            self.itens = [i for i in self.itens if i["id"] not in ids]
            if ids:
                self._salvar()
            return len(ids)

    def pendentes(self, limite=None):
        """Itens ainda não concluídos, em ordem de data."""
        with self._lock:
            lista = sorted((i for i in self.itens if not i["feito"]), key=lambda i: i["quando"])
        return lista[:limite] if limite else lista

    def todos(self):
        with self._lock:
            return sorted(self.itens, key=lambda i: i["quando"])

    def resumo_prompt(self, limite=5):
        """Linhas curtas para o prompt da Alice."""
        agora = datetime.now()
        linhas = []
        for i in self.pendentes(limite):
            dt = datetime.fromisoformat(i["quando"])
            atraso = " (ATRASADO)" if dt < agora and i["avisado"] else ""
            linhas.append(f"- {tempo.bonito(dt, agora)}: {i['texto']}{atraso}")
        return "\n".join(linhas)

    # ---------- disparo ----------
    def _loop(self):
        while True:
            time.sleep(10)
            try:
                self._conferir()
            except Exception as e:
                print("Erro na agenda:", e)

    def _conferir(self):
        agora = datetime.now()
        vencidos = []
        with self._lock:
            for i in self.itens:
                if not i["feito"] and not i["avisado"] and datetime.fromisoformat(i["quando"]) <= agora:
                    i["avisado"] = True
                    vencidos.append(dict(i))
            if vencidos:
                self._salvar()
        for i in vencidos:
            atrasado = (agora - datetime.fromisoformat(i["quando"])).total_seconds() > 120
            prefixo = "Lembrete atrasado" if atrasado else "Lembrete"
            self.notificar(f"{prefixo}: {i['texto']}")

