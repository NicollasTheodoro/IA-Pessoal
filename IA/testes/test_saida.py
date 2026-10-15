"""O erro 'charmap' codec can't encode '\\U0001f3a7' (python -m unittest testes.test_saida, dentro da pasta IA).
Cada teste roda num processo separado com a saída redirecionada em cp1252, igual ao Windows sem console."""
import os
import subprocess
import sys
import tempfile
import textwrap
import unittest

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, RAIZ)


def rodar(codigo, cp1252=True, extra_env=None):
    env = {**os.environ, "ALICE_DADOS": tempfile.mkdtemp(), "PYTHONPATH": RAIZ, **(extra_env or {})}
    env.pop("PYTHONUTF8", None)
    if cp1252:
        env["PYTHONIOENCODING"] = "cp1252"  # o que o Python usa no Windows quando a saída não é um console
    return subprocess.run([sys.executable, "-c", textwrap.dedent(codigo)], cwd=RAIZ, env=env,
                          capture_output=True, timeout=60)


class SaidaUtf8(unittest.TestCase):
    def test_reproduz_o_erro_do_usuario_sem_a_correcao(self):
        r = rodar("print('🎧 Ouvindo...')")
        self.assertNotEqual(r.returncode, 0)
        self.assertIn(b"charmap", r.stderr)

    def test_com_a_correcao_o_emoji_sai_em_utf8(self):
        r = rodar("""
            from brain.saida import forcar_utf8
            forcar_utf8()
            print('🎧 Ouvindo... ⏰ ação')
        """)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(r.stdout.decode("utf-8").strip(), "🎧 Ouvindo... ⏰ ação")

    def test_sem_console_nao_quebra(self):
        r = rodar("""
            import sys
            sys.stdout = sys.stderr = None  # pythonw: sem console
            from brain.saida import forcar_utf8
            forcar_utf8()
            print('🎧')
            print('ok', file=open(__import__('os').devnull, 'w'))
        """)
        self.assertEqual(r.returncode, 0, r.stderr)

    def test_o_listener_de_verdade_nao_quebra_com_saida_cp1252(self):
        """Exatamente o caminho do erro: ouvir_som() imprime '🎧 Ouvindo...' (microfone e Whisper simulados)."""
        r = rodar("""
            import testes.test_voz as tv   # instala o sounddevice/faster_whisper falsos
            tv.FluxoFalso.roteiro = [(0.002, 5), (0.2, 12)]
            from audio.listener import Listener
            l = Listener(); l.silence_time_limit = 0.15
            print('RESULTADO:', l.ouvir_som(espera_max=5))
        """)
        self.assertEqual(r.returncode, 0, r.stderr.decode("utf-8", "replace")[-600:])
        saida = r.stdout.decode("utf-8")
        self.assertIn("🎧 Ouvindo...", saida)
        self.assertIn("RESULTADO: olá alice", saida)

    def test_lembrete_com_emoji_nao_derruba_o_servidor(self):
        r = rodar("""
            import sys, types
            sys.modules['ollama'] = types.SimpleNamespace(chat=lambda **k: None)
            import server
            server.notificar('⏰ Lembrete: ligar pro banco 🎧')
            print('NOTIFICOU')
        """)
        self.assertEqual(r.returncode, 0, r.stderr.decode("utf-8", "replace")[-600:])
        self.assertIn("NOTIFICOU", r.stdout.decode("utf-8"))

    def test_servidor_ligado_pelo_pet_recebe_utf8_no_ambiente(self):
        import pet_logic as L
        import socket
        with socket.socket() as s:
            s.bind(("127.0.0.1", 0))
            porta = s.getsockname()[1]
        d = tempfile.mkdtemp()
        marca = os.path.join(d, "env.txt")
        script = os.path.join(d, "fake_server.py")
        with open(script, "w") as f:
            f.write(textwrap.dedent(f"""
                import json, os
                from http.server import BaseHTTPRequestHandler, HTTPServer
                open({marca!r}, "w").write(os.environ.get("PYTHONUTF8", "") + "|" + os.environ.get("PYTHONIOENCODING", ""))
                class H(BaseHTTPRequestHandler):
                    def do_GET(self):
                        b = b"{{}}"
                        self.send_response(200); self.send_header("Content-Type", "application/json"); self.end_headers(); self.wfile.write(b)
                    def log_message(self, *a): pass
                HTTPServer(("127.0.0.1", {porta}), H).serve_forever()
            """))
        proc = L.garantir_servidor(L.Cliente(f"http://127.0.0.1:{porta}"), script, d, espera=15)
        try:
            with open(marca) as f:
                self.assertEqual(f.read(), "1|utf-8")
        finally:
            proc.terminate()
            proc.wait(5)


if __name__ == "__main__":
    unittest.main()
