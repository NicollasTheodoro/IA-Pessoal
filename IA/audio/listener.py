import speech_recognition as sr


class Listener:
    def __init__(self):
        self.recognizer = sr.Recognizer()
        self.microfone = sr.Microphone()
        # self.recognizer.energy_threshold = 4000
        self.recognizer.pause_threshold = 1.5
        self.recognizer.dynamic_energy_threshold = True
        self.recognizer.non_speaking_duration = 1.0

    def ouvir_som(self):
        with self.microfone as source:
            print("Ajustando ruído ambiente...")
            self.recognizer.adjust_for_ambient_noise(source, duration=1)

            print("Fale algo:")
            audio = self.recognizer.listen(source)

        try:
            frase = self.recognizer.recognize_google(audio, language='pt-BR')
            print("Você disse:", frase)
            return frase

        except sr.UnknownValueError:
            print("Não entendi")
            return None

        except sr.RequestError as e:
            print("Erro na API:", e)
            return None