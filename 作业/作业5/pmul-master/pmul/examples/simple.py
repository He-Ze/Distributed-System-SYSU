#!/usr/bin/python3

"""
This script creates a P_MUL instance which sends data to itself.
"""

import sys
sys.path.append("../")
import pmul
import asyncio

class LoopbackProtocol(pmul.PmulProtocol):
    def __init__(self, conf):
        self.__conf = conf

    def connection_made(self, transport):
        self.transport = transport
        print('P_MUL protocol is ready')
        
    def data_received(self, data, addr):
        print("Received data from {}".format(addr))

    def delivery_completed(self, msid, delivery_status, ack_status):
        print('Delivery of Message-ID {} finished with {} {}'.format(msid, delivery_status, ack_status))

    async def sendto(self, dest, len):
        message = 'a';
        for i in range(0,len):
            message += 'a';
        bulk_data = message.encode("ascii")
        await self.transport.sendto(bulk_data, [dest])
        print("Finished delivery of message of len {}".format(len))

loop = asyncio.get_event_loop()
conf = pmul.conf_init()
coro = pmul.create_pmul_endpoint(LoopbackProtocol, loop, conf);
protocol, transport = loop.run_until_complete(coro)
loop.run_until_complete(protocol.sendto("127.0.0.1", 10000))
loop.close()