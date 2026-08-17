import os
import redis
from fastapi import FastAPI, Response

app = FastAPI()

REDIS_HOST = os.getenv("REDIS_HOST", "redis")
REDIS_PORT = int(os.getenv("REDIS_PORT", "6379"))

r = redis.Redis(host=REDIS_HOST, port=REDIS_PORT, socket_connect_timeout=2, socket_timeout=2)


def redis_is_up() -> bool:
    try:
        return r.ping()
    except Exception:
        return False


# Liveness: is the process itself alive (doesn't depend on Redis)
@app.get("/healthz")
def healthz():
    return {"status": "alive"}


# Readiness: only ready to serve traffic if the Redis dependency is up
@app.get("/readyz")
def readyz(response: Response):
    if redis_is_up():
        return {"status": "ready"}
    response.status_code = 503
    return {"status": "not-ready", "reason": "redis unavailable"}


# Main app route: increments a visit counter in Redis
@app.get("/")
def root(response: Response):
    try:
        count = r.incr("visits")
        return {"message": "Hello from Fluid AI backend", "visits": count}
    except Exception as e:
        response.status_code = 500
        return {"error": "Could not reach Redis", "detail": str(e)}
