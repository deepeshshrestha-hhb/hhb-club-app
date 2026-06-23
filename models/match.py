class Match:
    def __init__(self, id, tournament_id, team1, team2, score=None):
        self.id = id
        self.tournament_id = tournament_id
        self.team1 = team1
        self.team2 = team2
        self.score = score
