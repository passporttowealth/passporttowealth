#!/usr/bin/env python3
"""Cloudflare-Worker feedback endpoint smoke test.

Auto-skips when no endpoint is configured. Activates by setting:
    FEEDBACK_ENDPOINT_URL=https://passport-feedback.{your-subdomain}.workers.dev
    FEEDBACK_ENDPOINT_TOKEN=<the bearer token you set>

Then `python3 tests/test_feedback_endpoint.py` will:
  1. POST a synthetic feedback envelope.
  2. Assert 201 + the response includes an issue_url.
  3. Assert the worker rejects requests without (or with the wrong) bearer token.

Designed to run from a developer laptop, not in CI — CI doesn't hit the
network unless explicitly opted in via these env vars.
"""

from __future__ import annotations

import json
import os
import sys
import unittest
import urllib.error
import urllib.request
from datetime import datetime, timezone


ENDPOINT = os.environ.get("FEEDBACK_ENDPOINT_URL")
TOKEN = os.environ.get("FEEDBACK_ENDPOINT_TOKEN")


def _post(url: str, payload: dict, token: str | None = None, timeout: int = 10):
    body = json.dumps(payload).encode()
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    req = urllib.request.Request(url, data=body, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.status, json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read().decode() or "{}")


def _envelope(message: str = "Test feedback from CI smoke") -> dict:
    return {
        "v": 1,
        "ts": datetime.now(timezone.utc).isoformat(),
        "client_id": "test-client-fixture",
        "advisor_id": "passporttowealth",
        "skill_version": "0.0.1-test",
        "platform": f"test-runner Python {sys.version.split()[0]}",
        "message": message,
        "context_level": "a",
        "context": {"source": "tests/test_feedback_endpoint.py"},
    }


@unittest.skipUnless(ENDPOINT, "FEEDBACK_ENDPOINT_URL not set — skipping Cloudflare worker tests")
class TestFeedbackEndpoint(unittest.TestCase):
    def test_post_creates_issue(self):
        status, body = _post(ENDPOINT, _envelope("Smoke test from regression suite"), token=TOKEN)
        self.assertEqual(status, 201, f"expected 201 Created, got {status}: {body}")
        self.assertTrue(body.get("received"), f"response missing 'received': {body}")
        self.assertIn("issue_url", body, f"response missing 'issue_url': {body}")
        self.assertTrue(body["issue_url"].startswith("https://github.com/"),
                        f"issue_url should be a GitHub URL: {body['issue_url']}")
        print(f"  → issue created: {body['issue_url']}")

    def test_rejects_missing_bearer_when_required(self):
        # Only enforceable if FEEDBACK_ENDPOINT_TOKEN is set on this side
        if not TOKEN:
            self.skipTest("FEEDBACK_ENDPOINT_TOKEN not set; can't test bearer requirement")
        status, _ = _post(ENDPOINT, _envelope(), token=None)
        self.assertEqual(status, 401, f"expected 401 without bearer token, got {status}")

    def test_rejects_wrong_bearer(self):
        if not TOKEN:
            self.skipTest("FEEDBACK_ENDPOINT_TOKEN not set; can't test bearer requirement")
        status, _ = _post(ENDPOINT, _envelope(), token="not-the-real-token")
        self.assertEqual(status, 401, f"expected 401 with wrong bearer token, got {status}")

    def test_rejects_invalid_schema(self):
        status, body = _post(ENDPOINT, {"not": "a feedback envelope"}, token=TOKEN)
        self.assertIn(status, (400, 422), f"expected 4xx for invalid schema, got {status}: {body}")


if __name__ == "__main__":
    if not ENDPOINT:
        print("\nNo FEEDBACK_ENDPOINT_URL configured — nothing to test.")
        print("To activate: set the env var to your deployed Worker URL.")
        print("See docs/feedback-channel.md for the deploy recipe.\n")
        sys.exit(0)
    print(f"\nFeedback endpoint smoke test")
    print(f"  endpoint: {ENDPOINT}")
    print(f"  bearer:   {'<set>' if TOKEN else '<not set — auth tests will skip>'}\n")
    unittest.main(verbosity=2)
