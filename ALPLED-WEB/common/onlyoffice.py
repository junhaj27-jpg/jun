import base64
import hashlib
import hmac
import json


def _to_base64url(value):
    if isinstance(value, str):
        value = value.encode("utf-8")
    return base64.urlsafe_b64encode(value).rstrip(b"=").decode("ascii")


def encode_jwt(payload, secret):
    header = {"alg": "HS256", "typ": "JWT"}
    header_segment = _to_base64url(
        json.dumps(header, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    )
    payload_segment = _to_base64url(
        json.dumps(payload, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    )
    signing_input = f"{header_segment}.{payload_segment}".encode("ascii")
    signature = hmac.new(secret.encode("utf-8"), signing_input, hashlib.sha256).digest()
    return f"{header_segment}.{payload_segment}.{_to_base64url(signature)}"


def decode_jwt(token, secret):
    header_segment, payload_segment, signature_segment = token.split(".")
    signing_input = f"{header_segment}.{payload_segment}".encode("ascii")
    expected_signature = hmac.new(
        secret.encode("utf-8"), signing_input, hashlib.sha256
    ).digest()
    if not hmac.compare_digest(_to_base64url(expected_signature), signature_segment):
        raise ValueError("Invalid signature")

    padding = "=" * (-len(payload_segment) % 4)
    payload_bytes = base64.urlsafe_b64decode(f"{payload_segment}{padding}")
    return json.loads(payload_bytes.decode("utf-8"))
