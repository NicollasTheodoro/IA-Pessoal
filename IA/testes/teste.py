import pyautogui
import time
import keyboard

print("Autoclicker iniciado!")
print("Pressione F6 para começar e F7 para parar.")

clicando = False

while True:
    if keyboard.is_pressed("F6"):
        clicando = True
        print("Clicando...")

    if keyboard.is_pressed("F7"):
        clicando = False
        print("Parado.")

    if clicando:
        pyautogui.click()
        time.sleep(0.01)  # velocidade do clique
