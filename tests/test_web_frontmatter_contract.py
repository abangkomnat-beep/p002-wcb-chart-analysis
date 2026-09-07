import unittest

from tools import web_frontmatter_contract


class PublicAssetTagTests(unittest.TestCase):
    def test_alias_matrix(self):
        cases = {
            "wtiusd": "wti",
            " WTIUSD ": "wti",
            "WTIUSD": "wti",
            "btcusd": "btc",
            "btc": "btc",
            "xauusd": "xauusd",
            "eurusd": "eurusd",
            "usdjpy": "usdjpy",
            "audusd": "audusd",
        }
        for asset, expected in cases.items():
            with self.subTest(asset=asset):
                self.assertEqual(web_frontmatter_contract.public_asset_tag(asset), expected)

    def test_empty_asset_fails_closed(self):
        for asset in (None, "", "   ", "wti/usd", "WTI USD", "wti_usd"):
            with self.subTest(asset=asset), self.assertRaises(ValueError):
                web_frontmatter_contract.public_asset_tag(asset)

    def test_public_mapping_does_not_change_canonical_mapping(self):
        self.assertEqual(web_frontmatter_contract.canonical_asset("btc"), "btcusd")
        self.assertEqual(web_frontmatter_contract.canonical_asset("wtiusd"), "wtiusd")


if __name__ == "__main__":
    unittest.main()
