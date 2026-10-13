"""
Calcula calorias e macronutrientes de forma DETERMINÍSTICA (o LLM pequeno erra conta).

Valores por 100 g do alimento já no preparo indicado, aproximados (estilo tabela TACO).
São estimativas: serve para acompanhar a rotina, não para dieta clínica.
Para adicionar um alimento, basta incluir uma linha em ALIMENTOS:
    (["nomes", "que a pessoa fala"], kcal, proteina, carboidrato, gordura, gramas_por_unidade, frito?)
"""
import json
import re
import unicodedata

# (nomes/apelidos, kcal, prot, carb, gord, g por unidade (ou None), já é frito?)
ALIMENTOS = [
    (["arroz", "arroz branco"], 128, 2.5, 28.1, 0.2, None, False),
    (["arroz integral"], 124, 2.6, 25.8, 1.0, None, False),
    (["feijao", "feijao carioca"], 76, 4.8, 13.6, 0.5, None, False),
    (["feijao preto"], 77, 4.5, 14.0, 0.5, None, False),
    (["frango", "peito de frango", "frango grelhado", "peito de frango grelhado"], 159, 32.0, 0.0, 2.5, None, False),
    (["frango cozido", "peito de frango cozido", "frango desfiado"], 163, 31.5, 0.0, 3.2, None, False),
    (["frango frito", "frango empanado", "frango a milanesa", "empanado", "file de frango empanado"], 260, 23.0, 10.0, 14.0, None, True),
    (["carne", "carne grelhada", "bife", "patinho", "bife grelhado"], 219, 35.9, 0.0, 7.3, None, False),
    (["carne moida", "carne moida refogada"], 212, 26.7, 0.0, 10.9, None, False),
    (["ovo", "ovo cozido", "ovos", "ovos cozidos"], 146, 13.3, 0.6, 9.5, 50, False),
    (["ovo frito", "ovos fritos"], 240, 15.6, 1.2, 18.6, 50, True),
    (["ovo mexido", "omelete", "ovos mexidos"], 190, 13.0, 1.0, 15.0, 50, False),
    (["pao frances", "pao", "paozinho"], 300, 8.0, 58.6, 3.1, 50, False),
    (["pao de forma", "fatia de pao de forma"], 265, 8.5, 49.0, 3.5, 25, False),
    (["macarrao", "espaguete", "massa"], 102, 3.4, 19.9, 0.5, None, False),
    (["batata", "batata cozida"], 52, 1.2, 11.9, 0.0, 130, False),
    (["batata frita"], 267, 3.5, 35.6, 13.1, None, True),
    (["batata doce", "batata doce cozida"], 77, 0.6, 18.4, 0.1, 130, False),
    (["mandioca", "aipim", "macaxeira"], 125, 0.6, 30.1, 0.3, None, False),
    (["cuscuz", "cuscuz de milho"], 113, 2.2, 25.3, 0.7, None, False),
    (["banana"], 98, 1.3, 26.0, 0.1, 86, False),
    (["maca"], 56, 0.3, 15.2, 0.0, 130, False),
    (["laranja"], 37, 1.0, 8.9, 0.1, 150, False),
    (["leite", "leite integral"], 61, 3.2, 4.7, 3.3, None, False),
    (["leite desnatado"], 35, 3.4, 5.0, 0.1, None, False),
    (["iogurte", "iogurte natural"], 51, 4.1, 1.9, 3.0, 170, False),
    (["queijo", "queijo mussarela", "mussarela", "muçarela"], 330, 22.6, 3.0, 25.2, 20, False),
    (["queijo minas", "queijo branco"], 264, 17.4, 3.2, 20.2, 30, False),
    (["presunto"], 130, 14.0, 1.0, 7.0, 15, False),
    (["manteiga"], 726, 0.4, 0.1, 82.0, None, False),
    (["azeite", "oleo"], 884, 0.0, 0.0, 100.0, None, False),
    (["aveia"], 394, 13.9, 66.6, 8.5, None, False),
    (["whey", "whey protein"], 400, 80.0, 8.0, 6.0, 30, False),
    (["amendoim"], 544, 27.0, 20.0, 43.0, None, False),
    (["pasta de amendoim"], 590, 25.0, 20.0, 50.0, None, False),
    (["pizza"], 285, 11.5, 33.0, 11.5, 110, True),
    (["refrigerante", "coca", "coca cola"], 37, 0.0, 9.4, 0.0, None, False),
    (["salmao", "salmao grelhado"], 229, 25.0, 0.0, 14.0, None, False),
    (["tilapia", "tilapia grelhada", "peixe"], 128, 26.0, 0.0, 2.7, None, False),
    (["alface"], 11, 1.3, 1.7, 0.2, None, False),
    (["tomate"], 15, 1.1, 3.1, 0.2, 100, False),
    (["cenoura", "cenoura cozida"], 30, 0.8, 6.7, 0.2, None, False),
    (["brocolis", "brocolis cozido"], 25, 2.1, 4.4, 0.5, None, False),
]

GRAMAS_COLHER = 25  # 1 colher de sopa cheia de comida sólida, aproximado
OLEO_FRITURA = 6.0  # g de gordura extra por 100 g quando o preparo é frito e o alimento não é "de fritura"


def _norm(t):
    t = unicodedata.normalize("NFD", (t or "").lower())
    return "".join(c for c in t if unicodedata.category(c) != "Mn").strip()


def _palavras(t):
    return {p.rstrip("s") for p in re.findall(r"[a-z]+", _norm(t)) if p not in ("de", "da", "do", "com", "e")}


def achar(alimento, preparo=""):
    """Escolhe a linha da tabela cujo apelido está mais contido na frase (alimento + preparo)."""
    frase = _palavras(f"{alimento} {preparo}")
    melhor, tam = None, 0
    for item in ALIMENTOS:
        for nome in item[0]:
            p = _palavras(nome)
            if p and p <= frase and len(p) > tam:
                melhor, tam = item, len(p)
    return melhor


def gramas(qtd, item=None):
    """'150g', '1,5 kg', '200 ml', '2 unidades', '3 colheres', '2' -> gramas (ou None)."""
    t = _norm(qtd).replace(",", ".")
    m = re.search(r"(\d+(?:\.\d+)?)\s*(kg|g|gr|gramas?|ml|l|litros?|colher(?:es)?|un\w*|fatias?|)\b", t)
    if not m:
        return None
    n, un = float(m.group(1)), m.group(2) or ""
    if un == "kg":
        return n * 1000
    if un in ("g", "gr") or un.startswith("grama") or un == "ml":
        return n
    if un in ("l",) or un.startswith("litro"):
        return n * 1000
    if un.startswith("colher"):
        return n * GRAMAS_COLHER
    por_un = item[5] if item else None  # unidade, fatia ou número solto
    return n * por_un if por_un else None


def calcular(alimento, quantidade="", preparo="", kcal=None, llm=None):
    """
    Devolve (dict com kcal/proteina_g/carbo_g/gordura_g/obs, erro).
    - `kcal` informado pelo usuário: as calorias ficam como ele disse e os macros se ajustam a elas.
    - `llm`: função(prompt)->str opcional, só usada para alimentos fora da tabela.
    """
    item = achar(alimento, preparo)
    if item:
        _, k100, p100, c100, g100, _, ja_frito = item
        if re.search(r"fri(t|ci)|empan|milanesa", _norm(preparo)) and not ja_frito:
            g100 += OLEO_FRITURA
            k100 += OLEO_FRITURA * 9
        g = gramas(quantidade, item)
        if g is None and kcal:
            g = kcal / k100 * 100  # sem quantidade, deduz pelas calorias
        if g is None:
            return None, "Preciso da quantidade (ex.: 150g, 2 unidades) ou das calorias."
        f = g / 100
        r = {"kcal": k100 * f, "proteina_g": p100 * f, "carbo_g": c100 * f, "gordura_g": g100 * f}
        if kcal:  # respeita as calorias que o usuário informou
            esc = kcal / r["kcal"] if r["kcal"] else 1
            r = {k: v * esc for k, v in r.items()}
        r = {k: round(v, 1) for k, v in r.items()}
        r["kcal"] = round(r["kcal"])
        r["obs"] = "macros estimados pela tabela interna" + (f" (~{round(g)} g)" if g else "")
        return r, None

    # fora da tabela: pede uma estimativa ao modelo, se houver
    if llm:
        prompt = (
            f"Estime os valores nutricionais de: {alimento}, quantidade {quantidade or 'uma porção'}, "
            f"preparo {preparo or 'não informado'}." + (f" Total de {kcal} kcal." if kcal else "") +
            ' Responda SOMENTE um JSON: {"kcal": n, "proteina_g": n, "carbo_g": n, "gordura_g": n}'
        )
        try:
            bruto = llm(prompt)
            j = json.loads(re.search(r"\{.*\}", bruto, re.S).group(0))
            r = {k: round(float(j[k]), 1) for k in ("kcal", "proteina_g", "carbo_g", "gordura_g")}
            if kcal:
                esc = kcal / r["kcal"] if r["kcal"] else 1
                r = {k: round(v * esc, 1) for k, v in r.items()}
            r["kcal"] = round(r["kcal"])
            r["obs"] = "estimado pelo modelo (fora da tabela)"
            return r, None
        except Exception as e:
            print("Estimativa por modelo falhou:", e)
    if kcal:
        return {"kcal": round(kcal), "proteina_g": None, "carbo_g": None, "gordura_g": None,
                "obs": "alimento fora da tabela: só as calorias foram salvas"}, None
    return None, f"Não conheço '{alimento}'. Me diga as calorias que eu registro."
