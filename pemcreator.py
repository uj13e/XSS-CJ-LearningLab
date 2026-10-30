from cryptography import x509
from cryptography.x509.oid import NameOID
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives import serialization
import datetime, ipaddress, socket


def get_local_ip():
    """外部への疎通(UDP、実際には送信しない)を利用して、現在のローカルIPを取得する"""
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("8.8.8.8", 80))
        return s.getsockname()[0]
    except Exception:
        return "127.0.0.1"
    finally:
        s.close()


local_ip = get_local_ip()
print(f"検出したローカルIP: {local_ip}")

key = rsa.generate_private_key(public_exponent=65537, key_size=2048)

subject = issuer = x509.Name([
    x509.NameAttribute(NameOID.COMMON_NAME, u"localhost"),
])

san_list = [
    x509.DNSName(u"localhost"),
    x509.IPAddress(ipaddress.IPv4Address("127.0.0.1")),
]

# 検出したIPを追加（127.0.0.1と重複しなければ）
if local_ip != "127.0.0.1":
    san_list.append(x509.IPAddress(ipaddress.IPv4Address(local_ip)))

cert = (
    x509.CertificateBuilder()
    .subject_name(subject)
    .issuer_name(issuer)
    .public_key(key.public_key())
    .serial_number(x509.random_serial_number())
    .not_valid_before(datetime.datetime.utcnow())
    .not_valid_after(datetime.datetime.utcnow() + datetime.timedelta(days=365))
    .add_extension(
        x509.SubjectAlternativeName(san_list),
        critical=False,
    )
    .sign(key, hashes.SHA256())
)

with open("key.pem", "wb") as f:
    f.write(key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.TraditionalOpenSSL,
        encryption_algorithm=serialization.NoEncryption(),
    ))

with open("cert.pem", "wb") as f:
    f.write(cert.public_bytes(serialization.Encoding.PEM))

print("完了！ cert.pem と key.pem を生成しました。")