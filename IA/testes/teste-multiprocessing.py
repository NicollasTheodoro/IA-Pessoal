import multiprocessing

def tarefa():
    for i in range(10_000_000):
        pass

if __name__ == "__main__":
    p1 = multiprocessing.Process(target=tarefa)
    p2 = multiprocessing.Process(target=tarefa)

    p1.start()
    p2.start()

    p1.join()
    p2.join()