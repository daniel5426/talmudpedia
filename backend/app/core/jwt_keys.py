from __future__ import annotations

import base64
import hashlib
import json
import os
from dataclasses import dataclass
from typing import Dict, Any, Protocol

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa


class SigningKeyProvider(Protocol):
    def sign(self, payload: Dict[str, Any], headers: Dict[str, Any] | None = None) -> str:
        ...


class VerificationKeyProvider(Protocol):
    def get_jwks(self) -> Dict[str, Any]:
        ...


def _b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


@dataclass
class RSAKeyMaterial:
    private_key_pem: str
    public_key_pem: str
    kid: str
    algorithm: str = "RS256"


class LocalRSAKeyStore:
    """
    Dev/local keystore for workload JWT signing.
    Uses env-provided PEM keys if available; otherwise creates a process-local pair.
    """

    _material: RSAKeyMaterial | None = None

    @classmethod
    def get_material(cls) -> RSAKeyMaterial:
        if cls._material is not None:
            return cls._material

        private_key_pem = os.getenv("WORKLOAD_JWT_PRIVATE_KEY")
        public_key_pem = os.getenv("WORKLOAD_JWT_PUBLIC_KEY")

        if private_key_pem and public_key_pem:
            kid = os.getenv("WORKLOAD_JWT_KEY_ID") or cls._derive_kid(public_key_pem)
            cls._material = RSAKeyMaterial(
                private_key_pem=private_key_pem,
                public_key_pem=public_key_pem,
                kid=kid,
            )
            return cls._material

        private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        private_pem_bytes = private_key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption(),
        )
        public_pem_bytes = private_key.public_key().public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo,
        )
        private_key_pem = private_pem_bytes.decode("utf-8")
        public_key_pem = public_pem_bytes.decode("utf-8")
        kid = cls._derive_kid(public_key_pem)
        cls._material = RSAKeyMaterial(
            private_key_pem=private_key_pem,
            public_key_pem=public_key_pem,
            kid=kid,
        )
        return cls._material

    @staticmethod
    def _derive_kid(public_key_pem: str) -> str:
        digest = hashlib.sha256(public_key_pem.encode("utf-8")).hexdigest()
        return digest[:16]


class LocalJWKSProvider:
    def get_jwks(self) -> Dict[str, Any]:
        material = LocalRSAKeyStore.get_material()
        public_key = serialization.load_pem_public_key(material.public_key_pem.encode("utf-8"))
        numbers = public_key.public_numbers()

        e_bytes = numbers.e.to_bytes((numbers.e.bit_length() + 7) // 8, "big")
        n_bytes = numbers.n.to_bytes((numbers.n.bit_length() + 7) // 8, "big")

        jwk = {
            "kty": "RSA",
            "alg": material.algorithm,
            "use": "sig",
            "kid": material.kid,
            "n": _b64url(n_bytes),
            "e": _b64url(e_bytes),
        }
        return {"keys": [jwk]}


def current_signing_material() -> RSAKeyMaterial:
    return LocalRSAKeyStore.get_material()
