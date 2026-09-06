import unittest

import diretta_logos


PNG = b"\x89PNG\r\n\x1a\n" + b"test"


class FakeResponse:
    def __init__(self, *, payload=None, content=b"", status=200):
        self._payload = payload
        self.content = content
        self.status = status

    def json(self):
        return self._payload

    def raise_for_status(self):
        if self.status >= 400:
            raise RuntimeError(f"HTTP {self.status}")


class FakeSession:
    def __init__(self, search_payload, image=PNG):
        self.search_payload = search_payload
        self.image = image
        self.calls = []

    def get(self, url, **kwargs):
        self.calls.append((url, kwargs))
        if url == diretta_logos.SEARCH_URL:
            return FakeResponse(payload=self.search_payload)
        return FakeResponse(content=self.image)


def team(name, team_id, images=None, url=None):
    return {
        "id": team_id,
        "url": url or name.lower().replace(" ", "-"),
        "name": name,
        "type": {"id": 2},
        "sport": {"id": 1},
        "images": images if images is not None else [
            {"path": "small.png", "usageId": 2, "variantTypeId": 2},
            {"path": "full.png", "usageId": 2, "variantTypeId": 15},
        ],
    }


class DirettaLogoTests(unittest.TestCase):
    def test_resolves_exact_team_and_prefers_full_variant(self):
        session = FakeSession([
            team("Juventus U23", "reserve", url="juventus"),
            team("Juventus", "first"),
        ])

        result = diretta_logos.resolve_team_logo(["Juventus"], session)

        self.assertIsNotNone(result)
        data_uri, matched_name = result
        self.assertEqual(matched_name, "Juventus")
        self.assertTrue(data_uri.startswith("data:image/png;base64,"))
        self.assertEqual(session.calls[-1][0], diretta_logos.IMAGE_BASE_URL + "full.png")

    def test_uses_alias_to_match_different_display_name(self):
        session = FakeSession([team("Milan", "milan")])

        result = diretta_logos.resolve_team_logo(["Milan", "AC Milan"], session)

        self.assertEqual(result[1], "Milan")

    def test_rejects_ambiguous_or_unrelated_result(self):
        session = FakeSession([team("Juventus U23", "reserve")])

        result = diretta_logos.resolve_team_logo(["Juventus"], session)

        self.assertIsNone(result)
        self.assertTrue(all(call[0] == diretta_logos.SEARCH_URL for call in session.calls))

    def test_rejects_non_png_response(self):
        session = FakeSession([team("Milan", "milan")], image=b"not an image")

        result = diretta_logos.resolve_team_logo(["Milan"], session)

        self.assertIsNone(result)


if __name__ == "__main__":
    unittest.main()
