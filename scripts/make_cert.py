"""Self-signed TLS certificate for head office (the guard -> ingest link).

    python scripts/make_cert.py [extra-ip-or-hostname ...]

Writes certs/hq.crt (public: copy it to the shop laptop's certs/ folder) and certs/hq.key (private: never copy or commit).
run_hq.ps1 turns TLS on for ingest when both files exist; run_shop.ps1 pins the guard to certs/hq.crt when it exists,
so the guard trusts exactly this head office and nothing else.
"""
import datetime
import ipaddress
import socket
import sys
from pathlib import Path

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.x509.oid import NameOID


def names_for(extra):
    names = {"localhost", "127.0.0.1", "192.168.137.1", socket.gethostname()}   # 192.168.137.1 = Windows hotspot default
    try:
        names.update(i[4][0] for i in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET))
    except OSError:
        pass
    names.update(extra)
    return sorted(names)


def san(name):
    try:
        return x509.IPAddress(ipaddress.ip_address(name))
    except ValueError:
        return x509.DNSName(name)


def make(out_dir="certs", extra=(), days=90):
    out = Path(out_dir)
    out.mkdir(exist_ok=True)
    key = ec.generate_private_key(ec.SECP256R1())
    subject = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "airlock-head-office")])
    now = datetime.datetime.now(datetime.timezone.utc)
    cert = (
        x509.CertificateBuilder()
        .subject_name(subject).issuer_name(subject).public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - datetime.timedelta(minutes=5)).not_valid_after(now + datetime.timedelta(days=days))
        .add_extension(x509.SubjectAlternativeName([san(n) for n in names_for(extra)]), critical=False)
        .add_extension(x509.BasicConstraints(ca=True, path_length=None), critical=True)   # self-signed leaf doubles as its own trust anchor
        .sign(key, hashes.SHA256())
    )
    (out / "hq.crt").write_bytes(cert.public_bytes(serialization.Encoding.PEM))
    (out / "hq.key").write_bytes(key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()))
    return out / "hq.crt", out / "hq.key"


if __name__ == "__main__":
    crt, _ = make(extra=sys.argv[1:])
    print(f"wrote {crt} (copy to the shop laptop's certs/ folder) and certs/hq.key (keep private)")
