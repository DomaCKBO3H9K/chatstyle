"""Шифрование и расшифровка файлов загруженных чатов.

Использует AES-256-GCM из пакета cryptography.
"""

import base64
import os
from pathlib import Path

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from chatstyle.errors import CodedError

MAGIC = b"CSCHAT1\n"
NONCE_SIZE = 12
KEY_SIZE = 32


def new_key() -> bytes:
    """Создаёт новый случайный ключ шифрования длиной 32 байта."""
    return os.urandom(KEY_SIZE)


def encode_key(key: bytes) -> str:
    """Кодирует бинарный ключ в URL-безопасную base64-строку."""
    return base64.urlsafe_b64encode(key).decode("ascii")


def decode_key(text: str) -> bytes:
    """Декодирует ключ из URL-безопасной base64-строки.

    :raises CodedError: если текст не декодируется или результат не имеет длину KEY_SIZE.
    """
    try:
        raw = base64.urlsafe_b64decode(text.encode("ascii"))
    except (ValueError, UnicodeEncodeError) as exc:
        raise CodedError("chat_key_invalid", "Ключ шифрования чатов повреждён.") from exc
    if len(raw) != KEY_SIZE:
        raise CodedError("chat_key_invalid", "Ключ шифрования чатов повреждён.")
    return raw


def _aad(chat_id: str) -> bytes:
    """Формирует дополнительные проверяемые данные (AAD) для шифрования."""
    return b"chatstyle-chat-v1\0" + chat_id.encode("utf-8")


def encrypt(key: bytes, plaintext: bytes, chat_id: str) -> bytes:
    """Шифрует plaintext с помощью AES-256-GCM.

    :param key: ключ длины 32 байта.
    :param plaintext: данные для шифрования.
    :param chat_id: идентификатор чата, используется как часть AAD.
    :return: MAGIC + nonce + ciphertext.
    :raises ValueError: если ключ не имеет длину KEY_SIZE.
    """
    if len(key) != KEY_SIZE:
        raise ValueError("Ключ должен быть длины 32 байта.")
    nonce = os.urandom(NONCE_SIZE)
    ciphertext = AESGCM(key).encrypt(nonce, plaintext, _aad(chat_id))
    return MAGIC + nonce + ciphertext


def decrypt(key: bytes, blob: bytes, chat_id: str) -> bytes:
    """Расшифровывает данные, созданные функцией encrypt.

    :raises CodedError: если blob не начинается с MAGIC, слишком короток,
        или не удаётся расшифровать (неверный ключ/изменён файл).
    """
    if not blob.startswith(MAGIC) or len(blob) < len(MAGIC) + NONCE_SIZE + 16:
        raise CodedError("chat_decrypt", "Файл чата повреждён или это не файл chatstyle.")
    nonce = blob[len(MAGIC) : len(MAGIC) + NONCE_SIZE]
    ciphertext = blob[len(MAGIC) + NONCE_SIZE :]
    try:
        return AESGCM(key).decrypt(nonce, ciphertext, _aad(chat_id))
    except InvalidTag as exc:
        raise CodedError(
            "chat_decrypt",
            "Не удалось расшифровать чат: неверный ключ или файл изменён.",
        ) from exc


def wipe_file(path: Path) -> None:
    """Безопасно стирает содержимое файла и удаляет его.

    Если файла не существует — делает ничего.
    Ошибки при перезаписи нулями игнорируются, но ошибка удаления поднимается.
    """
    if not path.exists():
        return
    try:
        size = path.stat().st_size
        with open(path, "wb") as f:
            f.write(b"\x00" * size)
            f.flush()
            os.fsync(f.fileno())
    except OSError:
        pass
    finally:
        path.unlink()
