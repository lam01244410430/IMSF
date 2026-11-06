"""Check the local read-only PostgREST probe and denied access paths."""
import httpx


with httpx.Client(base_url="http://127.0.0.1:3033", timeout=10) as client:
    response = client.get("/")
    assert response.status_code == 200, response.text
    assert "/health" in response.json()["paths"]
    response = client.get("/health", params={"status": "eq.ok"})
    assert response.status_code == 200, response.text
    assert response.json() == [{"status": "ok"}]
    response = client.post("/health", json={"status": "changed"})
    assert response.status_code in (401, 403), response.text
    response = client.get("/users")
    assert response.status_code == 404, response.text
    response = client.get("/health")
    assert response.json() == [{"status": "ok"}]
print("PASS: OpenAPI, filtered GET, denied POST, hidden users, unchanged probe")
