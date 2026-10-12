"""
Diagnóstico: descobre o que derruba o Ollama dentro da Alice.

Rode de dentro da pasta IA/ (use o mesmo modelo que a Alice usa):

    python teste_ollama.py phi3:mini     (ou sem nome: testa o modelo que a Alice usa)

Cada teste muda UMA coisa em relação ao anterior. O primeiro que falhar mostra o culpado.
"""
import sys
import time

from ollama import chat

from brain.acoes import Acoes
from brain.personality import Personality
from brain.prompt_builder import build_system_prompt

from brain.actions import MODELO as MODELO_DA_ALICE  # o mesmo modelo que a Alice usa de verdade

MODELO = sys.argv[1] if len(sys.argv) > 1 else MODELO_DA_ALICE
SISTEMA = build_system_prompt(Personality(), {}, Acoes().descricoes())


def testar(nome, msgs, **kw):
    t0 = time.time()
    try:
        texto = "".join(c["message"]["content"] for c in chat(model=MODELO, messages=msgs, stream=True, **kw))
        print(f"  PASSOU  {nome}  ({time.time() - t0:.1f}s)  -> {texto[:60]!r}")
        return True
    except Exception as e:
        print(f"  FALHOU  {nome}  -> {str(e)[:110]}")
        time.sleep(4)  # dá tempo do Ollama subir o runner de novo
        return False


oi = [{"role": "user", "content": "oi"}]
com_sistema = [{"role": "system", "content": SISTEMA}, {"role": "user", "content": "oi"}]
print(f"Modelo: {MODELO} | prompt de sistema da Alice: ~{len(SISTEMA) // 4} tokens\n")

print("1) Prompt curto, configuração padrão do Ollama")
a = testar("curto + padrão", oi, options={"num_predict": 20})

print("2) Prompt curto, com as opções da Alice (num_ctx 3072, keep_alive)")
b = testar("curto + opções da Alice", oi, options={"num_predict": 20, "num_ctx": 3072}, keep_alive="30m")

print("3) Prompt de sistema REAL da Alice, com as opções da Alice")
c = testar("prompt da Alice", com_sistema, options={"num_predict": 60, "num_ctx": 3072}, keep_alive="30m")

if not c:
    print("\nO teste 3 falhou. Testando variações para achar a saída:")
    testar("prompt da Alice, só CPU (num_gpu=0)", com_sistema, options={"num_predict": 60, "num_ctx": 3072, "num_gpu": 0})
    for lote in (256, 128, 64):
        testar(f"prompt da Alice, num_batch={lote}", com_sistema, options={"num_predict": 60, "num_ctx": 3072, "num_batch": lote})
    testar("prompt da Alice, num_ctx=2048", com_sistema, options={"num_predict": 60, "num_ctx": 2048})
    testar("prompt da Alice, num_ctx=4096", com_sistema, options={"num_predict": 60, "num_ctx": 4096})

print("\nMande esta saída inteira para mim.")