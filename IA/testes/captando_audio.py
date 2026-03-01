import speech_recognition as sr
import os
import pyautogui as pg

def ouvir_mic():
    microfone = sr.Recognizer()


    with sr.Microphone() as source:

        microfone.adjust_for_ambient_noise(source)


        print("fale algo")

        audio = microfone.listen(source)

    try:

        frase = microfone.recognize_google(audio,language='pt-br')


        if "abra o navegador" in frase.lower():
            os.system("start opera")

        if "abre o navegador" in frase.lower():
            os.system("start opera")

        if "iniciar jogo" in frase.lower():
            os.system('start "" "D:\JOGOS\ZenlessZoneZero\HYP.exe"')
            pg.press("tab")
            pg.press("tab")
            pg.press("enter")

        
        print("\n", frase)

    except sr.UnknownValueError:
        print("Não entendi")
    
    return frase