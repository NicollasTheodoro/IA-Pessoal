import json

class PersistentMemory:
    def __init__(self, file="memory.json"):
        self.file = file
        self.data = self.load()

    def load(self):
        try:
            with open(self.file, "r") as f:
                return json.load(f)
        except:
            return {}

    def save(self):
        with open(self.file, "w") as f:
            json.dump(self.data, f, indent=4)

    def store(self, key, value):
        self.data[key] = value
        self.save()

    def get(self, key):
        return self.data.get(key)