import copy
import json
from pathlib import Path
import unittest
from respawn import summarize, broadcast_patch, map_name

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = json.loads((ROOT / 'tests/fixtures/post-game-6.json').read_text())
SETTINGS = json.loads((ROOT / 'defaults.json').read_text())['screens']['standings']


class RespawnTests(unittest.TestCase):
    def test_actual_post_game_six_fixture(self):
        summary = summarize(FIXTURE, SETTINGS)
        self.assertEqual(summary['gamesPlayed'], 6)
        self.assertEqual(summary['ignoredAbandoned'], 1)
        self.assertEqual(summary['mapName'], "World's Edge")
        self.assertEqual([(t['name'], t['total']) for t in summary['rankings'][:3]],
                         [('Texas A&M Maroon', 105), ('Fisher Esports', 98), ('Ferris State', 74)])
        self.assertEqual(summary['gameWinners'][0]['name'], 'W&M Apex Legends')
        patch = broadcast_patch(summary, 6)
        self.assertEqual(patch['screens']['stream-ending']['champion'], 'Texas A&M Maroon')
        self.assertEqual(patch['screens']['game-winner']['teamName'], 'W&M Apex Legends')
        self.assertEqual(patch['screens']['standings']['resultsFrom'], 'manual')

    def test_result_order_deduplication_and_skip_games(self):
        source = copy.deepcopy(FIXTURE)
        source['matches'] = list(reversed(source['matches'])) + source['matches'][:1]
        summary = summarize(source, SETTINGS)
        self.assertEqual(summary['gamesPlayed'], 6)
        settings = {**SETTINGS, 'skipGames': [1]}
        summary = summarize(source, settings)
        self.assertEqual(summary['gamesPlayed'], 5)
        self.assertEqual(broadcast_patch(summary, 6)['screens']['stream-ending']['championLabel'], 'SERIES LEADER')

    def test_school_alias_and_adjustment(self):
        settings = {**SETTINGS, 'teams': [{'name': 'Texas A&M University', 'lobbyName': 'Texas A&M Maroon', 'adjust': -10}]}
        summary = summarize(FIXTURE, settings)
        team = next(t for t in summary['rankings'] if t['name'] == 'Texas A&M University')
        self.assertEqual(team['total'], 95)
        self.assertEqual(summary['rankings'][0]['name'], 'Fisher Esports')

    def test_bad_and_abandoned_only_results_rejected(self):
        for payload in ({}, {'matches': []}, {'matches': [FIXTURE['matches'][-1]]},
                        {'matches': [{'player_results': [{'kills': 0}]}]}):
            with self.assertRaises(ValueError):
                summarize(payload, SETTINGS)

    def test_map_ids_and_unknown_fallback(self):
        self.assertEqual(map_name('mp_rr_tropic_island_mu2_landscape'), 'Storm Point')
        self.assertEqual(map_name('mp_rr_district_mu1'), 'E-District')
        self.assertEqual(map_name('new-map'), 'new-map')

    def test_tied_series_champions_remain_tied(self):
        players = [{'teamNum': i, 'teamName': f'School {i}', 'teamPlacement': 2, 'kills': 3} for i in (1,2)]
        summary = summarize({'matches': [{'mid': 'tie', 'match_start': 1, 'map_name': 'mp_rr_district', 'player_results': players}]}, SETTINGS)
        self.assertEqual([t['rank'] for t in summary['rankings']], [1,1])
        patch = broadcast_patch(summary, 1)
        self.assertEqual(patch['screens']['stream-ending']['championLabel'], 'SERIES CO-CHAMPIONS')


if __name__ == '__main__':
    unittest.main()
