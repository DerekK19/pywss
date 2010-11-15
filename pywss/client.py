"""
The MIT License

Copyright (c) 2010 Jodi Giordano

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in
all copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN
THE SOFTWARE.
"""

import struct
import hashlib
import socket
import errno
import server

from threading import Thread
from utilities import EventHook


class State:
    NotConnected = 0
    ConnectionEstablished = 1
    Ready = 2
    Disconnected = 3


class Client(Thread):

    def __init__(self, unique_id, socket, address, server_location, server_port):
        Thread.__init__(self)
        
        self.unique_id = unique_id

        self.socket = socket
        self.socket.setblocking(False)

        self.address = address
        self.server_location = server_location
        self.server_port = server_port
        
        self.state = State.ConnectionEstablished

        self.event_data_received = EventHook()
        self.event_connected = EventHook()
        self.event_disconnected = EventHook()


    def __receive_client_handshake(self):
        #todo: close the connection on error

        handshake_raw = self.socket.recv(4096) #todo: how much to receive ?

        handshake_entries = handshake_raw.split('\r\n')

        self._handshake_fields = {}

        self._handshake_fields['Resource'] = handshake_entries.pop(0).split(' ')[1]

        for entry in handshake_entries:
            entry_data = entry.split(': ')

            if (len(entry_data) == 2):
                self._handshake_fields[entry_data[0]] = entry_data[1]

        random_bytes_position = handshake_raw.find('\r\n\r\n')

        self._handshake_fields['Random_bytes'] = handshake_raw[random_bytes_position+4:random_bytes_position+12]

        return self._handshake_fields.has_key('Upgrade') and self._handshake_fields['Upgrade'] == "WebSocket"


    def __build_server_handshake(self):

        #todo: Sec-WebSocket-Protocol

        # build keys
        part_1 = self.__decode_key(self._handshake_fields['Sec-WebSocket-Key1'])
        part_2 = self.__decode_key(self._handshake_fields['Sec-WebSocket-Key2'])

        challenge = struct.pack('>II', part_1, part_2)
        challenge += self._handshake_fields['Random_bytes']

        response = hashlib.md5(challenge).digest()

        self.handshake =  "HTTP/1.1 101 WebSocket Protocol Handshake\r\n"
        self.handshake += "Upgrade: WebSocket\r\n"
        self.handshake += "Connection: Upgrade\r\n"
        self.handshake += "Sec-WebSocket-Origin: {0}\r\n".format(self._handshake_fields['Origin'])
        self.handshake += "Sec-WebSocket-Location: ws://{0}:{1}{2}\r\n\r\n".format(self.server_location, self.server_port, self._handshake_fields['Resource']) #multiple-resource by default
        self.handshake += response


    def __decode_key(self, encrypted_key):
        key = ""
        spaces = 0

        for c in encrypted_key:
            if c.isdigit():
                key += c
            elif c.isspace():
                spaces += 1

        return int(key) / spaces


    def __send_handshake(self):
        self.socket.send(self.handshake)

    #todo: blocking or not blocking ?
    def run(self):
        try:
            while (self.state != State.Disconnected and
                   self.state != State.NotConnected):

                if (not self.state == State.Ready):
                    self.__receive_client_handshake()
                    self.__build_server_handshake()
                    self.__send_handshake()
                    self.state = State.Ready
                    self.event_connected.fire(self)

                try:

                    data = ""
                    received_data = self.socket.recv(4096)

                    try:
                        while (True):
                            data += received_data
                            received_data = self.socket.recv(4096)
                    except socket.error: pass

                    if (data == ""):
                        raise socket.error(errno.WSAEWOULDBLOCK)

                    data = data.decode('utf-8', 'ignore')
                    data = data.lstrip('\x00')
                    #data = data.rstrip('\xFF')

                    commands = data.split('\x00')
 
                    for command in commands:
                        self.event_data_received.fire(self, command)

                except socket.error, msg:
                    if not msg.errno in server.socket_errors:
                        raise

        except socket.error, msg:
           self.stop()

        except KeyboardInterrupt:
            self.interrupt_main()


    def send(self, data):
        self.socket.send("\x00%s\xFF" % data.encode('utf-8'))


    def stop(self):
        self.socket.close()
        self.socket = None

        if (self.state == State.Ready):
            self.state = State.Disconnected
            self.event_disconnected.fire(self)
        else:
            self.state = State.NotConnected


    def __str__(self):
        return "{0}:{1}".format(self.unique_id, self.address)
