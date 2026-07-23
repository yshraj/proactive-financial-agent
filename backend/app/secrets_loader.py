"""
Cold-start secrets loading from AWS SSM Parameter Store.

On Lambda, secrets no longer arrive as function environment variables (env
vars are visible to anyone with lambda:GetFunctionConfiguration and persist
in CloudFormation history). Instead the deploy workflow writes them to
SecureString parameters under ``/kritifin/<env>/<NAME>`` and this module
fetches them once per execution environment, before Sentry/DB/LLM clients
initialise.

Behaviour:
- ``SECRETS_SSM_PREFIX`` unset (local dev, docker-compose, tests): no-op —
  .env / process env remain the single source of config.
- Set: fetch every parameter under the prefix and export each as an
  environment variable *only if not already set*, so an explicit env var
  always wins (useful for local overrides against a real prefix).
- Fetch failure with the prefix set is a hard error: a misconfigured IAM
  policy or missing parameter must fail the cold start loudly (alarms +
  the deploy smoke check catch it) rather than boot an app whose DB URL
  and API keys are silently absent.

Cost: one GetParametersByPath call per cold start. SSM standard parameters
and the API call are free; SecureStrings use the AWS-managed ``aws/ssm``
KMS key, whose key policy already permits in-account use via SSM (no
explicit kms:Decrypt grant needed).
"""
from __future__ import annotations

import logging
import os

logger = logging.getLogger("jarvis.secrets")

_loaded = False


def load_secrets() -> int:
    """Populate os.environ from SSM once per process. Returns count loaded."""
    global _loaded
    prefix = (os.environ.get("SECRETS_SSM_PREFIX") or "").strip().rstrip("/")
    if not prefix or _loaded:
        return 0

    try:
        import boto3

        ssm = boto3.client("ssm")
        loaded = 0
        next_token: str | None = None
        while True:
            kwargs = {"Path": prefix, "WithDecryption": True, "Recursive": False}
            if next_token:
                kwargs["NextToken"] = next_token
            page = ssm.get_parameters_by_path(**kwargs)
            for param in page.get("Parameters", []):
                name = param["Name"].rsplit("/", 1)[-1]
                if not (os.environ.get(name) or "").strip():
                    os.environ[name] = param["Value"]
                    loaded += 1
            next_token = page.get("NextToken")
            if not next_token:
                break
    except Exception as exc:
        # Fail the cold start: booting without secrets produces confusing
        # downstream errors (DB unreachable, auth open); this one is clear.
        raise RuntimeError(
            f"Failed to load secrets from SSM prefix {prefix!r}: "
            f"{type(exc).__name__}"
        ) from exc

    _loaded = True
    logger.info("Loaded %d secret(s) from SSM prefix %s", loaded, prefix)
    return loaded
