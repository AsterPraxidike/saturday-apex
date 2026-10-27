from datetime import datetime, timezone
import unittest
from schedule import broadcast_schedule


class ScheduleTests(unittest.TestCase):
    def info(self, instant, **overrides):
        return broadcast_schedule({'season': 'FALL 2026', 'seasonStart': '2026-10-03',
                                   'broadcastTimezone': 'America/Chicago', **overrides},
                                  datetime.fromisoformat(instant))

    def test_opening_saturday_and_subsequent_weeks(self):
        for instant, week in [('2026-10-03T12:00:00-05:00', 1),
                              ('2026-10-09T23:59:59-05:00', 1),
                              ('2026-10-10T00:00:00-05:00', 2),
                              ('2026-10-27T12:00:00-05:00', 4)]:
            self.assertEqual(self.info(instant)['week'], week)

    def test_timezone_boundary_and_dst(self):
        self.assertEqual(self.info('2026-10-10T04:59:59+00:00')['week'], 1)
        self.assertEqual(self.info('2026-10-10T05:00:00+00:00')['week'], 2)
        self.assertEqual(self.info('2026-11-07T05:59:59+00:00')['week'], 5)
        self.assertEqual(self.info('2026-11-07T06:00:00+00:00')['week'], 6)

    def test_before_season_is_week_zero(self):
        self.assertEqual(self.info('2026-10-02T23:59:59-05:00')['week'], 0)

    def test_invalid_anchor_or_timezone(self):
        for values in ({'seasonStart': '2026-10-04'}, {'seasonStart': 'bad'},
                       {'season': ''}, {'broadcastTimezone': 'unknown-zone'}):
            with self.assertRaises(ValueError):
                self.info('2026-10-03T12:00:00+00:00', **values)

    def test_halloween_break_keeps_week_four_then_advances_to_five(self):
        for day, week in [('2026-10-24', 4), ('2026-10-27', 4), ('2026-10-31', 4),
                          ('2026-11-06', 4), ('2026-11-07', 5), ('2026-11-14', 6)]:
            self.assertEqual(self.info(day+'T12:00:00-06:00', skippedSaturdays=['2026-10-31'])['week'], week)

    def test_multiple_breaks_and_dst_boundary(self):
        skipped = ['2026-10-31', '2026-11-14']
        self.assertEqual(self.info('2026-11-07T05:59:59+00:00', skippedSaturdays=skipped)['week'], 4)
        self.assertEqual(self.info('2026-11-07T06:00:00+00:00', skippedSaturdays=skipped)['week'], 5)
        self.assertEqual(self.info('2026-11-21T12:00:00+00:00', skippedSaturdays=skipped)['week'], 6)

    def test_bad_skip_dates_rejected(self):
        for skipped in (['2026-10-30'], ['2026-10-31', '2026-10-31'],
                        ['2026-10-03'], ['bad'], '2026-10-31'):
            with self.assertRaises(ValueError):
                self.info('2026-10-27T12:00:00+00:00', skippedSaturdays=skipped)

    def test_manual_week_fallback(self):
        self.assertEqual(broadcast_schedule({'week': 7})['week'], 7)
        self.assertIsNone(broadcast_schedule({})['week'])


if __name__ == '__main__':
    unittest.main()
