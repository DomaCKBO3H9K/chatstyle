"""Тесты для модуля chatstyle.chatcrypt.

Проверяют шифрование, расшифровку, работу с ключами и безопасное стирание файлов.
"""

import os
from pathlib import Path

import pytest
from chatstyle import chatcrypt
from chatstyle.errors import CodedError


class TestEncryptDecrypt:
    """Тесты цикла шифрование-расшифровка."""

    def test_round_trip_empty(self):
        """Пустые данные шифруются и расшифровываются корректно."""
        key = chatcrypt.new_key()
        plaintext = b""
        chat_id = "test_chat"

        blob = chatcrypt.encrypt(key, plaintext, chat_id)
        recovered = chatcrypt.decrypt(key, blob, chat_id)

        assert recovered == plaintext
        assert blob.startswith(chatcrypt.MAGIC)

    def test_round_trip_small(self):
        """Небольшие данные корректно обрабатываются."""
        key = chatcrypt.new_key()
        plaintext = b"Hello, world!"
        chat_id = "chat_123"

        blob = chatcrypt.encrypt(key, plaintext, chat_id)
        recovered = chatcrypt.decrypt(key, blob, chat_id)

        assert recovered == plaintext

    def test_round_trip_large_random(self):
        """Данные размером 1 МБ шифруются и расшифровываются без ошибок."""
        key = chatcrypt.new_key()
        plaintext = os.urandom(1024 * 1024)  # 1 МБ случайных байт
        chat_id = "large_chat"

        blob = chatcrypt.encrypt(key, plaintext, chat_id)
        recovered = chatcrypt.decrypt(key, blob, chat_id)

        assert recovered == plaintext

    def test_blob_does_not_contain_plaintext(self):
        """В шифротексте не должно быть открытых слов."""
        key = chatcrypt.new_key()
        plaintext = "секретный текст".encode()
        chat_id = "secret_chat"

        blob = chatcrypt.encrypt(key, plaintext, chat_id)

        assert plaintext not in blob
        assert blob.startswith(chatcrypt.MAGIC)

    def test_two_encryptions_produce_different_blobs(self):
        """Два шифрования одного текста дают разные blob (разные nonce)."""
        key = chatcrypt.new_key()
        plaintext = "одинаковый текст".encode()
        chat_id = "same_chat"

        blob1 = chatcrypt.encrypt(key, plaintext, chat_id)
        blob2 = chatcrypt.encrypt(key, plaintext, chat_id)

        assert blob1 != blob2


class TestDecryptErrors:
    """Тесты на ошибки расшифровки."""

    def test_decrypt_with_wrong_key(self):
        """Расшифровка с чужим ключом бросает CodedError."""
        key1 = chatcrypt.new_key()
        key2 = chatcrypt.new_key()
        plaintext = "важные данные".encode()
        chat_id = "chat"

        blob = chatcrypt.encrypt(key1, plaintext, chat_id)

        with pytest.raises(CodedError) as exc_info:
            chatcrypt.decrypt(key2, blob, chat_id)
        assert exc_info.value.code == "chat_decrypt"

    def test_decrypt_with_modified_ciphertext(self):
        """Изменение байта шифротекста приводит к ошибке."""
        key = chatcrypt.new_key()
        plaintext = "данные".encode()
        chat_id = "chat"

        blob = bytearray(chatcrypt.encrypt(key, plaintext, chat_id))
        # Меняем байт в части шифротекста (после MAGIC + nonce)
        if len(blob) > len(chatcrypt.MAGIC) + chatcrypt.NONCE_SIZE:
            index = len(chatcrypt.MAGIC) + chatcrypt.NONCE_SIZE
            blob[index] ^= 0xFF  # Инвертируем байт

        with pytest.raises(CodedError) as exc_info:
            chatcrypt.decrypt(key, bytes(blob), chat_id)
        assert exc_info.value.code == "chat_decrypt"

    def test_decrypt_with_truncated_blob(self):
        """Обрезанный blob вызывает ошибку."""
        key = chatcrypt.new_key()
        plaintext = "текст".encode()
        chat_id = "chat"

        blob = chatcrypt.encrypt(key, plaintext, chat_id)
        truncated = blob[:-5]  # Убираем несколько байт

        with pytest.raises(CodedError) as exc_info:
            chatcrypt.decrypt(key, truncated, chat_id)
        assert exc_info.value.code == "chat_decrypt"

    def test_decrypt_with_wrong_chat_id(self):
        """Использование чужого chat_id (AAD) приводит к ошибке."""
        key = chatcrypt.new_key()
        plaintext = "данные".encode()
        chat_id_original = "correct_chat"
        chat_id_wrong = "wrong_chat"

        blob = chatcrypt.encrypt(key, plaintext, chat_id_original)

        with pytest.raises(CodedError) as exc_info:
            chatcrypt.decrypt(key, blob, chat_id_wrong)
        assert exc_info.value.code == "chat_decrypt"

    def test_decrypt_with_garbage_file(self):
        """Данные, не являющиеся файлом chatstyle, вызывают ошибку."""
        key = chatcrypt.new_key()
        chat_id = "chat"

        with pytest.raises(CodedError) as exc_info:
            chatcrypt.decrypt(key, b"not a chat", chat_id)
        assert exc_info.value.code == "chat_decrypt"


class TestKeyEncoding:
    """Тесты для encode_key/decode_key."""

    def test_key_round_trip(self):
        """Ключ, закодированный в base64, декодируется обратно."""
        original_key = chatcrypt.new_key()
        encoded = chatcrypt.encode_key(original_key)
        decoded = chatcrypt.decode_key(encoded)

        assert decoded == original_key

    def test_new_key_is_32_bytes(self):
        """new_key() всегда возвращает 32 байта."""
        key = chatcrypt.new_key()
        assert len(key) == chatcrypt.KEY_SIZE

    def test_new_keys_are_different(self):
        """Все вызовы new_key() возвращают разные ключи."""
        keys = [chatcrypt.new_key() for _ in range(10)]
        assert len(set(keys)) == len(keys)

    def test_decode_invalid_base64(self):
        """Декодирование строки, не являющейся base64, бросает CodedError."""
        with pytest.raises(CodedError) as exc_info:
            chatcrypt.decode_key("не base64")
        assert exc_info.value.code == "chat_key_invalid"

    def test_decode_wrong_length(self):
        """Декодирование ключа неправильной длины бросает CodedError."""
        short_key = chatcrypt.encode_key("коротко".encode())
        with pytest.raises(CodedError) as exc_info:
            chatcrypt.decode_key(short_key)
        assert exc_info.value.code == "chat_key_invalid"


class TestEncryptKeyValidation:
    """Тест на валидацию ключа при шифровании."""

    def test_encrypt_with_wrong_key_length_raises_value_error(self):
        """Шифрование с ключом не из 32 байт бросает ValueError."""
        wrong_key = b"short_key"
        plaintext = "данные".encode()
        chat_id = "chat"

        with pytest.raises(ValueError):
            chatcrypt.encrypt(wrong_key, plaintext, chat_id)


class TestWipeFile:
    """Тесты для функции wipe_file."""

    def test_wipe_file_existing(self, tmp_path):
        """Существующий файл удаляется."""
        file_path = tmp_path / "x.bin"
        file_path.write_bytes(b"some data")

        chatcrypt.wipe_file(file_path)

        assert not file_path.exists()

    def test_wipe_file_nonexistent_no_error(self, tmp_path):
        """Вызов для несуществующего файла не бросает исключение."""
        file_path = tmp_path / "nonexistent.bin"

        # Не должно быть исключения
        chatcrypt.wipe_file(file_path)

    def test_wipe_file_wipes_with_zeros(self, tmp_path, monkeypatch):
        """Перед удалением файл затирается нулями."""
        file_path = tmp_path / "x.bin"
        original_data = b"sensitive information"
        file_path.write_bytes(original_data)

        # Сохраняем байты перед удалением через monkeypatch
        wiped_bytes = []
        original_unlink = Path.unlink

        def mock_unlink(self):
            if self.exists():
                with open(self, "rb") as f:
                    wiped_bytes.append(f.read())
            original_unlink(self)

        # Подменяем unlink
        monkeypatch.setattr(Path, "unlink", mock_unlink)

        chatcrypt.wipe_file(file_path)

        # Проверяем, что unlink вызывался и байты были затерты
        assert len(wiped_bytes) == 1
        assert len(wiped_bytes[0]) == len(original_data)
        assert wiped_bytes[0] == b"\x00" * len(original_data)
