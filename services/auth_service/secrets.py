import os

def get_secret(name: str, default: str = None) -> str:
    """Return a secret value. Currently reads from environment variables.

    If `VAULT_ADDR`/`VAULT_TOKEN` are configured in the environment, this
    function can be extended to fetch secrets from HashiCorp Vault or another
    KMS. For now, prefer injecting secrets via environment variables or
    Docker secrets.
    """
    val = os.getenv(name)
    if val:
        return val
    return default
