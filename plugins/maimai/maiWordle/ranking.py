import shelve

from dill import Pickler, Unpickler

shelve.Pickler = Pickler
shelve.Unpickler = Unpickler


class Ranking(object):
    def __init__(self):
        self.data_path = "./data/wordle_ranking.db"

    async def add_score(
        self,
        user_id: int,
        oc_times: int,
        it_times: int,
        pt_times: int,
        is_guesser: bool,
    ):
        obj = {
            "oc_times": oc_times,
            "it_times": it_times,
            "pt_times": pt_times,
            "is_guesser": is_guesser,
        }
        with shelve.open(self.data_path) as data:
            if str(user_id) in data:
                rank_data = data[str(user_id)]
                rank_data.append(obj)
                data[str(user_id)] = rank_data
                return

            data.setdefault(str(user_id), [obj])

    async def get_avg_scores(self):
        achis = list()
        with shelve.open(self.data_path) as data:
            for user_id in data.keys():
                l = len(data[user_id])
                if l <= 0:
                    continue

                scores = [self._compute_score(**d) for d in data[user_id]]
                achi = sum(scores) / l
                achis.append((user_id, achi, l))

        achis.sort(key=lambda x: x[1], reverse=True)

        return achis

    async def get_score(self, user_id):
        with shelve.open(self.data_path) as data:
            if str(user_id) in data:
                l = len(data[user_id])
                scores = [self._compute_score(**d) for d in data[str(user_id)]]
                achi = sum(scores) / l
                return (achi, l)

        return (0.0, 0)

    def _compute_score(
        self, oc_times: int, it_times: int, pt_times: int, is_guesser: bool
    ):
        score = 1.01
        if oc_times <= 0:
            score *= 1.002

        if pt_times > 0:
            score *= 0.991**pt_times
        elif it_times > 0:
            score *= 0.995**it_times

        if not is_guesser:
            score *= 0.98

        return score


ranking = Ranking()