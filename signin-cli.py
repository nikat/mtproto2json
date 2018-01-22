#!/usr/bin/env python3.6
"""This is a prototype module
"""

__author__ = "Nikita Miropolskiy"
__email__ = "nikita@miropolskiy.com"
__license__ = "https://creativecommons.org/licenses/by-nc-nd/4.0/legalcode"
__status__ = "Prototype"
__description__ = \
'''Connects to streamjson.py utility, performs Telegram sign in sequence, outputs session as JSON for further use.

Example usage: 
    - start streamsjon.py
    - run this utility, by default it will connect to streamjson.py
    - enter your phone number, code and password
    - you can't submit the code as a parameter because it makes no sense to do that
    - save it's output as my_session.json
    - load this session into another client later

Additional parameters:
    More info about extra parameters here: https://core.telegram.org/method/initConnection
    
More info: https://bitbucket.org/nikat/mtproto2json/overview
'''


import argparse
import socket
import json
import sys
import getpass
import hashlib
import base64
import warnings

from localsettings import TL_LAYER


def get_password_hash(password:str, salt:str) -> str:
    binsalt = base64.b64decode(salt)
    binpassword = password.encode('utf-8')
    binhash = hashlib.sha256(binsalt + binpassword + binsalt).digest()
    return base64.b64encode(binhash).decode('ascii')


def parse_command_line_args():
    parser = argparse.ArgumentParser(
        description=__description__,
        add_help=True,
        formatter_class=argparse.RawTextHelpFormatter
    )
    parser.add_argument('--host', dest='host', default='localhost', help='connect to HOST (default: localhost)')
    parser.add_argument('--port', dest='port', default=1543, type=int, help='listen to PORT (default: 1543)')
    parser.add_argument('--phone', dest='phone_number', default=None, help='phone number, for example: 79001002030')
    parser.add_argument('--password', dest='password', default=None, help='password')
    parser.add_argument('--api-id', dest='api_id', help='Get your own api_id here: https://my.telegram.org/apps')
    parser.add_argument('--api-hash', dest='api_hash', help='Get your own api_hash here: https://my.telegram.org/apps')
    parser.add_argument('--device-model', dest='device_model', default='Python', help='default: `Python`')
    parser.add_argument('--system-version', dest='system_version', default=sys.version, help='default: `%s`' % sys.version)
    parser.add_argument('--app-version', dest='app_version', default='prototype', help='default: `prototype`')
    parser.add_argument('--lang-code', dest='lang_code', default='en', help='default: `en`)')
    return parser.parse_args()


def send(jstream, d: dict):
    request = json.dumps(d)
    print(request, file=jstream)
    jstream.flush()


def receive(jstream):
    msg = json.loads(jstream.readline())
    return msg['message']


def prompt_string(prompt: str, hide: bool=False):
    if hide:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            ret = getpass.getpass(prompt=prompt + ' ')
    else:
        sys.stderr.write(prompt + ' ')
        sys.stderr.flush()
        ret = input()
    return ret


if __name__ == "__main__":
    command_line_args = parse_command_line_args()
    json_server = (command_line_args.host, command_line_args.port)
    json_client = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        json_client.connect(json_server)
    except ConnectionRefusedError:
        print("Can't connect to %s:%s" % json_server, file=sys.stderr)
        exit(-1)
    json_stream = json_client.makefile('rw', encoding='utf-8')

    phone_number = command_line_args.phone_number or prompt_string('Phone number:')
    api_id = command_line_args.api_id or prompt_string('App api_id (you can get one at https://my.telegram.org/apps):')
    api_hash = command_line_args.api_hash or prompt_string('App api_hash:')

    send(json_stream, dict(
        message=dict(
            _cons='invokeWithLayer',
            layer=TL_LAYER,
            _wrapped=dict(
                _cons='initConnection',
                api_id=api_id,
                device_model=command_line_args.device_model,
                system_version=command_line_args.system_version,
                app_version=command_line_args.app_version,
                lang_code=command_line_args.lang_code,
                system_lang_code=command_line_args.lang_code,
                lang_pack='',
                _wrapped=dict(
                    _cons='auth.sendCode',
                    phone_number=phone_number,
                    api_id=api_id,
                    api_hash=api_hash,
                )
            )
        )
    ))

    result = receive(json_stream)
    if 'error_message' in result:
        raise RuntimeError(result)

    phone_code = prompt_string('Code:')

    send(json_stream, dict(
        message=dict(
            _cons='auth.signIn',
            phone_number=phone_number,
            phone_code_hash=result['phone_code_hash'],
            phone_code=phone_code
        )
    ))

    result = receive(json_stream)

    if 'error_message' in result:
        if result['error_message'] != 'SESSION_PASSWORD_NEEDED':
            raise RuntimeError(result)

        send(json_stream, dict(
            message=dict(
                _cons='account.getPassword'
            )
        ))

        result = receive(json_stream)
        if 'error_message' in result:
            raise RuntimeError(result)

        current_salt = result["current_salt"]
        password = command_line_args.password or prompt_string('Password:', hide=True)
        password_hash = get_password_hash(password, current_salt)

        send(json_stream, dict(
            message=dict(
                _cons='auth.checkPassword',
                password_hash=password_hash
            )
        ))

        result = receive(json_stream)
        if 'error_message' in result:
            raise RuntimeError(result)

    send(json_stream, dict(session=dict()))
    print(json_stream.readline())

    exit(0)
