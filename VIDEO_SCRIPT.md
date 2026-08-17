# Video Narration Script — Fluid AI DevOps Challenge
(Read almost verbatim. Pauses marked with [...]. Total target: ~10 min.)

---

## INTRO (15 sec)
"Hi, I'm [name]. For this challenge I built a minimal but real production-style stack:
a Python FastAPI backend with a Redis dependency, deployed to a local Kubernetes cluster
using kind, with a GitHub Actions pipeline that builds the image, deploys it, and
smoke-tests it automatically. Let me walk through it."

---

## 1. LIVE DEMO (3–4 min)

[Terminal: kubectl get pods]
"Here's my cluster running two pods — the backend, running two replicas, and a single
Redis instance backing it. Both are Running and Ready — you can see 1/1 and 2/2 in the
READY column, which means the readiness probes are passing."

[Terminal: kubectl get svc]
"The backend is exposed via a NodePort service on port 30080."

[Terminal: curl localhost:8080/]
"Let's hit the app directly. [...] It returns a JSON response with a visit counter that's
incrementing in Redis — so this confirms both the backend and its database dependency
are wired up end to end."

[Terminal: curl localhost:8080/healthz and /readyz]
"I've also got two separate health endpoints — healthz for liveness, readyz for
readiness — I'll explain why they're split in a minute."

[Browser: GitHub Actions tab, click into the latest run]
"Here's my CI/CD pipeline. On every push to main, GitHub Actions builds the Docker
image, spins up a fresh kind cluster inside the runner itself — not a managed
platform — loads the image into it, applies my Kubernetes manifests, waits on rollout
status, and then curls the app as a smoke test. [...] You can see it went green,
confirming the deploy actually worked, not just that it applied without erroring."

[Terminal: kubectl describe deployment backend]
"And here's the deployment spec — rolling update strategy, resource requests and
limits, and the probes I'll go into next."

---

## 2. ARCHITECTURE WALKTHROUGH (2–3 min)

"Let me explain how this is put together. The cluster is a single-node kind cluster —
Kubernetes-in-Docker — which gave me a real, spec-compliant Kubernetes API without
needing cloud credentials or waiting on provisioning, which mattered a lot given the
90-minute limit.

The application layer is two pieces: a stateless FastAPI backend, running two
replicas behind a Service, and a Redis deployment it depends on for storing a visit
counter. I kept the app itself intentionally trivial — the challenge is about
infrastructure quality, not application complexity.

For the deploy flow: a push to main triggers GitHub Actions, which builds the image,
loads it directly into the kind cluster — since this is a local cluster, there's no
image registry round-trip needed — applies the manifests with kubectl, and then
blocks on rollout status before declaring success. If the rollout doesn't complete
within the timeout, the pipeline fails loudly instead of silently reporting green.

For reliability, I implemented readiness and liveness probes, and I deliberately
split them. The liveness probe only checks that the FastAPI process itself is
responding — it doesn't depend on Redis. The readiness probe, on the other hand,
checks that Redis is actually connected. That split matters: if Redis has a brief
blip, I don't want Kubernetes restarting my backend pods — that would just make
things worse. I want it to stop routing traffic to them until Redis recovers, then
resume automatically. That's exactly what readiness does, and liveness stays out of
the way unless the process itself is truly wedged."

---

## 3. FAILURE DEBUGGING WALKTHROUGH (2–3 min)

[Terminal, live]
"Now let me break this on purpose and debug it the way I would in production."

[Run: kubectl set env deployment/backend REDIS_HOST=redis-typo]
"I just pushed a bad environment variable — pointing the backend at a Redis
hostname that doesn't exist. Let's see what happens."

[Run: kubectl get pods]
"First symptom: the backend pods are not crashing — they're still Running, but
READY shows 0/1. That's an important distinction from a crash loop, so my first
assumption has to be checked: is this a startup problem or a dependency problem?"

[Run: kubectl get endpoints backend]
"Second check: the Service has zero endpoints. That confirms Kubernetes has
correctly pulled these pods out of rotation — no traffic is being routed to
something that isn't ready. Good, the readiness probe is doing its job.
But I still don't know why it's not ready."

[Run: kubectl describe pod <pod-name>]
"Let's describe the pod and look at the Events section. [...] Here — readiness
probe failing, repeated 503s from the /readyz endpoint. That tells me the app is
running but reporting itself unready, not that Kubernetes can't reach it."

[Run: kubectl logs <pod-name>]
"So the next step is application logs, not Kubernetes state. [...] Here's the
real signal: a redis.exceptions.ConnectionError — 'Name or service not known' for
'redis-typo'. That's the root cause — not a crash, not a resource issue, not a
network policy — a misconfigured environment variable pointing at a service name
that was never created.

If I'd stopped at 'pod isn't ready' and just restarted it, I'd have wasted time,
because restarting wouldn't fix a bad hostname. The logs were the step that
actually revealed root cause."

[Run: kubectl set env deployment/backend REDIS_HOST=redis]
"Fix: correct the hostname back to the real Redis service name."

[Run: kubectl rollout status deployment/backend]
"And the rollout completes — pods flip back to Ready."

[Run: curl localhost:8080/]
"Confirmed — 200 OK, visit counter still incrementing, dependency restored."

---

## 4. TRADEOFF DISCUSSION (1–2 min)

"A few things I deliberately simplified given the time limit. I used a NodePort
instead of an Ingress — fine for a local demo, but it wouldn't work the same way
across a real multi-node cluster, where I'd want an Ingress controller and a proper
LoadBalancer. Redis is a single replica with no persistent volume, so a pod
restart loses all data — in production I'd back it with a StatefulSet and PVC, or
just use a managed Redis service. Configuration is a plain ConfigMap rather than a
Secret — acceptable for a hostname, not for real credentials.

At scale, the things that would break first are: no autoscaling, so a traffic
spike just degrades the two fixed replicas; no centralized logging, so debugging
across many pods would get painful fast; and CI applying manifests directly
instead of a GitOps flow, which means there's no clean audit trail of what's
actually running in the cluster versus what's in Git.

If I were taking this to real production, I'd move to a Helm chart for
templating across environments, add an HPA tied to CPU or request latency, put
this behind ArgoCD for GitOps-style reconciliation, and add centralized logging
and metrics — probably Prometheus and Loki — so debugging doesn't rely on me
manually running kubectl describe and logs against a small number of pods.

That's the full stack — thanks for watching."
