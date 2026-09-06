"""End-to-end HTTP load test for the asynchronous claim intake path."""

import argparse
import asyncio
import base64
import statistics
import time

import httpx

# 1x1 transparent PNG used only as a lightweight synthetic upload fixture.
PNG_BYTES = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII="
)


async def submit_claim(client: httpx.AsyncClient, token: str, index: int) -> tuple[bool, float, str]:
    started = time.perf_counter()
    files = {"file": (f"benchmark-{index}.png", PNG_BYTES, "image/png")}
    data = {"treatment": "Benchmark"}
    try:
        response = await client.post(
            "/claims/upload",
            headers={"Authorization": f"Bearer {token}"},
            files=files,
            data=data,
        )
        latency = time.perf_counter() - started
        return response.is_success, latency, str(response.status_code)
    except Exception as exc:
        return False, time.perf_counter() - started, type(exc).__name__


async def run(base_url: str, token: str, requests: int, concurrency: int) -> None:
    limits = httpx.Limits(max_connections=concurrency, max_keepalive_connections=concurrency)
    timeout = httpx.Timeout(30.0)
    semaphore = asyncio.Semaphore(concurrency)

    async with httpx.AsyncClient(base_url=base_url.rstrip("/"), limits=limits, timeout=timeout) as client:
        async def bounded(index: int):
            async with semaphore:
                return await submit_claim(client, token, index)

        started = time.perf_counter()
        results = await asyncio.gather(*(bounded(index) for index in range(requests)))
        elapsed = time.perf_counter() - started

    successes = [item for item in results if item[0]]
    latencies = [item[1] for item in results]
    target_per_day = 250
    target_rps = target_per_day / 86400
    observed_rps = requests / elapsed if elapsed else 0
    estimated_daily_intake = observed_rps * 86400

    print(f"Requests: {requests}")
    print(f"Concurrency: {concurrency}")
    print(f"Successful uploads: {len(successes)} ({len(successes) / requests * 100:.2f}%)")
    print(f"Elapsed: {elapsed:.3f}s")
    print(f"Observed intake rate: {observed_rps:.2f} req/s")
    print(f"Estimated intake capacity: {estimated_daily_intake:.0f} claims/day")
    print(f"Target: {target_per_day} claims/day ({target_rps:.5f} req/s)")
    if latencies:
        ordered = sorted(latencies)
        p50 = statistics.median(ordered)
        p95 = ordered[min(len(ordered) - 1, int(len(ordered) * 0.95))]
        print(f"Latency p50: {p50 * 1000:.1f} ms")
        print(f"Latency p95: {p95 * 1000:.1f} ms")

    if len(successes) != requests:
        failures = [item[2] for item in results if not item[0]]
        print(f"Failure samples: {failures[:10]}")
        raise SystemExit(1)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Load test the asynchronous claim intake endpoint")
    parser.add_argument("--base-url", default="http://localhost:8000")
    parser.add_argument("--token", required=True, help="Employee bearer token")
    parser.add_argument("--requests", type=int, default=250)
    parser.add_argument("--concurrency", type=int, default=10)
    args = parser.parse_args()
    if args.requests < 1 or args.concurrency < 1:
        parser.error("requests and concurrency must be positive")
    asyncio.run(run(args.base_url, args.token, args.requests, args.concurrency))
