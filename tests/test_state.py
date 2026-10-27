import copy
from datetime import datetime
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

# Keep tests independent of operator data.
TEMP = tempfile.TemporaryDirectory()
os.environ['APEX_STATE_FILE'] = str(Path(TEMP.name) / 'state.json')
import app


class StateTests(unittest.TestCase):
    def setUp(self):
        app.STATE = copy.deepcopy(app.DEFAULTS)

    def test_shared_values_and_nested_colors(self):
        original = app.effective_settings('intermission')['colors']['white']
        app.update_state({'global': {'eventLine': 'FINALS', 'colors': {'red': '#123456'}}})
        for name in app.SCREENS:
            if 'eventLine' in app.DEFAULTS['screens'][name]:
                self.assertEqual(app.effective_settings(name)['eventLine'], 'FINALS')
            self.assertEqual(app.effective_settings(name)['colors']['red'], '#123456')
        self.assertEqual(app.effective_settings('intermission')['colors']['white'], original)

    def test_screen_changes_are_isolated_and_saved(self):
        before = app.effective_settings('starting-soon')
        app.update_state({'screens': {'intermission': {'footer': 'GAME 5'}}})
        self.assertEqual(app.effective_settings('intermission')['footer'], 'GAME 5')
        self.assertEqual(app.effective_settings('starting-soon'), before)
        self.assertEqual(json.loads(app.STATE_FILE.read_text()), app.STATE)

    def test_invalid_patch_does_not_mutate_state_or_file(self):
        app.update_state({'global': {'eventLine': 'FINALS'}})
        before = copy.deepcopy(app.STATE)
        saved = app.STATE_FILE.read_bytes()
        for patch in ({'screens': {'intermission': {'showTrivia': 'false'}}},
                      {'global': {'colors': []}}, {'global': []},
                      {'screens': {'unknown': {}}}, {'global': {'random': 'bad'}},
                      {'global': {'triviaSeconds': float('nan')}}):
            with self.assertRaises(ValueError):
                app.update_state(patch)
            self.assertEqual(app.STATE, before)
            self.assertEqual(app.STATE_FILE.read_bytes(), saved)

    def test_clear_shared_override(self):
        app.update_state({'global': {'season': 'FINALS'}})
        app.update_state({'global': {'season': None}})
        self.assertEqual(app.effective_settings('standings')['season'], app.DEFAULTS['screens']['standings']['season'])

    def test_broadcast_week_updates_every_label_and_map(self):
        app.update_state({'global': {'season': 'SPRING 2027', 'week': 2, 'mapName': "World's Edge"}})
        for name in ('starting-soon', 'intermission', 'standings', 'game-winner'):
            self.assertEqual(app.effective_settings(name)['season'], 'SPRING 2027')
            self.assertEqual(app.effective_settings(name)['eventLine'], 'REGULAR SEASON // WEEK 2')
        for name in ('starting-soon', 'intermission', 'stream-ending'):
            text = app.effective_settings(name)['sideText']
            self.assertIn('SPRING 2027', text)
            self.assertIn('WEEK 2', text)
        overlay = app.effective_settings('ingame-overlay')
        self.assertEqual(overlay['eventLine'], "SPRING 2027 WEEK 2 // World's Edge")
        app.update_state({'global': {'week': 3, 'mapName': 'Olympus'}})
        self.assertEqual(app.effective_settings('ingame-overlay')['eventLine'], 'SPRING 2027 WEEK 3 // Olympus')
        self.assertEqual(app.effective_settings('intermission')['eventLine'], 'REGULAR SEASON // WEEK 3')

    def test_broadcast_metadata_validation(self):
        for shared in ({'week': 0}, {'week': 2}, {'season': '', 'week': 2},
                       {'season': 'SPRING', 'week': True}, {'season': 'SPRING', 'week': 1.5},
                       {'phase': []}):
            with self.assertRaises(ValueError):
                app.update_state({'global': shared})
        self.assertEqual(app.STATE, app.DEFAULTS)

    def test_saturday_rollover_updates_live_labels_without_state_change(self):
        app.update_state({'global': {'season': 'FALL 2026', 'seasonStart': '2026-10-03'}})
        saved = copy.deepcopy(app.STATE)
        with patch('schedule.datetime') as clock:
            clock.now.return_value = datetime.fromisoformat('2026-10-09T23:59:59-05:00')
            self.assertEqual(app.effective_settings('intermission')['eventLine'], 'REGULAR SEASON // WEEK 1')
            clock.now.return_value = datetime.fromisoformat('2026-10-10T00:00:00-05:00')
            self.assertEqual(app.effective_settings('intermission')['eventLine'], 'REGULAR SEASON // WEEK 2')
            self.assertIn('WEEK 2', app.effective_settings('stream-ending')['sideText'])
        self.assertEqual(app.STATE, saved)

    def test_clear_week_restores_explicit_event_line(self):
        app.update_state({'global': {'season': 'SPRING', 'week': 2, 'eventLine': 'CUSTOM'}})
        self.assertEqual(app.effective_settings('standings')['eventLine'], 'REGULAR SEASON // WEEK 2')
        app.update_state({'global': {'week': None}})
        self.assertEqual(app.effective_settings('standings')['eventLine'], 'CUSTOM')

    def test_weekly_token_clears_previous_results_and_persists(self):
        app.update_state({'global': {'statsTokens': ['previous-test-token']}, 'screens': {
            'standings': {'teams': [{'name': 'School', 'lobbyName': 'Lobby', 'games': [[1, 5]]}]},
            'stream-ending': {'champion': 'School', 'rankings': [{'name': 'School'}]}}})
        app.configure_token('next-test-token')
        self.assertEqual(app.current_token(), 'next-test-token')
        self.assertEqual(app.STATE['screens']['standings']['teams'][0]['games'], [])
        self.assertEqual(app.STATE['screens']['standings']['teams'][0]['lobbyName'], 'Lobby')
        self.assertEqual(app.STATE['screens']['stream-ending']['champion'], '')
        self.assertEqual(app.STATE['screens']['stream-ending']['rankings'], [])
        self.assertEqual(json.loads(app.STATE_FILE.read_text())['global']['statsTokens'], ['next-test-token'])

    def test_polling_uses_variable_token_and_keeps_data_on_failure(self):
        fixture = json.loads((Path(__file__).parent / 'fixtures/post-game-6.json').read_text())
        app.update_state({'global': {'statsTokens': ['weekly-test-token']}})
        with patch('app.fetch_results', return_value=fixture) as fetch:
            app.poll_once()
            fetch.assert_called_once_with('weekly-test-token')
        self.assertEqual(app.STATE['screens']['stream-ending']['champion'], 'Texas A&M Maroon')
        saved = copy.deepcopy(app.STATE)
        with patch('app.fetch_results', side_effect=app.URLError('offline')):
            app.poll_once()
        self.assertEqual(app.STATE, saved)
        self.assertIn('previous results kept', app.FEED_STATUS['error'].lower())

    def test_arrays_replace_instead_of_merge(self):
        app.update_state({'screens': {'intermission': {'trivia': ['ONE FACT']}}})
        self.assertEqual(app.effective_settings('intermission')['trivia'], ['ONE FACT'])


if __name__ == '__main__':
    unittest.main()
