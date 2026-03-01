import threading
import time

def tarefa():
    for i in range(5):
        print("Rodando tarefa...")
        time.sleep(1)

thread = threading.Thread(target=tarefa)
thread.start()

print("Programa continua executando...")