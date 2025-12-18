import base64


def encrypt_token(token: str) -> str:
    """
    PLACEHOLDER: Encrypts a token.
    REPLACE with cryptography.fernet
    """
    token_bytes = token.encode('utf-8')
    encrypted_bytes = base64.b64encode(token_bytes)
    return encrypted_bytes.decode('utf-8')

def decrypt_token(encrypted_token: str) -> str:
    """
    PLACEHOLDER: Decrypts a token.
    REPLACE with cryptography.fernet
    """
    try:
        encrypted_bytes = encrypted_token.encode('utf-8')
        decrypted_bytes = base64.b64decode(encrypted_bytes)
        return decrypted_bytes.decode('utf-8')
    except Exception as e:
        print(f"Error decrypting token: {e}")
        # In a real app, handle this error more gracefully
        return ""