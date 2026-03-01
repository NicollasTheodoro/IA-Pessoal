import speech_recognition as sr

entrada = sr.Recognizer()
entrada.energy_threshold = 4000

with sr.Microphone() as source:

        entrada.adjust_for_ambient_noise(source)


        print("fale algo")

        audio = entrada.listen(source)

try:
    frase = entrada.recognize_google(audio,language='pt-br')
    print(frase)

except sr.UnknownValueError:
      print("Não entendi")
       