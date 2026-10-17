p = "IA/brain/actions.py"
s = open(p, encoding="utf-8").read()
a = s.index("        contexto = self.contexto()\n        try:")
b = s.index("        parser = StreamParser()")
NOVO = r'''        contexto = self.contexto()
        try:  # vazio se o usuario nao pediu para ela olhar a tela; um erro aqui nunca derruba a conversa
            tela = self.visao.contexto_para(user_input)
        except Exception as e:
            print("Visão de tela falhou:", e)
            tela = f"NA TELA AGORA: você NÃO conseguiu ver a tela ({str(e)[:120]}). Diga isso; não invente."
        sistema = build_system_prompt(self.personalidade, self.memory.data, self.acoes.descricoes(), contexto)
        historico, pergunta = self.messages, user_input
        if tela:
            print(f"[visão] {len(tela)} caracteres da tela entraram no prompt")
            historico = self.messages[-2:]
            pergunta = f"{user_input}\n\n---\n{tela}"
        msgs = [
            {"role": "system", "content": sistema},
            *historico,
            {"role": "user", "content": pergunta},
        ]

'''
if "[visão]" in s:
    raise SystemExit("O patch já foi aplicado.")
open(p, "w", encoding="utf-8", newline="").write(s[:a] + NOVO + s[b:])
print("OK: actions.py atualizado.")
