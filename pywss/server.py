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

import socket
import errno
import platform

from client import Client
from utilities import EventHook


#==============================================================================#
#==============================================================================#

def build_socket_errors():
    error_codes = [errno.EAGAIN]

    if platform.system() == 'Windows':
        error_codes.append(errno.WSAEWOULDBLOCK)
    else:
        error_codes.append(errno.ENODATA)

    return error_codes

socket_errors = build_socket_errors()    

#==============================================================================#
#==============================================================================#


class WebSocketsServer:

    def __init__(self, location, port):

        self.location = "localhost" if location == "" else location
        self.port = port
        self.max_queued_connections = 5
        self.event_data_received = EventHook()
        self.event_client_connected = EventHook()
        self.event_client_disconnected = EventHook()

        self.running = False

        self.__clients = {}
        self.__next_client = 0


    def start(self):

        self.__socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.__socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1) #reuse the address as soon as possible
        self.__socket.setblocking(False)
        self.__socket.bind((self.location, self.port))
        self.__socket.listen(self.max_queued_connections)

        self.running = True

        print "Waiting for clients from ws://{0}:{1}".format(self.location, self.port)

        while self.running:
            try:
                client_socket, client_address = self.__socket.accept()

                client = Client(self.__next_client, client_socket, client_address, self.location, self.port)
                client.event_data_received += self.__on_data_received
                client.event_connected += self.__on_client_connected
                client.event_disconnected += self.__on_client_disconnected

                self.__next_client += 1

                client.start()

            except socket.error, msg:
                if not msg.errno in socket_errors:
                    raise


    def __on_data_received(self, client, data):
        print("Data received [{0}: {1}].".format(client.unique_id, data))

        self.event_data_received.fire(client.unique_id, data)


    def __on_client_connected(self, client):
        print "Client connected [{0}].".format(client)

        self.__clients[client.unique_id] = client
        self.event_client_connected.fire(client.unique_id)


    def __on_client_disconnected(self, client):
        print "Client disconnected [{0}].".format(client)

        self.__clients.pop(client.unique_id)
        self.event_client_disconnected.fire(client.unique_id)


    def send_to(self, unique_id, data):
        self.__clients[unique_id].send(data)


    def send_all(self, data):
        for client in self.__clients.values():
            client.send(data)


    def stop(self):
        print 'Stopping the WebSockets server.'

        for client in self.__clients.values():
            client.stop()

        self.__socket.close()

        self.running = False

        print 'WebSockets Server stopped gracefully.'
