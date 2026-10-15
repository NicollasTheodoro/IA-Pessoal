"""
Mede, NA SUA MÁQUINA, qual configuração deixa a Alice mais rápida: só CPU ou com a GT 740.

Rode de dentro da pasta IA/ :

    python benchmark_gpu.py                 (usa o modelo padrão da Alice)
    python benchmark_gpu.py qwen2.5:7b      (ou outro modelo)

Para testar a GPU, o servidor do Ollama precisa ter sido iniciado com Vulkan ligado
(feche o Ollama da bandeja e rode no PowerShell):

    $env:OLLAMA_VULKAN="1"
    $env:GGML_VK_VISIBLE_DEVICES="0"     # índice da GT 740 (se a UHD 630 for escolhida, troque por 1)
    ollama serve

O que cada número significa:
    leitura do prompt  = tokens/s ao ler o prompt novo (define o tempo até a 1ª palavra)
    geração            = tokens/s ao escrever a resposta (define a velocidade da fala)
    1ª frase (cache)   = tempo total de uma fala normal, com o prompt fixo já no cache

Quanto MAIOR tok/s e MENOR o tempo, melhor.
"""
import os
import sys
import time

from ollama import chat, ps

from brain.acoes import Acoes
from brain.actions import MODELO as MODELO_DA_ALICE
from brain.personality import Personality
from brain.prompt_builder import build_prompt_parts

MODELO = sys.argv[1] if len(sys.argv) > 1 else MODELO_DA_ALICE
FIXO, VARIAVEL = build_prompt_parts(Personality(), {}, Acoes().descricoes())

CONFIGS = [
    ("CPU, 4 threads (padrão)", {"num_gpu": 0, "num_thread": 4}),
    ("CPU, 8 threads", {"num_gpu": 0, "num_thread": 8}),
    ("GPU inteira (num_gpu=999)", {"num_gpu": 999, "num_thread": 4}),
    ("GPU parcial (num_gpu=16)", {"num_gpu": 16, "num_thread": 4}),
]


def _chamar(sistema, pergunta, opcoes):
    t0 = time.time()
    r = chat(
        model=MODELO,
        messages=[{"role": "system", "content": sistema}, {"role": "user", "content": pergunta}],
        options={"num_predict": 60, "num_ctx": 4096, "temperature": 0.7, **opcoes},
        keep_alive="10m",
    )
    return r, time.time() - t0


def _tps(n, ns):
    return n / (ns / 1e9) if n and ns else 0.0


def _onde_roda():
    """Quanto do modelo está na GPU, segundo o próprio Ollama."""
    try:
        for m in ps()["models"]:
            nome = getattr(m, "model", None) or getattr(m, "name", "") or ""
            if nome.startswith(MODELO.split(":")[0]):
                total, vram = m["size"], m.get("size_vram", 0)
                return f"{100 * vram / total:.0f}% na GPU" if total else "?"
    except Exception:
        pass
    return "?"


def medir(nome, opcoes):
    print(f"\n>>> {nome}")
    try:
        # 1) carrega o modelo com esta configuração (não conta no resultado)
        chat(model=MODELO, messages=[{"role": "user", "content": "oi"}],
             options={"num_predict": 1, "num_ctx": 4096, **opcoes}, keep_alive="10m")
        onde = _onde_roda()

        # 2) prompt NOVO (nonce no começo impede o cache): mede leitura do prompt e geração
        nonce = f"[{time.time():.3f}] "
        r, _ = _chamar(nonce + FIXO + VARIAVEL, "me conta uma piada curta", opcoes)
        leitura = _tps(r.get("prompt_eval_count"), r.get("prompt_eval_duration"))
        geracao = _tps(r.get("eval_count"), r.get("eval_duration"))

        # 3) mesma situação de uma fala normal: prompt fixo já no cache
        _, t_cache = _chamar(nonce + FIXO + VARIAVEL, "que dia é hoje?", opcoes)

        print(f"    onde roda: {onde}")
        print(f"    leitura do prompt: {leitura:6.1f} tok/s")
        print(f"    geração:           {geracao:6.1f} tok/s")
        print(f"    fala com cache:    {t_cache:6.1f} s")
        return {"nome": nome, "geracao": geracao, "cache": t_cache, "opcoes": opcoes, "onde": onde}
    except Exception as e:
        print(f"    FALHOU: {str(e)[:140]}")
        time.sleep(4)  # dá tempo do Ollama subir o runner de novo
        return None


if __name__ == "__main__":
    print(f"Modelo: {MODELO}  |  prompt fixo ~{len(FIXO) // 3} tokens")
    print(f"OLLAMA_VULKAN={os.getenv('OLLAMA_VULKAN', '(não definido aqui)')}  "
          "(o que vale é a variável do processo `ollama serve`)")
    resultados = [r for r in (medir(n, o) for n, o in CONFIGS) if r]

    if not resultados:
        raise SystemExit("\nNenhuma configuração funcionou. O Ollama está aberto e o modelo instalado?")

    print("\n================ RESUMO ================")
    for r in sorted(resultados, key=lambda r: r["cache"]):
        print(f"{r['cache']:5.1f} s   {r['geracao']:5.1f} tok/s   {r['nome']}   ({r['onde']})")

    melhor = min(resultados, key=lambda r: r["cache"])
    print(f"\nMais rápida: {melhor['nome']}")
    g = melhor["opcoes"]["num_gpu"]
    print("Para usar na Alice, no PowerShell antes de iniciar:")
    print(f'    $env:ALICE_GPU="{g}"')
    print(f'    $env:ALICE_THREADS="{melhor["opcoes"]["num_thread"]}"')
    if g:
        print("    (e o Ollama precisa estar rodando com OLLAMA_VULKAN=1)")
