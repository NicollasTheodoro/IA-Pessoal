# Nota da personalidade da Alice: ELA VAI FALAR MUITO RECEBA, NÃO SOBRA NADA PRO BETA, BRUTAL, Chique Chique BAHIA
from . import vocabulario as vc


class Personality:
    def __init__(self):
        self.emotion = 0
        self.state = "neutral"
        self.traits = {
            "carinho": 7,
            "energia": 5,
            "sarcasmo": 4,
            "paciencia": 3
        }

    def update_from_interaction(self, user_input):
        user_input = user_input.lower()

        if any(word in user_input for word in vc.goodWords):
            self.traits["carinho"] += 1
            self.traits["energia"] += 1
            self.traits["paciencia"] += 1
        
        if any(word in user_input for word in vc.badWords):
            self.traits["carinho"] -= 1
            self.traits["energia"] -= 1
            self.traits["paciencia"] -= 1
            self.traits["sarcasmo"] +=1

        self._clamp()
        self.update_emotions()
        self.update_state()

    def _clamp(self):
        for k in self.traits:
            self.traits[k] = max(0, min(10, self.traits[k]))
        
    def update_emotions(self):
        neutral = {
            "carinho": 7,
            "energia": 5,
            "sarcasmo": 4,
            "paciencia": 3
        }

            # neutral
        if neutral == self.traits:
            self.emotion = 0

            # excited
        elif self.traits["energia"] >7 and self.traits["paciencia"] >5:
            self.emotion = 1
        
            # irritated
        elif self.traits["paciencia"] <=2:
            self.emotion = 2

            # needy
        elif self.traits["carinho"] >=8 and self.traits["energia"] <=3:
            self.emotion = 3

    
    def update_state(self):
        
        if self.emotion == 0:
            self.state = "neutral"
        elif self.emotion == 1:
            self.state = "excited"
        elif self.emotion == 2:
            self.state = "irritated"
        elif self.emotion == 3:
            self.state = "needy"
        


# print(vc.goodWords)