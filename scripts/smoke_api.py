"""HTTP end-to-end check against a running API + worker; no credentials are printed."""

import argparse
import secrets
import time

import httpx


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--base", default="http://localhost:8000")
    args = parser.parse_args()
    with httpx.Client(base_url=args.base, timeout=15, trust_env=False) as client:
        client.get("/health/ready").raise_for_status()
        companies = client.get("/api/v1/organizations").json()["items"]
        if not companies:
            raise SystemExit("No company profiles; run seed-demo or import-data first")
        signup = client.post(
            "/api/v1/auth/register",
            json={
                "email": f"smoke-{secrets.token_hex(5)}@example.test",
                "password": secrets.token_urlsafe(20),
                "name": "HTTP smoke test",
                "role": "cfo",
                "organization_id": companies[0]["id"],
            },
        )
        signup.raise_for_status()
        client.headers["Authorization"] = "Bearer " + signup.json()["access_token"]
        response = client.post("/api/v1/analyses", json={"max_events": 3})
        response.raise_for_status()
        job = response.json()["id"]
        for _ in range(60):
            result = client.get("/api/v1/analyses/" + job)
            result.raise_for_status()
            data = result.json()
            if data["status"] in ("completed", "failed"):
                break
            time.sleep(1)
        else:
            raise SystemExit("Worker timeout")
        if data["status"] != "completed":
            raise SystemExit("Analysis failed: " + str(data.get("error_code")))
        feed = client.get("/api/v1/feed").json()
        if not feed["items"]:
            raise SystemExit("No insights: seed directional demo events or inspect the job summary")
        insight = client.get("/api/v1/insights/" + str(feed["items"][0]["id"]))
        insight.raise_for_status()
        if not insight.json()["evidence"]:
            raise SystemExit("Missing evidence")
        client.post("/api/v1/auth/logout").raise_for_status()
        print(
            "HTTP scenario passed: registration -> queued analysis -> worker -> feed -> cited insight -> logout."
        )


if __name__ == "__main__":
    main()
