"""
Clima e hora, sem chave de API (Open-Meteo). Atualiza em segundo plano a cada 15 min,
então montar o prompt nunca espera a internet.

Troque a cidade sem mexer no código:
    set ALICE_CIDADE=Nova Iguaçu
    set ALICE_LAT=-22.7592   set ALICE_LON=-43.4511   (se informar, não precisa de busca)
"""
import json
import os
import threading
import time
import urllib.parse
import urllib.request

CIDADE = os.getenv("ALICE_CIDADE", "Nova Iguaçu")
LAT = os.getenv("ALICE_LAT", "-22.7592")
LON = os.getenv("ALICE_LON", "-43.4511")
INTERVALO = 15 * 60

CODIGOS = {
    0: "céu limpo", 1: "quase sem nuvens", 2: "parcialmente nublado", 3: "nublado",
    45: "neblina", 48: "neblina", 51: "garoa fraca", 53: "garoa", 55: "garoa forte",
    61: "chuva fraca", 63: "chuva", 65: "chuva forte", 66: "chuva congelante", 67: "chuva congelante forte",
    71: "neve fraca", 73: "neve", 75: "neve forte", 80: "pancadas de chuva fracas",
    81: "pancadas de chuva", 82: "pancadas de chuva fortes", 95: "trovoada", 96: "trovoada com granizo",
    99: "trovoada com granizo forte",
}
ICONES = {0: "☀️", 1: "🌤️", 2: "⛅", 3: "☁️", 45: "🌫️", 48: "🌫️", 51: "🌦️", 53: "🌦️", 55: "🌧️",
          61: "🌦️", 63: "🌧️", 65: "🌧️", 80: "🌦️", 81: "🌧️", 82: "⛈️", 95: "⛈️", 96: "⛈️", 99: "⛈️"}


class Clima:
    def __init__(self):
        self.dados = None  # dict ou None enquanto não carregou / sem internet
        self.erro = None
        self._lock = threading.Lock()
        threading.Thread(target=self._loop, daemon=True).start()

    def _loop(self):
        while True:
            try:
                self.atualizar()
            except Exception as e:
                self.erro = str(e)
                print("Clima indisponível:", e)
            time.sleep(INTERVALO if self.dados else 60)  # sem dados: tenta de novo em 1 min

    def atualizar(self):
        params = {
            "latitude": LAT, "longitude": LON, "timezone": "auto",
            "current": "temperature_2m,apparent_temperature,relative_humidity_2m,weather_code,wind_speed_10m",
            "daily": "temperature_2m_max,temperature_2m_min,precipitation_probability_max,weather_code",
            "forecast_days": 2,
        }
        url = "https://api.open-meteo.com/v1/forecast?" + urllib.parse.urlencode(params)
        with urllib.request.urlopen(url, timeout=10) as r:
            j = json.load(r)
        c, d = j["current"], j["daily"]
        novo = {
            "cidade": CIDADE,
            "temp": round(c["temperature_2m"]),
            "sensacao": round(c["apparent_temperature"]),
            "umidade": round(c["relative_humidity_2m"]),
            "vento": round(c["wind_speed_10m"]),
            "codigo": c["weather_code"],
            "descricao": CODIGOS.get(c["weather_code"], "tempo indefinido"),
            "icone": ICONES.get(c["weather_code"], "🌡️"),
            "max": round(d["temperature_2m_max"][0]),
            "min": round(d["temperature_2m_min"][0]),
            "chuva": d["precipitation_probability_max"][0],
            "atualizado": time.strftime("%H:%M"),
        }
        with self._lock:
            self.dados, self.erro = novo, None

    def resumo_prompt(self):
        d = self.dados
        if not d:
            return ""
        return (f"{d['cidade']}: {d['temp']}°C (sensação {d['sensacao']}°C), {d['descricao']}, "
                f"máx {d['max']}°C, mín {d['min']}°C, chance de chuva {d['chuva']}%.")
