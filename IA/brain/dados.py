"""
Planilhas da Alice (SQLite em dados/alice.db), com gráficos e exportação para CSV/Excel.

PARA CRIAR OU AUMENTAR UMA TABELA, edite só o dicionário TABELAS abaixo:
  - tabela nova: copie um bloco e mude os nomes;
  - coluna nova: acrescente em "colunas" (o banco se atualiza sozinho na próxima vez que ligar).
Tipos de coluna: "data", "num", "texto", "opcao" (com "opcoes": [...]).
A interface web e a Alice leem este dicionário, então nada mais precisa ser mexido.
"""
import csv
import io
import os
import re
import sqlite3
import threading
from datetime import date, datetime, timedelta

from brain import tempo
from brain.nutricao import _norm

TABELAS = {
    "financeiro": {
        "titulo": "Financeiro", "icone": "💰",
        "dica": "Ganhos e quando entraram. Use valor negativo para gastos.",
        "colunas": [
            {"nome": "data", "tipo": "data"},
            {"nome": "valor", "tipo": "num", "unidade": "R$"},
            {"nome": "origem", "tipo": "opcao", "opcoes": ["trabalho", "bico", "outro"]},
            {"nome": "descricao", "tipo": "texto"},
        ],
        "grafico": {"y": "valor", "agg": "soma", "periodo": "mes", "por": "origem"},
    },
    "treino": {
        "titulo": "Treinos", "icone": "🏋️",
        "dica": "Exercícios, carga, e tempo/distância de corrida.",
        "colunas": [
            {"nome": "data", "tipo": "data"},
            {"nome": "tipo", "tipo": "opcao", "opcoes": ["musculação", "corrida", "caminhada", "outro"]},
            {"nome": "exercicio", "tipo": "texto"},
            {"nome": "series", "tipo": "num"},
            {"nome": "repeticoes", "tipo": "num"},
            {"nome": "carga_kg", "tipo": "num", "unidade": "kg"},
            {"nome": "duracao_min", "tipo": "num", "unidade": "min"},
            {"nome": "distancia_km", "tipo": "num", "unidade": "km"},
            {"nome": "obs", "tipo": "texto"},
        ],
        "grafico": {"y": "duracao_min", "agg": "soma", "periodo": "semana", "por": "tipo"},
    },
    "corpo": {
        "titulo": "Peso e altura", "icone": "⚖️",
        "dica": "Pese-se de vez em quando; a altura só precisa ser informada uma vez.",
        "colunas": [
            {"nome": "data", "tipo": "data"},
            {"nome": "peso_kg", "tipo": "num", "unidade": "kg"},
            {"nome": "altura_cm", "tipo": "num", "unidade": "cm"},
        ],
        "grafico": {"y": "peso_kg", "agg": "media", "periodo": "dia"},
    },
    "alimentacao": {
        "titulo": "Alimentação", "icone": "🍽️",
        "dica": "Diga o alimento, a quantidade e o preparo; a Alice calcula calorias e macros (estimativa).",
        "colunas": [
            {"nome": "data", "tipo": "data"},
            {"nome": "refeicao", "tipo": "opcao", "opcoes": ["café da manhã", "almoço", "lanche", "jantar", "outro"]},
            {"nome": "alimento", "tipo": "texto"},
            {"nome": "quantidade", "tipo": "texto"},
            {"nome": "preparo", "tipo": "texto"},
            {"nome": "kcal", "tipo": "num", "unidade": "kcal"},
            {"nome": "proteina_g", "tipo": "num", "unidade": "g"},
            {"nome": "carbo_g", "tipo": "num", "unidade": "g"},
            {"nome": "gordura_g", "tipo": "num", "unidade": "g"},
            {"nome": "obs", "tipo": "texto"},
        ],
        "grafico": {"y": "kcal", "agg": "soma", "periodo": "dia"},
    },
    "estudo": {
        "titulo": "Estudo", "icone": "📚",
        "dica": "O que estudou e por quanto tempo.",
        "colunas": [
            {"nome": "data", "tipo": "data"},
            {"nome": "materia", "tipo": "texto"},
            {"nome": "assunto", "tipo": "texto"},
            {"nome": "duracao_min", "tipo": "num", "unidade": "min"},
            {"nome": "obs", "tipo": "texto"},
        ],
        "grafico": {"y": "duracao_min", "agg": "soma", "periodo": "dia", "por": "materia"},
    },
}

LIMITE_TEXTO = 200
# apelidos que o modelo costuma usar para as colunas
ALIAS = {"proteina": "proteina_g", "carboidrato": "carbo_g", "carboidratos": "carbo_g", "carbo": "carbo_g",
         "gordura": "gordura_g", "peso": "peso_kg", "altura": "altura_cm", "carga": "carga_kg",
         "duracao": "duracao_min", "tempo": "duracao_min", "distancia": "distancia_km", "fonte": "origem",
         "valor_r": "valor", "descricão": "descricao", "reps": "repeticoes", "caloria": "kcal", "calorias": "kcal"}
_NOME = re.compile(r"^[a-z_][a-z0-9_]*$")


class Dados:
    def __init__(self, pasta):
        os.makedirs(pasta, exist_ok=True)
        self.caminho = os.path.join(pasta, "alice.db")
        self._lock = threading.RLock()
        self._criar()

    def _con(self):
        con = sqlite3.connect(self.caminho)
        con.row_factory = sqlite3.Row
        return con

    def _criar(self):
        """Cria as tabelas e acrescenta colunas novas (nunca apaga nada)."""
        with self._lock, self._con() as con:
            for nome, t in TABELAS.items():
                assert _NOME.match(nome), nome
                tipos = {"num": "REAL"}
                cols = ", ".join(f'{c["nome"]} {tipos.get(c["tipo"], "TEXT")}' for c in t["colunas"])
                con.execute(f"CREATE TABLE IF NOT EXISTS {nome} (id INTEGER PRIMARY KEY AUTOINCREMENT, {cols})")
                existentes = {r["name"] for r in con.execute(f"PRAGMA table_info({nome})")}
                for c in t["colunas"]:
                    assert _NOME.match(c["nome"]), c["nome"]
                    if c["nome"] not in existentes:
                        con.execute(f'ALTER TABLE {nome} ADD COLUMN {c["nome"]} {tipos.get(c["tipo"], "TEXT")}')

    # ---------- esquema ----------
    def esquema(self):
        return [{"nome": n, **t} for n, t in TABELAS.items()]

    def _tabela(self, nome):
        nome = (nome or "").strip().lower()
        nome = {"academia": "treino", "treinos": "treino", "peso": "corpo", "comida": "alimentacao",
                "alimentação": "alimentacao", "financas": "financeiro", "finanças": "financeiro",
                "estudos": "estudo"}.get(nome, nome)
        if nome not in TABELAS:  # lista fechada: nome vem do dicionário, nunca direto para o SQL
            raise ValueError(f"Tabela desconhecida: {nome}. Existem: {', '.join(TABELAS)}")
        return nome, TABELAS[nome]

    # ---------- conversão dos valores ----------
    def _converter(self, col, valor):
        if valor is None or str(valor).strip() == "":
            return date.today().isoformat() if col["tipo"] == "data" else None
        v = str(valor).strip()
        if col["tipo"] == "data":
            dt = tempo.data_registro(v)
            if not dt:
                raise ValueError(f"Data inválida: {v}")
            return dt.date().isoformat()
        if col["tipo"] == "num":
            m = re.search(r"-?\d+(?:[.,]\d+)?", v.replace(" ", ""))
            if not m:
                raise ValueError(f"'{col['nome']}' precisa ser um número (recebi '{v}')")
            return float(m.group(0).replace(",", "."))
        if col["tipo"] == "opcao":
            for o in col.get("opcoes", []):
                if _norm(o) == _norm(v):
                    return o
        return v[:LIMITE_TEXTO]

    def _limpar(self, t, valores, completo):
        cols = {c["nome"]: c for c in t["colunas"]}
        saida = {}
        for k, v in (valores or {}).items():
            k = _norm(k).replace(" ", "_")
            k = ALIAS.get(k, k)
            if k in cols:
                saida[k] = self._converter(cols[k], v)
        if completo and "data" in cols and "data" not in saida:
            saida["data"] = date.today().isoformat()
        return saida

    # ---------- CRUD ----------
    def inserir(self, tabela, valores):
        nome, t = self._tabela(tabela)
        v = self._limpar(t, valores, completo=True)
        if not any(k != "data" for k in v):
            raise ValueError("Faltou informar os campos (ex.: valor=100).")
        with self._lock, self._con() as con:
            cur = con.execute(f"INSERT INTO {nome} ({', '.join(v)}) VALUES ({', '.join('?' * len(v))})", list(v.values()))
            return cur.lastrowid

    def atualizar(self, tabela, linha_id, valores):
        nome, t = self._tabela(tabela)
        v = self._limpar(t, valores, completo=False)
        if not v:
            return False
        with self._lock, self._con() as con:
            cur = con.execute(f"UPDATE {nome} SET {', '.join(k + '=?' for k in v)} WHERE id=?", [*v.values(), int(linha_id)])
            return cur.rowcount > 0

    def remover(self, tabela, linha_id):
        nome, _ = self._tabela(tabela)
        with self._lock, self._con() as con:
            return con.execute(f"DELETE FROM {nome} WHERE id=?", (int(linha_id),)).rowcount > 0

    def listar(self, tabela, limite=300):
        nome, _ = self._tabela(tabela)
        with self._lock, self._con() as con:
            rows = con.execute(f"SELECT * FROM {nome} ORDER BY data DESC, id DESC LIMIT ?", (int(limite),)).fetchall()
        return [dict(r) for r in rows]

    # ---------- gráficos ----------
    def grafico(self, tabela, y=None, agg=None, periodo=None, por=None, dias=120):
        """
        Agrupa a coluna numérica `y` por dia/semana/mês.
        Devolve {"rotulos": [...], "series": [{"nome": "...", "valores": [...]}], "unidade": "R$"}.
        """
        nome, t = self._tabela(tabela)
        padrao = t.get("grafico", {})
        y = y or padrao.get("y")
        agg = agg or padrao.get("agg", "soma")
        periodo = periodo or padrao.get("periodo", "dia")
        por = padrao.get("por") if por is None else (por or None)
        col_y = next((c for c in t["colunas"] if c["nome"] == y and c["tipo"] == "num"), None)
        if not col_y:
            raise ValueError("Escolha uma coluna numérica para o gráfico.")
        if por and por not in {c["nome"] for c in t["colunas"]}:
            por = None
        desde = (date.today() - timedelta(days=int(dias))).isoformat()
        sel_por = f", COALESCE({por}, '—') AS grupo" if por else ""
        with self._lock, self._con() as con:
            rows = con.execute(
                f"SELECT data, {y} AS v{sel_por} FROM {nome} WHERE {y} IS NOT NULL AND data >= ? ORDER BY data", (desde,)
            ).fetchall()

        def chave(d):
            dt = date.fromisoformat(d)
            if periodo == "mes":
                return dt.strftime("%Y-%m")
            if periodo == "semana":
                return (dt - timedelta(days=dt.weekday())).isoformat()  # segunda-feira da semana
            return d

        acum = {}  # (grupo, periodo) -> [valores]
        periodos = set()
        for r in rows:
            k = chave(r["data"])
            periodos.add(k)
            acum.setdefault((r["grupo"] if por else "total", k), []).append(r["v"])
        rotulos = sorted(periodos)

        def reduzir(vs):
            return round(sum(vs) / len(vs), 2) if agg == "media" else round(max(vs), 2) if agg == "max" else round(sum(vs), 2)

        grupos = sorted({g for g, _ in acum})
        series = [{"nome": g, "valores": [reduzir(acum[(g, p)]) if (g, p) in acum else 0 for p in rotulos]} for g in grupos]
        return {"rotulos": rotulos, "series": series, "unidade": col_y.get("unidade", ""),
                "y": y, "agg": agg, "periodo": periodo}

    # ---------- exportação ----------
    def csv(self, tabela):
        nome, t = self._tabela(tabela)
        buf = io.StringIO()
        w = csv.writer(buf, delimiter=";")  # ';' abre direto no Excel em português
        cols = ["id"] + [c["nome"] for c in t["colunas"]]
        w.writerow(cols)
        for r in reversed(self.listar(nome, 100000)):
            w.writerow([("" if r[c] is None else str(r[c]).replace(".", ",") if isinstance(r[c], float) else r[c]) for c in cols])
        return "\ufeff" + buf.getvalue()  # BOM: o Excel reconhece os acentos

    # ---------- resumo para o prompt e para o painel ----------
    def resumo(self):
        hoje = date.today().isoformat()
        mes = hoje[:7]
        out = {}
        with self._lock, self._con() as con:
            r = con.execute("SELECT SUM(kcal) k, SUM(proteina_g) p, SUM(carbo_g) c, SUM(gordura_g) g FROM alimentacao WHERE data=?", (hoje,)).fetchone()
            out["comida_hoje"] = {k: round(r[k] or 0) for k in ("k", "p", "c", "g")}
            out["ganhos_mes"] = round(con.execute("SELECT SUM(valor) FROM financeiro WHERE data LIKE ?", (mes + "%",)).fetchone()[0] or 0, 2)
            out["estudo_hoje_min"] = round(con.execute("SELECT SUM(duracao_min) FROM estudo WHERE data=?", (hoje,)).fetchone()[0] or 0)
            p = con.execute("SELECT peso_kg, data FROM corpo WHERE peso_kg IS NOT NULL ORDER BY data DESC, id DESC LIMIT 1").fetchone()
            out["peso"] = {"kg": p["peso_kg"], "data": p["data"]} if p else None
            a = con.execute("SELECT altura_cm FROM corpo WHERE altura_cm IS NOT NULL ORDER BY data DESC, id DESC LIMIT 1").fetchone()
            out["altura_cm"] = a["altura_cm"] if a else None
            tr = con.execute("SELECT data, tipo, exercicio FROM treino ORDER BY data DESC, id DESC LIMIT 1").fetchone()
            out["ultimo_treino"] = dict(tr) if tr else None
            sem = (date.today() - timedelta(days=date.today().weekday())).isoformat()
            out["treinos_semana"] = con.execute("SELECT COUNT(DISTINCT data) FROM treino WHERE data >= ?", (sem,)).fetchone()[0]
        if out["peso"] and out["altura_cm"]:
            out["imc"] = round(out["peso"]["kg"] / (out["altura_cm"] / 100) ** 2, 1)
        return out

    def resumo_prompt(self):
        r = self.resumo()
        linhas = []
        c = r["comida_hoje"]
        if c["k"]:
            linhas.append(f"Hoje já comeu {c['k']} kcal (P {c['p']} g, C {c['c']} g, G {c['g']} g).")
        if r["ganhos_mes"]:
            linhas.append(f"Ganhos neste mês: R$ {r['ganhos_mes']:.2f}.")
        if r["estudo_hoje_min"]:
            linhas.append(f"Estudou {r['estudo_hoje_min']} min hoje.")
        if r["peso"]:
            linhas.append(f"Último peso: {r['peso']['kg']} kg em {datetime.fromisoformat(r['peso']['data']):%d/%m}.")
        if r["ultimo_treino"]:
            t = r["ultimo_treino"]
            linhas.append(f"Último treino: {t['tipo'] or t['exercicio']} em {datetime.fromisoformat(t['data']):%d/%m}; {r['treinos_semana']} dia(s) de treino nesta semana.")
        return "\n".join(linhas)
