# Alice no celular, agenda, clima e planilhas

Nenhuma biblioteca nova: tudo usa o que o Python já tem (SQLite, urllib).
Só o `pyautogui` (que você já usa) precisa estar instalado para pular vídeo.

## 1. Usar a Alice pelo celular

A Alice controla o seu PC, então o acesso de fora é protegido por **senha**
(`ALICE_TOKEN`). O servidor se recusa a abrir para a rede sem ela.

**Recomendado: Tailscale** (grátis, sem abrir porta no roteador, tráfego criptografado).

1. Instale o Tailscale no PC e no celular e entre na mesma conta.
2. Veja o IP do PC no app (algo como `100.64.12.34`).
3. Gere uma senha longa:
   `python -c "import secrets; print(secrets.token_urlsafe(24))"`
4. No PowerShell, na pasta do projeto:

```powershell
$env:ALICE_HOST="0.0.0.0"
$env:ALICE_TOKEN="cole-a-senha-aqui"
python IA\server.py
```

5. No celular, abra `http://100.64.12.34:5000` (o IP do passo 2).
6. Abra o menu ☰, preencha **Senha de acesso** e marque
   **"Executar as ações que a Alice decidir sozinha"** (essa caixa vale por aparelho).
   Deixe o campo "Servidor" vazio.

Se o Windows perguntar sobre o Firewall, permita só em **rede privada**.
Não use `ALICE_HOST=0.0.0.0` em Wi-Fi público sem o Tailscale.
Não ponha a Alice atrás de proxy ou túnel público (ngrok etc.): o servidor
confia em quem chega pelo próprio PC.

A voz do Murf toca no PC. No celular o texto aparece normalmente; o microfone do
navegador do celular só funciona em HTTPS, então por lá use o teclado (ou o ditado
do teclado do celular).

### Lembretes no celular com a página fechada (opcional)
1. Instale o app **ntfy** no celular e assine um tópico difícil de adivinhar
   (ex.: `alice-x7k2q9m4`).
2. Antes de ligar o servidor: `$env:ALICE_NTFY="alice-x7k2q9m4"`

Os lembretes chegam como notificação normal. O texto passa pelo servidor público
do ntfy.sh, então evite coisas sensíveis nos lembretes se isso te incomoda.

## 2. O que dá para pedir

| Você diz | O que acontece |
|---|---|
| "me lembra amanhã às 9h de ligar pro banco" | agenda (`amanhã 9h`, `sexta 14h`, `dia 20 às 18h`, `20/10 7:30`, `daqui a 2 horas`) |
| "me lembra de beber água em 20 minutos" | lembrete rápido |
| "cancela o lembrete do banco" | remove da agenda |
| "anota: comprar ração" | grava em `notas.txt` |
| "o que eu anotei?" / "o que tenho na agenda?" | ela responde pelo que sabe (últimas 6 anotações e próximos 5 avisos) |
| "vai chover hoje?" / "que horas são?" | usa o clima e a hora atuais |
| "mostra o clima na tela" | deixa um cartão no Painel |
| "pula esse vídeo" / "volta o vídeo" | tecla de mídia no PC |
| "comi 150g de arroz cozido no almoço" | grava em Alimentação e calcula kcal e macros |
| "comi 2 ovos fritos, deu 250 kcal" | usa as suas kcal e distribui os macros |
| "ganhei 200 reais num bico" | grava em Financeiro |
| "corri 5 km em 30 minutos" | grava em Treinos |
| "me pesei, 79,8" | grava em Peso e altura |
| "estudei python por 1h30" | grava em Estudo |

Tudo também pode ser lançado à mão na aba **Planilhas** (com gráfico, lista e
botão de CSV, que abre direto no Excel).

### Esconder o dinheiro na tela
No **Painel**, o cartão "Ganhos no mês" tem um olhinho (👁 / 🙈). Clique para ocultar: o valor vira
`R$ ••••••`. O mesmo interruptor vale na aba **Planilhas > Financeiro** (coluna de valores e
gráfico ocultos, e a confirmação de "Registrado" não mostra o valor). A escolha fica salva no
navegador, então vale também depois de recarregar a página. Cada aparelho (PC, celular) guarda a sua.
Atenção: isso esconde só a **tela**. Se você perguntar "quanto ganhei?", a Alice responde com o
valor, e o CSV exportado e o arquivo `dados/alice.db` continuam com os números.

## 3. Limites que vale saber
- **Macros são estimativas.** A conta é feita pelo Python com uma tabela de ~45
  alimentos brasileiros (`brain/nutricao.py`, valores aproximados). Alimento fora
  da tabela: se você disser as calorias, ela guarda só elas; senão pede ao modelo
  uma estimativa (mais lenta e menos confiável).
- **Pular vídeo** usa a tecla de mídia, que na maioria dos casos funciona com o
  YouTube em segundo plano. Se não pular no seu navegador, use
  `$env:ALICE_PULAR="youtube"` (Shift+N; a aba precisa estar em foco).
- **Clima**: padrão Nova Iguaçu. Mude com `ALICE_CIDADE`, `ALICE_LAT`, `ALICE_LON`.
- **Lembretes só disparam com o PC e o servidor ligados.** Os que passaram nesse
  tempo avisam assim que ela volta ("Lembrete atrasado").
- O qwen2.5:7b na CPU às vezes erra o formato de uma ação. Se registrar algo
  errado, apague na aba Planilhas. Dá para ajustar os exemplos em `prompt_builder.py`.
- O contexto do modelo subiu de 3072 para 4096 (o prompt agora leva agenda, clima
  e resumo). Se ficar pesado na sua máquina, volte em `actions.py` (`num_ctx`).

## 4. Onde ficam os dados
`dados/alice.db` (planilhas) e `dados/agenda.json`, na pasta de onde você roda o
servidor. O `.gitignore` já impede de subir isso para o GitHub. Atenção: o
`memory.json` e o `notas.txt` que já estão no repositório podem ter informação
pessoal; considere tirá-los do Git.

## 5. Criar uma tabela ou coluna nova
Edite só o dicionário `TABELAS` em `IA/brain/dados.py`. A interface, os gráficos e a
Alice passam a enxergar a tabela sozinhos; colunas novas entram no banco na próxima
vez que você ligar.
