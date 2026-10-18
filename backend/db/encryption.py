from cryptography.fernet import Fernet
import os

# In a real production environment, this key would be loaded from a secure vault
# such as AWS Secrets Manager, HashiCorp Vault, or GCP Secret Manager.
# For the purpose of this build unit, we use a consistent key for testing.
_ENCRYPTION_KEY = os.getenv("PHI_ENCRYPTION_KEY", Fernet.generate_key().decode())
_cipher = Fernet(_ENCRYPTION_KEY.encode())

def encrypt_phi(data: str) -> str:
    """Encrypts Patient Health Information (PHI) for HIPAA compliance."""
    if data is None:
        return None
    return _cipher.encrypt(data.encode()).decode()

def decrypt_phi(encrypted_data: str) -> str:
    """Decrypts Patient Health Information (PHI) for HIPAA compliance."""
    if encrypted_data is None:
        return None
    return _cipher.decrypt(encrypted_data.encode()).decode()
