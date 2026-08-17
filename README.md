# Fluid AI DevOps Challenge — Runbook & Video Script

Stack: Python/FastAPI backend + Redis, deployed on **Kind**, CI/CD via **GitHub Actions**
(builds image, spins up a real kind cluster inside the CI runner, deploys, smoke-tests).
Reliability feature: **readiness/liveness probes**. Failure sim: **bad env var → CrashLoopBackOff / NotReady**.

---

## 0. Prereqs (install once, ~5 min)
```bash
# Docker must be running
# Install kind
curl -Lo ./kind https://kind.sigs.k8s.io/dl/latest/kind-linux-amd64
chmod +x ./kind && sudo mv ./kind /usr/local/bin/kind

# Install kubectl (skip if you have it)
curl -LO "https://dl.k8s.io/release/$(curl -L -s https://dl.k8s.io/release/stable.txt)/bin/linux/amd64/kubectl"
chmod +x kubectl && sudo mv kubectl /usr/local/bin/
```

## 1. Local cluster + manual first deploy (proves it works end-to-end)
```bash
kind create cluster --name fluidai-cluster

cd app
docker build -t fluidai-backend:latest .   # builds the FastAPI + uvicorn image
kind load docker-image fluidai-backend:latest --name fluidai-cluster
cd ..

kubectl apply -f k8s/configmap.yaml
kubectl apply -f k8s/redis.yaml
kubectl apply -f k8s/backend.yaml

kubectl get pods -w        # watch until both are Running/Ready
kubectl get svc
```

Test it:
```bash
kubectl port-forward svc/backend 8080:80
curl localhost:8080/            # {"message":"Hello from Fluid AI backend","visits":1}
curl localhost:8080/readyz      # {"status":"ready"}
curl localhost:8080/healthz     # {"status":"alive"}
```

## 2. Push to GitHub → CI/CD runs automatically
```bash
git init
git add .
git commit -m "Fluid AI DevOps challenge: initial stack"
git branch -M main
git remote add origin <your-repo-url>
git push -u origin main
```
Open the **Actions** tab — this is your CI/CD proof for the video. The workflow builds the
image, creates its own kind cluster, loads the image, applies manifests, waits on rollout
status, and curls the app as a smoke test.

## 3. Reliability improvement: readiness/liveness probes
- **Why chosen**: with only 90 minutes, this is the single change with the highest
  reliability payoff per minute of setup — it directly prevents the most common
  production incident (traffic routed to a pod that can't serve it).
- **Problem it solves**: without a readiness probe, Kubernetes sends traffic to a pod
  the instant its container starts, even if the app hasn't finished connecting to
  Redis yet — causing 500s during rollout. The liveness probe separately catches a
  pod that's alive as a process but permanently wedged (e.g., deadlocked), and
  restarts it automatically.
- **Tradeoff**: probes add latency to detecting real problems (probe interval +
  failure threshold before k8s acts), and a badly tuned liveness probe can cause
  restart loops under normal load spikes if the threshold is too aggressive. I split
  readiness (depends on Redis) from liveness (doesn't depend on Redis) specifically
  to avoid a Redis blip triggering unnecessary container restarts.

## 4. Failure simulation (the part they weigh most heavily)

**Inject the failure** — set a bad Redis host so the app can never become ready:
```bash
kubectl set env deployment/backend REDIS_HOST=redis-typo
```

**Observe symptoms:**
```bash
kubectl get pods                     # backend pods stuck, READY 0/1 (not crashing — just NotReady)
kubectl get endpoints backend        # empty — service has no pods to route to
curl localhost:8080/                 # port-forward will fail / hang since pod isn't ready
```

**Debug methodology (narrate this live):**
```bash
kubectl describe pod <backend-pod>   # check Events section — readiness probe failing, "connection refused" or DNS errors
kubectl logs <backend-pod>           # app logs: redis.exceptions.ConnectionError: Error -2 connecting to redis-typo:6379. Name or service not known.
```
Talk through it: first check *is the pod running* (yes) → *is it ready* (no) →
*why not ready* (probe failing) → *why is the probe failing* (app can't reach
its dependency) → *check app logs for the real reason* (DNS resolution failure
on hostname) → root cause: **misconfigured env var pointing at a service name
that doesn't exist**.

**Fix:**
```bash
kubectl set env deployment/backend REDIS_HOST=redis
kubectl rollout status deployment/backend
curl localhost:8080/                 # back to 200 OK
```

Bonus (if time): show `kubectl rollout undo deployment/backend` as an alternate
recovery path if the bad config had been shipped via a full deploy instead of
`kubectl set env`.

## 5. Tradeoff discussion (for the video's last section)
- **Simplified**: single-node kind cluster, NodePort instead of Ingress/LoadBalancer,
  no persistent volume for Redis (data lost on pod restart), no image registry
  (image loaded directly into kind), no secrets manager (config is a plain
  ConfigMap, not a Secret — fine for a hostname, not for real credentials).
- **What breaks at scale**: single Redis replica is a single point of failure;
  no HPA means no automatic scaling under load; NodePort doesn't work across
  real multi-node clusters the way an Ingress + LoadBalancer would; no
  centralized logging means debugging across many pods becomes painful fast.
- **What I'd do in real production**: Helm chart instead of raw manifests,
  Ingress + TLS, Redis via a managed service or StatefulSet with PVC,
  Secrets (or external secrets manager) for credentials, HPA based on CPU/
  memory, and a proper GitOps flow (ArgoCD) instead of CI directly running
  `kubectl apply`.

---

## Video structure (fits 8–12 min)
1. **Live demo (3–4 min)** — curl the app, `kubectl get pods/svc`, show GitHub Actions
   run green, show rollout status.
2. **Architecture walkthrough (2–3 min)** — kind cluster, backend+Redis deployments,
   how CI/CD flows from push → build → kind cluster in CI → deploy → smoke test,
   why probes were chosen.
3. **Failure debugging (2–3 min)** — run section 4 live, narrate the diagnostic
   steps in order, show the fix and recovery.
4. **Tradeoffs (1–2 min)** — read through section 5 conversationally.
