from cryptography.fernet import Fernet
import os

# In a real production environment, this key would be managed by a secure
# Key Management Service (KMS) like AWS KMS, GCP KMS, or HashiCorp Vault.
# For this implementation, we use an environment variable.
ENCRYPTION_KEY = os.environ.get("PHI_ENCRYPTION_KEY", Fernet.generate_key().decode())
cipher_suite = Fernet(ENCRYPTION_KEY.encode())

def encrypt_phi(data: str) -> str:
    """Encrypts PHI data using AES-256 (Fernet)."""
    if data is None:
        return None
    return cipher_suite.encrypt(data.encode()).decode()

def decrypt_phi(encrypted_data: str) -> str:
    """Decrypts PHI data using AES-256 (Fernet)."""
    if encrypted_data is None:
        return None
    return cipher_suite.decrypt(encrypted_data.encode()).decode()
