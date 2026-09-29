"""Managed identity, mocked. `MockManagedIdentityCredential.get_token(scope)` hands out a fake,
unsigned token whose claims (audience, roles) the MCP gateway checks the way a server would check
a real Entra ID token. No secret, key or connection string exists anywhere in the labs."""

from __future__ import annotations

import hashlib
import time
from dataclasses import dataclass, field

from labcore.config import AzureStub


@dataclass(frozen=True)
class MockToken:
    token: str
    audience: str
    client_id: str
    roles: frozenset[str]
    expires_on: int


@dataclass
class MockManagedIdentityCredential:
    client_id: str = "mi-labs-local"
    role_grants: dict[str, set[str]] = field(default_factory=dict)  # audience -> app roles granted
    issued: list[str] = field(default_factory=list)

    def get_token(self, scope: str) -> MockToken:
        audience = scope.removesuffix("/.default")
        digest = hashlib.sha256(f"{self.client_id}|{audience}".encode()).hexdigest()[:16]
        self.issued.append(audience)
        return MockToken(
            token=f"mock-mi.{digest}",
            audience=audience,
            client_id=self.client_id,
            roles=frozenset(self.role_grants.get(audience, set())),
            expires_on=int(time.time()) + 3600,
        )


class ManagedIdentityCredentialStub(AzureStub):
    """Where azure.identity.ManagedIdentityCredential would be used."""

    service = "entra-managed-identity"
