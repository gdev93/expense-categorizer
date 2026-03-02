from django.test import TestCase, override_settings
from decimal import Decimal
from processors.stats import calculate_ama_from_history, ForecastInput
from api.privacy_utils import decrypt_value

class TestKAMA(TestCase):

    def test_kama(self):
        """Test with real-world inputs from the issue description"""
        # Case 1: Abbonamenti
        abbonamenti_inputs = [
            ForecastInput(amount=19.89, date='2026-02-04'), ForecastInput(amount=34.8, date='2026-01-08'),
            ForecastInput(amount=29.99, date='2026-01-07'), ForecastInput(amount=19.89, date='2026-01-07'),
            ForecastInput(amount=5.99, date='2026-01-01'), ForecastInput(amount=14.64, date='2025-12-09'),
            ForecastInput(amount=34.8, date='2025-12-08'), ForecastInput(amount=5.99, date='2025-12-02'),
            ForecastInput(amount=84.99, date='2025-11-29'), ForecastInput(amount=4.88, date='2025-11-25'),
            ForecastInput(amount=34.8, date='2025-11-10'), ForecastInput(amount=5.0, date='2025-11-04'),
            ForecastInput(amount=34.8, date='2025-10-08'),
            ForecastInput(amount=4.99, date='2025-10-06'), ForecastInput(amount=34.8, date='2025-09-08'),
            ForecastInput(amount=25.8, date='2025-09-08'), ForecastInput(amount=5.0, date='2025-08-19'),
            ForecastInput(amount=34.8, date='2025-08-08'), ForecastInput(amount=4.99, date='2025-08-06'),
            ForecastInput(amount=5.0, date='2025-07-30'), ForecastInput(amount=50.0, date='2025-07-30'),
            ForecastInput(amount=4.99, date='2025-07-08'), ForecastInput(amount=34.8, date='2025-07-08'),
            ForecastInput(amount=48.0, date='2025-06-16'), ForecastInput(amount=34.8, date='2025-06-09'),
            ForecastInput(amount=4.99, date='2025-06-06'), ForecastInput(amount=4.99, date='2025-06-06'),
            ForecastInput(amount=31.9, date='2025-05-08'), ForecastInput(amount=4.99, date='2025-04-08')
        ]
        kama = calculate_ama_from_history(abbonamenti_inputs)

        # Case 2: Affitto
        affitto_inputs = [
            ForecastInput(amount=765.0, date='2026-02-04'), ForecastInput(amount=765.0, date='2026-01-05'),
            ForecastInput(amount=765.0, date='2025-12-04'), ForecastInput(amount=765.0, date='2025-11-04'),
            ForecastInput(amount=765.0, date='2025-10-06'), ForecastInput(amount=765.0, date='2025-09-04'),
            ForecastInput(amount=765.0, date='2025-08-04'), ForecastInput(amount=765.0, date='2025-07-04'),
            ForecastInput(amount=765.0, date='2025-06-03'), ForecastInput(amount=765.0, date='2025-05-02'),
            ForecastInput(amount=765.0, date='2025-04-01'), ForecastInput(amount=765.0, date='2025-03-04'),
            ForecastInput(amount=765.0, date='2025-02-03'), ForecastInput(amount=765.0, date='2025-01-02')
        ]

        # Case 3: Spesa (highly frequent)
        spesa_inputs = [
            ForecastInput(amount=6.29, date='2026-02-14'), ForecastInput(amount=9.0, date='2026-02-14'),
            ForecastInput(amount=35.0, date='2026-02-14'), ForecastInput(amount=17.4, date='2026-02-14'),
            ForecastInput(amount=7.75, date='2026-02-13'), ForecastInput(amount=6.58, date='2026-02-09'),
            ForecastInput(amount=3.33, date='2026-02-08'), ForecastInput(amount=8.3, date='2026-02-07'),
            ForecastInput(amount=27.27, date='2026-02-07'), ForecastInput(amount=40.85, date='2026-02-07'),
            ForecastInput(amount=4.64, date='2026-02-05'), ForecastInput(amount=3.46, date='2026-02-02'),
            ForecastInput(amount=3.0, date='2026-01-31'), ForecastInput(amount=15.9, date='2026-01-31'),
            ForecastInput(amount=26.02, date='2026-01-31'), ForecastInput(amount=10.13, date='2026-01-29'),
            ForecastInput(amount=13.3, date='2026-01-27'), ForecastInput(amount=20.34, date='2026-01-25'),
            ForecastInput(amount=10.85, date='2026-01-25'), ForecastInput(amount=36.76, date='2026-01-24'),
            ForecastInput(amount=1.58, date='2026-01-22'), ForecastInput(amount=5.79, date='2026-01-19'),
            ForecastInput(amount=0.73, date='2026-01-19'), ForecastInput(amount=25.37, date='2026-01-17'),
            ForecastInput(amount=5.49, date='2026-01-16'), ForecastInput(amount=8.85, date='2026-01-15'),
            ForecastInput(amount=4.84, date='2026-01-14'), ForecastInput(amount=2.96, date='2026-01-12'),
            ForecastInput(amount=3.61, date='2026-01-12'), ForecastInput(amount=15.8, date='2026-01-10')
        ]

        # Case 4: Bollette
        bollette_inputs = [
            ForecastInput(amount=9.38, date='2026-01-28'), ForecastInput(amount=16.6, date='2026-01-02'),
            ForecastInput(amount=85.01, date='2025-12-30'), ForecastInput(amount=61.95, date='2025-11-18'),
            ForecastInput(amount=54.69, date='2025-11-18'), ForecastInput(amount=54.69, date='2025-10-16'),
            ForecastInput(amount=47.18, date='2025-10-16'), ForecastInput(amount=88.0, date='2025-10-08'),
            ForecastInput(amount=104.62, date='2025-10-04'), ForecastInput(amount=145.74, date='2025-09-30'),
            ForecastInput(amount=54.69, date='2025-09-16'), ForecastInput(amount=87.0, date='2025-09-08'),
            ForecastInput(amount=54.69, date='2025-08-18'), ForecastInput(amount=61.95, date='2025-07-21'),
            ForecastInput(amount=54.69, date='2025-07-21'), ForecastInput(amount=87.0, date='2025-07-08'),
            ForecastInput(amount=31.3, date='2025-07-04'), ForecastInput(amount=54.69, date='2025-06-18'),
            ForecastInput(amount=61.95, date='2025-06-18'), ForecastInput(amount=111.43, date='2025-06-06'),
            ForecastInput(amount=54.69, date='2025-05-19'), ForecastInput(amount=61.95, date='2025-05-19'),
            ForecastInput(amount=64.92, date='2025-04-16'), ForecastInput(amount=48.22, date='2025-04-16'),
            ForecastInput(amount=87.0, date='2025-04-08'), ForecastInput(amount=48.22, date='2025-03-18'),
            ForecastInput(amount=64.92, date='2025-03-18'), ForecastInput(amount=64.92, date='2025-02-18'),
            ForecastInput(amount=48.22, date='2025-02-18'), ForecastInput(amount=48.22, date='2025-01-17')
        ]
        # Case 5: Trasporti
        trasporti_inputs = [
            ForecastInput(amount=2.16, date='2026-02-04'), ForecastInput(amount=0.03, date='2026-02-04'),
            ForecastInput(amount=0.9, date='2026-01-30'), ForecastInput(amount=1.5, date='2026-01-08'),
            ForecastInput(amount=10.8, date='2026-01-07'), ForecastInput(amount=25.5, date='2026-01-03'),
            ForecastInput(amount=1.4, date='2026-01-02'), ForecastInput(amount=1.4, date='2026-01-01'),
            ForecastInput(amount=0.06, date='2025-12-31'), ForecastInput(amount=0.37, date='2025-12-31'),
            ForecastInput(amount=1.3, date='2025-12-31'), ForecastInput(amount=0.23, date='2025-12-31'),
            ForecastInput(amount=2.8, date='2025-12-31'), ForecastInput(amount=3.0, date='2025-12-26'),
            ForecastInput(amount=1.4, date='2025-12-25'), ForecastInput(amount=1.4, date='2025-12-25'),
            ForecastInput(amount=22.3, date='2025-12-23'), ForecastInput(amount=8.0, date='2025-12-15'),
            ForecastInput(amount=7.7, date='2025-12-15'), ForecastInput(amount=0.28, date='2025-12-12'),
            ForecastInput(amount=0.52, date='2025-12-12'), ForecastInput(amount=1.0, date='2025-12-12'),
            ForecastInput(amount=1.3, date='2025-12-11'), ForecastInput(amount=1.79, date='2025-12-10'),
            ForecastInput(amount=0.03, date='2025-12-10'), ForecastInput(amount=2.2, date='2025-12-09'),
            ForecastInput(amount=2.2, date='2025-12-09'), ForecastInput(amount=8.1, date='2025-12-07'),
            ForecastInput(amount=8.1, date='2025-12-05'), ForecastInput(amount=1.3, date='2025-12-04')
        ]
        # Verify KAMA also runs on this data
        ama_spesa = calculate_ama_from_history(spesa_inputs)
