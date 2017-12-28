#!/usr/bin/env python3.6
"""This is a prototype module
"""
import time
import datetime

__author__ = "Nikita Miropolskiy"
__email__ = "nikita@miropolskiy.com"
__license__ = "https://creativecommons.org/licenses/by-nc-nd/4.0/legalcode"
__status__ = "Prototype"
__description__ = \
'''Starts a concurrent TCP server on <host:port>. Reads and writes JSON objects, one per line.
Client can inquire a MTProto connection to the Telegram server. (more info: https://core.telegram.org/mtproto)

After a MTProto connection is established it works as a proxy:
    - JSON objects from the client are serialized into MTProto objects using TL scheme and sent to the Telegram server.
    - MTProto objects from the Telegram server are deserialized and forwarded to the client as JSON objects.

More info: https://bitbucket.org/mtproto2json/mtproto2json/overview
'''


import json
import sys
import argparse
import asyncio
import traceback


import mtproto

from localsettings import TELEGRAM_HOST, TELEGRAM_PORT, TELEGRAM_RSA

class PendingRequest():
    def __init__(self, loop, message):
        self.request = message
        self.response = loop.create_future()

class Session:
    def __init__(self, reader, writer, peername, loop, args):
        self._peername = peername
        self._mtproto = None
        self._json_in = reader
        self._json_out = writer
        self._loop = loop
        self._print_objects = args.print_objects
        self._print_tracebacks = args.print_tracebacks
        self._send_tracebacks = args.send_tracebacks
        self._msgids_to_ack = []
        self._last_time_acks_flushed = time.time()
        self._last_seqno = 0
        self._stable_seqno = False
        self._seqno_increment = 1
        self._mtproto_loop = None
        self._mtproto_read_future = None
        self._pending_requests = dict()
        self._future_flood_wait = None
        self._host = TELEGRAM_HOST
        self._port = TELEGRAM_PORT
        self._rsa = TELEGRAM_RSA

    def _get_next_odd_seqno(self):
        self._last_seqno = ((self._last_seqno + 1) // 2) * 2 + 1
        return self._last_seqno

    def _get_next_even_seqno(self):
        self._last_seqno = (self._last_seqno//2 + 1) * 2
        return self._last_seqno

    def log(self, message):
        print(str(datetime.datetime.now()), self._peername, message, file=sys.stdout)

    async def receive_line(self, line: bytes) -> bool:
        if line in (b'\n', '\n'):
            return True
        try:
            request = json.loads(line, encoding='utf-8')
        except json.JSONDecodeError as exception:
            self.write_json(id=-2, error='JSONDecodeError', msg=exception.msg, pos=exception.pos, doc=line.decode('utf-8'))
            return False
        if self._print_objects:
            self.log('> %s' % line.decode('utf-8')[:-1])
        try:
            await self.receive_json(request)
        except Exception:
            etype, evalue, tb = sys.exc_info()
            traceback.print_exception(etype, evalue, tb if self._print_tracebacks else None, file=sys.stderr)
            response = dict(id=request.get('id', -3), error=etype.__name__, msg=' '.join(getattr(evalue, 'args', ())))
            if self._send_tracebacks:
                response['traceback'] = traceback.format_tb(tb)
            self.write_json(**response)
            return False
        return True

    def start_mtproto_loop(self):
        self._seq_no = -1
        if self._mtproto is not None:
            self._mtproto_loop.cancel()
            self._mtproto = None
        self.log("connecting to Telegram at %s:%d" % (self._host, self._port))
        self._mtproto_loop = self._loop.create_task(self.mtproto_loop())
        self._mtproto = mtproto.MTProto(self._loop, self._host, self._port, self._rsa)

    def _handle_json_server(self, rserver):
        if 'host' in rserver:
            self._host = rserver['host']
            self._port = server['port']
            self._rsa = server['rsa']
        return dict(
            host=self._host,
            port=self._port,
            rsa=self._rsa
        )

    def _handle_json_session(self, session):
        if self._mtproto is None:
            self.start_mtproto_loop()
        if 'auth_key' in session:
            auth_key = session['auth_key']
            session_id = session['session_id']
            self._mtproto.set_session(auth_key, session_id)
            return dict(status="ok")
        try:
            auth_key, session_id = self._mtproto.get_session()
        except TypeError:
            return dict(error_message="no session found, please provide your session or send a message to create a new one")
        return dict(
            session_id=session_id,
            auth_key=auth_key,
        )

    def _delete_pending_request(self, msg_id):
        if msg_id in self._pending_requests:
            print("Timeout, no rpc_response, I am deleting this:", self._pending_requests[msg_id].request)
            self._pending_requests[msg_id].response.set_result(dict(_cons='rpc_timeout', error_message='no response from telegram'))

    async def _handle_json_message(self, message):
        if self._mtproto is None:
            self.start_mtproto_loop()
        if '_cons' not in message:
            raise RuntimeError('`_cons` attribute is required in message object')
        pending_request = PendingRequest(self._loop, message)
        return await self._rpc_call(pending_request)

    async def _rpc_call(self, pending_request):
        self._flush_msgids_to_ack()
        seqno = self._get_next_odd_seqno()
        if self._print_objects:
            self.log("^ %r" % dict(_cons='message', seqno=seqno, body=pending_request.request))
        await self._flood_sleep()
        message_id = self._mtproto.write(seqno, **pending_request.request)
        self._pending_requests[message_id] = pending_request
        self._loop.call_later(600, self._delete_pending_request, message_id)
        response = await pending_request.response
        self._seqno_increment = 1
        if message_id in self._pending_requests:
            del self._pending_requests[message_id]
        return response

    async def receive_json(self, request):
        response = dict(id=request.get('id', 1))
        if 'server' in request:
            response['server'] = self._handle_json_server(request['server'])
        if 'session' in request:
            response['session'] = self._handle_json_session(request['session'])
        if 'message' in request:
            response['message'] = await self._handle_json_message(request['message'])
        self.write_json(**response)

    async def read_loop(self):
        self.log('connected')
        while True:
            try:
                line = await self._json_in.readline()
            except ConnectionResetError:
                self.disconnect()
                return
            if line is b'':
                self.disconnect()
                return
            await self.receive_line(line)

    async def mtproto_loop(self):
        self.log("mtproto loop started")
        while True:
            try:
                self._mtproto_read_future = self._loop.create_task(self._mtproto.read())
                message_mtproto = await self._mtproto_read_future
                self._process_telegram_message(message_mtproto)
                if len(self._msgids_to_ack) >= 32 or (time.time() - self._last_time_acks_flushed) > 10:
                    self._flush_msgids_to_ack()
            except asyncio.CancelledError:
                return

    def _process_telegram_message(self, message) -> None:
        self._update_last_seqno_from_incoming_message(message)
        if self._print_objects:
            self.log("v %r" % message)
        body = message.body.packed_data if message.body == 'gzip_packed' else message.body
        if body == 'msg_container':
            for m in body.messages:
                self._process_telegram_message(m)
        else:
            self._process_telegram_message_body(body)
            self._acknowledge_telegram_message(message)

    def _process_telegram_message_body(self, body):
        if body == 'new_session_created':
            pass
        elif body == 'msgs_ack':
            pass
        elif body == 'bad_server_salt':
            self._process_bad_server_salt(body)
        elif body == 'bad_msg_notification' and body.error_code == 32 and not self._stable_seqno:  # msg_seqno too low
            self._process_bad_msg_notification_msg_seqno_too_low(body)
        elif body == 'rpc_result':
            if body.result == 'rpc_error' and body.result.error_message[:11] == 'FLOOD_WAIT_':
                self._process_rpc_error_flood_wait(body)
            else:
                self._process_rpc_result(body)
        else:
            self._process_any_other_telegram_message(body)

    def _acknowledge_telegram_message(self, message):
        if message.seqno % 2 == 1:
            self._msgids_to_ack.append(message.msg_id)
            #self._flush_msgids_to_ack()

    def _flush_msgids_to_ack(self):
        self._last_time_acks_flushed = time.time()
        if not self._msgids_to_ack or not self._stable_seqno:
            return
        seqno = self._get_next_even_seqno()
        if self._print_objects:
            self.log("^ %r" % dict(_cons='message', seqno=seqno, body=dict(_cons='msgs_ack', msg_ids=self._msgids_to_ack)))
        self._mtproto.write(seqno, _cons='msgs_ack', msg_ids=self._msgids_to_ack)
        self._msgids_to_ack = []

    def _process_any_other_telegram_message(self, body):
        self.write_json(id=0, message=body.get_dict())

    def _update_last_seqno_from_incoming_message(self, message):
        self._last_seqno = max(self._last_seqno, message.seqno)

    def _process_bad_server_salt(self, body):
        # TODO: dont store messages and use future_salts method instead
        if self._mtproto.get_server_salt != 0:
            #self._last_seqno = 0
            self._stable_seqno = False
        self._mtproto.set_server_salt(body.new_server_salt)
        self.log('updating salt: %d' % body.new_server_salt)
        if body.bad_msg_id in self._pending_requests:
            bad_request = self._pending_requests[body.bad_msg_id]
            self._loop.create_task(self._rpc_call(bad_request))
        else:
            self.log("bad_msg_id not found")

    def _process_bad_msg_notification_msg_seqno_too_low(self, body):
        self._seqno_increment = min(2**31 - 1, self._seqno_increment << 1)
        self._last_seqno += self._seqno_increment
        self.log('updating seqno by %d to %d' % (self._seqno_increment, self._last_seqno))
        if body.bad_msg_id in self._pending_requests:
            bad_request = self._pending_requests[body.bad_msg_id]
            self._loop.create_task(self._rpc_call(bad_request))
            del self._pending_requests[body.bad_msg_id]

    def _process_rpc_error_flood_wait(self, body):
        seconds_to_wait = 2 * int(body.result.error_message[11:])
        self._set_flood_wait(seconds_to_wait)
        if body.req_msg_id in self._pending_requests:
            pending_request = self._pending_requests[body.req_msg_id]
            self._loop.create_task(self._rpc_call(pending_request))
            del self._pending_requests[body.bad_msg_id]

    def _process_rpc_result(self, body):
        self._stable_seqno = True
        if body.req_msg_id in self._pending_requests:
            pending_request = self._pending_requests[body.req_msg_id]
            if body.result == 'gzip_packed':
                result = body.result.packed_data
            else:
                result = body.result
            pending_request.response.set_result(result.get_dict())
        else:
            self.log("req_msg_id not found")

    def write_json(self, **kwargs):
        response = json.dumps(kwargs)
        if self._print_objects:
            self.log('< %s' % response)
        self._json_out.write(response.encode('utf-8')+b'\n')

    def _flood_wait(self):
        return self._future_flood_wait is not None and not self._future_flood_wait.done()

    async def _flood_sleep(self):
        if self._flood_wait():
            await self._future_flood_wait

    def _set_flood_wait(self, seconds_to_wait):
        if not self._flood_wait():
            self._future_flood_wait = self._loop.create_future()
            self._loop.create_task(self._resume_after_flood_wait_delay(seconds_to_wait))

    async def _resume_after_flood_wait_delay(self, seconds_to_wait):
        print("FLOOD_WAIT for %d seconds", seconds_to_wait)
        await asyncio.sleep(seconds_to_wait)
        self._future_flood_wait.set_result(True)

    def disconnect(self):
        # TODO graceful stop here
        #self._mtproto_read_future.cancel()
        self._flush_msgids_to_ack()
        self._loop.create_task(self._mtproto.stop())
        self.log('disconnected')
        del self._mtproto


def parse_command_line_args():
    parser = argparse.ArgumentParser(
        description=__description__,
        add_help=True,
        formatter_class=argparse.RawTextHelpFormatter
    )
    parser.add_argument('--host', dest='host', default='localhost', help='bind to HOST (default: localhost)')
    parser.add_argument('--port', dest='port', default=1543, type=int, help='listen to PORT (default: 1543)')
    parser.add_argument('--verbose', dest='print_objects', action='store_true', help='copy all objects to stdout')
    parser.add_argument('--print-tracebacks', dest='print_tracebacks', action='store_true', help='enable printing tracebacks to stderr')
    parser.add_argument('--send-tracebacks', dest='send_tracebacks', action='store_true', help='enable sending tracebacks to client')
    return parser.parse_args()


def connection_factory(*args):
    async def connection(reader, writer):
        peername = '%s:%d' % writer.transport._extra['peername'][:2]
        session = Session(reader, writer, peername, *args)
        await session.read_loop()
        writer.close()
    return connection


if __name__ == "__main__":
    command_line_args = parse_command_line_args()

    def global_exception_handler(etype, evalue, tb):
        traceback.print_exception(etype, evalue, tb if command_line_args.print_tracebacks else None, file=sys.stderr)
        exit(getattr(evalue, 'errno', -1))

    sys.excepthook = global_exception_handler

    main_loop = asyncio.get_event_loop()
    #main_loop.set_debug(True)
    #main_loop.slow_callback_duration = 0.015
    factory = connection_factory(main_loop, command_line_args)
    server = asyncio.start_server(factory, command_line_args.host, command_line_args.port, loop=main_loop)
    server_task = main_loop.run_until_complete(server)

    print('Started listening on', ', '.join('%s:%d' % s.getsockname()[:2] for s in server_task.sockets), file=sys.stdout)

    try:
        main_loop.run_forever()
    except KeyboardInterrupt:
        print('Interrupted by signal. Exiting.', file=sys.stdout)
        pass
    finally:
        server_task.close()
        main_loop.run_until_complete(main_loop.shutdown_asyncgens())
        main_loop.close()