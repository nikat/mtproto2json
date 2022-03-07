## Disclaimer ##
Please note that with the release of Td::TdJson and MTProto 2.0 this tool has become outdated.

Please use LL-mtproto instead, it's derived from my code: https://github.com/andrew-ld/LL-mtproto


# FAQ #

## What is mtproto2json? ##

**mtproto2json** is a prototype proxy service for testing Telegram API (not to be confused with Telegram Bot API, to the countrary Telegram API is what's used by Telegram client apps). It uses JSON/TCP to talk to clients and MTProto to talk to Telegram API servers.

## What is Telegram? ##

Telegram is a cloud-based instant messaging and social service. https://telegram.org

## What does this proxy do? ##

Telegram uses a complicated encryption scheme called MTProto. *More info on MTProto here: https://core.telegram.org/mtproto*

While MTProto is open and documented, it uses binary serialization and encryption and is	comparatively difficult to implement.

**mtproto2json** implements MTProto for you, you only need to establish a JSON/TCP connection to start writing your app and it's usually very easy to do in any language or framework.

You might want to create a simple utility, to prototype an application or just to play with new Telegram API methods without having to implement MTProto. **mtproto2json** allows your application to use JSON/TCP streams instead.

You could also start developing your application with **mtproto2json** and switch to native MTProto implementation later.

## What is JSON? ##

JSON is a very common and a language-independent data format. Almost every platform, programming language and framework has simple and well-known ways to use JSON objects. JSON objects are human-readable, much easier to test and to debug than encrypted binary MTProto objects.

## There are libraries implementing MTProto, why would I use mtproto2json? ##

**mtproto2json** is not a library, it's a service. You can use it with applications written in any language or framework and sometimes it's simpler than including a library.

Another reason to use **mtproto2json** over other MTProto implementations is that the Telegram TL scheme is constantly updated. Other libraries are slow to catch with new methods and new features.

**mtproto2json** uses **scheme.tl** dynamically and depends on a very small subset of TL methods and types, so we don't have to rewrite or regenerate the library code to follow **scheme.tl** updates. The only thing you need to update after updating **scheme.tl** is the TL_LAYER parameter in **localsettings.py**.

*More on TL language here: https://core.telegram.org/mtproto/TL*

*The most recent scheme.tl for Telegram can be found here: https://raw.githubusercontent.com/telegramdesktop/tdesktop/dev/Telegram/Resources/scheme.tl*

## License? ##

**mtproto2json** is distributed under Creative Commons Attribution-NonCommercial-NoDerivatives 4.0 license https://creativecommons.org/licenses/by-nc-nd/4.0/legalcode

For commercial use please address the author.

# Description # 

This utility implements encryption and binary serialization layers of **MTProto** client protocol for **Telegram messenger**. It allows developing Telegram client applications in a simple way in any programming language using only a JSON parser and a TCP connection.

**client** ⇄ (JSON/TCP) ⇄ **streamjson.py**  ⇄ (MTProto) ⇄ **Telegram**

**streamjson.py** works as a TCP server, it reads and writes JSON objects separated by newlines. Connections are proxied to Telegram API using MTProto protocol. For each client one or multiple MTProto connections to Telegram API are established. JSON objects from clients are serialized into MTProto objects using TL scheme from **scheme.tl**, encrypted and sent to Telegram servers. MTProto objects from Telegram API are unencrypted, deserialized and forwarded to clients as JSON objects. Multiple connections per client and concurrent clients supported. Clients don't share MTProto connections or any data.

More info on MTProto here: https://core.telegram.org/mtproto

Telegram Messenger: https://telegram.org

**mtproto2json** is written in Python 3.6 and has only one external dependency: **pyaes**.

# Installation #

## Prerequisites ##

* Python 3.6 or above
* pyaes

*mtproto2json is not platform-dependent and would work on either Linux, OSX or Windows*

## Installing Python 3.6 on Ubuntu 16.10 and newer ##

```commandline
sudo apt install python3.6 python3-pip
```

## Installing Python 3.6 on Ubuntu 16.04 and older ##

```commandline
sudo apt-get install software-properties-common python-software-properties
sudo add-apt-repository ppa:jonathonf/python-3.6
sudo apt-get update
sudo apt-get install python3.6 python3-pip
```

## Installing pyaes ##

```commandline
python3.6 -m pip install pyaes
```

# Quickstart example #

 1. If you don't have a Telegram account yet, install one of the official clients (https://telegram.org/apps) and create an account. 
 2. Sign in on https://my.telegram.org and obtain **api_id** and **api_hash** as described here: https://core.telegram.org/api/obtaining_api_id.
 3. Install Python3.6, pyaes and netcat
 4. Download and unpack mtproto2json using either git or this link: https://github.com/nikat/mtproto2json/archive/master.zip
 5. Open a command line, start **streamsjon.py** and let it run
 6. Open another command line and run **signin-cli.py**
 7. Enter your phone number (for example 79001002030), api parameters, code and password.
 8. Output should look like `{"id": 1, "session": {"session_id": <...>, "auth_key": "<...>"}}`. Save this output as a single string to your clipboard and/or a file. 
 
 *NOTE: this is your authorization data, keep it secret and dont share! Anyone knowing this string can use your Telegram session without a password.*
 
 9. Connect to streamjson with netcat `nc localhost 1543`
 10. Paste the saved output to stdin.
 11. Copy and paste the following JSON code to your console: 
 
 ```
 {"message":{"_cons":"messages.getDialogs","offset_date":0,"offset_id":0,"offset_peer":{"_cons":"inputPeerEmpty"},"limit":0}}
 ```
 
 12. You should receive an answer to your *messages.getDialogs* request with id=1 and client updates with id=0.
 
 ```
 {"id": 0, "message": {"_cons": "updates", "updates": [{"_cons": "updateNewChannelMessage", "message": {"_cons": "message", "id": ...
 {"id": 0, "message": {"_cons": "updateShort", "update": {"_cons": "updateChatUserTyping", "chat_id": ...
 {"id": 1, "message": {"_cons": "messages.dialogsSlice", "count": 452, "dialogs": [{"_cons": "dialog", "pinned": {"_cons": "true"}, "peer": { ...
{"id": 0, "message": {"_cons": "updates", "updates": [{"_cons": "updateNewChannelMessage", "message": {"_cons": "message", "id":  ...
...
 ```
 
 13. Read **scheme.tl** to learn functions, parameters and types for requests and responses. More on TL language here: https://core.telegram.org/mtproto/TL
 
# Detailed description #

## signin-cli.py ##

```text
usage: signin-cli.py [-h] [--host HOST] [--port PORT] [--phone PHONE_NUMBER]
                     [--password PASSWORD] [--api-id API_ID]
                     [--api-hash API_HASH] [--device-model DEVICE_MODEL]
                     [--system-version SYSTEM_VERSION]
                     [--app-version APP_VERSION] [--lang-code LANG_CODE]


optional arguments:
  -h, --help            show this help message and exit
  --host HOST           connect to HOST (default: localhost)
  --port PORT           listen to PORT (default: 1543)
  --phone PHONE_NUMBER              phone number, for example: 79001002030
  --password PASSWORD               password
  --api-id API_ID                   Get your own api_id here: https://my.telegram.org/apps
  --api-hash API_HASH               Get your own api_hash here: https://my.telegram.org/apps
  --device-model DEVICE_MODEL       default: `Python`
  --system-version SYSTEM_VERSION   default: `<your python version -- sys.version>`
  --app-version APP_VERSION         default: `prototype`
  --lang-code LANG_CODE             default: `en`)
```

## streamjson.py ##

```text
Usage: streamjson.py [-h] [--host HOST] [--port PORT] [--verbose]
                     [--print-tracebacks] [--send-tracebacks]


optional arguments:
  -h, --help          show this help message and exit
  --host HOST         bind to HOST (default: localhost)
  --port PORT         listen to PORT (default: 1543)
  --verbose           copy all objects to stdout
  --print-tracebacks  enable printing tracebacks to stderr
  --send-tracebacks   enable sending tracebacks to client
```

Starts a TCP server, reads and writes JSON objects, one per line.
For each client a MTProto connection to Telegram API is established. TCP/JSON service works as a proxy:

* JSON objects from clients are serialized into MTProto objects using TL scheme and sent to Telegram servers.
* MTProto objects from the Telegram servers are deserialized and forwarded to clients as JSON objects.
* concurrent clients supported, clients don't share MTProto connections or any data

More info on MTProto here: https://core.telegram.org/mtproto

## stdio/pipe interface ##

If you prefer stdin/stdout interface, please use netcat utility: `nc localhost 1543`.

# JSON API #

Client sends objects containing any of the following attributes in any combination. 

Server answers each request with a single response which includes **"id"** attribute to distinguish responses. 

Messages from telegram are sent asynchronously and always have **id** equal to zero. 

Error messages contain **error** attribute and can have negative **id** or **id** from request.

Example:

```json
{
  "id" : 100,
  "message": {
    "_cons": "ping",
    "ping_id": 100
  }
}
```
*NOTE: we are using linebreaks and identation in this and the following examples only for clarity. Since **mtproto2json** expects one JSON object per line, you will have to eliminate line breaks in your JSON objects*

## id ##

Numeric. Optional, defaults to 1 when omitted.

## server ##

Object. Optional, sets and gets server parameters. A response will always contain **server** attribute with current (or new) parameters.

```json
{
    "id" : 100,
    "server": {},
    "message" : {
        "_cons" : ... ,
        ...
    }
}
```
or  
```json
{
    "id" : 100,
    "server": {
        "host": "149.154.167.40",
        "port": 443,
        "rsa": "-----BEGIN RSA PUBLIC KEY-----\n ..."
    }
}
```

*Note1: default host, port and RSA key are specified in localsettings.py*

*Note2: 149.154.167.40 is the telegram DC2 test server, it won't allow you to start a new session*

## session ##

Object. Optional, sets and gets MTProto key and session. A response will always contain **session** attribute
with current (or new) parameters. `last_seqno` is the last client seqno acknowledged by server, this value must
be stored with the session.

```json
{
    "session": {}
}
```
or 
```json
{
    "session": {
        "auth_key": "<2048 bit key in base64 encoding>",
        "session_id": 53201012847611012222,
    }
}
```

## message ##

Object. Optional attribute, forms and sends a message to Telegram server. Must have *_cons* attribute.
Utility establishes the first connection to Telegram for the client just after is receives the first message
from this client. *_seqno* is optional, next odd integer is used when it is omitted.

*Note: available methods and fields are listed in scheme.tl file in TL Language and documented (very poorly :-( ) at the telegram website: https://core.telegram.org/methods*

*TL Language is documented here: https://core.telegram.org/mtproto/TL*

*You can always obtain the most recent scheme.tl from Telegram Desktop source code repository: https://github.com/telegramdesktop/tdesktop/blob/master/Telegram/Resources/scheme.tl*

*Please update TL_LAYER in localsettings.py if you choose to update the TL Scheme.*

Request example:

```json
{
    "id" : 104,
    "message": {
        "_cons": "namespace.functionFromScheme",
        "parameter_str": "value",
        "parameter_num": 555
    }
}
```

Another request example:

```json
{
    "id" : 203,
    "message": {
        "_cons": "namespace.functionFromScheme",
        "field1": "value",
        "field2": {
            "_cons": "namespace.functionFromScheme",
            "field3vector": [1, 2, 3, 4, 5],
            "field4float": -15.11111
        }
    }
}
```

If you need to call a polymorphic constructor with **{X:Type}**, use **_wrapped** field to send the parametric type object.
For example:

```json
{
    "id" : 104,
    "message": {
        "_cons": "invokeWithLayer",
        "layer": 66,
        "_wrapped": {
            "_cons": "initConnection",
            "api_id": 33333,
            ...
        }
    }
}
```

Possible response:

```json
{
    "id" : 104,
    "message": {
        "_cons": "returnedCons",
        "field1": "value1",
        "field2": "value2"
    }
}
```

Rpc error:

```json
{
    "id" : 104,
    "message": {
        "_cons": "rpc_error",
        "error_message": ...
    }
}
```

Possible error that came outside of rpc_result

```json
{
    "id" : 0,
    "message": {
        "_cons": "bad_msg_notification",
        "bad_msg_id": 111222333444,
        ...
    }
}
```

If telegram failed to return anything in 10 seconds:

```json
{
    "id" : 104,
    "message": {
        "_cons": "rpc_timeout",
        "error_message": ...
    }
}
```

Another possible response:

```json
{
    "id" : 104,
    "message": {
        "_cons": "namespace.typeFromScheme",
        "field1": ... ,
        "field2:": {
            "_cons": "anotherNamespace.anotherTypeFromScheme",
            "field1": ... ,
            "field2:": ...
        }
    }
}
```

## updates ##

Updates will be issued by **streamjson.py** as messages with **id** equal to zero:

```json
{
    "id" : 0,
    "message": {
        "_cons": "updateShortMessage",
        ...
    }
}
```

Another example:

```json
{
  "id": 0,
  "message": {
    "_cons": "updates",
    "updates": [
      {
        "_cons": "updateNewChannelMessage",
        "message": {
          "_cons": "message",
          "id": 2222,
          "from_id": 55555555,
          "to_id": {
            "_cons": "peerChannel",
            "channel_id": 11111111
          },
          "date": 1494517469,
          "message": "text"
        },
        "pts": 11111,
        "pts_count": 1
      }
    ],
    "users": [
      {
        "_cons": "user",
        "id": 333333333,
        "access_hash": -1111111111111,
        "first_name": "name",
        "username": "username",
        "status": {
          "_cons": "userStatusRecently"
        }
      }
    ],
    "chats": [
      {
        "_cons": "channel",
        "megagroup": {
          "_cons": "true"
        },
        "democracy": {
          "_cons": "true"
        },
        "id": 11111111,
        "access_hash": -11111111111111111,
        "title": "channel",
        "photo": {
          "_cons": "chatPhoto",
          "photo_small": {
            "_cons": "fileLocation",
            "dc_id": 2,
            "volume_id": 1111111,
            "local_id": 11111111,
            "secret": 11111111111111
          },
          "photo_big": {
            "_cons": "fileLocation",
            "dc_id": 2,
            "volume_id": 22222222,
            "local_id": 2222222,
            "secret": -222222222222
          }
        },
        "date": 1493486262,
        "version": 0
      }
    ],
    "date": 1494517468,
    "seq": 0
  }
}
```
