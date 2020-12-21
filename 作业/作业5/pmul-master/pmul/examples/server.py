#!/usr/bin/python3

import sys
sys.path.append("../")
import pmul
import asyncio
import argparse

class ServerProtocol(pmul.PmulProtocol):
    def __init__(self, conf):
        self.__conf = conf

    def connection_made(self, transport):
        self.transport = transport
        print('P_MUL protocol is ready')
        
    def data_received(self, data, addr):
        print("Received data from {}".format(addr))

    def delivery_completed(self, msid, delivery_status, ack_status):
        print('Delivery of Message-ID {} finished with {} {}'.format(msid, delivery_status, ack_status))

async def forever():
    while True:
        try:
            await asyncio.sleep(1)
        except KeyboardInterrupt:
            pass

def init_arguments(conf):
    parser = argparse.ArgumentParser()
    parser.add_argument('-b', '--bind', type=str)
    args = parser.parse_args()
    if args.bind is None:
        parser.print_help()
        exit()
    else:
        conf['src_ipaddr'] = args.bind

if __name__ == '__main__':
    loop = asyncio.get_event_loop()
    conf = pmul.conf_init()
    init_arguments(conf)
    coro = pmul.create_pmul_endpoint(ServerProtocol, loop, conf);
    protocol, transport = loop.run_until_complete(coro)
    loop.run_until_complete(forever())
    loop.close()

