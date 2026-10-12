# Nota da personalidade da Alice: ELA VAI FALAR MUITO RECEBA, NÃO SOBRA NADA PRO BETA, BRUTAL, Chique Chique BAHIA
from . import vocabulario as vc

BASE = {"carinho": 7, "energia": 5, "sarcasmo": 4, "paciencia": 3}
CALMOS_PARA_RELAXAR = 3  # a cada 3 mensagens "normais", os traços andam 1 ponto de volta ao padrão


class Personality:
    def __init__(self):
        self.emotion = 0
        self.state = "neutral"
        self.traits = dict(BASE)
        self._calmos = 0

    def update_from_interaction(self, user_input):
        texto = user_input.lower()
        bom = any(w in texto for w in vc.goodWords)
        ruim = any(w in texto for w in vc.badWords)

        if bom:
            self.traits["carinho"] += 1
            self.traits["energia"] += 1
            self.traits["paciencia"] += 1
        if ruim:
            self.traits["carinho"] -= 1
            self.traits["energia"] -= 1
            self.traits["paciencia"] -= 1
            self.traits["sarcasmo"] += 1

        if bom or ruim:
            self._calmos = 0
        else:
            self._calmos += 1
            if self._calmos >= CALMOS_PARA_RELAXAR:
                self._calmos = 0
                self._relaxar()

        self._clamp()
        self.update_emotions()
        self.update_state()

    def _relaxar(self):
        """Cada traço dá 1 passo em direção ao valor padrão: a Alice 'esfria' com o tempo."""
        for k, base in BASE.items():
            if self.traits[k] < base:
                self.traits[k] += 1
            elif self.traits[k] > base:
                self.traits[k] -= 1

    def _clamp(self):
        for k in self.traits:
            self.traits[k] = max(0, min(10, self.traits[k]))

    def update_emotions(self):
        t = self.traits
        if t == BASE:
            self.emotion = 0      # neutral
        elif t["energia"] > 7 and t["paciencia"] > 5:
            self.emotion = 1      # excited
        elif t["paciencia"] <= 2:
            self.emotion = 2      # irritated
        elif t["carinho"] >= 8 and t["energia"] <= 3:
            self.emotion = 3      # needy
        else:
            self.emotion = 0      # entre estados: volta ao neutro (antes ficava preso no estado anterior)

    def update_state(self):
        self.state = ["neutral", "excited", "irritated", "needy"][self.emotion]