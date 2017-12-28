#!/usr/bin/env python3.6
"""This is a prototype module

This module implements transport component and Cryptographic layer of MTProto for Telegram.
https://core.telegram.org/mtproto#general-description

"""


__author__ = "Nikita Miropolskiy"
__email__ = "nikita@miropolskiy.com"
__license__ = "https://creativecommons.org/licenses/by-nc-nd/4.0/legalcode"
__status__ = "Prototype"


import asyncio
import secrets
import time
from concurrent.futures import ThreadPoolExecutor


import encryption
import primes
import tl
from byteutils import to_bytes, sha1, xor, base64decode, base64encode
from tcp import AbridgedTCP


_singleton_executor = None
_singleton_scheme = None

def _get_executor():
    global _singleton_executor
    if _singleton_executor is None:
        _singleton_executor = ThreadPoolExecutor(max_workers=3)
    return _singleton_executor

def _get_scheme(in_thread):
    global _singleton_scheme
    if _singleton_scheme is None:
        _singleton_scheme = tl.Scheme(in_thread, open('scheme.tl', 'r').read() + "\n" + open('service.tl', 'r').read())
    return _singleton_scheme


class MTProto:
    def __init__(self, loop, host: str, port: int, public_rsa_key: str):
        self._loop = loop
        self._link = AbridgedTCP(loop, host, port)
        self._public_rsa_key = encryption.PublicRSA(public_rsa_key)
        self._auth_key = None
        self._auth_key_id = None
        self._auth_key_lock = asyncio.Lock()
        self._read_message_lock = asyncio.Lock()
        self._session_id = secrets.randbits(64)
        self._client_salt = int.from_bytes(secrets.token_bytes(4), 'little', signed=True)
        self._server_salt = 0
        self._last_message_id = 0
        self._executor = _get_executor()
        self._scheme = _get_scheme(self._in_thread)


    async def _in_thread(self, *args, **kwargs):
        return await self._loop.run_in_executor(self._executor, *args, **kwargs)

    def _get_message_id(self):
        message_id = (int(time.time() * 2 ** 30) | secrets.randbits(12)) * 4
        if message_id <= self._last_message_id:
            message_id = self._last_message_id + 4
        self._last_message_id = message_id
        return message_id

    # reading and writing messages at service level

    async def _read_unencrypted_message(self):
        async with self._read_message_lock:
            return await self._scheme.read(
                self._link.read,
                is_boxed=False,
                parameter_type='unencrypted_message'
            )

    def _write_unencrypted_message(self, **kwargs):
        message = self._scheme.bare(
            _cons='unencrypted_message',
            auth_key_id=0,
            message_id=0,
            body=self._scheme.boxed(**kwargs)
        )
        return self._loop.create_task(self._link.write(message.get_flat_bytes()))

    async def _get_auth_key(self):
        async with self._auth_key_lock:
            if self._auth_key is None:
                await self._create_auth_key()
        return self._auth_key, self._auth_key_id

    async def _create_auth_key(self):
        generate_b = self._loop.create_task(self._in_thread(secrets.randbits, 2048))
        nonce = await self._in_thread(secrets.token_bytes, 16)

        await self._write_unencrypted_message(_cons='req_pq', nonce=nonce)

        respq = (await self._read_unencrypted_message()).body

        # check if we have got the right public key
        if self._public_rsa_key.fingerprint not in respq.server_public_key_fingerprints:
            raise ValueError("Our certificate is not supported by the server")

        server_nonce = respq.server_nonce
        pq = int.from_bytes(respq.pq, 'big', signed=False)

        new_nonce, (p, q) = await asyncio.gather(
            self._in_thread(secrets.token_bytes, 32),
            self._in_thread(primes.factorize, pq)
        )

        p_string = to_bytes(p)
        q_string = to_bytes(q)

        # request Diffie–Hellman parameters
        p_q_inner_data = self._scheme.boxed(
                _cons='p_q_inner_data',
                pq=respq.pq,
                p=p_string,
                q=q_string,
                nonce=nonce,
                server_nonce=server_nonce,
                new_nonce=new_nonce
        ).get_flat_bytes()

        await self._write_unencrypted_message(
            _cons='req_DH_params',
            nonce=nonce,
            server_nonce=server_nonce,
            p=p_string,
            q=q_string,
            public_key_fingerprint=self._public_rsa_key.fingerprint,
            encrypted_data=self._public_rsa_key.encrypt_with_hash(p_q_inner_data)
        )
        params = (await self._read_unencrypted_message()).body

        if params != 'server_DH_params_ok' or params.nonce != nonce or params.server_nonce != server_nonce:
            raise RuntimeError("Diffie–Hellman exchange failed: `%r`", params)

        # https://core.telegram.org/mtproto/auth_key#presenting-proof-of-work-server-authentication
        tmp_aes_key = sha1(new_nonce + server_nonce) + sha1(server_nonce + new_nonce)[:12]
        tmp_aes_iv = sha1(server_nonce + new_nonce)[12:] + sha1(new_nonce + new_nonce) + new_nonce[:4]

        tmp_aes = encryption.AesIge(tmp_aes_key, tmp_aes_iv)
        answer, b = await asyncio.gather(
            self._in_thread(tmp_aes.decrypt_with_hash, params.encrypted_answer),
            generate_b
        )

        params2 = await self._scheme.read_from_string(answer)

        # FIXME! save server_time
        # print(params2.server_time)
        # print(time.time())

        if params2 != 'server_DH_inner_data':
            raise RuntimeError("Diffie–Hellman exchange failed: `%r`", params2)

        dh_prime = int.from_bytes(params2.dh_prime, 'big')
        g = params2.g
        g_a = int.from_bytes(params2.g_a, 'big')
        if (params2.nonce != nonce
            or params2.server_nonce != server_nonce
            or not primes.is_safe_dh_prime(g, dh_prime)):
            raise RuntimeError("Diffie–Hellman exchange failed: `%r`", params2)

        g_b, self._auth_key = map(to_bytes, await asyncio.gather(
            self._in_thread(pow, g, b, dh_prime),
            self._in_thread(pow, g_a, b, dh_prime)
        ))
        self._set_auth_key_id()
        self._server_salt = int.from_bytes(xor(new_nonce[:8], server_nonce[:8]), 'little', signed=True)

        client_DH_inner_data = self._scheme.boxed(
            _cons='client_DH_inner_data',
            nonce=nonce,
            server_nonce=server_nonce,
            retry_id=0,
            g_b=g_b
        ).get_flat_bytes()

        tmp_aes = encryption.AesIge(tmp_aes_key, tmp_aes_iv)
        await self._write_unencrypted_message(
            _cons='set_client_DH_params',
            nonce=nonce,
            server_nonce=server_nonce,
            encrypted_data=await self._in_thread(tmp_aes.encrypt_with_hash, client_DH_inner_data)
        )

        params3 = (await self._read_unencrypted_message()).body

        if params3 != 'dh_gen_ok':
            raise RuntimeError("Diffie–Hellman exchange failed: `%r`", params3)

    def _set_auth_key_id(self):
        self._auth_key_id = sha1(self._auth_key)[-8:]

    async def read(self):
        auth_key, auth_key_id = await self._get_auth_key()
        async with self._read_message_lock:
            server_auth_key_id = await self._link.read(8)
            if server_auth_key_id != auth_key_id:
                raise RuntimeError("Received a message with unknown auth_key!", server_auth_key_id)
            msg_key = await self._link.read(16)
            aes = await self._in_thread(encryption.prepare_key_to_read, auth_key, msg_key)
            decryptor = aes.decrypt_async_stream(self._loop, self._executor, self._link.read)
            message = await self._scheme.read(decryptor, is_boxed=False, parameter_type='message_inner_data')
            #FIXME check session_id and salt
            return message.message

    def set_session(self, auth_key: str, session_id: int):
        self._auth_key = base64decode(auth_key)
        self._session_id = session_id
        self._set_auth_key_id()

    def get_session(self):
        return base64encode(self._auth_key), self._session_id

    def set_server_salt(self, salt: int):
        self._server_salt = salt

    def get_server_salt(self):
        return self._server_salt

    def write(self, seq_no: int, **kwargs):
        message_id = self._get_message_id()
        message = self._scheme.bare(
            _cons='message',
            msg_id=message_id,
            seqno=seq_no,
            body=self._scheme.boxed(**kwargs)
        )
        self._loop.create_task(self._write(message))
        return message_id

    async def _write(self, message):
        auth_key, auth_key_id = await self._get_auth_key()
        message_inner_data = self._scheme.bare(
            _cons='message_inner_data',
            salt=self._server_salt,
            session_id=self._session_id,
            message=message
        ).get_flat_bytes()
        msg_key = (await self._in_thread(sha1, message_inner_data))[4:20]
        aes = await self._in_thread(encryption.prepare_key_to_write, auth_key, msg_key)
        encrypted_message = await self._in_thread(aes.encrypt, message_inner_data)
        full_message = self._scheme.bare(
            _cons='encrypted_message',
            auth_key_id=int.from_bytes(auth_key_id, 'little', signed=False),
            msg_key=msg_key,
            encrypted_data=encrypted_message
        ).get_flat_bytes()
        await self._link.write(full_message)

    async def stop(self):
        await self._link.stop()
        pass
