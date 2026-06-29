from cryptography.fernet import Fernet

# 支持直接运行和作为包导入两种方式
try:
    from .config import KEY_PATH
    from .database import ensure_app_dir
except ImportError:
    from config import KEY_PATH
    from database import ensure_app_dir

def get_fernet() -> Fernet:
    """获取Fernet加密实例"""
    ensure_app_dir()
    if not KEY_PATH.exists():
        KEY_PATH.write_bytes(Fernet.generate_key())
    return Fernet(KEY_PATH.read_bytes())

def encrypt_text(text: str) -> str:
    """加密文本"""
    return get_fernet().encrypt(text.encode("utf-8")).decode("utf-8")

def decrypt_text(token: str) -> str:
    """解密文本"""
    return get_fernet().decrypt(token.encode("utf-8")).decode("utf-8")