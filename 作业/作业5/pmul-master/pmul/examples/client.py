#!/usr/bin/python3

"""
This script creates a P_MUL client which delivers multiple messages to a destination P_MUL server.
"""

import sys
sys.path.append("../")
import pmul
import asyncio
import argparse

class ClientProtocol(pmul.PmulProtocol):
    def __init__(self, conf):
        self.__conf = conf

    def connection_made(self, transport):
        self.transport = transport
        print('P_MUL protocol is ready')
        
    def data_received(self, data, addr):
        print("Received data from {}".format(addr))

    def delivery_completed(self, msid, delivery_status, ack_status):
        print('Delivery of M/Users/heze/Library/Mobile Documents/com~apple~CloudDocs/大三上/分布式系统/作业/作业5/pmul-master/pmul/pmul.pyessage-ID {} finished with {} {}'.format(msid, delivery_status, ack_status))

    async def sendto(self, dest, len):
        message = 'a';
        for i in range(0,len):
            message += 'a';
        bulk_data = message.encode("ascii")
        await self.transport.sendto(bulk_data, [dest])
        print("Finished delivery of message of len {}".format(len))

    async def send_message(self, dst_address, len):
        message = 'a';
        for i in range(0,len):
            message += 'a'.format(len);
        bulk_data = message.encode("ascii")
        result = await self.transport.sendto(bulk_data, [dst_address])
        print('Delivery finished with {} {}'.format(result[0], result[1]))

    async def run(self):
        for i in range(0,self.__conf['num']):
            print('send message {} of len {} to {}'.format(i, self.__conf['message_len'], self.__conf['destination']))
            await self.send_message(self.__conf['destination'], self.__conf['message_len'])
        print('finished message transmission')
    
def init_arguments(conf):
    parser = argparse.ArgumentParser()
    parser.add_argument('-b', '--bind', type=str)
    parser.add_argument('-d', '--destination', type=str)
    parser.add_argument('-m', '--multicast', type=str)
    parser.add_argument('-l', '--length', type=int)
    parser.add_argument('-n', '--num', type=int)
    args = parser.parse_args()

    if args.bind is not None:
        conf['src_ipaddr'] = args.bind

    conf['destination'] = '127.0.0.1'
    if args.destination is None:
        parser.print_help()
        exit()
    else:
        conf['destination'] = args.destination

    if args.multicast is not None:
        conf['mcast_ipaddr'] = args.multicast

    conf['message_len'] = 5000
    if args.length is not None:
        conf['message_len'] = args.length

    conf['num'] = 10
    if args.num is not None:
        conf['num'] = args.num

if __name__ == '__main__':
    loop = asyncio.get_event_loop()
    conf = pmul.conf_init()
    init_arguments(conf)

    coro = pmul.create_pmul_endpoint(ClientProtocol, loop, conf);
    protocol, transport = loop.run_until_complete(coro)
    loop.run_until_complete(protocol.run())
    loop.close()
