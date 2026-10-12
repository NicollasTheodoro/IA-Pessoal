import json
import os

MAX_ITENS = 40


def _consertar(s):
    """Repara texto UTF-8 que foi lido como latin-1 (ex.: 'NÃ­collas' -> 'Nícollas')."""
    if isinstance(s, str) and ("Ã" in s or "Â" in s):
        try:
            return s.encode("latin-1").decode("utf-8")
        except (UnicodeEncodeError, UnicodeDecodeError):
            return s
    return s


class PersistentMemory:
    def __init__(self, file="memory.json"):
        self.file = file
        self.data = self.load()

    def load(self):
        try:
            with open(self.file, "r", encoding="utf-8") as f:
                bruto = json.load(f)
        except FileNotFoundError:
            return {}
        except Exception as e:
            print("Não consegui ler o memory.json:", e)
            return {}
        return {_consertar(k): _consertar(v) for k, v in bruto.items()}

    def save(self):
        tmp = self.file + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(self.data, f, indent=4, ensure_ascii=False)
        os.replace(tmp, self.file)  # troca atômica: nunca deixa o arquivo pela metade

    def store(self, key, value):
        key = str(key).strip()[:40]
        value = str(value).strip()[:200]
        if not key or not value:
            return
        if key not in self.data and len(self.data) >= MAX_ITENS:
            self.data.pop(next(iter(self.data)))  # descarta a mais antiga
        self.data[key] = value
        self.save()

    def get(self, key):
        return self.data.get(key)