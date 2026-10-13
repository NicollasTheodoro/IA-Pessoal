"""
Entende datas e horas escritas em português e devolve um datetime.

O modelo pequeno erra conta de calendário, então ele só repassa a frase do usuário
("amanhã 14:30", "sexta 9h", "dia 20 às 18h", "daqui a 2 horas") e o Python calcula.

    interpretar("amanhã 14:30")            -> datetime de amanhã às 14:30
    interpretar("2026-10-15 08:00")        -> formato ISO também vale
    interpretar("daqui a 90 minutos")      -> agora + 90 min
"""
import re
import unicodedata
from datetime import datetime, timedelta

DIAS = {
    "segunda": 0, "terca": 1, "quarta": 2, "quinta": 3, "sexta": 4, "sabado": 5, "domingo": 6,
}
MESES = {
    "janeiro": 1, "fevereiro": 2, "marco": 3, "abril": 4, "maio": 5, "junho": 6,
    "julho": 7, "agosto": 8, "setembro": 9, "outubro": 10, "novembro": 11, "dezembro": 12,
}
HORA_PADRAO = 9  # quando a pessoa diz só o dia ("sexta"), avisa às 9h


def _norm(t):
    t = unicodedata.normalize("NFD", (t or "").lower())
    return "".join(c for c in t if unicodedata.category(c) != "Mn")


def _hora(t):
    """Acha a hora na frase. Devolve (hora, minuto) ou None."""
    if re.search(r"\bmeio[- ]?dia\b", t):
        return 12, 0
    if re.search(r"\bmeia[- ]noite\b", t):
        return 0, 0
    m = re.search(r"\b(\d{1,2})\s*(?::|h|horas?)\s*(\d{2})?\b", t) or re.search(
        r"\b(\d{1,2})()\s+(?:da|de)\s+(?:manha|tarde|noite)\b", t)
    if not m:  # sem número: "à noite" = 20h, "de tarde" = 15h, "de manhã" = 9h
        if re.search(r"\bnoite\b", t):
            return 20, 0
        if re.search(r"\btarde\b", t):
            return 15, 0
        if re.search(r"\bmanha\b", t):
            return 9, 0
        return None
    h, mi = int(m.group(1)), int(m.group(2) or 0)
    if h > 23 or mi > 59:
        return None
    if re.search(r"\b(da|de)\s+(tarde|noite)\b", t) and h < 12:
        h += 12
    elif re.search(r"\bda\s+manha\b", t) and h == 12:
        h = 0
    return h, mi


def interpretar(frase, agora=None):
    """Devolve um datetime futuro (ou None se não entendeu)."""
    agora = agora or datetime.now()
    t = _norm(frase).strip()
    if not t:
        return None

    # 1) ISO: 2026-10-15 08:00  /  2026-10-15T08:00
    m = re.fullmatch(r"(\d{4})-(\d{2})-(\d{2})(?:[t ]+(\d{1,2}):(\d{2}))?", t)
    if m:
        a, mes, d, h, mi = (int(x) if x else 0 for x in m.groups())
        try:
            return datetime(a, mes, d, h or (0 if m.group(4) else HORA_PADRAO), mi)
        except ValueError:
            return None

    # 2) relativo: daqui a 20 minutos / em 2 horas / daqui 1 dia
    m = re.search(r"\b(?:daqui\s+a?|em)\s+(\d+(?:[.,]\d+)?)\s*(segundo|minuto|min|hora|h|dia)s?\b", t)
    if m:
        n = float(m.group(1).replace(",", "."))
        un = m.group(2)
        delta = {"segundo": timedelta(seconds=n), "minuto": timedelta(minutes=n), "min": timedelta(minutes=n),
                 "hora": timedelta(hours=n), "h": timedelta(hours=n), "dia": timedelta(days=n)}[un]
        return agora + delta
    if re.search(r"\bdaqui\s+a?\s*meia\s+hora\b", t):
        return agora + timedelta(minutes=30)

    # 3) dia: hoje / amanha / depois de amanha / dia da semana / dia 20 / 20/10 / 20 de outubro
    hm = _hora(t)
    dia = None
    if re.search(r"\bontem\b", t):
        dia = agora.date() - timedelta(days=1)
    elif re.search(r"\bdepois\s+de\s+amanha\b", t):
        dia = agora.date() + timedelta(days=2)
    elif re.search(r"\bamanha\b", t):
        dia = agora.date() + timedelta(days=1)
    elif re.search(r"\bhoje\b", t) or re.search(r"\b(a|de)\s+noite\b", t) and not re.search(r"\b(segunda|terca|quarta|quinta|sexta|sabado|domingo)\b", t):
        dia = agora.date()

    if dia is None:
        m = re.search(r"\b(\d{1,2})\s*/\s*(\d{1,2})(?:\s*/\s*(\d{2,4}))?\b", t)
        if m:
            d, mes = int(m.group(1)), int(m.group(2))
            a = int(m.group(3)) if m.group(3) else agora.year
            a += 2000 if a < 100 else 0
            try:
                dia = datetime(a, mes, d).date()
            except ValueError:
                return None
            if not m.group(3) and datetime.combine(dia, datetime.min.time()) < agora.replace(hour=0, minute=0, second=0, microsecond=0):
                dia = dia.replace(year=dia.year + 1)

    if dia is None:
        m = re.search(r"\bdia\s+(\d{1,2})(?:\s+de\s+([a-z]+))?\b", t) or re.search(r"\b(\d{1,2})\s+de\s+([a-z]+)\b", t)
        if m:
            d = int(m.group(1))
            mes = MESES.get(m.group(2)) if m.lastindex and m.group(2) else None
            try:
                if mes:
                    dia = datetime(agora.year, mes, d).date()
                    if dia < agora.date():
                        dia = dia.replace(year=agora.year + 1)
                else:  # "dia 20": este mês, ou o próximo se já passou
                    mes, ano = agora.month, agora.year
                    try:
                        dia = datetime(ano, mes, d).date()
                    except ValueError:
                        dia = None
                    if dia is None or dia < agora.date():
                        mes, ano = (1, ano + 1) if mes == 12 else (mes + 1, ano)
                        dia = datetime(ano, mes, d).date()
            except ValueError:
                return None

    if dia is None:
        for nome, idx in DIAS.items():
            if re.search(rf"\b{nome}", t):
                falta = (idx - agora.weekday()) % 7
                dia = agora.date() + timedelta(days=falta)
                if falta == 0 and hm and (hm[0], hm[1]) <= (agora.hour, agora.minute):
                    dia += timedelta(days=7)  # "segunda 8h" dito na segunda às 10h = próxima segunda
                break

    if dia is None and hm:  # só a hora: hoje, ou amanhã se já passou
        alvo = agora.replace(hour=hm[0], minute=hm[1], second=0, microsecond=0)
        return alvo if alvo > agora else alvo + timedelta(days=1)
    if dia is None:
        return None

    h, mi = hm if hm else (HORA_PADRAO, 0)
    alvo = datetime(dia.year, dia.month, dia.day, h, mi)
    if alvo <= agora and not hm and dia == agora.date():
        alvo = agora + timedelta(minutes=1)
    return alvo


def bonito(dt, agora=None):
    """'hoje às 14:30', 'amanhã às 09:00', 'sex, 16/10 às 18:00'."""
    agora = agora or datetime.now()
    nomes = ["seg", "ter", "qua", "qui", "sex", "sáb", "dom"]
    diff = (dt.date() - agora.date()).days
    hora = f"{dt:%H:%M}"
    if diff == 0:
        return f"hoje às {hora}"
    if diff == 1:
        return f"amanhã às {hora}"
    return f"{nomes[dt.weekday()]}, {dt:%d/%m} às {hora}"


def data_registro(frase, agora=None):
    """
    Como interpretar(), mas para REGISTROS (o que já aconteceu): se a data cair no futuro
    sem ter sido dita assim ("05/10" dito em 12/10), volta para a ocorrência mais recente.
    """
    agora = agora or datetime.now()
    dt = interpretar(frase, agora)
    t = _norm(frase)
    if not dt or dt.date() <= agora.date() or re.search(r"amanha|depois|daqui|\b\d{4}\b|\bem\s+\d", t):
        return dt
    if re.search(r"\b\d{1,2}\s*/\s*\d{1,2}\b|\bde\s+[a-z]+\b", t):
        try:
            return dt.replace(year=dt.year - 1)
        except ValueError:
            return dt
    if re.search(r"\bdia\s+\d{1,2}\b", t):
        mes, ano = (12, dt.year - 1) if dt.month == 1 else (dt.month - 1, dt.year)
        try:
            return dt.replace(year=ano, month=mes)
        except ValueError:
            return dt
    if any(re.search(rf"\b{n}", t) for n in DIAS):
        return dt - timedelta(days=7)
    return dt
