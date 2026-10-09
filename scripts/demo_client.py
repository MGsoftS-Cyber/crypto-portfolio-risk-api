"""Run from repository root against a fresh local API; synthetic data only."""

import argparse
import json
from pathlib import Path
import secrets
import httpx

parser = argparse.ArgumentParser()
parser.add_argument("--url", default="http://localhost:8008")
parser.add_argument("--output", default="demo-report.json")
args = parser.parse_args()
with httpx.Client(base_url=args.url, timeout=60, trust_env=False) as client:
    auth = client.post(
        "/api/auth/register",
        json={"email": f"demo-{secrets.token_hex(8)}@example.com", "password": secrets.token_urlsafe(24)},
    )
    auth.raise_for_status()
    client.headers["X-CSRF-Token"] = auth.json()["csrf_token"]
    demo = client.post("/api/v1/demo", headers={"Idempotency-Key": secrets.token_hex(16)})
    demo.raise_for_status()
    ids = demo.json()
    review = client.post(
        f"/api/v1/portfolios/{ids['portfolio_id']}/analyses",
        headers={"Idempotency-Key": secrets.token_hex(16)},
        json={"dataset_id": ids["dataset_id"], "as_of": ids["as_of"], "name": "Demo risk review", "enable_ml": True},
    )
    review.raise_for_status()
    report = review.json()
    for fmt in ["json", "holdings", "history", "trades", "alerts"]:
        response = client.get(f"/api/v1/analyses/{report['id']}/report", params={"format": fmt})
        response.raise_for_status()
    Path(args.output).write_text(json.dumps(report, indent=2))
    print(
        json.dumps(
            {
                "summary": report["results"]["summary"],
                "risk": report["results"]["risk"],
                "ml_status": report["results"]["ml"]["status"],
                "alerts": len(report["results"]["alerts"]),
            },
            indent=2,
        )
    )
    logout = client.post("/api/auth/logout")
    logout.raise_for_status()
    assert client.get("/api/auth/session").status_code == 401
