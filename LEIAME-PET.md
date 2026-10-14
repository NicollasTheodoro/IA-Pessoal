# Alice, desktop pet

Ela fica na sua tela, por cima das janelas, com as 10 poses do pacote de expressões, e
conversa, reage e muda de cara sozinha. A interface web (navegador) usa as **mesmas** expressões.

## Como ligar
1. Uma vez: `pip install PySide6` (ou clique em `iniciar_pet.bat`, que instala sozinho).
2. `python IA\pet.py`, ou dois cliques em `iniciar_pet.bat`.

Se o servidor (`server.py`) ainda não estiver no ar, o pet liga ele sem janela de console e o
desliga ao sair (só se foi o pet que ligou). Se você já roda o servidor, ele só conecta.
Opções: `--sem-servidor`, `--servidor http://...`, `--escala 1.0`.

> **Aviso honesto:** eu não consegui abrir uma janela Qt no ambiente onde escrevi isso. A lógica
> (emoções, conversa com o servidor, fila de expressões, balão, queda, passeio) tem testes que
> passam, e a janela foi executada com um Qt de mentira, mas **a primeira vez com o PySide6 de
> verdade é no seu PC**. Se algo ficar estranho (transparência, fonte, posição), me diga o que viu.

## O que fazer com ela
| Ação | Resultado |
|---|---|
| Clique | cutuca. Uma vez ela é simpática; várias seguidas e ela se irrita |
| Duplo clique | abre a caixa de texto (Enter envia, Esc ou clicar fora fecha) |
| Arrastar | muda de lugar; solta no ar e ela cai e quica |
| Botão direito | menu: conversar, expressões, ritmo, dormir/acordar, tamanho, passear, ações do PC, sempre por cima |
| Ícone na bandeja | mostrar, esconder, conversar, sair |

Lembretes aparecem num balão amarelo (clique nela para dispensar). No menu, **"Executar ações do
PC ao conversar"** vem ligado: o pet é no seu PC, então "pula esse vídeo" ou "abre o youtube"
funcionam direto. Desligue se preferir.

## As emoções (16, antes eram 4)
Como o pacote tem 10 poses, algumas emoções reaproveitam a pose e se diferenciam pelo movimento
e pelas partículas.

| Emoção | Pose | Movimento / extra |
|---|---|---|
| Neutra · Desconfiada | séria | respira · inclina a cabeça |
| Animada · Brincalhona | piscadinha | pula leve ✨ · balança ♪ |
| Vitoriosa | paz e amor | pula 🎉✨ |
| Apaixonada | encantada | balança ♥ |
| Ideia! | apontando | pula leve 💡 |
| Irritada | brava | treme |
| Entediada · Confusa | entediada | respira · inclina ❓ |
| Sonolenta · Dormindo | sonolenta | cochila · cochila 💤 |
| Espreguiçando | bocejo | estica |
| Tímida · Chorosa · Carente | tímida | encolhe · treme leve 💧 · balança ♥ |

Para ver todas: menu do pet > Expressões, ou na interface web o painel "Expressões".

## Por que a troca parece natural
- **Reage a você antes de responder**: "oi" anima, elogio deixa tímida ou apaixonada, xingamento
  irrita, comando vira "ideia", "boa noite" dá sono.
- **Uma emoção por frase**: o modelo marca cada frase com `<emo:nome>` (a tag não é falada nem
  aparece). Se ele esquecer, as palavras e a pontuação da frase decidem. Com voz, a expressão
  muda quando a frase **começa a ser falada**.
- **Parada, ela vive**: troca a cada poucos segundos para uma emoção "vizinha" da atual
  (animada vai para brincalhona, não direto para irritada). Os traços do painel (carinho,
  energia, sarcasmo, paciência) e o humor inclinam as escolhas, e ela raramente se irrita sem motivo.
- **Escada do sono**: ~1:40 sem você e vem o tédio; ~4:20 ela espreguiça e boceja; ~10 min dorme
  (metade do tempo de madrugada). Ao falar com ela, acorda espreguiçando e só depois reage.
  A primeira conversa do dia também começa com um espreguiçar.
- **Ritmo**: menu do pet > Ritmo (Parada, Calma, Normal, Animada). Para definir ao ligar o
  servidor: `$env:ALICE_EMO_RITMO="2"` (2 = mais calma, 0.6 = mais agitada, 0 = só reage).

## Onde ajustar
- Tempos, vizinhanças e pesos: `IA/brain/emocoes.py` (`EMOCOES` tem a duração de cada emoção,
  `VIZINHAS` quem vai para quem, `T_TEDIO`/`T_BOCEJO`/`T_SONO`/`T_DORME` a escada do sono).
- O que ela diz em cada humor: exemplos em `IA/brain/prompt_builder.py`.
- Sprites: `IA/static/pet/*.png` (fundo já recortado). Para uma pose nova, ponha o PNG ali e
  aponte `sprite` da emoção em `EMOCOES`; pet e navegador passam a usar.
- Tamanho, passear, posição: salvos em `~/.alice_pet.json`.

## Limites
- 10 poses sem boca animada: a "vida" vem de troca de pose, movimento e partículas.
- Os sprites têm 320 px: em "Enorme" ficam um pouco suaves.
- O qwen2.5:7b às vezes erra a tag `<emo:>` ou esquece; o plano B por palavras cobre, mas pode
  ficar menos preciso (ironia, por exemplo).
- Jogos em tela cheia exclusiva escondem qualquer janela; use o modo janela sem bordas ou
  "Esconder" na bandeja.
- A caixa de texto do pet usa o teclado. Voz continua pelo microfone do servidor/navegador.

## Testes
Dentro da pasta `IA`:
`python -m unittest testes.test_emocoes testes.test_integracao_pet testes.test_pet_logic testes.test_pet_janela`
