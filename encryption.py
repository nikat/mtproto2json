#!/usr/bin/env python3.6
"""This is a prototype module for Telegram client

RSA public keys
AES keys, AES-IGE mode

"""

__author__ = "Nikita Miropolskiy"
__email__ = "nikita@miropolskiy.com"
__license__ = "https://creativecommons.org/licenses/by-nc-nd/4.0/legalcode"
__status__ = "Prototype"


# TODO: use secrets module to compare digests to protect against timing attacks


import base64
import hashlib
import re
import secrets

import pyaes

from byteutils import xor, long_hex, to_bytes, short_hex_int, pack_binary_string, short_hex, sha1, Bytedata

_rsa_public_key_RE = re.compile(r'-----BEGIN RSA PUBLIC KEY-----(?P<key>.*)-----END RSA PUBLIC KEY-----', re.S)


# reads a public RSA key from .pem file, encrypts strings with it
class PublicRSA:
    def __init__(self, pem_data: str):
        match = _rsa_public_key_RE.match(pem_data)
        if not match:
            raise SyntaxError("Error parsing public key data")
        asn1 = base64.standard_b64decode(match.groupdict()['key'])
        n, e = self._read_asn1(Bytedata(asn1))
        self.fingerprint = int.from_bytes(
            hashlib.sha1(pack_binary_string(n[1:]) + pack_binary_string(e)).digest()[-8:], 'little', signed=True)
        self.n = int.from_bytes(n, 'big')
        self.e = int.from_bytes(e, 'big')

    @staticmethod
    def _read_asn1(bytedata):
        field_type, field_length = bytedata.read(2)
        if field_length & 0x80:
            field_length = int.from_bytes(bytedata.read(field_length ^ 0x80), 'big')
        if field_type == 0x30:  # SEQUENCE
            sequence = []
            while bytedata:
                sequence.append(PublicRSA._read_asn1(bytedata))
            return sequence
        elif field_type == 0x02:  # INTEGER
            return bytedata.read(field_length)
        else:
            raise NotImplementedError("Unknown ASN.1 field `%02X` in record")

    def encrypt(self, data: bytes) -> bytes:
        padding_length = max(0, 255 - len(data))
        m = int.from_bytes(data + secrets.token_bytes(padding_length), 'big')
        x = pow(m, self.e, self.n)
        return to_bytes(x)

    def encrypt_with_hash(self, plain: bytes) -> bytes:
        return self.encrypt(sha1(plain) + plain)

# AES encryption in IGE mode
class AesIge:
    def __init__(self, key: bytes, iv: bytes):
        if len(key) != 32:
            raise ValueError("AES key length must be 32 bytes, got %d bytes: %s" %(len(key), short_hex(key)))
        if len(iv) != 32:
            raise ValueError("AES init vector length must be 32 bytes, got %d bytes: %s" %(len(iv), short_hex(key)))
        self.iv1, self.iv2 = iv[:16], iv[16:]
        self.aes = pyaes.AES(key)
        self.plain_buffer = b''

    def decrypt_block(self, cipher_block: bytes) -> bytes:
        plain_block = xor(self.iv1, self.aes.decrypt(xor(self.iv2, cipher_block)))
        self.iv1, self.iv2 = cipher_block, plain_block
        return plain_block

    def decrypt_async_stream(self, loop, executor, reader):
        async def decryptor(n: int) -> bytes:
            while len(self.plain_buffer) < n:
                self.plain_buffer += await loop.run_in_executor(executor, self.decrypt_block, await reader(16))
            plain = self.plain_buffer[:n]
            self.plain_buffer = self.plain_buffer[n:]
            return plain
        return decryptor

    def decrypt(self, cipher: bytes) -> bytes:
        if len(cipher) % 16:
            raise ValueError("cipher length must be divisible by 16 bytes\n%s" % long_hex(cipher))
        return b''.join(self.decrypt_block(plain_block) for plain_block in Bytedata(cipher).blocks(16))

    def encrypt_block(self, plain_block: bytes) -> bytes:
        if len(plain_block) != 16:
            raise RuntimeError("plain block is wrong")
        if len(self.iv1) != 16:
            raise RuntimeError("iv1 block is wrong")
        if len(self.iv2) != 16:
            raise RuntimeError("iv2 block is wrong")
        cipher_block = xor(self.iv2, self.aes.encrypt(xor(self.iv1, plain_block)))
        self.iv1, self.iv2 = cipher_block, plain_block
        return cipher_block

    def encrypt(self, plain: bytes) -> bytes:
        padding = secrets.token_bytes((-len(plain)) % 16)
        return b''.join(self.encrypt_block(plain_block) for plain_block in Bytedata(plain + padding).blocks(16))

    def encrypt_with_hash(self, plain: bytes) -> bytes:
        return self.encrypt(sha1(plain) + plain)

    def decrypt_with_hash(self, cipher: bytes) -> bytes:
        plain_with_hash = self.decrypt(cipher)
        plain = plain_with_hash[20:]
        # hash = plain_with_hash[:20]
        #if sha1(plain) != hash:
        #    raise RuntimeError("Wrong hash while decrypting") #FIXME: this wont work until we know the padding
        return plain


# https://core.telegram.org/mtproto/description#defining-aes-key-and-initialization-vector
def prepare_key_to_write(auth_key: bytes, msg_key: bytes):
    sha1_a = sha1(msg_key + auth_key[:32])
    sha1_b = sha1(auth_key[32:48] + msg_key + auth_key[48:64])
    sha1_c = sha1(auth_key[64:96] + msg_key)
    sha1_d = sha1(msg_key + auth_key[96:128])
    aes_key = sha1_a[:8] + sha1_b[8:20] + sha1_c[4:16]
    aes_iv = sha1_a[8:20] + sha1_b[:8] + sha1_c[16:20] + sha1_d[:8]
    aes = AesIge(aes_key, aes_iv)
    return aes


# https://core.telegram.org/mtproto/description#defining-aes-key-and-initialization-vector
def prepare_key_to_read(auth_key: bytes, msg_key: bytes):
    sha1_a = sha1(msg_key + auth_key[8:40])
    sha1_b = sha1(auth_key[40:56] + msg_key + auth_key[56:72])
    sha1_c = sha1(auth_key[72:104] + msg_key)
    sha1_d = sha1(msg_key + auth_key[104:136])
    aes_key = sha1_a[:8] + sha1_b[8:20] + sha1_c[4:16]
    aes_iv = sha1_a[8:20] + sha1_b[:8] + sha1_c[16:20] + sha1_d[:8]
    aes = AesIge(aes_key, aes_iv)
    return aes

#tests
if __name__ == "__main__":
    server_public_key_file = open('telegram.rsa.pub', 'r').read()
    k = PublicRSA(server_public_key_file)
    print("E = ", short_hex_int(k.e))
    print("N = ")
    print(long_hex(to_bytes(k.n)))
    print("Fingerprint = ", k.fingerprint)


