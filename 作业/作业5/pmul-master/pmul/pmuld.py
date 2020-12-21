#!/usr/bin/python3

"""
This script run a P_MUL protocol as daemon waiting for requests on a UDP socket.
"""

import sys
import pmul
import asyncio
import argparse
import logging
import socket
import json

PMUL_SERVER_PORT = 32103

class UdpReceiver():
    def udp_packet_received(self, data, addr):
        logger.debug('Received data from daemon socket')

class UdpSocket(asyncio.DatagramProtocol):
    def __init__(self, conf, receiver, logger):
        self.loop = conf['loop']
        self.src_ipaddr = conf['src_ipaddr']
        self.port = conf['daemon_port']
        self.receiver = receiver
        self.cli_ipaddr = None
        self.cli_port = None
        self.__logger = logger

        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
        self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.__logger.error('P_MUL daemon listens to {}:{}'.format(self.src_ipaddr, self.port))
        self.sock.bind((self.src_ipaddr, self.port))
        asyncio.ensure_future(self.start())

    async def start(self):
        coro = self.loop.create_datagram_endpoint(lambda: self, sock=self.sock)
        await asyncio.wait_for(coro, 1) 

    def connection_made(self, transport):
        self.transport = transport
        self.__logger.debug('UDP socket is ready')

    def datagram_received(self, data, addr):
        self.__logger.debug("Received message from {}".format(addr))
        msg = json.loads(data)
        if msg['type'] == 'register':
            self.cli_ipaddr = addr[0];
            self.cli_port = addr[1];
            self.__logger.error("Registered client {}".format(addr))
        elif msg['type'] == 'send':
            self.receiver.udp_packet_received(msg['payload'], msg['destinations'])  
        else:
            self.__logger.error("Received unkown message from client")

    def error_received(self, exc):
        self.__logger.debug('Error received:', exc)

    def connection_lost(self, exc):
        self.__logger.debug("Socket closed, stop the event loop")
        self.transport = None

    def send_delivery_complete_to_client(self):
        msg = dict()
        msg['type'] = 'finished'
        jmsg = json.dumps(msg)
        self.__.logger.debug('send delivery complete to {}:{}'.format(self.cli_ipaddr, self.cli_port))
        self.transport.sendto(jmsg.encode("ascii"), (self.cli_ipaddr, self.cli_port))

    def send_received_message_to_client(self, data, from_addr):
        msg = dict()
        msg['type'] = 'message'
        msg['from_addr'] = from_addr
        msg['payload'] = data.decode("utf-8")
        self.__logger.debug('Received data {}'.format(data))
        jmsg = json.dumps(msg)
        self.__logger.debug('Send received message to client')
        self.transport.sendto(jmsg.encode("ascii"), (self.cli_ipaddr, self.cli_port))

class PmulDaemon(pmul.PmulProtocol, UdpReceiver):
    def __init__(self, conf):
        self.__conf = conf
        self.__loop = conf['loop']
        # Create logging system
        self.__logger = logging.getLogger('pmuld')
        if conf['logfile'] is not 'stdout':
            fh = logging.FileHandler(conf['logfile'])
            self.__logger.addHandler(fh)
        if conf['loglevel'] is 'debug':
            self.__logger.setLevel(logging.DEBUG)
        else:
            self.__logger.setLevel(logging.ERROR)
        # Create UDP socket for communication with the P_MUL protocol server
        self.udp_socket = UdpSocket(conf, self, self.__logger);

    def udp_packet_received(self, data, destinations):
        self.__logger.debug('Send message of len {} to {}'.format(len(data), destinations))
        asyncio.ensure_future(self.sendto(destinations, data))

    def connection_made(self, transport):
        self.transport = transport
        self.__logger.debug('P_MUL daemon is running')
        
    def data_received(self, data, addr):
        self.__logger.debug('Received data from {}'.format(addr))
        self.udp_socket.send_received_message_to_client(data, addr)

    def delivery_completed(self, msid, delivery_status, ack_status):
        self.__logger.debug('Delivery of Message-ID {} finished with {} {}'.format(msid, delivery_status, ack_status))

    async def sendto(self, dests, data):
        self.__logger.debug("try to send a message of len {} to {}".format(len(data), dests))
        await self.transport.sendto(data.encode("ascii"), dests)
        self.__logger.debug("Finished delivery of message of len {}".format(len))
        self.udp_socket.send_delivery_complete_to_client()
    
def init_arguments(conf):
    parser = argparse.ArgumentParser()
    parser.add_argument('-b', '--bind', type=str)
    parser.add_argument('-p', '--port', type=str)
    parser.add_argument('-m', '--multicast', type=str)
    parser.add_argument('-l', '--loglevel', type=str)
    parser.add_argument('-f', '--logfile', type=str)
    args = parser.parse_args()

    if args.bind is not None:
        conf['src_ipaddr'] = args.bind
    if args.multicast is not None:
        conf['mcast_ipaddr'] = args.multicast
    if args.port is not None:
        conf['daemon_port'] = args.port
    else:
        conf['daemon_port'] = PMUL_SERVER_PORT
    if args.loglevel is not None:
        conf['loglevel'] = args.loglevel
    if args.logfile is not None:
        conf['logfile'] = args.logfile      

async def forever():
    while True:
        try:
            await asyncio.sleep(1)
        except KeyboardInterrupt:
            pass

if __name__ == '__main__':
    loop = asyncio.get_event_loop()
    conf = pmul.conf_init()
    init_arguments(conf)
    conf['loop'] = loop

    coro = pmul.create_pmul_endpoint(PmulDaemon, loop, conf);
    protocol, transport = loop.run_until_complete(coro)
    loop.run_until_complete(forever())
    loop.close()
