from django.test import TestCase

class RobotsTest(TestCase):
    def test_robots_txt(self):
        response = self.client.get("/robots.txt")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "text/plain")
        self.assertIn(b"User-agent: *", response.content)
        self.assertIn(b"Disallow: /admin/", response.content)
        self.assertIn(b"Disallow: /accounts/", response.content)
