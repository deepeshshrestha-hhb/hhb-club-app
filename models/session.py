class Session:
    def __init__(self, id, date, source="manual", notes=None):
        self.id = id
        self.date = date
        self.source = source
        self.notes = notes
