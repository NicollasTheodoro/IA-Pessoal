import threading
from audio.listener import Listener
from brain.actions import Think

class Controller:
    def __init__(self, listener, brain):
        self.listener = listener
        self.brain = brain
        self.partial_generation_id = 0

        self.partial_thread = None
        self.partial_lock = False
        self.partial_response = None
        self.last_partial_sent = ""

        self.listener.on_partial_callback = self.handle_partial

    def start_partial_thinking(self, texto):
        if self.partial_lock:
            return

        self.partial_generation_id += 1
        current_id = self.partial_generation_id

        def think():
            self.partial_lock = True
            print("🧠 Pensando com parcial...")
            resposta = self.brain.generate(texto)

            # só salva se for a geração mais recente
            if current_id == self.partial_generation_id:
                self.partial_response = resposta

            self.partial_lock = False

        self.partial_thread = threading.Thread(target=think, daemon=True)
        self.partial_thread.start()

    def handle_partial(self, texto):
        if texto == self.last_partial_sent:
            return
        if len(texto) < 30:
            return
        self.last_partial_sent = texto
        self.start_partial_thinking(texto)
    
    def talk_with_voice(self):
        texto_final = self.listener.ouvir_som()

        if not texto_final:
            return None
        
        if self.partial_response:
            print("Usando resposta parcial pronta!")
            resposta = self.partial_response
            self.partial_response = None
            return resposta
        
        print("Gerando resposta final...")
        return self.brain.generate(texto_final)