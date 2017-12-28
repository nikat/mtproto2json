#!/usr/bin/env python3.6
"""This is a prototype module

This module implements Abdidged TCP for Telegram MTProto
 https://core.telegram.org/mtproto#tcp-transport
 
"""

__author__ = "Nikita Miropolskiy"
__email__ = "nikita@miropolskiy.com"
__license__ = "https://creativecommons.org/licenses/by-nc-nd/4.0/legalcode"
__status__ = "Prototype"


from asyncio import Lock, open_connection


class AbridgedTCP:
    def __init__(self, loop, host, port):
        self._loop = loop
        self._host = host
        self._port = port
        self._connect_lock = Lock()
        self._buffer = b''
        self._reader = None
        self._writer = None
        self._write_lock = Lock()

    async def _reconnect_if_needed(self):
        async with self._connect_lock:
            if self._reader is None or self._writer is None:
                # set limit to 16 mb
                self._reader, self._writer = await open_connection(self._host, self._port, loop=self._loop, limit=2**24)
                print("RECONNECT")
                self._writer.write(b'\xef')

    async def _write_abridged_packet(self, data: bytes) -> None:
        await self._reconnect_if_needed()
        packet_data_length = len(data) >> 2
        if packet_data_length < 0x7f:
            self._writer.write(packet_data_length.to_bytes(1, 'little'))
        elif packet_data_length <= 0x7fffff:
            self._writer.write(b'\x7f')
            self._writer.write(packet_data_length.to_bytes(3, 'little'))
        else:
            raise OverflowError('Packet data is too long')
        self._writer.write(data)

    async def _read_abridged_packet(self) -> bytes:
        await self._reconnect_if_needed()
        packet_data_length = ord(await self._reader.readexactly(1))
        if packet_data_length > 0x7f:
            raise NotImplementedError("Wrong packet data length %d" % packet_data_length)
        if packet_data_length == 0x7f:
            packet_data_length = int.from_bytes(await self._reader.readexactly(3), 'little', signed=False)
        return await self._reader.readexactly(packet_data_length * 4)

    async def read(self, nbytes: int) -> bytes:
        while len(self._buffer) < nbytes:
            self._buffer += await self._read_abridged_packet()
        result = self._buffer[:nbytes]
        self._buffer = self._buffer[nbytes:]
        return result

    async def write(self, data: bytes) -> None:
        async with self._write_lock:
            while len(data) > 0:
                chunk_len = min(len(data), 0x7fffff)
                await self._write_abridged_packet(data[:chunk_len])
                data = data[chunk_len:]

    async def stop(self) -> None:
        # not implemented yet
        # drain ouptut and cancel reading
        pass
