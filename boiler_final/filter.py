class Filter:
    def __init__(self):
        self.history = []
        self.history_len = 5;

    def filter(self, temps):
        self.history.extend(temps)
        self.history = self.history[-self.history_len:]
        return sum(self.history) / len(self.history)
        
    def set_history_len(self, length):
        self.history_len = length
