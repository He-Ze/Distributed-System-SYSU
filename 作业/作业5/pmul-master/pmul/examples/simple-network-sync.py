#!/usr/bin/python3

import sys
sys.path.append("../")
import airchannel as chan
import pmul
import asyncio

class UserProtocol(pmul.PmulProtocol):
    def __init__(self, conf):
        self.__conf = conf

    def connection_made(self, transport):
        self.transport = transport
        print('P_MUL protocol is ready')
        
    def data_received(self, data, addr):
        print("Received data from {}".format(addr))

    def delivery_completed(self, msid, delivery_status, ack_status):
        print('Delivery of Message-ID {} finished with {} {}'.format(msid, delivery_status, ack_status))

    async def send(self, dst_addresses, msglen):
        message = 'a';
        for i in range(0,msglen):
            message += 'a';
        bulk_data = message.encode("ascii")
        print("send a message of len {}".format(msglen))
        result = await self.transport.sendto(bulk_data, dst_addresses)
        print('Delivery finished with {} {}'.format(result[0], result[1]))

    async def run(self, dests, msglen, iterations):
        for i in range(0,iterations):
            await self.send(dests, msglen)
            print("finished delivery of message")
        print("finished message transmission")
        
async def forever():
    while True:
        try:
            await asyncio.sleep(1)
        except KeyboardInterrupt:
            pass

if __name__ == '__main__':
    loop = asyncio.get_event_loop()
    conf = pmul.conf_init()

    channel = chan.WirelessChannel(loop)
    channel.add_link("198.18.10.250", 25000, 10, 20)
    channel.add_link("198.18.20.250", 25000, 10, 20)
    channel.add_link("198.18.30.250", 25000, 10, 20)

    # Radio 1
    conf["src_ipaddr"] = "198.18.10.250"
    conf["chan_cli_port"] = 8000
    conf["chan_srv_port"] = 8001
    coro = pmul.create_pmul_endpoint(UserProtocol, loop, conf);
    protocol1, transport1 = loop.run_until_complete(coro)

    # Radio 2
    conf["src_ipaddr"] = "198.18.20.250"
    conf["chan_cli_port"] = 8002
    conf["chan_srv_port"] = 8003
    coro = pmul.create_pmul_endpoint(UserProtocol, loop, conf);
    protocol2, transport2 = loop.run_until_complete(coro)

    # Radio 3
    conf["src_ipaddr"] = "198.18.30.250"
    conf["chan_cli_port"] = 8004
    conf["chan_srv_port"] = 8005
    coro = pmul.create_pmul_endpoint(UserProtocol, loop, conf);
    protocol3, transport3 = loop.run_until_complete(coro)

    loop.run_until_complete(protocol1.run(['198.18.20.250','198.18.30.250'], 10000, 3))
    loop.run_until_complete(forever())
    loop.close()

