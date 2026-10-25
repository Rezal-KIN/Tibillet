from __future__ import annotations

import unittest
from pathlib import Path


COMPOSE = Path(__file__).resolve().parents[1] / "Lespass/docker-compose.yml"


class LespassComposeContractTests(unittest.TestCase):
    def test_celery_shares_django_media_and_logging_directories(self) -> None:
        compose = COMPOSE.read_text(encoding="utf-8")
        django = compose.split("  lespass_django:\n", 1)[1].split("  lespass_celery:\n", 1)[0]
        celery = compose.split("  lespass_celery:\n", 1)[1].split("  lespass_nginx:\n", 1)[0]
        for mount in ("./www:/DjangoFiles/www", "./logs:/DjangoFiles/logs"):
            self.assertIn(mount, django)
            self.assertIn(mount, celery)


if __name__ == "__main__":
    unittest.main()
