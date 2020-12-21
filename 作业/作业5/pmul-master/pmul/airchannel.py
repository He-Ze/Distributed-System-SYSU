
from enum import Enum
import time
import logging
import asyncio
import socket
import struct
import random
import types

WIRELESS_PORT = 27016
MCAST_IPADDR = "224.0.2.240"

REGISTER_PDU = 1
RESPONSE_PDU = 2
DATA_PDU     = 3

def is_mcast(ipaddr):
    addr = socket.inet_aton(ipaddr)
    if addr >= socket.inet_aton('224.0.0.0') and addr <= socket.inet_aton('239.255.255.255'):
        return True
    return False

################################################################################
#
# Protocol PDUs
#
# ControlPdu
#
# 0                   1                   2                   3
# 0 1 2 3 4 5 6 7 8 9 0 1 2 3 4 5 6 7 8 9 0 1 2 3 4 5 6 7 8 9 0 1
# +-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+
# |        PDU_Type             |        Length of PDU          |
# +-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+
# |                         Radio_ID                            |
# +-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+
# |                        Source_Port                          |
# +-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+
#
#
# DataPdu:
#
# 0                   1                   2                   3
# 0 1 2 3 4 5 6 7 8 9 0 1 2 3 4 5 6 7 8 9 0 1 2 3 4 5 6 7 8 9 0 1
# +-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+
# |        PDU_Type             |        Length of PDU          |
# +-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+
# |                      Source Radio ID                        |
# +-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+
# |                    Destination Radio ID                     |
# +-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+
# |                                                             |     
# /                    Data (Variable Length)                   /
# |                                                             | 
# +-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+
# 
##/

################################################################################
## WirelessLink class definition
#
##/
class WirelessLink():

    def __init__(self, loop, channel, datarate, loss, max_qlen):
        self.loop = loop
        self.task = None
        self.datarate = datarate
        self.max_qlen = max_qlen
        self.loss = loss
        self.queue = []
        self.channel = channel
        self.packet_drop_due_overflow = 0
        self.max_queue_fill_level = 0
        self.clients = []

    def add_client(self, ipaddr, port):
        #print('added client {}:{}'.format(ipaddr, port))
        self.clients.append((ipaddr, port))

    def done(self, future):
        # Clear the task handle. Will be created at transmit() again
        self.task = None

    async def handle_enqueued_packet(self):
        while (len(self.queue) > 0):
            msg = self.queue.pop(0)

            # Sleep until the packet has arrived over the wireless channel
            delay = float(len(msg)*8) / float(self.datarate)
            await asyncio.sleep(delay)
            #print("sleep finished after delay of {}".format(delay))

            # Test if the packet was received correctly. This is based on a random packet loss
            rand = random.randrange(101)
            #print("random {} loss: {}".format(rand, self.loss))
            if self.loss > rand:
                #print('Lossed packet - configured loss: {} rand: {}'.format(self.loss, rand))
                self.packet_drop_due_overflow += 1               
            else:
                for cli in self.clients:
                    #print('Send packet of len {}'.format(len(msg)))
                    self.channel.sendto(cli[0], cli[1], msg)

    def transmit(self, msg):
        if len(self.queue) >= self.max_qlen:
            print('Lossed packet due packet overflow');
            self.packet_drop_due_overflow += 1
            return
        if len(self.queue) >= self.max_queue_fill_level:
            self.max_queue_fill_level = len(self.queue)

        # Add message to the transmit queue
        self.queue.append(msg)

        # If transmission timer is not running, then start it
        if self.task is None:
            self.task = asyncio.ensure_future(self.handle_enqueued_packet())
            self.task.add_done_callback(self.done)

################################################################################
## Observer class definitions
##

class Observer():
    def notify(self, message, src_addr):
        print('received message of len {} from {}'.format(len(message), src_addr))

################################################################################
## WirelessChannelClient class definition
#
##/
class WirelessChannelClient(asyncio.DatagramProtocol):

    def __init__(self, loop, observer, local_addr, pyld_port, local_port, srv_addr = "127.0.0.1"):
        if loop is None:
            self.loop = asyncio.get_event_loop()
        else:
            self.loop = loop
        self.observer = observer
        self.registered = False
        self.local_addr = local_addr
        self.local_port = local_port
        self.pyld_port = pyld_port
        self.srv_addr   = srv_addr
        #print("Client {}:{} starts up".format(local_addr, local_port))

        # Create client socket for data transmission
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
        self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.sock.bind(('', local_port))

        asyncio.ensure_future(self.registering())
        #print("start registering()")

    async def registering(self):
        coro = self.loop.create_datagram_endpoint(lambda: self, sock=self.sock)
        await asyncio.wait_for(coro, 1)

        while self.registered is False:
            addr = socket.ntohl(int.from_bytes(socket.inet_aton(self.local_addr), byteorder="big", signed=False))
            message = struct.pack("< H H I I", REGISTER_PDU, 12, addr, self.local_port)
            #print("Client sends register message to ({}:{})".format(self.srv_addr, WIRELESS_PORT))
            self.transport.sendto(message, (self.srv_addr, WIRELESS_PORT))
            await asyncio.sleep(5)

    def sendto(self, remote_ipaddr, port, payload):
        src_addr = int.from_bytes(socket.inet_aton(self.local_addr), byteorder="big", signed=False)
        dst_addr = int.from_bytes(socket.inet_aton(remote_ipaddr), byteorder="big", signed=False)
        src_addr = socket.ntohl(src_addr)
        dst_addr = socket.ntohl(dst_addr)

        message = struct.pack("< H H I I I", DATA_PDU, 16+len(payload), src_addr, dst_addr, port)
        buf = bytearray(message)
        buf.extend(payload)

        if self.transport is not None:
            self.transport.sendto(buf, (self.srv_addr, WIRELESS_PORT))

    def connection_made(self, transport):
        self.transport = transport
        #print('Client Connection is made')

    def ctrl_packet_received(self, message, addr):
        #print("Client successully registered at WirelessChannel")
        self.registered = True

    def data_packet_received(self, message, addr):
        #print("Client received data packet  of len {} from WirelessChannel".format(len(message)))
        unpacked = struct.unpack("< H H I I I", message[:16])
        src_addr = socket.inet_ntoa(struct.pack("I",unpacked[2]))
        dst_addr = socket.inet_ntoa(struct.pack("I",unpacked[3]))
        port = unpacked[4]
        payload = message[16:]
        if port != self.pyld_port:
            #print("{} Destination port {} does not match our own port {}".format(self.local_addr, port, self.pyld_port))
            return
        #print("{} Received a packet on port {}".format(self.local_addr, port))
        if self.observer is not None:
            self.observer.notify(payload, src_addr)

    def datagram_received(self, data, addr):
        #print("Client received packet {} of len {} from {}".format(data, len(data), addr))
        tlv_packed = data[:4]
        tlv_unpacked = struct.unpack("< H H", tlv_packed)
        tlv_type = tlv_unpacked[0]
        tlv_len  = tlv_unpacked[1]

        if tlv_type is RESPONSE_PDU:
            self.ctrl_packet_received(data, addr)
        elif tlv_type is DATA_PDU:
            self.data_packet_received(data, addr)
        else:
            print("Received unkown PDU type {}".format(tlv_type))
        
################################################################################
## WirelessLink class definition
#
##/
class WirelessChannel(asyncio.DatagramProtocol):

    def __init__(self, loop):
        if loop is None:
            self.loop = asyncio.get_event_loop()
        else:
            self.loop = loop
        self.clients = {}
        self.links = {}

        #print("Create socket for beaconing")
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
        #self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        #self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEPORT, 1)
        #print('socket listens to port {}'.format(WIRELESS_PORT))
        self.sock.bind(('', WIRELESS_PORT))
        #mreq = struct.pack("=4sl", socket.inet_aton(MCAST_IPADDR), socket.INADDR_ANY)
        #self.sock.setsockopt(socket.IPPROTO_IP, socket.IP_ADD_MEMBERSHIP, mreq)

        #print("Create multicast beacon task")
        self.task = asyncio.ensure_future(self.start())

    def add_link(self, ipaddr, datarate, loss, max_qlen):
        if ipaddr not in self.links:
            self.links[ipaddr] = WirelessLink(self.loop, self, datarate, loss, max_qlen)

    def sendto(self, dst_addr, port, message):
        self.transport.sendto(message, (dst_addr, port))

    def connection_made(self, transport):
        self.transport = transport
        #print('Connection is made')

    def ctrl_packet_received(self, message, addr):
        unpacked = struct.unpack("< H H I I", message)
        remote_addr = socket.inet_ntoa(struct.pack("I",unpacked[2]))
        remote_port = unpacked[3]
        key = (remote_addr, remote_port)
        if key not in self.clients:
            #print("Registered new client {}".format(key))
            self.clients[key] = True
        if remote_addr in self.links:
            self.links[remote_addr].add_client(addr[0], addr[1])
        myaddr = socket.ntohl(int.from_bytes(socket.inet_aton("0.0.0.0"), byteorder="big", signed=False))
        message = struct.pack("< H H I I", RESPONSE_PDU, 12, myaddr, WIRELESS_PORT)
        #print("Server sends response message to ({}:{})".format(remote_addr, remote_port))
        self.transport.sendto(message, addr)

    def data_packet_received(self, message, addr):
        unpacked = struct.unpack("< H H I I", message[:12])
        src_addr = socket.inet_ntoa(struct.pack("I",unpacked[2]))
        dst_addr = socket.inet_ntoa(struct.pack("I",unpacked[3]))
        if is_mcast(dst_addr) is True:
            for key in self.links:
                if key != src_addr:
                    #print("transmit packet from {} to {}".format(src_addr, key))
                    self.links[key].transmit(message)
        else:
            if dst_addr in self.links:
                self.links[dst_addr].transmit(message)
            else:
                print("no link available for {}".format(dst_addr))
        
    def datagram_received(self, data, addr):
        #print("Received packet of len {} from {}".format(len(data), addr))

        tlv_packed = data[:4]
        tlv_unpacked = struct.unpack("< H H", tlv_packed)
        tlv_type = tlv_unpacked[0]
        tlv_len  = tlv_unpacked[1]

        if tlv_type is REGISTER_PDU:
            self.ctrl_packet_received(data, addr)
        elif tlv_type is DATA_PDU:
            self.data_packet_received(data, addr);
        else:
            print("Received unkown PDU type {}".format(tlv_type))

    async def start(self):
        coro = self.loop.create_datagram_endpoint(lambda: self, sock=self.sock)
        await asyncio.wait_for(coro, 5)

