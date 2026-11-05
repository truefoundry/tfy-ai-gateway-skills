---
name: model-deploy-nim-classical
description: Deploy an NVIDIA NIM container (get_nim_deployment_specs) or a classical sklearn/XGBoost model (Model Registry version or bare artifact). Read when the user asks for a NIM, an nvcr.io model, or a sklearn/XGBoost/pickle/joblib model. HuggingFace and transformers models are in `model-deploy.md`.
---

These two paths do not use the HuggingFace catalogue flow in `model-deploy.md`. Do not mix their inputs into a HuggingFace `get_model_deployment_specs` call.

## NVIDIA NIM

### Inputs to collect

| Input | How |
|---|---|
| Workspace | `list_workspaces` → `id` |
| `nimModelId` | `<org>/<team>/<model>`, e.g. `nim/meta/llama3-8b-instruct` — any other shape is rejected |
| `nvcrDockerRegistryProviderIntegrationFqn` | FQN of a docker-registry integration for `nvcr.io` (username `$oauthtoken`, password = NGC API key). Find it in `list_provider_accounts` |
| `ngcApiKeySecretFqn` | `list_secrets` → take the secret's `fqn` and pass `tfy-secret://<fqn>`. A bare FQN fails with "Secret with FQN … not found" |

`list_workspaces`, `list_provider_accounts` and `list_secrets` are independent — call them in one parallel batch. If the registry integration or NGC secret does not exist, send the user to https://www.truefoundry.com/docs/deploying-nvidia-nims to create them; you cannot.

### Steps

1. `get_nim_deployment_specs workspaceId=<id> nimModelId=<org/team/model> nvcrDockerRegistryProviderIntegrationFqn=<fqn> ngcApiKeySecretFqn=tfy-secret://<fqn>`.
2. Options come grouped as `NIM`, `NIM-Latency`, `NIM-Throughput`. Each deployment is named `"<n> x <gpu_type> (<precision>)"` and carries `modelPrecision`, `performanceProfile` and `isAvailableInWorkspace`. Prefer an available option; ask the user latency vs throughput if they did not say.
3. The spec is built from the NIM profile, not a server template: there is no `artifacts_download` — NIM downloads weights inside its own container. To avoid re-downloading on every restart, mount a volume at `/opt/nim/.cache` (ask first; it adds a volume).
4. Apply, verify, smoke-test, and offer Gateway / sticky / scale-to-0 exactly as in **Apply and verify** and **Post-deploy loop** of `model-deploy.md`. NIM specs carry the sticky label when the cluster has a base domain.

## Classical ML (sklearn / XGBoost)

### Model Registry version

1. `get_model_deployment_specs workspaceId=<id> modelVersionFqn=<model:…>`.
2. For a version whose `framework.type` is `sklearn` or `xgboost`, it returns `FastAPI` and `Triton` options with empty `deployments` — that is expected, not a failure; do not run the similar-model recovery from `model-deploy.md`.
3. Give the user the `tfy deploy-init model --name … --model-version-fqn … --workspace-fqn … --model-server fastapi|triton` command from the option's `description` and link https://www.truefoundry.com/docs/model-deployment/deploy-sklearn-xgboost. It generates model-server code (`server.py`, `deploy.py`, `README.md`); the user deploys it by following that README.

Any other framework type is rejected with `Framework is not supported for deployment`; transformers versions go through `model-deploy.md`.

### Bare artifact (pickle / joblib / MLflow URI, not in the registry)

Deploy a service from image or source that runs the user's inference server (FastAPI, MLflow scoring, …) — `deploy-from-image.md` / `deploy-from-source.md`. Do not force vLLM onto tabular models.

## Checklist

- [ ] NIM: `nimModelId` in `<org>/<team>/<model>` form, nvcr.io registry integration FQN, NGC secret as `tfy-secret://<fqn>`?
- [ ] NIM: picked a performance profile and an available GPU option; offered a `/opt/nim/.cache` volume for large models?
- [ ] Classical: treated empty `deployments` as expected and handed over the `tfy deploy-init model` command?

For more info: `search_docs` with "deploying nvidia nims", "deploy sklearn xgboost".
