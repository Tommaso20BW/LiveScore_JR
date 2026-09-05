import io
import json
import tempfile
import unittest
from datetime import date
from pathlib import Path

import requests
from PIL import Image

import fclogo_sync


def png_bytes(color=(20, 80, 160, 255)) -> bytes:
    output = io.BytesIO()
    Image.new("RGBA", (24, 18), color).save(output, format="PNG")
    return output.getvalue()


class FakeResponse:
    def __init__(self, *, text="", content=b"", status=200):
        self.text = text
        self.content = content
        self.status_code = status

    def raise_for_status(self):
        if self.status_code >= 400:
            response = requests.Response()
            response.status_code = self.status_code
            raise requests.HTTPError(
                f"{self.status_code} response", response=response
            )

    def json(self):
        return json.loads(self.text)


class FakeSession:
    def __init__(self, responses):
        self.responses = {
            url: list(value) if isinstance(value, tuple) else [value]
            for url, value in responses.items()
        }
        self.calls = []

    def get(self, url, **kwargs):
        self.calls.append(url)
        if url not in self.responses or not self.responses[url]:
            if url.startswith(fclogo_sync.ESPN_BASE):
                raise requests.ConnectionError("ESPN offline")
            raise AssertionError(f"Unexpected GET {url}")
        return self.responses[url].pop(0)


def pack_listing(*slugs):
    return "".join(f'<a href="/pack/{slug}">{slug}</a>' for slug in slugs)


def pack_page(*clubs):
    return "".join(
        f'<a href="/figc/club/{slug}">'
        f'<img src="https://cdn.example/{slug}-{version}.png" alt="{name} logo">'
        "</a>"
        for slug, name, version in clubs
    )


def detail_page(asset_url):
    return f'<meta property="og:image" content="{asset_url}">'


class FCLogoSyncTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.output_dir = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def test_season_changes_in_july(self):
        self.assertEqual(fclogo_sync.season_label(date(2026, 6, 30)), "2025-26")
        self.assertEqual(fclogo_sync.season_label(date(2026, 7, 1)), "2026-27")

    def test_pack_discovery_does_not_assume_slug_year_format(self):
        page_one = FakeResponse(text=pack_listing(
            "2026-27-serie-a",
            "26-27-serie-b",
            "2026-27-uefa-europa-league",
        ))
        session = FakeSession({
            f"{fclogo_sync.BASE_URL}/packs?season=2026&page=1": page_one,
            f"{fclogo_sync.BASE_URL}/packs?season=2026&page=2": FakeResponse(text=""),
        })
        self.assertEqual(
            fclogo_sync.discover_pack_slugs(session, 2026),
            [
                "2026-27-serie-a",
                "26-27-serie-b",
                "2026-27-uefa-europa-league",
            ],
        )

    def test_selects_serie_a_and_b_but_only_juventus_uefa_pack(self):
        slugs = [
            "2026-27-serie-a",
            "2026-27-serie-b",
            "2026-27-uefa-europa-league",
            "2026-27-uefa-champions-league",
            "2026-27-brazilian-serie-a",
        ]
        juve = ("Juventus-FC-v2020", "Juventus", "one")
        inter = ("FC-Inter-Milan-v2021", "Inter Milan", "one")
        benfica = ("SL-Benfica-v2025", "Benfica", "one")
        session = FakeSession({
            f"{fclogo_sync.BASE_URL}/pack/{slugs[0]}": FakeResponse(text=pack_page(juve)),
            f"{fclogo_sync.BASE_URL}/pack/{slugs[1]}": FakeResponse(text=pack_page(inter)),
            f"{fclogo_sync.BASE_URL}/pack/{slugs[2]}": FakeResponse(text=pack_page(juve, benfica)),
            f"{fclogo_sync.BASE_URL}/pack/{slugs[3]}": FakeResponse(text=pack_page(benfica)),
        })
        selected, errors = fclogo_sync.select_pack_records(session, slugs)
        self.assertEqual(
            set(selected),
            {slugs[0], slugs[1], slugs[2]},
        )
        self.assertEqual(errors, [])

    def test_unchanged_valid_mono_logo_is_reused(self):
        pack_slug = "2026-27-serie-a"
        club_slug = "Juventus-FC-v2020"
        preview = f"https://cdn.example/{club_slug}-one.png"
        filename = f"{club_slug}-mono.png"
        (self.output_dir / filename).write_bytes(png_bytes())
        (self.output_dir / fclogo_sync.MANIFEST_FILENAME).write_text(
            json.dumps({
                "season": "2026-27",
                "teams": [{
                    "name": "Juventus",
                    "slug": club_slug,
                    "file": filename,
                    "aliases": ["Juventus FC"],
                    "espn_id": "111",
                    "variant": "mono",
                    "source_url": "cached",
                    "preview_url": preview,
                    "packs": [pack_slug],
                }]
            }),
            encoding="utf-8",
        )
        session = FakeSession({
            f"{fclogo_sync.BASE_URL}/packs?season=2026&page=1": FakeResponse(
                text=pack_listing(pack_slug)
            ),
            f"{fclogo_sync.BASE_URL}/packs?season=2026&page=2": FakeResponse(text=""),
            f"{fclogo_sync.BASE_URL}/pack/{pack_slug}": FakeResponse(
                text=pack_page((club_slug, "Juventus", "one"))
            ),
        })
        report = fclogo_sync.sync_current_season(
            output_dir=self.output_dir,
            session=session,
            today=date(2026, 9, 1),
        )
        self.assertEqual(report.downloaded, 0)
        self.assertEqual(report.reused, 1)
        self.assertFalse(any("assets.fclogo.top" in url for url in session.calls))
        updated = json.loads((self.output_dir / fclogo_sync.MANIFEST_FILENAME).read_text())
        self.assertEqual(updated["teams"][0]["espn_id"], "111")
        self.assertEqual(report.failed, 0)

        # Al successivo avvio ESPN torna disponibile: stesso PNG, ID e alias
        # aggiornati senza richieste per il singolo club o riscaricamenti.
        session.responses = {
            f"{fclogo_sync.BASE_URL}/packs?season=2026&page=1": [FakeResponse(text=pack_listing(pack_slug))],
            f"{fclogo_sync.BASE_URL}/packs?season=2026&page=2": [FakeResponse(text="")],
            f"{fclogo_sync.BASE_URL}/pack/{pack_slug}": [FakeResponse(text=pack_page((club_slug, "Juventus", "one")))],
            f"{fclogo_sync.ESPN_BASE}/ita.1/teams?limit=1000&season=2026": [FakeResponse(
                text=json.dumps({"sports": [{"leagues": [{"teams": [
                    {"team": {"id": "111", "displayName": "Juventus", "shortDisplayName": "Juve"}}
                ]}]}]}))],
        }
        report = fclogo_sync.sync_current_season(output_dir=self.output_dir, session=session,
                                                today=date(2026, 9, 1))
        updated = json.loads((self.output_dir / fclogo_sync.MANIFEST_FILENAME).read_text())
        self.assertIn("Juve", updated["teams"][0]["aliases"])
        self.assertEqual(report.reused, 1)
        self.assertEqual(report.downloaded, 0)

    def test_missing_logo_downloads_mono_and_writes_manifest(self):
        pack_slug = "2026-27-serie-b"
        club_slug = "US-Palermo-v2024"
        mono_detail_url = f"{fclogo_sync.BASE_URL}/figc/club/{club_slug}-mono"
        mono_url = f"{fclogo_sync.ASSET_BASE_URL}/Palermo_FC-v2024-mono.png"
        session = FakeSession({
            f"{fclogo_sync.ESPN_BASE}/ita.2/teams?limit=1000&season=2026": FakeResponse(
                text=json.dumps({"sports": [{"leagues": [{"teams": [
                    {"team": {"id": "2920", "displayName": "Palermo"}}
                ]}]}]})
            ),
            f"{fclogo_sync.BASE_URL}/packs?season=2026&page=1": FakeResponse(
                text=pack_listing(pack_slug)
            ),
            f"{fclogo_sync.BASE_URL}/packs?season=2026&page=2": FakeResponse(text=""),
            f"{fclogo_sync.BASE_URL}/pack/{pack_slug}": FakeResponse(
                text=pack_page((club_slug, "Palermo", "one"))
            ),
            mono_detail_url: FakeResponse(text=detail_page(mono_url)),
            mono_url: FakeResponse(content=png_bytes()),
        })
        report = fclogo_sync.sync_current_season(
            output_dir=self.output_dir,
            session=session,
            today=date(2026, 9, 1),
        )
        self.assertEqual(report.downloaded, 1)
        manifest = json.loads(
            (self.output_dir / fclogo_sync.MANIFEST_FILENAME).read_text(encoding="utf-8")
        )
        self.assertEqual(manifest["teams"][0]["variant"], "mono")
        self.assertEqual(manifest["teams"][0]["espn_id"], "2920")
        self.assertTrue((self.output_dir / manifest["teams"][0]["file"]).is_file())

    def test_new_season_removes_old_clubs_and_logo_versions(self):
        old_filename = "Old-Club-v2025-mono.png"
        (self.output_dir / old_filename).write_bytes(png_bytes())
        (self.output_dir / fclogo_sync.MANIFEST_FILENAME).write_text(
            json.dumps({
                "season": "2025-26",
                "teams": [{
                    "name": "Old Club",
                    "slug": "Old-Club-v2025",
                    "file": old_filename,
                    "variant": "mono",
                    "packs": ["2025-26-serie-a"],
                }],
            }),
            encoding="utf-8",
        )
        pack_slug = "2026-27-serie-a"
        new_slug = "New-Club-v2026"
        mono_url = f"{fclogo_sync.ASSET_BASE_URL}/{new_slug}-mono.png"
        session = FakeSession({
            f"{fclogo_sync.BASE_URL}/packs?season=2026&page=1": FakeResponse(
                text=pack_listing(pack_slug)
            ),
            f"{fclogo_sync.BASE_URL}/packs?season=2026&page=2": FakeResponse(text=""),
            f"{fclogo_sync.BASE_URL}/pack/{pack_slug}": FakeResponse(
                text=pack_page((new_slug, "New Club", "one"))
            ),
            f"{fclogo_sync.BASE_URL}/figc/club/{new_slug}-mono": FakeResponse(
                text=detail_page(mono_url)
            ),
            mono_url: FakeResponse(content=png_bytes()),
        })

        report = fclogo_sync.sync_current_season(
            output_dir=self.output_dir,
            session=session,
            today=date(2026, 9, 1),
        )

        self.assertEqual(report.removed, 1)
        self.assertFalse((self.output_dir / old_filename).exists())
        manifest = json.loads(
            (self.output_dir / fclogo_sync.MANIFEST_FILENAME).read_text(encoding="utf-8")
        )
        self.assertEqual([team["slug"] for team in manifest["teams"]], [new_slug])

    def test_new_season_redownloads_even_when_club_slug_is_unchanged(self):
        pack_slug = "2026-27-serie-a"
        club_slug = "Juventus-FC-v2020"
        filename = f"{club_slug}-mono.png"
        old_bytes = png_bytes((10, 10, 10, 255))
        new_bytes = png_bytes((240, 240, 240, 255))
        (self.output_dir / filename).write_bytes(old_bytes)
        preview = f"https://cdn.example/{club_slug}-one.png"
        (self.output_dir / fclogo_sync.MANIFEST_FILENAME).write_text(
            json.dumps({
                "season": "2025-26",
                "teams": [{
                    "name": "Juventus",
                    "slug": club_slug,
                    "file": filename,
                    "variant": "mono",
                    "preview_url": preview,
                    "packs": ["2025-26-serie-a"],
                }],
            }),
            encoding="utf-8",
        )
        mono_url = f"{fclogo_sync.ASSET_BASE_URL}/{club_slug}-mono.png"
        session = FakeSession({
            f"{fclogo_sync.BASE_URL}/packs?season=2026&page=1": FakeResponse(
                text=pack_listing(pack_slug)
            ),
            f"{fclogo_sync.BASE_URL}/packs?season=2026&page=2": FakeResponse(text=""),
            f"{fclogo_sync.BASE_URL}/pack/{pack_slug}": FakeResponse(
                text=pack_page((club_slug, "Juventus", "one"))
            ),
            f"{fclogo_sync.BASE_URL}/figc/club/{club_slug}-mono": FakeResponse(
                text=detail_page(mono_url)
            ),
            mono_url: FakeResponse(content=new_bytes),
        })

        report = fclogo_sync.sync_current_season(
            output_dir=self.output_dir,
            session=session,
            today=date(2026, 9, 1),
        )

        self.assertEqual(report.downloaded, 1)
        self.assertEqual((self.output_dir / filename).read_bytes(), new_bytes)

    def test_failed_new_season_sync_does_not_delete_previous_files(self):
        old_filename = "Old-Club-v2025-mono.png"
        (self.output_dir / old_filename).write_bytes(png_bytes())
        (self.output_dir / fclogo_sync.MANIFEST_FILENAME).write_text(
            json.dumps({
                "season": "2025-26",
                "teams": [{
                    "name": "Old Club",
                    "slug": "Old-Club-v2025",
                    "file": old_filename,
                    "variant": "mono",
                    "packs": ["2025-26-serie-a"],
                }],
            }),
            encoding="utf-8",
        )
        pack_slug = "2026-27-serie-a"
        new_slug = "New-Club-v2026"
        session = FakeSession({
            f"{fclogo_sync.BASE_URL}/packs?season=2026&page=1": FakeResponse(
                text=pack_listing(pack_slug)
            ),
            f"{fclogo_sync.BASE_URL}/packs?season=2026&page=2": FakeResponse(text=""),
            f"{fclogo_sync.BASE_URL}/pack/{pack_slug}": FakeResponse(
                text=pack_page((new_slug, "New Club", "one"))
            ),
            f"{fclogo_sync.BASE_URL}/figc/club/{new_slug}-mono": FakeResponse(status=404),
            f"{fclogo_sync.BASE_URL}/figc/club/{new_slug}": FakeResponse(status=404),
        })

        report = fclogo_sync.sync_current_season(
            output_dir=self.output_dir,
            session=session,
            today=date(2026, 9, 1),
        )

        self.assertEqual(report.failed, 1)
        self.assertEqual(report.removed, 0)
        self.assertTrue((self.output_dir / old_filename).is_file())
        manifest = json.loads(
            (self.output_dir / fclogo_sync.MANIFEST_FILENAME).read_text(encoding="utf-8")
        )
        self.assertEqual(manifest["season"], "2025-26")

    def test_color_asset_is_used_only_when_mono_is_unavailable(self):
        pack_slug = "2026-27-serie-b"
        club_slug = "US-Palermo-v2024"
        mono_detail_url = f"{fclogo_sync.BASE_URL}/figc/club/{club_slug}-mono"
        color_detail_url = f"{fclogo_sync.BASE_URL}/figc/club/{club_slug}"
        color_url = f"{fclogo_sync.ASSET_BASE_URL}/Palermo_FC-v2024.png"
        session = FakeSession({
            f"{fclogo_sync.BASE_URL}/packs?season=2026&page=1": FakeResponse(
                text=pack_listing(pack_slug)
            ),
            f"{fclogo_sync.BASE_URL}/packs?season=2026&page=2": FakeResponse(text=""),
            f"{fclogo_sync.BASE_URL}/pack/{pack_slug}": FakeResponse(
                text=pack_page((club_slug, "Palermo", "one"))
            ),
            mono_detail_url: FakeResponse(status=404),
            color_detail_url: FakeResponse(text=detail_page(color_url)),
            color_url: FakeResponse(content=png_bytes((220, 30, 60, 255))),
        })
        report = fclogo_sync.sync_current_season(
            output_dir=self.output_dir,
            session=session,
            today=date(2026, 9, 1),
        )
        self.assertEqual(report.downloaded, 1)
        manifest = json.loads(
            (self.output_dir / fclogo_sync.MANIFEST_FILENAME).read_text(encoding="utf-8")
        )
        self.assertEqual(manifest["teams"][0]["variant"], "color")


if __name__ == "__main__":
    unittest.main()
