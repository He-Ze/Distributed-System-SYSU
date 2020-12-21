#!/usr/bin/python3

from enum import Enum
from enum import IntEnum
from datetime import datetime
from datetime import timedelta
import random
import time
import logging
import asyncio
import socket
import struct
import logging
import random
from . import airchannel as chan

logger = logging.getLogger('pmul')
logger.setLevel(logging.ERROR)

################################################################################
## TODOs
#
# - Calculate goodput in kbit/s
# 
# - Calculate loss-rate per peer
#
# - Save statistics in a json file.
#   Adapts timing on startup
#   pmul-settings.json can be writte also by an other process (similar to TCP timings)
#   flush statistics on startup
#
# Performance:
#  - The first window shall be sent with minimum delay to measure the maximum datarate
#    The datarate must also be increased to fill the pipe.
#
# Robustness:
# - Remove contexts after a expiration_timeout
#   Create context if data was received (wait for AddressPdu)
# - Adapt PDU length based on channel conditions (packet-loss)
# - Add channel codong
# - Add RxOnly mode -> Use AirDatarate and Packet loss based on an external process
# - Adaptive Window size (no lookup table)
#
# Debugging:
# - Calculate metrics based on logged information (e.g. probepoint)
# - Log for display of a sequence chart
#   Execute test and generate sequence chart

################################################################################
## Constants
#

# The minimum PDU delay between sending packets
MIN_PDU_DELAY = 10 # msec

# The maximum allowed priority of P_MUL PDUs
MAX_PRIORITY = 7

# Indicating that TransmissionPhase is a retransmission 
IS_RETRANSMISSION = True

# Assumption of the maximum AddressPdu length. Is used to calculate the AckPduTimeout 
MAX_ADDRESS_PDU_LEN = 100

# Assumption of the maximum AckPdu length. Is used to calculate the AckPduTimeout
MAX_ACK_PDU_LEN = 100

# The delay between AckPDUs at a multicast communication 
ACK_PDU_DELAY_MSEC = 500 # 500sec

# The minimum length of a P_MUL packet
MINIMUM_PACKET_LEN = 4

# The length of a destination entry PDU 
DESTINATION_ENTRY_LEN = 8

# The minimum length of an address-pdu
MINIMUM_ADDRESS_PDU_LEN = 32

# The length of the Data PDU
DATA_PDU_HDRLEN = 24

# The minimum length of an AckInfo entry
MINIMUM_ACK_INFO_ENTRYLEN = 24

# The minimum length of an AckPdu
MINIMUM_ACK_PDU_LEN = 14

# PDU types
class PduType(IntEnum):
    Data = 0
    Ack = 1
    Address = 2
    Unkown = 3
    ExtraAddress = 4

class Option(IntEnum):
    TsVal = 0
    TsEcr = 1

# Event types for RX statemachine
class RxEvent(Enum):
    Entry = 0
    Exit = 1
    AddressPdu = 2
    ExtraAddressPdu = 3
    DataPdu = 4
    LastPduTimeout = 5
    AckPduTimeout = 6

class Traffic(Enum): 
    Message = 0
    Bulk = 1

################################################################################
## Exception class definitions
##

class ClientException(Exception): pass

# Divide message into a list of fragments with given MTU size
def fragment(message, mtu_size): 
    fragments = []
    curr = 0
    while curr < len(message):
        if len(message[curr:]) > mtu_size:
            fragments.append(message[curr:curr+mtu_size])
            curr += mtu_size
        else:
            fragments.append(message[curr:])
            curr += len(message[curr:])
    return fragments

# Reassemble dictionary of fragments into a complete message
def reassemble(fragments): 
    message = bytearray()
    for i, val in fragments.items():
        message.extend(val)
    return message

# Calculate datarate based on a start timestamp and the received bytes
def calc_datarate(ts, bytes):
    datarate = 0
    d = datetime.now() - ts
    msec = timedelta_milli(d)
    if msec > 0:
        datarate = (float)(bytes*8*1000) / msec
    logger.info("RCV | Datarate(): {} Received bytes: {} Interval: {}".format(int(datarate), bytes, msec))
    return round(datarate)

# Calculate an average datarate. Weight-Factor: 50%
def avg_datarate(old, new):
    avg = old * 0.50 + new * 0.50
    logger.info("RCV | Avg_datarate() old: {} bit/s new: {} bit/s avg: {} bit/s".format(old, new, avg))
    return round(avg)

# Calculate the time period to wait for the remaining bytes
def calc_remaining_time(remaining_bytes, rx_datarate):
    if rx_datarate == 0:
        rx_datarate = 5000 # just to be sure we have a value here
    msec = 1000.0 * remaining_bytes * 8 / rx_datarate
    logger.info("RCV | Remaining Time {} msec - Payload {} bytes - AirDatarate: {} bit/s".format(round(msec), remaining_bytes, rx_datarate))
    return round(msec)

# Convert an integer into a byte
def int_to_bytes(x):
    return x.to_bytes((x.bit_length() + 7)//8, 'big')

# Convert a byte into an integer
def int_from_bytes(xbytes):
    return int.from_bytes(xbytes, 'big')

# Convert milliseconds into datetime representation
def milli_to_date(milli):
    if milli == None:
        return None
    elif milli < 0:
        return datetime.utcfromtimestamp(0) + datetime.timedelta(seconds=(milli/1000))
    else:
        return datetime.utcfromtimestamp(milli/1000)

# Convert a datetime into milliseconds
def date_to_milli(date):
    if isinstance(date, datetime):
        epoch = datetime.utcfromtimestamp(0)
        return round((date - epoch).total_seconds() * 1000.0)

def timedelta_milli(td):
    return td.days*86400000 + td.seconds*1000 + td.microseconds/1000

def message_len(fragments):
    bytes = 0
    for i,val in enumerate(fragments):
        bytes = bytes + len(val) 
    return bytes

def get_sent_bytes(fragments):
    bytes = 0
    for key in fragments:
        bytes = bytes + fragments[key]["len"]
    return bytes

def received_all_acks(dest_status_list):
    for addr in dest_status_list:
        if dest_status_list[addr].ack_received == False:
            return False
    return True

def num_sent_fragments(fragments):
    count = 0
    for key in fragments:
        if fragments[key].sent == True:
            count = count + 1
    return count

# Returns a dict() of all unacked fragment sizes
def unacked_fragments(dest_status_list, fragments, cwnd): 
    unacked_list = dict()
    curr = 0
    for i,val in enumerate(fragments):
        for addr in dest_status_list:
            if dest_status_list[addr].fragment_ack_status[i] == False:
                if i not in unacked_list:
                    unacked_list[i] = dict()
                    unacked_list[i]['sent'] = False
                    unacked_list[i]['len'] = len(fragments[i])
                    curr += len(fragments[i])
                    if curr >= cwnd:
                        # Reached window limit
                        logger.debug("TX unacked_fragments: {} cwnd: {} curr: {}".format(unacked_list, cwnd, curr))
                        return unacked_list
    logger.debug("TX unacked_fragments: {}".format(unacked_list))
    return unacked_list

def get_seqnohi(tx_fragments):
    seqno = 0
    for key in tx_fragments:
        seqno = key
    return seqno

def get_cwnd(cwnd_list, air_datarate):
    for i,val in enumerate(cwnd_list):
        if air_datarate <= val["datarate"]:
            return val["cwnd"]
    return 5000

################################################################################
## Pdu Header
# 
# 0                   1                   2                   3
# 0 1 2 3 4 5 6 7 8 9 0 1 2 3 4 5 6 7 8 9 0 1 2 3 4 5 6 7 8 9 0 1
# +-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+
# |        Length_of_PDU        |    Priority   |MAP|  PDU_Type |
# +-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+
#
class Pdu():
    def __init__(self):
        self.len = 0                # The length of the PDU in bytes
        self.priority = 0           # The priority of the message transfer
        self.map = 0                # The map field is only filled at ACK PDUs
        self.type = int(PduType.Unkown) # The type of the PDU

    def from_buffer(self, buffer):
        mask = bytes([0x3f])
        if len(buffer) < MINIMUM_PACKET_LEN:
            logger.error('Pdu.from_buffer() FAILED with: Message too small')
            return 0
        unpacked_data = struct.unpack('<Hcc', buffer[:MINIMUM_PACKET_LEN])
        self.len = unpacked_data[0]
        self.priority = int.from_bytes(unpacked_data[1], byteorder='big')
        self.type = int.from_bytes(bytes([unpacked_data[2][0] & mask[0]]), byteorder='big')
        return MINIMUM_PACKET_LEN

    def log(self, rxtx):
        logger.debug('{}: --- PDU --------------------------------------------------------'.format(rxtx))
        logger.debug('{}: - Len[{}] Prio[{}] Type[{}]'.format(rxtx, self.len, self.priority, self.type))
        logger.debug('{}: ----------------------------------------------------------------'.format(rxtx))

################################################################################
## Destination_Entry class definition
#
# 0                   1                   2                   3
# 0 1 2 3 4 5 6 7 8 9 0 1 2 3 4 5 6 7 8 9 0 1 2 3 4 5 6 7 8 9 0 1
# +-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+
# |                      Destination ID                         |
# +-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+
# |                  Message_Sequence_Number                    |
# +-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+
# |              Reserved_Field (variable length)               |
# +-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+
#
class DestinationEntry():
    def __init__(self): 
        # This field holds a unique identifier identifying a receiving node on the 
        # actual multicast network (e.g. the Internet version 4 address of the 
        # receiving node). Destination_ID is a unique identifier within the scope 
        # of the nodes supporting P_MUL.
        self.dest_ipaddr = ''

        # This entry holds a message sequence number, which is unique for the 
        # sender/receiver pair denoted by Source_ID and Destination_ID. 
        # This sequence number is generated by the transmitter consecutively 
        # with no omissions and is used by receivers to detect message loss.
        self.seqno = 0

    def len(self):
        return DESTINATION_ENTRY_LEN

    def to_buffer(self):
        destid = int_from_bytes(socket.inet_aton(self.dest_ipaddr))
        return struct.pack("<II", destid, self.seqno)

    def from_buffer(self, buffer):
        if len(buffer) < DESTINATION_ENTRY_LEN:
            logger.error("RX: DestinationEntry.from_buffer() FAILED with: Message to small")
            return 0
        unpacked_data = struct.unpack('<II', buffer[:DESTINATION_ENTRY_LEN])
        self.dest_ipaddr = socket.inet_ntoa(int_to_bytes(unpacked_data[0]))
        self.seqno = unpacked_data[1]
        return DESTINATION_ENTRY_LEN

################################################################################
## Option: Timestamp Value
#
# 0                   1                   2                   3
# 0 1 2 3 4 5 6 7 8 9 0 1 2 3 4 5 6 7 8 9 0 1 2 3 4 5 6 7 8 9 0 1 2
# +-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+
# |      Type     |     Length      |            Reserved           |
# +-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+
# |                                                               |
# +                             TSval                             +
# |                                                               |
# +-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+
#
OPT_TS_VAL_LEN = 12

################################################################################
## TLV Timestamp Echo Reply
#
# 0                   1                   2                   3
# 0 1 2 3 4 5 6 7 8 9 0 1 2 3 4 5 6 7 8 9 0 1 2 3 4 5 6 7 8 9 0 1 2
# +-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+
# |      Type     |     Length    |         Reserved              |
# +-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+
# |                                                               |
# +                             TSecr                             +
# |                                                               |
# +-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+
#

OPT_TS_ECR_LEN = 12

################################################################################
## AddressPdu class definition
#
# The P_MUL transmitter generates an Address_PDU to announce to the intended 
# recipients of a message transmission and provide the Message_ID. This PDU 
# and the ACK_PDU (para 212 to 214) effect re-transmission control of P_MUL 
# packets. The total list of Destination_Entries has to be a sorted list in 
# increasing order concerning the element Destination_ID of each 
# Destination_Entry. As P_MUL has to observe a maximum PDU size and as the 
# number of Destination_Entries has no maximum value, it is essential that 
# the total address information be able to be split into more than one 
# Address_PDU. To distinguish between the first, middle and last Address_PDU 
# the MAP field is used.
#
# 0                   1                   2                   3
# 0 1 2 3 4 5 6 7 8 9 0 1 2 3 4 5 6 7 8 9 0 1 2 3 4 5 6 7 8 9 0 1
# +-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+
# |        Length_of_PDU        |    Priority   |MAP|  PDU_Type | 4
# +-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+
# |     Total_Number_of_PDUs    |            Checksum           | 8
# +-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+
# |   Number_of_PDUs_in_Window  |  Highest_Seq_Number_in_Window | 12
# +-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+
# |        Data Offset          |            Reserved           | 16
# +-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+
# |                         Source_ID                           | 20
# +-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+
# |                      Message_ID (MSID)                      | 24
# +-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+
# |                        Expiry_Time                          | 28
# +-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+
# |Count_of_Destination_Entries |   Length_of_Reserved_Field    | 32
# +-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+
# |                                                             | 8 each
# |        List of Destination_Entries (variable length)        |
# |                                                             |
# +-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+
# |                                                             | 12
# /                 Options (variable length)                   /
# |                                                             |
# +-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+
# |                                                             |
# /                  Data (variable length)                     /
# |                                                             |
# +-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+
#

class AddressPdu():
    def __init__(self):
        self.type = PduType.Address         # Either AddressPdu or ExtraAddressPdu Type */ 
        self.total = 0                      # Total number of fragmented DataPDUs of the message 
        self.cwnd = 0                       # Number of PDUs which are sent in the current transmission window
        self.seqnohi = 0                    # Sequence Number of the last PDU in the current window
        self.src_ipaddr = ''                # Emitter address (IPv4 address)
        self.msid = 0                       #  MSID is a unique identifier created by the transmitter.
        self.expires = 0                    # Number of seconds since 00:00:00 1.1.1970 - UnixTime
        self.rsvlen = 0                     # This field contains the length of the reserved field
        self.dst_entries = []               # This field is an array of destination entries
        self.tsval = 0                      # Timestamp Value Option 
        self.payload = bytearray()          # Data Buffer (Optional)

    def length(self):
        return (32 + DESTINATION_ENTRY_LEN * len(self.dst_entries) + OPT_TS_VAL_LEN + len(self.payload))

    def log(self, rxtx):
        logger.debug('{} *** {} *************************************************'.format(rxtx, self.type))
        logger.debug('{} * total:{} wnd:{} seqnoh:{} srcid:{} msid:{} expires:{} rsvlen:{}'.format(
            rxtx, self.total, self.cwnd, self.seqnohi, self.src_ipaddr, self.msid, self.expires, self.rsvlen))
        for i, val in enumerate(self.dst_entries):
            logger.debug('{} * dst[{}] dstid:{} seqno:{}'.format(rxtx, i, val.dest_ipaddr, val.seqno))
        logger.debug('{} * tsval: {}'.format(rxtx, self.tsval))
        logger.debug('{} ****************************************************************'.format(rxtx))

    def find_addr(self, addr):
        for i,val in enumerate(self.dst_entries):
            if val.dest_ipaddr == addr:
                return True
        return False

    def is_unicast(self):
        if len(self.dst_entries) == 1:
            return True
        return False

    def get_seqno(self, addr_id):
        seqno = -1
        for i,val in enumerate(self.dst_entries):
            if val.destid == addr_id:
                seqno = val.seqno
        return seqno

    def get_dest_list(self):
        dsts = []
        for i,val in enumerate(self.dst_entries):
            dsts.append(val.dest_ipaddr)
        return dsts

    def num_fragments(self):
        return self.cwnd

    def to_buffer(self):
        srcid = int_from_bytes(socket.inet_aton(self.src_ipaddr))
        packet = bytearray()
        packet.extend(struct.pack("<HccHHHHHHIIIHH", 
            self.length(),                      # 0: lengthOfPDU 
            bytes([0]),                         # 1: priority
            bytes([int(self.type)]),            # 2: PDU Type
            self.total,                         # 3: Total Number of PDUs
            0,                                  # 4: chksum
            self.cwnd,                          # 5: current window
            self.seqnohi,                       # 6: highest seqno of window
            self.length()-len(self.payload),    # 7: data-offset
            0,                                  # 8: reserved: Must be zero.
            srcid,                              # 9: Source identifier
            self.msid,                          # 10: Message identifier
            self.expires,                       # 11: Expires in sec
            len(self.dst_entries),              # 12: count of dest entries
            self.rsvlen                         # 13: length of reserved field
            ))
        # append dest-entries
        for i,val in enumerate(self.dst_entries):
            destid = int_from_bytes(socket.inet_aton(val.dest_ipaddr))
            packet.extend(struct.pack("<II", destid, val.seqno))
        # append TLV tsval #fixme
        packet.extend(struct.pack("<ccHQ",bytes([int(Option.TsVal)]), bytes([12]), 0, self.tsval))
        # append data to address-pdu
        packet.extend(self.payload)
        return packet

    def from_buffer(self, buffer):
        if len(buffer) < MINIMUM_ADDRESS_PDU_LEN:
            logger.error("RX: AddressPdu.from_buffer() FAILED with: Message to small")
            return 0
        # Read AddressPdu Header 
        unpacked_data = struct.unpack('<HccHHHHHHIIIHH', buffer[:MINIMUM_ADDRESS_PDU_LEN])
        pdu_len = unpacked_data[0]
        self.type = PduType(int_from_bytes(unpacked_data[2]))
        self.total = unpacked_data[3]
        self.cwnd = unpacked_data[5]
        self.seqnohi = unpacked_data[6]
        offset = unpacked_data[7]
        reserved_len = unpacked_data[8]
        self.src_ipaddr = socket.inet_ntoa(int_to_bytes(unpacked_data[9]))
        self.msid = unpacked_data[10]
        self.expires = unpacked_data[11]
        total_entries = unpacked_data[12]
        if len(buffer) < offset:
            logger.error("RX: AddressPdu.from_buffer() FAILED with: Message to small")
            return 0
        if len(buffer) - MINIMUM_ADDRESS_PDU_LEN < total_entries * DESTINATION_ENTRY_LEN:
            logger.error("RX: AddressPdu.from_buffer() FAILED with: Message to small")
            return 0
        #logger.debug("Received AddressPdu with total_length of {}".format(total_entries))

        # Read Destination entries
        num_entries = 0
        nbytes = MINIMUM_ADDRESS_PDU_LEN
        while num_entries < total_entries:
            if nbytes + DESTINATION_ENTRY_LEN + reserved_len > offset:
                logger.error("RX: AddressPdu.from_buffer() FAILED with: Invalid DestinationEntry")
                return 0
            dest_entry = DestinationEntry()
            consumed = dest_entry.from_buffer(buffer[nbytes:])
            if consumed < 0:
                logger.error("RX: AddressPdu.from_buffer() FAILED with: Invalid DestinationEntry")
                return 0
            nbytes = nbytes + consumed
            num_entries = num_entries + 1
            self.dst_entries.append(dest_entry)

        # Read additional options 
        while nbytes + 2 < offset:
            type = buffer[nbytes]
            optlen = buffer[nbytes+1]
            if optlen == 0:
                logger.error("RX: AddressPdu.from_buffer() FAILED with: Invalid option TLV")
                return 0
            if type == int(Option.TsVal):
                if optlen != 12:
                    logger.error("RX: AddressPdu.from_buffer() FAILED with: Invalid option len of tsVal")
                    return 0
                tlv_unpacked = struct.unpack('<ccHQ', buffer[nbytes:nbytes+12])
                self.tsval = tlv_unpacked[3]
            else:
                logger.info("RX: Ignore unkown option {}".format(type))
            nbytes = nbytes + optlen

        # Save additional data
        self.payload = buffer[nbytes:pdu_len]
        return nbytes

################################################################################
## DataPDU class definition
#
# The P_MUL transmitter generates the Data_PDU to pass each of the message 
# fragments to the intended recipients. This PDU holds the unique identifier 
# of the message, the position of this Data_PDU within the ordered set of all 
# Data_PDUs and a part of the total message.
#
# 0                   1                   2                   3
# 0 1 2 3 4 5 6 7 8 9 0 1 2 3 4 5 6 7 8 9 0 1 2 3 4 5 6 7 8 9 0 1
# +-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+
# |        Length_of_PDU        |    Priority   |   |  PDU_Type | 4
# +-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+
# |   Number_of_PDUs_in_Window  |  Highest_Seq_Number_in_Window | 8
# +-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+
# |    Sequence_Number_of_PDU   |            Checksum           | 12
# +-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+
# |  Sequence_Number_of_Window  |            Reserved           | 16
# +-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+
# |                        Source_ID                            | 20
# +-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+
# |                     Message_ID (MSID)                       | 24
# +-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+
# |                                                             |
# |             Fragment of Data (variable length)              |
# |                                                             |
# +-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+
#

class DataPdu():
    def __init__(self):
        self.cwnd = 0                       # Number of PDUs in current transmission window
        self.seqnohi = 0                    # Highest sequence number in current transmission window
        self.cwnd_seqno = 0                 # Sequence number of transmission window 
        self.seqno = 0                      # Sequence number of PDU within the original message
        self.src_ipaddr = ''                # IPv4 address of sender
        self.msid = 0                       # MSID is a unique identifier created within the scope of Source_ID by the transmitter. */
        self.data = bytearray()             # Buffer holding the data

    def len(self):
        return (DATA_PDU_HDRLEN + len(self.data))

    def log(self, rxtx):
        logger.debug('{} *** Data *************************************************'.format(rxtx))
        logger.debug('{} * cwnd:{} seqnohi:{} cwnd_seqno:{} seqno:{} srcid:{} msid:{}'.format(
            rxtx, self.cwnd, self.seqnohi, self.cwnd_seqno, self.seqno, self.src_ipaddr, self.msid))
        logger.debug('{} ****************************************************************'.format(rxtx))

    def to_buffer(self):
        srcid = int_from_bytes(socket.inet_aton(self.src_ipaddr))
        packet = bytearray()
        packet.extend(struct.pack("<HccHHHHHHII", 
            self.len(),                         # 0: lengthOfPDU 
            bytes([0]),                         # 1: priority
            bytes([int(PduType.Data)]),         # 2: PDU Type
            self.cwnd,                          # 3: Number of PDUs in window
            self.seqnohi,                       # 4: Highest number in window
            self.seqno,                         # 5: Sequence number of PDU
            0,                                  # 6: Checksum
            self.cwnd_seqno,                    # 7: Sequence number of window
            0,                                  # 8: Reserved
            srcid,                              # 9: Source Identifier
            self.msid                           # 10: Message-ID
            ))
        packet.extend(self.data)
        return packet

    def from_buffer(self, buffer):
        if len(buffer) < DATA_PDU_HDRLEN:
            logger.error("RX: DataPdu.from_buffer() FAILED with: Message to small")
            return 0
        # Read DataPdu Header 
        unpacked_data = struct.unpack('<HccHHHHHHII', buffer[:DATA_PDU_HDRLEN])
        length = unpacked_data[0]
        self.cwnd = unpacked_data[3]
        self.seqnohi = unpacked_data[4]
        self.seqno = unpacked_data[5]
        cksum = unpacked_data[6]
        self.cwnd_seqno = unpacked_data[7]
        reserved = unpacked_data[8]
        self.src_ipaddr = socket.inet_ntoa(int_to_bytes(unpacked_data[9]))
        self.msid = unpacked_data[10]
        if length < DATA_PDU_HDRLEN:
            logger.error("RX: DataPdu.from_buffer() FAILED with: Invalid length field")
            return 0
        if length > len(buffer):
            logger.error("RX: DataPdu.from_buffer() FAILED with: Message to small")
            return 0            
        if reserved != 0:
            logger.error("RX: DataPdu.from_buffer() FAILED with: Reserved field is not zero")
            return 0
        self.data.extend(buffer[DATA_PDU_HDRLEN:length])
        return length

################################################################################
## AckInfoEntry class definition
#
# This field contains the Source_ID of the transmitting node, the Message_ID 
# and a variable length list of the sequence numbers of the Data_PDUs that 
# have not yet been received.
#
# 0                   1                   2                   3
# 0 1 2 3 4 5 6 7 8 9 0 1 2 3 4 5 6 7 8 9 0 1 2 3 4 5 6 7 8 9 0 1
# One ACK_Info_Entry            +-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+
#                               |    Length_of_ACK_Info_Entry   |
# +-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+
# |          Reserved           |  Highest_Seq_Number_in_Window |
# +-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+
# |                         Source_ID                           |
# +-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+
# |                     Message_ID (MSID)                       |
# +-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+
# | Count_Of_Missing_Seq_Number | Missing_Data_PDU_Seq_Number 1 |
# +-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+
# |...                          | Missing_Data_PDU_Seq_Number n |
# +-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+
# |                                                             |
# +                           TValue                            +
# |                                                             |
# +-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+
# |                                                             |
# |                  Options (variable length)                  |
# |                                                             |
# +-------------------------------------------------------------+
#
class AckInfoEntry():
    def __init__(self):
        self.seqnohi = 0             # Highest Sequence Number which was received from the sender
        self.remote_ipaddr = ''      # Identifier of the transmitting node from the AddressPdu
        self.msid = 0                # Message Identifier received from AddressPdu
        self.missing_seqnos = []     # List of missing sequence numbers
        # The Tval field of 8 bytes may be used for reporting the time elapsed
        # (in units of 100ms) from the receiver received the Address_PDU to the 
        # receiver sent back the ACK_PDU. The sender may use this time to estimate 
        # the time it has taken to transmit the Data_PDUs and to adaptively adjust 
        # the parameter “PDU_DELAY” used for congestion control. 
        # No synchronization of clocks is required.
        self.tvalue = 0              # Time elapsed (in units of 100ms)
        self.tsecr = 0               # Timestamp echo reply

    def length(self):
        return (MINIMUM_ACK_INFO_ENTRYLEN + 2*len(self.missing_seqnos) + 12)

    def to_buffer(self):
        srcid = int_from_bytes(socket.inet_aton(self.remote_ipaddr))
        packet = bytearray()
        packet.extend(struct.pack("<HHHIIH", 
            self.length(),                      # 0: lengthOfPDU 
            0,                                  # 1: Reserved
            self.seqnohi,                       # 2: Highest Sequence Number in window
            srcid,                              # 3: Source Id
            self.msid,                          # 4: Message identifier
            len(self.missing_seqnos)            # 5: Count of missing sequence number
            ))
        for i, val in enumerate(self.missing_seqnos):
            packet.extend(struct.pack("<H", val))
        packet.extend(struct.pack("<Q",self.tvalue))
        packet.extend(struct.pack("<ccHQ",bytes([int(Option.TsEcr)]), bytes([12]), 0, self.tsecr))
        return packet

    def from_buffer(self, buffer):
        if len(buffer) < MINIMUM_ACK_INFO_ENTRYLEN:
            logger.error("RX: AckInfoEntry.from_buffer() FAILED with: Message to small")
            return 0
        # Read AckInfoEntry Header 
        unpacked_data = struct.unpack('<HHHIIH', buffer[:16])
        length = unpacked_data[0]
        reserved = unpacked_data[1]
        self.seqnohi = unpacked_data[2]
        self.remote_ipaddr = socket.inet_ntoa(int_to_bytes(unpacked_data[3]))
        self.msid = unpacked_data[4]
        total_entries = unpacked_data[5]
        if length > len(buffer):
            logger.error("RX AckInfoEntry.from_buffer() FAILED with: Buffer too small")
            return 0
        if reserved != 0:
            logger.error("RX AckInfoEntry.from_buffer() FAILED with: Reserved field is not zero")
            return 0
        if length != MINIMUM_ACK_INFO_ENTRYLEN + 12 + total_entries * 2:
            logger.error("RX AckInfoEntry.from_buffer() FAILED with: Corrupt PDU")
            return 0
        num_entries = 0
        nbytes = 16
        while num_entries < total_entries:
            self.missing_seqnos.append((struct.unpack("<H", buffer[nbytes:nbytes+2]))[0])
            nbytes = nbytes + 2
            num_entries = num_entries + 1
        self.tvalue = struct.unpack("<Q",buffer[nbytes:nbytes+8])[0]
        nbytes = nbytes + 8

        # Read additional options 
        while nbytes + 2 < length:
            type = buffer[nbytes]
            optlen = buffer[nbytes+1]
            if optlen == 0:
                logger.error("RX: AckInfoEntry.from_buffer() FAILED with: Invalid option TLV")
                return 0
            if type == int(Option.TsEcr):
                if optlen != 12:
                    logger.error("RX: AckInfoEntry.from_buffer() FAILED with: Invalid option len of tsEcr")
                    return 0
                tlv_unpacked = struct.unpack('<ccHQ', buffer[nbytes:nbytes+12])
                self.tsecr = tlv_unpacked[3]
            else:
                logger.info("RX: Ignore unkown option {}".format(type))
            nbytes = nbytes + optlen
        return nbytes

################################################################################
## AckPDU class definition
#
# This PDU is generated by a receiving node identified by the Source_ID_of_ACK_Sender 
# and is used to inform the transmitting node of the status of one or more messages 
# received. This information is composed as one or more entries of the list of 
# ACK_Info_Entries. Each of these entries holds a message identifier (Source_ID 
# and Message_ID) and a list of Missing_Data_PDU_Seq_Numbers, which may contain 
# a list of those Data_PDUs not yet received. If this list is empty, the message 
# identified by Source ID and Message ID has been correctly received.
#
# 0                   1                   2                   3
# 0 1 2 3 4 5 6 7 8 9 0 1 2 3 4 5 6 7 8 9 0 1 2 3 4 5 6 7 8 9 0 1
# +-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+
# |        Length_of_PDU        |    Priority   |   |  PDU_Type |  4
# +-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+
# |           unused            |            Checksum           |  8
# +-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+
# |                  Source_ID_of_ACK_Sender                    | 12
# +-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+
# |  Count_of_ACK_Info_Entries  |                               | 14
# +-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+                               +
# |                                                             |
# |          List of ACK_Info_Entries (variable length)         |
# |                                                             |
# +-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+
#

class AckPdu():
    def __init__(self):
        self.src_ipaddr = ''        # IP address of ACK emitter
        self.info_entries = []      # List of AckInfo entries

    def length(self):
        length = MINIMUM_ACK_PDU_LEN
        for i, val in enumerate(self.info_entries):
            length += val.length()
        return length

    def to_buffer(self):
        srcid = int_from_bytes(socket.inet_aton(self.src_ipaddr))
        packet = bytearray()
        packet.extend(struct.pack("<HccHHIH", 
            self.length(),                      # 0: lengthOfPDU 
            bytes([0]),                         # 1: priority
            bytes([int(PduType.Ack)]),          # 2: PDU type
            0,                                  # 3: unused
            0,                                  # 4: checksum
            srcid,                              # 5: source-id
            len(self.info_entries)              # 6: Count of AckInfo entries
            ))
        for i,val in enumerate(self.info_entries):
            packet.extend(val.to_buffer())
        return packet

    def from_buffer(self, buffer):
        if len(buffer) < MINIMUM_ACK_PDU_LEN:
            logger.error("RX: AckPdu.from_buffer() FAILED with: Message to small")
            return 0

        # Read AddressPdu Header 
        unpacked_data = struct.unpack('<HccHHIH', buffer[:MINIMUM_ACK_PDU_LEN])
        length = unpacked_data[0]
        unused = unpacked_data[3]
        chksum = unpacked_data[4]
        self.src_ipaddr = self.src_ipaddr = socket.inet_ntoa(int_to_bytes(unpacked_data[5]))
        total_entries = unpacked_data[6]
        if len(buffer) < length:
            logger.error("RX: AckPdu.from_buffer() FAILED with: Message to small")
            return 0
        if unused != 0:
            logger.error("RX: AckPdu.from_buffer() FAILED witg: Unused field is not zero")
            return 0

        # Read AckInfo entries
        num_entries = 0
        nbytes = MINIMUM_ACK_PDU_LEN
        while num_entries < total_entries:
            infolen = struct.unpack("<H",buffer[nbytes:nbytes+2])[0]
            if nbytes + infolen > len(buffer):
                logger.error("RX: AckPdu.from_buffer() FAILED with: Corrupt AckInfoEntry")
                return 0
            ack_info_entry = AckInfoEntry()
            consumed = ack_info_entry.from_buffer(buffer[nbytes:])
            if consumed < 0:
                logger.error("RX: AckPdu.from_buffer() FAILED with: Invalid AckInfoEntry")
                return 0
            self.info_entries.append(ack_info_entry)
            nbytes = nbytes + infolen
            num_entries = num_entries + 1
        return nbytes

    def log(self, rxtx):
        logger.debug('{} *** AckPdu *************************************************'.format(rxtx))
        logger.debug('{} * src:{}'.format(rxtx, self.src_ipaddr))
        for i,val in enumerate(self.info_entries):
            logger.debug('{} * seqnohi:{} remote_ipaddr:{} msid:{} missed:{} tval:{} tsecr:{}'.format(rxtx,
                val.seqnohi, val.remote_ipaddr, val.msid, val.missing_seqnos, val.tvalue, val.tsecr))
        logger.debug('{} ****************************************************************'.format(rxtx))

################################################################################
## P_MUL Client
##

# Default P_MUL configuration */
cfg = dict()
cfg['mtu'] = 1024
cfg['inflight_bytes']    = 9000
cfg['rtt_extra_delay']   = 1000
cfg['max_increase']      = 0.25
cfg['max_decrease']      = 0.75
cfg['max_retry_count']   = 10
cfg['max_missed_acks']   = 3
cfg['min_datarate']      = 250
cfg['max_datarate']      = 800000
cfg["rtt_extra_delay"] = 1000
cfg["max_ack_retry_count"] = 3 # formerly 5
cfg['default_datarate']  = 50000
cfg['min_ack_timeout']   = 1000
cfg['max_ack_timeout']   = 60000
cfg['default_ack_timeout']       = 10000
cfg['min_retry_timeout']         = 250
cfg['max_retry_timeout']         = 120000
cfg['default_retry_timeout']    = 10000
cfg['initial_cwnd']              = 5000
cfg['cwnds'] = [ 
    {'datarate':    3000, 'cwnd':   5000},
    {'datarate':    6000, 'cwnd':  10000},  # 3000 < x < 6000
    {'datarate':    9000, 'cwnd':  20000},
    {'datarate':   40000, 'cwnd':  25000},
    {'datarate':   80000, 'cwnd':  50000},
    {'datarate':  160000, 'cwnd': 100000},
    {'datarate':  800000, 'cwnd': 100000}
    ]

################################################################################
## Destination Context
#
class Destination(): 
    def __init__(self, cfg, dest, num_fragments, air_datarate, retry_timeout, ack_timeout): 
        self.dest = dest                             # Destination Identifier 
        self.completed = False                       # Transfer Status
        self.cfg = cfg
        # Ack Status 
        self.ack_received = False                    # Flag indicating if an ACK was received
        self.last_received_tsecr = 0                 # Received echoed timestamp from the last AckPdu
        self.sent_data_count = 0                     # Number of sent DataPDUs
        self.missed_data_count = 0                   # Total number of reported missed DataPdus
        self.missed_ack_count = 0                    # Number of consecutive missed Acks
        self.fragment_ack_status = dict()            # 0: false, 1: true,
        for i in range(0,num_fragments):
            self.fragment_ack_status[i] = False
        # Measurement
        self.air_datarate  = air_datarate            # Measured AirDatarate for bulk traffic
        self.retry_timeout = retry_timeout           # Measured retry timeout for message transfer
        self.ack_timeout   = ack_timeout             # RTT for AddressPdu and AckPdu back
        logger.debug("TX: Destination(to: {}):".format(dest))
        logger.debug("AirDatarate: {}".format(self.air_datarate))
        logger.debug("RetryTimeout: {}".format(self.retry_timeout))
        logger.debug("AckTimeout: {}".format(self.ack_timeout))
        # Loss detection
        self.missing_fragments = []

    def update_missed_data_cnt(self):
        for i,val in enumerate(self.missing_fragments):
            self.missed_data_count = self.missed_data_count + 1

    def is_completed(self):
        for key, val in self.fragment_ack_status.items():
            if val == False:
                return False
        return True

    def update_fragment_ack_status(self, missing_fragments, seqnohi):
        # Mark all not missing DataPDUs as acked */
        # FIXME: check if seqno should be 0 or 1 for one packet transmission
        for i in range(0,seqnohi+1):
            if i in missing_fragments:
                self.fragment_ack_status[i] = False
            else:
                self.fragment_ack_status[i] = True
        self.missing_fragments = missing_fragments
        # Update the transfer status
        self.completed = self.is_completed()
        # Reset the missedAckCount
        self.missed_ack_count = 0

    def is_duplicate(self, tsecr): 
        if tsecr is None or tsecr <= 0:
            logger.debug("TX: Ignore invalid Timestamp Echo Reply for Duplicate Detection")
            return False # no duplicate
        if tsecr == self.last_received_tsecr:
            logger.debug("TX: AckPdu from {} is a duplicate".format(self.dest))
            return True #is duplicate */
        logger.debug("Sender: Updated TSecr to {}".format(tsecr))
        self.last_received_tsecr = tsecr
        return False # Not duplicate

    def update_ack_timeout(self, tsecr, tvalue): 
        if tsecr is None or tsecr <= 0:
            logger.debug("TX: Ignore invalid Timestamp Echo Reply for AckTimeout")
            return
        if tvalue is None:
            tvalue = 0
        # Calculate the ack_timeout based on the RTT and TValue
        milli_now = date_to_milli(datetime.now())
        delivery_time = milli_now - tsecr
        new_ack_timeout = delivery_time - tvalue
        if new_ack_timeout <= 0:
            logger.debug("TX Ignore invalid ackTimeout of {}".format(new_ack_timeout))
            return
        self.ack_timeout = round((self.ack_timeout + new_ack_timeout) / 2)
        logger.debug("TX: Updated AckTimeout for {} to {} new_ack_timeout: {} tValue: {} delivery_time: {}".format(
            self.dest, self.ack_timeout, new_ack_timeout, tvalue, delivery_time))

    def update_retry_timeout(self, tsecr):
        if tsecr is None or tsecr <= 0:
            logger.debug("TX: Ignore invalid Timestamp Echo Reply for RetryTimeout")
            return
        # Calculate the retryTimeout based on the RTT */
        milli_now = date_to_milli(datetime.now())
        retry_timeout = milli_now - tsecr
        if retry_timeout <= 0:
            logger.error("TX: Ignore invalid retry_timeout of {}".format(retry_timeout))
            return
        retry_timeout = min(retry_timeout, self.cfg["max_retry_timeout"])   # upper boundary
        retry_timeout = max(retry_timeout, self.cfg["min_retry_timeout"])   # lower boundary
        self.retry_timeout = round((self.retry_timeout + retry_timeout) / 2)
        logger.debug("TX: Updated retry_timeout for {} to {} new_retry_timeout: {}".format(
            self.dest, self.retry_timeout, retry_timeout))

    def update_air_datarate(self, air_datarate):
        air_datarate = min(air_datarate, self.cfg["max_datarate"])  # upper boundary
        air_datarate = max(air_datarate, self.cfg["min_datarate"])  # lower boundary
        self.air_datarate = round((self.air_datarate + air_datarate) / 2)
        logger.debug("TX: Updated air_datarate for {} to {} new_air_datarate: {}".format(
            self.dest, self.air_datarate, air_datarate))

    def update_air_datarate_after_timeout(self): 
        self.air_datarate = round(self.air_datarate / 2)
        self.air_datarate = min(self.air_datarate, self.cfg["max_datarate"])  # upper boundary
        self.air_datarate = max(self.air_datarate, self.cfg["min_datarate"])  # lower boundary
        logger.debug("TX: Updated air_datarate for {} to {} after timeout".format(
            self.dest, self.air_datarate))

    def log(self):
        acked, total = 0, 0
        for key in self.fragment_ack_status:
            if self.fragment_ack_status[key] == True:
                acked = acked + 1
            total = total + 1
        logger.debug("TX {}: {}/{} air_datarate: {} retry_timeout: {} loss: {} {}/{} missed-ack: {} missing: {}".format(
            self.dest, acked, total, self.air_datarate, self.retry_timeout,
            round(100*self.missed_data_count/self.sent_data_count), self.missed_data_count, self.sent_data_count,
            self.missed_ack_count, self.missing_fragments))

# Event types for TX statemachine
class TxEvent(Enum):
    Entry = 0
    Exit = 1
    Start = 2
    Abort = 3
    AckPdu = 4
    PduDelayTimeout = 5
    RetransmissionTimeout = 6
    ExpiryTimeout = 7

class TxState(Enum):
    Idle = 0
    SendingData = 1
    SendingExtraAddressPdu = 2
    WaitingForAcks = 3
    Finished = 4

class TxContext():
    def __init__(self, cli, loop, observer, cfg, destip, dest_list, msid, message, traffic_mode, future):
        # Statemachine
        self.states = dict()
        self.states[TxState.Idle] = self.state_IDLE
        self.states[TxState.SendingData] = self.state_sending_data
        self.states[TxState.SendingExtraAddressPdu] = self.state_sending_extra_address_pdu
        self.states[TxState.WaitingForAcks] = self.state_WAITING_FOR_ACKS
        self.states[TxState.Finished] = self.state_finished
        self.curr = TxState.Idle
        self.cli = cli                          # Pointer to P_MUL instance
        self.loop = loop
        self.observer = observer
        self.cfg = cfg                          # Configuration
        self.traffic_mode = traffic_mode        # Message or Bulk traffic
        self.future = future

        # Address_PDU and Transmission of DATA_PDUs ******************************
        self.dest_list = []                     # The list of destinations of the current transmission phase */
        for i,val in enumerate(dest_list):
            self.dest_list.append(val["addr"])
        self.destip = destip                    # Destination IP address. Either unicast or multicast
        self.msid  = msid                       # Unique message id of the message transfer
        self.seqno = 0                          # Sequence number which is incremented with each Address PDU
        self.cwnd_seqno = 0                     # Incremented with each new announced transmission window
        self.cwnd = cfg["initial_cwnd"]         # The number of bytes of the current window
        self.tx_cwnd = cfg["initial_cwnd"]      # The current window in bytes
        self.air_datarate = cfg["default_datarate"] # The minimum AirDatarate of the current transmission window
        self.tx_fragments = dict()              # The list of fragment IDs to sent in the current window { 'sent': false, 'len': xy }
    
        # Data Fragments *********************************************************
        self.fragments = fragment(message, cfg["mtu"])   # List of fragments
        self.fragments_txcount = dict()             # For each fragment the number of transmission is accounted
        for i,val in enumerate(self.fragments):
            self.fragments_txcount[i] = 0
        
        # PDU_Delay Control and Retransmission Timeout ***************************
        self.use_min_pdu_delay = True           # True: All PDUs are sent PDU_Delay=0, False: PDU_Delay is used
        self.pdu_delay_timer = None             # PDU Delay Timer to delay sending of messages
        self.pdu_delay = MIN_PDU_DELAY          # The delay between sending Data PDUs in milliseconds
        self.retry_timer = None                 # Timer to trigger a Retransmission
        self.retry_timeout = 0                  # The retransmission timeout in msec
        self.retry_timestamp = 0                # Timestamp at which a Retransmission shall occur
        self.tx_datarate = 1                    # Tx datarate

        # Destination Context ****************************************************
        self.dest_status = dict()              # List of Destination status information
        for i,val in enumerate(dest_list):
            self.dest_status[val["addr"]] = Destination(
                cfg, 
                val["addr"], 
                len(self.fragments),
                val["air_datarate"], 
                val["retry_timeout"], 
                val["ack_timeout"])

        # Statistics *************************************************************
        self.num_sent_data_pdus = 0             # Total number of sent PDUs
        self.start_timestamp = datetime.now()   # Start timestamp
        self.tx_phases = []                     # For each transmission phase the following is accounted:
                                                # { tx_datarate: bit/s, air_datarate: bit/s retry_timeout: ms, fragments: []}

    def log(self, rxtx):
        logger.debug('{} +--------------------------------------------------------------+'.format(rxtx))
        logger.debug('{} | TX Context                                                   |'.format(rxtx))
        logger.debug('{} +--------------------------------------------------------------+'.format(rxtx))
        logger.debug('{} | dest_list: {}'.format(rxtx, self.dest_list))
        logger.debug('{} | destip: {}'.format(rxtx, self.destip))
        logger.debug('{} | msid: {}'.format(rxtx, self.msid))
        logger.debug('{} | traffic_type: {}'.format(rxtx, self.traffic_mode));
        logger.debug('{} | PduDelay: {} msec'.format(rxtx, self.pdu_delay))
        logger.debug('{} | Datarate: {} bit/s'.format(rxtx, self.tx_datarate))
        logger.debug('{} | MinDatarate: {} bit/s'.format(rxtx, self.cfg["min_datarate"]))
        logger.debug('{} | MaxDatarate: {} bit/s'.format(rxtx, self.cfg["max_datarate"]))
        logger.debug('{} | MaxIncreasePercent: {} %'.format(rxtx, self.cfg["max_increase"]*100))
        for key in self.dest_status:
            logger.debug('{} | fragmentsAckStatus[{}]: {}'.format(rxtx, key, self.dest_status[key].fragment_ack_status))
        logger.debug('{} +--------------------------------------------------------------+'.format(rxtx))

    def increment_number_of_sent_data_pdus(self):
        for i, val in enumerate(self.dest_list):
            dest = self.dest_status[val]
            if dest is not None:
                dest.sent_data_count = dest.sent_data_count + 1

    def min_air_datarate(self):
        min_air_datarate = None
        for addr in self.dest_status:
            dest = self.dest_status[addr]
            if min_air_datarate is None:
                min_air_datarate = dest.air_datarate;
            elif dest.air_datarate < min_air_datarate:
                min_air_datarate = dest.air_datarate
        if min_air_datarate is None:
            return 1500
        else:
            return min_air_datarate

    def max_retry_timeout(self):
        max_retry_timeout = None
        for addr in self.dest_status:
            dest = self.dest_status[addr]
            if max_retry_timeout is None:
                max_retry_timeout = dest.retry_timeout
            elif dest.retry_timeout > max_retry_timeout:
                max_retry_timeout = dest.retry_timeout
        if max_retry_timeout is None:
            return 10000
        else:
            return max_retry_timeout

    def max_ack_timeout(self):
        max_ack_timeout = None
        for addr in self.dest_status:
            dest = self.dest_status[addr]
            if max_ack_timeout is None:
                max_ack_timeout = dest.ack_timeout
            elif dest.ack_timeout > max_ack_timeout:
                max_ack_timeout = dest.ack_timeout
        if max_ack_timeout is None:
            return 2000
        else:
            return max_ack_timeout

    def get_first_received_fragid(self, missing_fragments):
        for key in self.tx_fragments:
            if key in missing_fragments:
                return key
        return None

    def calc_received_bytes(self, fragid):
        bytes = 0
        for key in self.tx_fragments:
            if key >= fragid:
                bytes += self.cfg["mtu"]
        return bytes

    def calc_air_datarate(self, remote_ipaddr, ts_ecr, missing_fragments, tvalue):
        if len(self.tx_fragments) == 0:
            return None         # Nothing was sent
        if ts_ecr is not None:   
            # AddressPdu was received
            bytes = get_sent_bytes(self.tx_fragments)
            air_datarate = round(bytes*8*1000/tvalue)
            logger.debug("TX: {} measured air-datarate: {} bit/s send-bytes: {} tValue: {}".format(
                remote_ipaddr, air_datarate, bytes, tvalue))
        else:                   
            # AddressPdu wasn´t received
            first_seqno = self.get_first_received_fragid(missing_fragments)
            if first_seqno is None:
                return None     # Nothing was received, neither AddressPdu nor DataPdu
            bytes = self.calc_received_bytes(first_seqno)
            air_datarate = round(bytes*8*1000/tvalue)
            logger.debug("TX: {} measured air-datarate: {} bit/s 1st rx-fragment: {}end-bytes: {} tValue: {}".format(
                remote_ipaddr, first_seqno, bytes, tvalue))
        return air_datarate

    def get_max_retry_count(self):
        retry_count = 0
        for key in self.fragments_txcount:
            if self.fragments_txcount[key] > retry_count:
                retry_count = retry_count + 1
        return (retry_count - 1)

    def init_tx_phase(self, timeout_occured = False):
        _retry_timeout = 0
        _ack_timeout = 0
        _air_datarate = 0
        _cwnd = 5000
        remaining_bytes = 0

        #***************************************************************************
        ## Loss Detection for each Destination
        #  
        for addr in self.dest_status:
            dest = self.dest_status[addr]
            dest.update_missed_data_cnt()
            dest.missing_fragments = []

        #***************************************************************************
        ## Address_PDU Initialization
        #

        # Initialize list of destinations. All destinations which haven´t acked
        # all fragments will be part of the destination list */
        self.dest_list = []
        for addr in self.dest_status:   # Iterate through all destinations */
            dest = self.dest_status[addr]
            dest.completed = dest.is_completed()
            if dest.completed:
                dest.ack_received = True
            else:
                dest.ack_received = False
                self.dest_list.append(addr)
        # Increment the sequence number of the transmission window. Receiver should
        # detect if we have started an new transmission phase */
        self.cwnd_seqno = self.cwnd_seqno + 1

        #***************************************************************************
        ## TxDatarate Control && Window Management
        #

        # Update the txDatarate based on the measured AirDatarate
        self.tx_datarate = self.min_air_datarate()
        logger.debug('TX-CTX: Measured AirDatarate: {}'.format(self.tx_datarate))  
    
        # Calculate the current window based on the calculated TX Datarate */
        _cwnd = get_cwnd(self.cfg['cwnds'], self.tx_datarate)
        if self.use_min_pdu_delay or timeout_occured:
            _cwnd = 5000    # When sending with the minPduDelay we use the default window size */

        # Calculate the number of fragments in the current window based on the cwnd */
        self.tx_fragments = unacked_fragments(self.dest_status, self.fragments, _cwnd)
        # Update the number of transmission for each fragment */
        for seq in self.tx_fragments:
            self.fragments_txcount[seq] = self.fragments_txcount[seq] + 1

        # In case of no retransmission the txDatarate is increased by the 
        # configured number of inflight bytes. */
        old_tx_datarate = self.min_air_datarate()
        remaining = len(self.tx_fragments) * self.cfg["mtu"]
        if timeout_occured is False and remaining > 0:
            duration = round((remaining * 8 * 1000) / self.tx_datarate)
            # The txDatarate is increased by the configured number of inflightBytes.
            # This shall ensure that the txDatarate gets higher if more AirDatarate
            # is available. The limitation to the maximum number of inflightBytes
            # shall prevent packet loss due buffer overflow if the AirDatarate didn´t increase */
            self.tx_datarate = round(((remaining + self.cfg["inflight_bytes"]) * 8 * 1000) / duration)
            #Limit the increase to an upper boundary */
            logger.debug('TX-CTX: Increased txDatarate: {}'.format(self.tx_datarate))
            logger.debug('TX-CTX: Limit TxDatarate to {}'.format(old_tx_datarate * (1 + self.cfg["max_increase"])))
            self.tx_datarate = min(self.tx_datarate, old_tx_datarate * (1 + self.cfg["max_increase"]))
            logger.debug("TX-CTX: Increased txDatarate to {}".format(self.tx_datarate))

        # At full speed the txDatarate is set to the maximum configured txDatarate */
        if self.use_min_pdu_delay is True:
            self.tx_datarate = self.cfg["max_datarate"]
            self.use_min_pdu_delay = False
        # Correct Datarate to boundaries. Just to be sure we didn´t increase or decrease too much */
        self.tx_datarate = max(self.tx_datarate, self.cfg["min_datarate"])
        self.tx_datarate = min(self.tx_datarate, self.cfg["max_datarate"])

        #***************************************************************************
        ## PDU_Delay Control
        #

        # Update PDU_Delay Timeout based on the current txDatarate */
        self.pdu_delay = round((1000 * self.cfg["mtu"] * 8) / self.tx_datarate)
        self.pdu_delay = max(self.pdu_delay, MIN_PDU_DELAY)

        #***************************************************************************
        ## Retransmission Timeout
        #

        if self.traffic_mode == Traffic.Message:
            # When sending a single message the minimum PDU_Delay can be used */
            self.pdu_delay = MIN_PDU_DELAY

            # The Retransmission Timeout is based on the maximum Timeout which was
            # previously measured for one of the destination nodes */
            _retry_timeout = self.max_retry_timeout()
            _retry_timeout = min(_retry_timeout, self.cfg["max_retry_timeout"])
            _retry_timeout = max(_retry_timeout, self.cfg["min_retry_timeout"]) 

            max_retry_count = self.get_max_retry_count()
            for i in range(0, max_retry_count):
                _retry_timeout = _retry_timeout * 2
            if 0 == max_retry_count:
                _retry_timeout = _retry_timeout * (1 + self.cfg["max_increase"])
            logger.debug("TX-CTX: Message: Set RetryTimeout to {} at retrycount of {}".format(_retry_timeout, max_retry_count))

            # Retry Timeout
            self.retry_timestamp = datetime.now() + timedelta(milliseconds=_retry_timeout)
            self.retry_timeout = _retry_timeout
            self.air_datarate = 0 # not used
        else:    # Bulk Traffic
            # The retransmission timeout is based on an estimation of the airDatarate.
            # This estimation takes into account that the airDatarate can have a large
            # decrease. This amount of decrease can be configure. e.g. in a worst case
            # scenario the datarate can be 50% smaller due modulation change of the waveform. */
            _air_datarate = round(self.min_air_datarate() * (1 - self.cfg["max_decrease"]))
            # Calculate the retransmission timeout based on the remaining bytes to sent
            remaining_bytes = len(self.tx_fragments) * self.cfg["mtu"]
            # The Retransmission Timeout takes into account that extra Address PDUs have to be sent
            remaining_bytes = remaining_bytes + self.cfg["mtu"] # ExtraAddressPdu
            # Calculate the timeInterval it takes to sent the data to the receiver
            _retry_timeout = round((remaining_bytes * 8 * 1000) / _air_datarate)
            # At multicast communication the retransmission timeout must take into account that
            # multiple time-sliced ACK_PDUs have to be sent. FIXME: What about multiple ACK_PDU retries ?
            if len(self.dest_list) > 1:
                _retry_timeout = _retry_timeout + len(self.dest_list) * ACK_PDU_DELAY_MSEC
            # The AckTimeout is the maximum value of one of the destinations
            _ack_timeout = self.max_ack_timeout()
            # FIXME: Check if ackTimeout should be added to the retryTimeout

            # Limit the RetransmissionTimeout
            _retry_timeout = max(_retry_timeout, self.cfg["min_retry_timeout"])
            _retry_timeout = min(_retry_timeout, self.cfg["max_retry_timeout"])
            # Calculate the timestamp at which a retransmission has too occur
            logger.debug("TX-CTX Bulk: Set RetryTimeout {} to for AirDatarate of {} and ackTimeout of {}".format(
                _retry_timeout, _air_datarate, _ack_timeout))
            # Retry Timeout
            self.retry_timestamp = datetime.now() + timedelta(milliseconds=_retry_timeout)
            self.retry_timeout = _retry_timeout
            logger.debug("TX Init() tx_datarate: {} air_datarate: {} retry_timeout: {} ack_timeout: {}".format(
            self.tx_datarate, _air_datarate, _retry_timeout, _ack_timeout))

        #***************************************************************************
        ## Update Statistics
        #
        fragment_list = []
        for key in self.tx_fragments:
            fragment_list.append(key)
        dest_list = []
        for i,val in enumerate(self.dest_list):
            dest_list.append(val)

        tx_phase = dict()
        tx_phase["dest_list"] = dest_list
        tx_phase["tx_datarate"] = self.tx_datarate
        tx_phase["air_datarate"] = _air_datarate
        tx_phase["retry_timeout"] = _retry_timeout
        tx_phase["fragment_list"] = fragment_list
        self.tx_phases.append(tx_phase)

        logger.debug('TX +--------------------------------------------------------------+')
        logger.debug('SND | TX Phase                                                     |')
        logger.debug('SND |--------------------------------------------------------------+')
        logger.debug('SND | dest_list: {}'.format(dest_list))
        logger.debug('SND | cwnd: {}'.format(_cwnd))
        logger.debug('SND | seqnohi: {}'.format(get_seqnohi(self.tx_fragments)))
        logger.debug('SND | tx_fragments: {}'.format(self.tx_fragments))
        ack_recv_status = dict()
        for addr in self.dest_status:
            if self.dest_status[addr].completed == False:
                ack_recv_status[addr] = self.dest_status[addr].ack_received
        logger.debug('SND | AckRecvStatus: {}'.format(ack_recv_status))
        logger.debug('SND | OldTxDatarate: {}'.format(old_tx_datarate))
        logger.debug('SND | NewTxDatarate: {}'.format(self.tx_datarate))
        logger.debug('SND | AirDatarate: {}'.format(_air_datarate))
        logger.debug('SND | AckTimeout: {}'.format(_ack_timeout))
        logger.debug('SND | RetryTimeout: {}'.format(_retry_timeout))
        logger.debug('SND | InflightBytes: {}'.format(self.cfg["inflight_bytes"]))
        logger.debug('SND | RemainingBytes: {}'.format(remaining_bytes))
        logger.debug('SND | RetryCount: {} Max: {}'.format(self.get_max_retry_count(), self.cfg["max_retry_count"]))
        logger.debug('TX +--------------------------------------------------------------+')

    def get_next_tx_fragment(self):
        for key in self.tx_fragments:
            if self.tx_fragments[key]['sent'] == False:
                return key
        return 0

    def is_final_fragment(self, fragid): 
        last_id = -1
        for key in self.tx_fragments:
            last_id = key
        if fragid == last_id:
            return True
        return False

    def get_tx_status(self): 
        sent = num_sent_fragments(self.tx_fragments)
        percent = round(100 * (sent / len(self.tx_fragments)));
        bytes = sent * self.cfg["mtu"]
        logger.debug("TX: sent: {} total: {}".format(sent, total))
        return { 'state': 'SendingData', 'bytes': bytes, 'percent': percent, 'tx_datarate': self.tx_datarate }

    def get_deliver_status(self): 
        deliver_status = [];
        # Iterate through all receivers of the message
        for addr in self.dest_status:
            dest = self.dest_status[addr]
            delivered = 0
            delivered_bytes = 0

            if dest.air_datarate:
                air_datarate = round(dest.air_datarate)
            else:
                air_datarate = 0
            
            for frag_id in dest.fragment_ack_status:
                if dest.fragment_ack_status[frag_id] == True:
                    delivered = delivered + 1
                    delivered_bytes = delivered_bytes + self.cfg["mtu"]    
            delivered_percent = round(100 * (delivered / len(self.fragments)));

            deliver_status.append({
                "addr": addr,
                "delivered_bytes": delivered_bytes,
                "delivered_percent": delivered_percent,
                "air_datarate": air_datarate,
                "sent": dest.sent_data_count,
                "missed": dest.missed_data_count
            });
        return deliver_status

    def get_delivery_status(self): 
        deltatime = datetime.now() - self.start_timestamp
        delivery_time = timedelta_milli(deltatime)
        loss = round(100 * ((self.num_sent_data_pdus - len(self.fragments)) / len(self.fragments)))
        status = dict()
        status['tx_datarate'] = self.tx_datarate
        status['goodput'] = calc_datarate(self.start_timestamp, message_len(self.fragments))
        status['delivery_time'] = delivery_time
        status['num_data_pdus'] = len(self.fragments)
        status['num_sent_data_pdus'] = self.num_sent_data_pdus
        status['loss'] = loss
        return status

    def retransmission_timeout(self):
        event = { 'id': TxEvent.RetransmissionTimeout }
        asyncio.ensure_future(self.dispatch(event))

    def cancel_retransmission_timer(self):
        if self.retry_timer is not None:
            self.retry_timer.cancel()
            self.retry_timer = None

    def start_retransmission_timer(self, timeout):
        if self.retry_timer is not None:
            self.cancel_retransmission_timer()
        timeout = timeout/1000
        #logger.debug("start retransmission timer in {} milliseconds".format(timeout))
        self.retry_timer = self.loop.call_later(timeout, self.retransmission_timeout)

    def pdu_delay_timeout(self):
        event = { 'id': TxEvent.PduDelayTimeout }
        asyncio.ensure_future(self.dispatch(event))

    def cancel_pdu_delay_timer(self):
        if self.pdu_delay_timer is not None:
            #print("cancel pdu_delay timer")
            self.pdu_delay_timer.cancel()
            self.pdu_delay_timer = None

    def start_pdu_delay_timer(self, timeout):
        if self.pdu_delay_timer is not None:
            self.cancel_pdu_delay_timer()
        timeout = timeout/1000
        #logger.debug("start pdu_delay timer in {} milliseconds".format(timeout))
        self.pdu_delay_timer = self.loop.call_later(timeout, self.pdu_delay_timeout)

    def tran(self, to):
        self.curr = to

    async def dispatch(self, ev):
        func = self.states[self.curr]
        if func is not None:
            await func(ev)

    async def state_IDLE(self, ev):
        logger.debug("SND | IDLE: {}".format(ev['id']))
        self.cancel_pdu_delay_timer()
        self.cancel_retransmission_timer()
        now = datetime.now()
        
        if ev["id"] == TxEvent.Start:
            addr_list = []
            self.init_tx_phase()
        
            # Send Address PDU
            address_pdu = AddressPdu()
            address_pdu.type = PduType.Address
            address_pdu.total = len(self.fragments)
            address_pdu.cwnd  = len(self.tx_fragments)
            address_pdu.seqnohi = get_seqnohi(self.tx_fragments)
            address_pdu.src_ipaddr = self.cli.src_ipaddr
            address_pdu.msid = self.msid
            address_pdu.tsval = date_to_milli(now)
            for i,val in enumerate(self.dest_list):
                dest_entry = DestinationEntry()
                dest_entry.dest_ipaddr = val
                dest_entry.seqno = self.seqno
                address_pdu.dst_entries.append(dest_entry)
            self.seqno += 1

            if self.traffic_mode == Traffic.Message:
                # Append Data if we have only a small message to transfer */
                address_pdu.payload = self.fragments[0]
                self.tx_fragments[0]['sent'] = True
                self.tx_fragments[0]['len'] = len(self.fragments[0])
                self.increment_number_of_sent_data_pdus()
                self.num_sent_data_pdus += 1
            address_pdu.log('SND')
            pdu = address_pdu.to_buffer()
            self.cli.sendto(self.destip, pdu)
        
            if self.traffic_mode == Traffic.Message:
                # Start Retransmission timer
                timeout = round(timedelta_milli(self.retry_timestamp - now))
                logger.debug('SND | start Retransmission timer with {} msec delay'.format(timeout))
                self.cancel_retransmission_timer()
                self.start_retransmission_timer(timeout)
                # Change State to WAITING_FOR_ACKS
                logger.debug('SND | change state to WAITING_FOR_ACKS')
                self.tran(TxState.WaitingForAcks)
            else:      # BULK traffoc mpde
                # Start PDU_Delay Timer
                logger.debug('SND | IDLE - start PDU Delay timer with a {} msec timeout'.format(MIN_PDU_DELAY))
                self.start_pdu_delay_timer(MIN_PDU_DELAY)
                logger.debug('SND | IDLE - Change state to SENDING_DATA')
                self.tran(TxState.SendingData)

        elif ev["id"] == TxEvent.Abort:
            pass
        elif ev["id"] == TxEvent.AckPdu:
            pass
        elif ev["id"] == TxEvent.PduDelayTimeout:
            pass
        elif ev["id"] == TxEvent.RetransmissionTimeout:
            pass
        elif ev["id"] == TxEvent.ExpiryTimeout:
            pass
        else:
            pass

    async def state_sending_data(self, ev):
        logger.debug("SND | SENDING_DATA: {}".format(ev['id']))
        if ev["id"] == TxEvent.Start:
            pass
        elif ev["id"] == TxEvent.Abort:
            pass
        elif ev["id"] == TxEvent.AckPdu:
            pass
        elif ev["id"] == TxEvent.PduDelayTimeout:
            self.cancel_pdu_delay_timer();
            pdu_delay = self.pdu_delay;
            
            # Send Data PDU
            data_pdu = DataPdu()
            data_pdu.cwnd = len(self.tx_fragments);
            data_pdu.seqnohi = get_seqnohi(self.tx_fragments);
            data_pdu.src_ipaddr = self.cli.src_ipaddr;
            data_pdu.msid = self.msid;
            data_pdu.seqno = self.get_next_tx_fragment();
            data_pdu.cwnd_seqno = self.cwnd_seqno;
            data_pdu.data.extend(self.fragments[data_pdu.seqno]);
            data_pdu.log('SND');

            pdu = data_pdu.to_buffer()
            logger.debug('SND | SND DataPdu[{}] len: {} cwnd_seqno: {}'.format(data_pdu.seqno, len(data_pdu.data), data_pdu.cwnd_seqno));
            self.cli.sendto(self.destip, pdu)
            self.tx_fragments[data_pdu.seqno]['sent'] = True
            self.tx_fragments[data_pdu.seqno]['len'] = len(data_pdu.data)
            self.increment_number_of_sent_data_pdus()
            self.num_sent_data_pdus += 1

            logger.debug('SND | SENDING_DATA - start PDU Delay timer with a {} msec timeout'.format(self.pdu_delay));
            self.start_pdu_delay_timer(self.pdu_delay);

            if self.is_final_fragment(data_pdu.seqno):
                logger.debug('SND | SENDING_DATA - Change state to SENDING_EXTRA_ADDRESS_PDU');
                self.tran(TxState.SendingExtraAddressPdu);

        elif ev["id"] == TxEvent.RetransmissionTimeout:
            pass
        elif ev["id"] == TxEvent.ExpiryTimeout:
            pass
        else:
            pass

    async def state_sending_extra_address_pdu(self, ev):
        logger.debug("SND | SENDING_EXTRA_ADDRESS_PDU: {}".format(ev['id']))
        if ev["id"] == TxEvent.Start:
            pass
        elif ev["id"] == TxEvent.Abort:
            pass
        elif ev["id"] == TxEvent.AckPdu:
            pass
        elif ev["id"] == TxEvent.PduDelayTimeout:
            self.cancel_pdu_delay_timer();
            now = datetime.now()

            # Send Address PDU
            address_pdu = AddressPdu()
            address_pdu.type = PduType.ExtraAddress
            address_pdu.total = len(self.fragments)
            address_pdu.cwnd  = len(self.tx_fragments)
            address_pdu.seqnohi = get_seqnohi(self.tx_fragments)
            address_pdu.src_ipaddr = self.cli.src_ipaddr
            address_pdu.msid = self.msid
            address_pdu.tsval = date_to_milli(now)
            for i,val in enumerate(self.dest_list):
                dest_entry = DestinationEntry()
                dest_entry.dest_ipaddr = val
                dest_entry.seqno = self.seqno
                address_pdu.dst_entries.append(dest_entry)
            self.seqno += 1

            if self.traffic_mode == Traffic.Message:
                # Append Data if we have only a small message to transfer */
                address_pdu.payload = self.fragments[0]
                self.tx_fragments[0]['sent'] = True
                self.tx_fragments[0]['len'] = len(address_pdu.payload)
                self.increment_number_of_sent_data_pdus()
                self.num_sent_data_pdus += 1
            address_pdu.log('SND')
            pdu = address_pdu.to_buffer()
            self.cli.sendto(self.destip, pdu)
        
            # Start Retransmission timer
            timeout = round(timedelta_milli(self.retry_timestamp - now))
            logger.debug('SND | start Retransmission timer with {} msec delay'.format(timeout))
            self.cancel_retransmission_timer()
            self.start_retransmission_timer(timeout)
            # Change State to WAITING_FOR_ACKS
            logger.debug('SND | change state to WAITING_FOR_ACKS')
            self.tran(TxState.WaitingForAcks)
            
        elif ev["id"] == TxEvent.RetransmissionTimeout:
            self.cancel_retransmission_timer()
        elif ev["id"] == TxEvent.ExpiryTimeout:
            pass
        else:
            pass

    async def state_WAITING_FOR_ACKS(self, ev):
        logger.debug("SND | WAITING_FOR_ACKS: {}".format(ev['id']))
        if ev["id"] == TxEvent.Start:
            pass
        elif ev["id"] == TxEvent.Abort:
            pass
        elif ev["id"] == TxEvent.AckPdu:
            remote_ipaddr = ev['remote_ipaddr']
            info_entry = ev['info_entry']
            tvalue = info_entry.tvalue

            # Check if ACK sender is in our destination list
            if remote_ipaddr not in self.dest_list:
                logger.debug("TX: Ignore ACK from {}".format(remote_ipaddr))
                return
            if remote_ipaddr not in self.dest_status:
                logger.debug("TX: Ignore ACK from {}".format(remote_ipaddr))
                return
            dest_status = self.dest_status[remote_ipaddr]

            # Update the Ack-Status of each fragment
            dest_status.update_fragment_ack_status(info_entry.missing_seqnos, info_entry.seqnohi)
            # If this AckPdu with the same timestamp hasn´t already been received
            # before we update the retryTimeout and the ackTimeout */
            if dest_status.is_duplicate(info_entry.tsecr) == False:
                # Update RetryTimeout for that destination
                dest_status.update_retry_timeout(info_entry.tsecr)
                # Update the AckTimeout for that destination
                dest_status.update_ack_timeout(info_entry.tsecr, tvalue)
            # We have received an Ack from that remote address
            dest_status.ack_received = True

            # Update the airDatarate based on the received tvalue
            if tvalue > 0:
                air_datarate = self.calc_air_datarate(remote_ipaddr, info_entry.tsecr, info_entry.missing_seqnos, tvalue)
                logger.debug("TX Measured air-datarate: {} and tvalue: {} sec".format(air_datarate, tvalue/1000))
                # Prevent increase of airDatarate in a wrong case
                if air_datarate > self.tx_datarate:
                    logger.debug("SND | air-datarate {} is larger than tx-datarate - Update air-datarate to {}".format(
                        air_datarate, self.tx_datarate, self.tx_datarate))
                    dest_status.update_air_datarate(self.tx_datarate)
                else:
                    dest_status.update_air_datarate(air_datarate)
            dest_status.log()
            
            # If we have received all ACK PDU we can continue with the next
            # transmission phase sending Data_PDU retransmissions. If ACK_PDUs
            # still are missing we continue waiting */
            if received_all_acks(self.dest_status):
                self.cancel_retransmission_timer()
                self.init_tx_phase()

                if self.get_max_retry_count() > self.cfg["max_retry_count"]:
                    logger.debug("SND | Max Retransmission Count Reached")
                    logger.debug("SND | change state to Idle")
                    self.tran(TxState.Idle)

                    num_acked_dests = 0
                    ack_status = dict()
                    for addr in self.dest_status:
                        dest = self.dest_status[addr]
                        if dest.completed == True:
                            num_acked_dests += 1
                        ack_status[addr] = dict()
                        ack_status[addr]["ack_status"] = dest.completed
                        ack_status[addr]["ack_timeout"] = dest.ack_timeout
                        ack_status[addr]["retry_timeout"] = dest.retry_timeout
                        ack_status[addr]["retry_count"] = self.get_max_retry_count()
                        ack_status[addr]["num_sent"] = dest.sent_data_count
                        ack_status[addr]["air_datarate"] = dest.air_datarate
                        ack_status[addr]["missed"] = dest.missed_data_count

                    self.cli.transmission_finished(self.msid, self.get_delivery_status(), ack_status)
                    return
            
                # Send Address PDU
                address_pdu = AddressPdu()
                address_pdu.type = PduType.Address
                address_pdu.total = len(self.fragments)
                address_pdu.cwnd  = len(self.tx_fragments)
                address_pdu.seqnohi = get_seqnohi(self.tx_fragments)
                address_pdu.src_ipaddr = self.cli.src_ipaddr
                address_pdu.msid = self.msid
                address_pdu.tsval = date_to_milli(datetime.now())
                for i,val in enumerate(self.dest_list):
                    dest_entry = DestinationEntry()
                    dest_entry.dest_ipaddr = val
                    dest_entry.seqno = self.seqno
                    address_pdu.dst_entries.append(dest_entry)
                self.seqno += 1

                if self.traffic_mode == Traffic.Message and len(self.dest_list) > 0:
                    # Append Data if we have only a small message to transfer
                    address_pdu.payload = self.fragments[0]
                    self.tx_fragments[0] = dict()
                    self.tx_fragments[0]["len"] = len(self.fragments[0])
                    self.tx_fragments[0]["sent"] = True
                    self.increment_number_of_sent_data_pdus()
                    self.num_sent_data_pdus += 1

                address_pdu.log('SND')
                pdu = address_pdu.to_buffer()
                self.cli.sendto(self.destip, pdu)

                if len(self.dest_list) > 0:
                    if self.traffic_mode == Traffic.Message:
                        # Start Retransmission timer
                        timeout = round(timedelta_milli(self.retry_timestamp - datetime.now()))
                        logger.debug('SND | start Retransmission timer with {} msec delay'.format(timeout))
                        self.cancel_retransmission_timer()
                        self.start_retransmission_timer(timeout)
                        # Change State to WAITING_FOR_ACKS
                        logger.debug('SND | change state to WAITING_FOR_ACKS')
                        self.tran(TxState.WaitingForAcks)
                    else:      # BULK traffoc mpde
                        # Start PDU_Delay Timer
                        logger.debug('SND | IDLE - start PDU Delay timer with a {} msec timeout'.format(MIN_PDU_DELAY))
                        self.start_pdu_delay_timer(MIN_PDU_DELAY)
                        logger.debug('SND | IDLE - Change state to SENDING_DATA')
                        self.tran(TxState.SendingData)
                else:
                    # Change state to FINISHED
                    self.cancel_retransmission_timer()
                    logger.debug('SND | change state to FINISHED');
                    self.tran(TxState.Finished)

                    ack_status = dict()
                    for addr in self.dest_status:
                        dest = self.dest_status[addr]
                        ack_status[addr] = dict()
                        ack_status[addr]["ack_status"] = dest.completed
                        ack_status[addr]["ack_timeout"] = dest.ack_timeout
                        ack_status[addr]["retry_timeout"] = dest.retry_timeout
                        ack_status[addr]["retry_count"] = self.get_max_retry_count()
                        ack_status[addr]["num_sent"] = dest.sent_data_count
                        ack_status[addr]["air_datarate"] = dest.air_datarate
                        ack_status[addr]["missed"] = dest.missed_data_count
                    
                    self.cli.transmission_finished(self.msid, self.get_delivery_status(), ack_status)

        elif ev["id"] == TxEvent.PduDelayTimeout:
            pass
        elif ev["id"] == TxEvent.RetransmissionTimeout:
            self.cancel_retransmission_timer()
            num_acked_dests = 0
            ack_status = dict()
            remove_list = []
        
            # Update MissedAckCount, Retry Count and AirDatarate for all destinations we have missed the AckPdu */
            for addr in self.dest_status:
                dest_status = self.dest_status[addr]
                if dest_status.ack_received == False:
                    # Reduce air_datarate
                    dest_status.update_air_datarate_after_timeout() 
                    # Increment the missed ACK counter
                    dest_status.missed_ack_count += 1
                    logger.debug('SND | {} missed acks: {}'.format(addr, dest_status.missed_ack_count))
                
                    # Add a list of missing data pdus for calculating the missed_data_count
                    missing = [];
                    for i,val in enumerate(self.tx_fragments):
                        missing.append(i)
                    dest_status.missing_fragments = missing

                    # Check if destination has reached the maximum missed count
                    # If so, remove it from the list of active destinations
                    if dest_status.missed_ack_count >= self.cfg['max_missed_acks']:
                        remove_list.append(addr)
                        self.use_min_pdu_delay = True

                # Ack status
                if dest_status.completed == True:
                    num_acked_dests += 1
                status = dict()
                status["ack_status"] = dest_status.completed
                status["ack_timeout"] = dest_status.ack_timeout
                status["retry_timeout"] = dest_status.retry_timeout
                status["retry_count"] = self.get_max_retry_count()
                status["num_sent"] = dest_status.sent_data_count
                status["air_datarate"] = dest_status.air_datarate
                status["missed"] = dest_status.missed_data_count
                ack_status[addr] = status

            # Remove destinations if they have not responded several times
            for i,val in enumerate(remove_list):    
                logger.debug('SND | Remove {} from active destinations'.format(val))
                del self.dest_status[val]
            
            # Check if transmission should be canceled
            if self.get_max_retry_count() > self.cfg['max_retry_count']:
                logger.debug('SND | Max Retransmission Count Reached')
                logger.debug('SND | change state to Idle')
                self.tran(TxState.Idle)
            
                if num_acked_dests > 0:
                    self.cli.transmission_finished(self.msid, self.get_delivery_status(), ack_status)
                else:
                    self.cli.transmission_finished(self.msid, self.get_delivery_status(), ack_status)
                    #self.finished_callback({"txt":"RetransmissionCount reached"},self.msid, None)
                return

            # Initialize after Retransmission 
            logger.debug('TX WAITING_FOR_ACKS - initTransmissionPhase after RetransmissionTimeout')
            self.init_tx_phase(timeout_occured=True)

            # Send Address PDU
            address_pdu = AddressPdu()
            address_pdu.type = PduType.Address
            address_pdu.total = len(self.fragments)
            address_pdu.cwnd  = len(self.tx_fragments)
            address_pdu.seqnohi = get_seqnohi(self.tx_fragments)
            address_pdu.src_ipaddr = self.cli.src_ipaddr
            address_pdu.msid = self.msid
            address_pdu.tsval = date_to_milli(datetime.now())
            for i,val in enumerate(self.dest_list):
                dest_entry = DestinationEntry()
                dest_entry.dest_ipaddr = val
                dest_entry.seqno = self.seqno
                address_pdu.dst_entries.append(dest_entry)
            self.seqno += 1
        
            if Traffic.Message == self.traffic_mode and len(self.dest_list) > 0:
                pass
                # Append Data if we have only a small message to transfer */
                # TODO
                #addressPdu.dataBuffer = new Buffer(self.fragments[0].length);
                #self.fragments[0].copy(addressPdu.dataBuffer);
                #this.txFragments[0].len = addressPdu.dataBuffer.length;
                #this.txFragments[0].sent = true;
                #self.incrementNumberOfSentDataPDUs();
                #this.numSentDataPDUs++
            address_pdu.log('SND')
            pdu = address_pdu.to_buffer()
            self.cli.sendto(self.destip, pdu)

            if len(self.dest_list) > 0:
                if self.traffic_mode == Traffic.Message:
                    # Start Retransmission timer
                    timeout = round(timedelta_milli(self.retry_timestamp - datetime.now()))
                    logger.debug('SND | start Retransmission timer with {} msec delay'.format(timeout))
                    self.cancel_retransmission_timer()
                    self.start_retransmission_timer(timeout)     
                else:
                    # Start PDU Delay Timer
                    logger.debug('SND | start PDU Delay timer with a {} msec timeout'.format(MIN_PDU_DELAY))
                    self.start_pdu_delay_timer(MIN_PDU_DELAY)
                    # Change state to SENDING_DATA */
                    logger.debug('SND | change state to SENDING_DATA')
                    self.tran(TxState.SendingData)
            else:
                # Change state to FINISHED */
                logger.debug('SND | WAITING_FOR_ACKS - Change state to FINISHED')
                self.tran(TxState.Finished)
                self.cli.transmission_finished(self.msid, self.get_delivery_status(), ack_status)
        elif ev["id"] == TxEvent.ExpiryTimeout:
            pass
        else:
            pass

    async def state_finished(self, ev):
        logger.debug("SND | WAITING_FOR_ACKS: {}".format(ev['id']))
        if ev["id"] == TxEvent.Start:
            pass
        elif ev["id"] == TxEvent.Abort:
            pass
        elif ev["id"] == TxEvent.AckPdu:
            pass
        elif ev["id"] == TxEvent.PduDelayTimeout:
            pass
        elif ev["id"] == TxEvent.RetransmissionTimeout:
            pass
        elif ev["id"] == TxEvent.ExpiryTimeout:
            pass
        else:
            pass

class StatusObserver():
    def message_received(self, message, from_addr):
        logger.debug('received message of len {} from {}'.format(len(message), from_addr))

    def transmission_finished(self, msid, delivery_status, ack_status):
        logger.debug('transmission of msid: {} finished with {} {}'.format(msid, delivery_status, ack_status))

class Client(asyncio.DatagramProtocol, chan.Observer):
    # Constructor
    def __init__(self, loop, observer, conf):
        # The event loop
        self.loop = loop
        self.observer = observer
        self.src_ipaddr = conf["src_ipaddr"]
        self.mcast_ipaddr = conf["mcast_ipaddr"]
        self.dport = conf["dport"]
        self.aport = conf["aport"]
        self.channel_port = conf["chan_cli_port"]
        self.transport = None
        self.tx_ctx_list = dict()   # List of TX Sessions. Each session has a unique Message ID */

        if self.channel_port > 0:
            self.channel = pmul.WirelessChannelClient(loop, self, self.src_ipaddr, self.aport, self.channel_port)
        else:
            self.channel = None
            # Create socket
            self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
            self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            logger.error('socket listens to port {}'.format(self.aport))
            self.sock.bind((self.src_ipaddr, self.aport))
            #mreq = struct.pack("=4sl", socket.inet_aton(mcast_ipaddr), socket.INADDR_ANY)
            #self.sock.setsockopt(socket.IPPROTO_IP, socket.IP_ADD_MEMBERSHIP, mreq)
            self.task = asyncio.ensure_future(self.start())

    def generate_msid(self):
        for i in range(0,1000):
            msid = random.randrange(10000000)
            if msid not in self.tx_ctx_list:
                return msid
        return -1

    def transmission_finished(self, msid, delivery_status, ack_status):
        if msid not in self.tx_ctx_list:
            return
        ctx = self.tx_ctx_list[msid]
        if ctx.future is not None:
            ctx.future.set_result((delivery_status, ack_status))
        else:
            ctx.observer.transmission_finished(msid, delivery_status, ack_status)


    def sendto(self, ipaddr, packet):
        if self.channel is not None:
            #logger.debug('send packet over wireless channel'.format(ipaddr, self.aport))
            self.channel.sendto(ipaddr, self.dport, packet)
        else:
            logger.debug('send packet to addr {} port {}'.format(ipaddr, self.dport))
            if self.transport is not None:
                self.transport.sendto(packet, (ipaddr, self.dport))
            else:
                logger.error('UDP socket is not ready')

    async def start(self):
        coro = self.loop.create_datagram_endpoint(lambda: self, sock=self.sock)
        await asyncio.wait_for(coro, 2)

    async def _send(self, message, dst_addresses, traffic_type, node_info, future):
        logger.debug('_send')
        # For unicast communication we use the unicast IP address
        if len(dst_addresses) == 1:
            dstip = dst_addresses[0]
        else:
            dstip = self.mcast_ipaddr

        # Generate unique message-id
        msid = self.generate_msid()
        if msid == -1:
            logger.error('send_message() FAILED with: No msid found')
            return False

        # Convert IPv4 addresses from string format into 32bit values
        dests = []
        for i,val in enumerate(dst_addresses):
            entry = dict()
            entry['addr'] = val
            if val in node_info:
                node_info = node_info[val]
                entry['air_datarate'] = node_info['air_datarate']
                entry['ack_timeout'] = node_info['ack_timeout']
                entry['retry_timeout'] = node_info['retry_timeout']
            else:
                entry['air_datarate'] = 5000
                entry['ack_timeout'] = 10
                entry['retry_timeout'] = 1000                
            dests.append(entry)

        ctx = TxContext(
            self,                   # Client
            self.loop,              # loop representing the single thread
            self.observer,          # this callback shall be called after finishing the transfer
            cfg,                    # Configuration
            dstip,                  # Destintation IP address, either unicast or multicast
            dests,                  # {id: xy, airDatarate: xy, ackTimeout: xy, retryTimeout: xy }
            msid,                   # Message Id
            message,                # The Message Buffer
            traffic_type,           # Context for sending a single message */
            future,                 # Future if send operation should be done synchronously
            )           
        ctx.log("SND")

        # Add context to storage
        self.tx_ctx_list[msid] = ctx

        event = { 'id': TxEvent.Start }
        await ctx.dispatch(event)
        return msid

    async def send_message(self, message, dst_addresses, node_info, future=None):
        return await self._send(message, dst_addresses, Traffic.Message, node_info, future);

    async def send_bulk(self, message, dst_addresses, node_info, future=None):
        return await self._send(message, dst_addresses, Traffic.Bulk, node_info, future);

    def _on_ack_pdu(self, data, remote): 
        ack_pdu = AckPdu()
        ack_pdu.from_buffer(data)
        ack_pdu.log("SND")
        remote_ipaddr = ack_pdu.src_ipaddr

        for i,info_entry in enumerate(ack_pdu.info_entries):
            if info_entry.remote_ipaddr != self.src_ipaddr:
                continue # Ack_InfoEntry is not addressed to me
            msid = info_entry.msid
            if msid not in self.tx_ctx_list:
                continue # Received AckInfoEntry for unkown MessageId
            ctx = self.tx_ctx_list[msid]
            ev = dict()
            ev['id'] = TxEvent.AckPdu
            ev['remote_ipaddr'] = remote_ipaddr
            ev['info_entry'] = info_entry
            asyncio.ensure_future(ctx.dispatch(ev))

    def connection_made(self, transport):
        self.transport = transport
        logger.debug('UDP socket is ready')

    def notify(self, message, addr):
        logger.debug("P_MUL Client ({}) received message of len {} from {}".format(self.src_ipaddr, len(message), addr))
        self.datagram_received(message, addr)

    def datagram_received(self, data, addr):
        pdu = Pdu()
        pdu.from_buffer(data[:MINIMUM_PACKET_LEN])
        pdu.log("SND")

        logger.debug("SND | Received packet from {} type: {} len:{}".format(addr, pdu.type, pdu.len))

        if pdu.type == int(PduType.Ack):
            self._on_ack_pdu(data, addr)
        else:
            logger.debug("Received unkown PDU type {}".format(pdu.type))

    def error_received(self, exc):
        logger.debug('Error received:', exc)

    def connection_lost(self, exc):
        logger.debug("Socket closed, stop the event loop")
        loop = asyncio.get_event_loop()
        loop.stop()

################################################################################
## P_MUL server
##

# Event types for RX statemachine
class RxEvent(Enum):
    Entry = 0
    Exit = 1
    AddressPdu = 2
    ExtraAddressPdu = 3
    DataPdu = 4
    LastPduTimeout = 5
    AckPduTimeout = 6
    ExpiryTimeout = 7

class RxState(Enum):
    Idle = 0
    ReceivingData = 1
    SentAck = 2
    Finished = 3

class RxContext(): 
    def __init__(self, cli, loop, cfg, my_ipaddr, remote_ipaddr, msid):
        self.cfg = cfg                          # Global Configuration
        self.states = dict()
        self.states[RxState.Idle] = self.state_IDLE
        self.states[RxState.ReceivingData] = self.state_RECEIVING_DATA
        self.states[RxState.SentAck] = self.state_SENT_ACK
        self.states[RxState.Finished] = self.state_FINISHED
        self.curr = RxState.Idle
        self.cli = cli
        self.loop = loop

        # Address_PDU and Reception of DATA_PDUs ###############################
        self.total = 0                         # The total number of PDUs of the message
        self.my_ipaddr = my_ipaddr              # My own identifier
        self.remote_ipaddr = remote_ipaddr      # The ipaddress of the sender
        self.dests = []                         # List of destination IDs of message reception
        self.msid  = msid                       # Unique Message ID of transfer
        self.max_address_pdu_len = 0            # The maximum length of the AddressPdu - User to calc RoundTripTime
        self.start_timestamp = None             # Timestamp at which 1st AddressPdu or 1st DataPdu of a RxPhase was received 
        self.cwnd = 0                           # Number of PDUs which should be received in the current RxPhase
        self.seqnohi = 0                        # Highest Sequence Number of current window
        self.cwnd_seqno = 0                     # Transmission Window sequence number
        self.ts_val = 0                         # Timestamp Value from 1st AddressPdu
        self.tvalue = 0                         # TValue which is sent with 1st AckPdu
        self.mtu = 1024                         # Packet Size of received fragments

        # Fragments and AckStatus ###############################################
        self.fragments = dict()                 # The list of received fragments
        self.received = dict()                  # List of received fragments in the current RxPhase

        # LastPduTimer and AckPduTimer ##############################################
        self.rx_datarate = 0                    # The rxDatarate which is used to calc the last PDU timer
        self.last_pdu_delay_timer = None        # Last PDU Timer for sending ACKs
        self.ack_pdu_timer = None               # ACK PDU Timer for retransmitting ACKs
        self.mcast_ack_timeout = 0              # Additional timeout for sending an ACK
        self.ack_retry_count = 0                # Current number of Ack retries
        self.max_ack_retry_count = cfg["max_ack_retry_count"]

    def tran(self, to):
        self.curr = to

    async def dispatch(self, ev):
        func = self.states[self.curr]
        if func is not None:
            await func(ev)

    # When we received an AddressPdu the current number of announced PDUs is set. 
    # Thus if this value is set the RContext is initialized */
    def initialized(self): 
        return (self.cwnd != 0)

    # Returns if message transfer if destined to a group. In case we don´t know the 
    # destinations yet we assume that it is a mcast transfer */ 
    def is_mcast(self): 
        return (len(self.dests) != 1)

    def last_pdu_delay_timeout(self):
        event = { 'id': RxEvent.LastPduTimeout }
        asyncio.ensure_future(self.dispatch(event))

    def cancel_last_pdu_delay_timer(self):
        if self.last_pdu_delay_timer is not None:
            self.last_pdu_delay_timer.cancel()
            self.last_pdu_delay_timer = None

    def start_last_pdu_delay_timer(self, timeout):
        if self.last_pdu_delay_timer is not None:
            self.cancel_last_pdu_delay_timer()
        timeout = timeout/1000
        #logger.debug("start last_pdu_delay timer in {} milliseconds".format(timeout))
        self.last_pdu_delay_timer = self.loop.call_later(timeout, self.last_pdu_delay_timeout)

    def ack_pdu_timeout(self):
        event = { 'id': RxEvent.AckPduTimeout }
        asyncio.ensure_future(self.dispatch(event))

    def cancel_ack_pdu_timer(self):
        if self.ack_pdu_timer is not None:
            #print("cancel ack_pdu timer")
            self.ack_pdu_timer.cancel()
            self.ack_pdu_timer = None

    def start_ack_pdu_timer(self, timeout):
        if self.ack_pdu_timer is not None:
            self.cancel_ack_pdu_timer()
        timeout = timeout/1000
        #logger.debug("start ack_pdu_ timer in {} milliseconds".format(timeout))
        self.ack_pdu_timer = self.loop.call_later(timeout, self.ack_pdu_timeout)

    # Copy buffer to internal fragment buffer */
    def save_fragment(self, seqno, buffer):
        if seqno not in self.fragments:
            self.fragments[seqno] = buffer
            logger.debug('RCV | Saved fragment {} with len {}'.format(seqno, len(buffer)))

    # Return list of missing fragment Seq numbers */
    def get_missing_fragments(self): 
        missing = []
        for i in range(0,self.seqnohi):
            if i not in self.fragments:
                missing.append(i)
        return missing

    # Get number of remaining fragments */
    def get_remaining_fragments(self, seqno): 
        remaining = 0

        if self.total <= 0:
            logger.debug("RCV | Remaining fragment: 0 - Total number of PDUs is unkown")
            return 0
        # Calculate remaining number of PDUs based on the total number of
        # PDUs in the current window and the already received number of PDUS */
        remaining_window_num = self.cwnd - len(self.received)
        # Calculate the remaining number of PDUS based on the sequence number
        # of the current received PDU and the highest sequence number of the current window */
        remaining_window_seqno = self.seqnohi - seqno
        # The smallest number will become the remaining number of PDUs */
        remaining = min(remaining_window_num, remaining_window_seqno)
        remaining = max(remaining, 0)
        logger.debug('RCV | Remaining: {} windowNum: {} window_seqno: {}'.format(remaining, remaining_window_num, remaining_window_seqno))
        return remaining

    # Update the MTU size based on the received fragments
    def update_mtu_size(self): 
        mtu_size = 0
        for key,val in self.received.items():
            if val > mtu_size:
                mtu_size = val
        if mtu_size != 0:
            self.mtu = mtu_size

    # Calculate the RxDatarate based on the current received bytes and the time interval
    def update_rx_datarate(self, seqno):
        datarate = 0
        nbytes = 0

        if self.total > 1:
            remaining = self.get_remaining_fragments(seqno)
            nbytes = (self.cwnd - remaining) * self.mtu
        else:
            for key,val in self.received.items():
                nbytes += val
        # Calculate average datarate since 1st received DataPdu
        datarate = calc_datarate(self.start_timestamp, nbytes)
        # Weight new datarate with old datarate
        if self.rx_datarate == 0:
            self.rx_datarate = datarate
        datarate = avg_datarate(self.rx_datarate, datarate);
        # Update the stored datarate
        self.rx_datarate = min(datarate, self.cfg["max_datarate"])  # upper boundary
        self.rx_datarate = max(datarate, self.cfg["min_datarate"])  # lower boundary
        logger.debug("RCV | {} Updated RxDatarate to {} bit/s".format(self.my_ipaddr, self.rx_datarate))

    # Calculate the timeout at which a AckPDU should be retransmitted */
    def calc_ack_pdu_timeout(self, num_dests, rx_datarate):
        if rx_datarate == 0:
            rx_datarate = 5000 # just to be sure we have a valid value here
        if num_dests > 1:
            # Multicast
            message_len = MAX_ADDRESS_PDU_LEN
            timeout = self.cfg["rtt_extra_delay"]
            timeout += num_dests * ACK_PDU_DELAY_MSEC
            timeout += round(message_len*8*1000/rx_datarate)
        else:
            # Unicast
            message_len = MAX_ADDRESS_PDU_LEN + MAX_ACK_PDU_LEN
            timeout = self.cfg["rtt_extra_delay"]
            timeout += round(message_len*8*1000/rx_datarate)
        logger.debug('RX AckPduTimeout: {} num_dests: {}'.format(timeout, num_dests))
        return timeout

    # Calculate the Time Value which should be included in the AckPdu */
    def calc_tvalue(self):
        deltatime = datetime.now() - self.start_timestamp
        tvalue = round(timedelta_milli(deltatime))
        logger.debug("RX TValue: {}".format(tvalue))
        return tvalue

    # Update the maximum length of a AddressPdu
    def update_max_address_pdu_len(self, pdu_len):
        if pdu_len > self.max_address_pdu_len:
            self.max_address_pdu_len = pdu_len

    def send_ack(self, seqnohi, missing, tvalue, ts_ecr):
        ack_pdu = AckPdu()
        ack_pdu.src_ipaddr = self.my_ipaddr
        ack_info_entry = AckInfoEntry()
        ack_info_entry.seqnohi = seqnohi
        ack_info_entry.remote_ipaddr = self.remote_ipaddr
        ack_info_entry.msid = self.msid
        ack_info_entry.tvalue = tvalue
        ack_info_entry.tsecr = ts_ecr
        ack_info_entry.missing_seqnos = missing
        ack_pdu.info_entries.append(ack_info_entry)        
        pdu = ack_pdu.to_buffer()
        logger.debug("RCV | {} send AckPdu to {} of len {} with ts_ecr: {} tvalue: {} seqnohi: {} missing: {}".format(
            self.my_ipaddr, self.remote_ipaddr, len(pdu), ts_ecr, tvalue, seqnohi, missing))
        if self.cli.channel is not None:
            self.cli.channel.sendto(self.remote_ipaddr, self.cli.aport, pdu)
        else:
            self.cli.transport.sendto(pdu, (self.remote_ipaddr, self.cli.aport))
        return len(pdu)

    def log(self):
        logger.debug('RCV +--------------------------------------------------------------+')
        logger.debug('RCV | RX Phase                                                     |')
        logger.debug('RCV +--------------------------------------------------------------+')
        logger.debug('RCV | remote_ipaddr: {}'.format(self.remote_ipaddr))
        logger.debug('RCV | dests: {}'.format(self.dests))
        logger.debug('RCV | cwnd: {}'.format(self.cwnd))
        logger.debug('RCV | total: {}'.format(self.total))
        logger.debug('RCV | seqnohi: {}'.format(self.seqnohi))
        logger.debug('RCV | tsVal: {}'.format(self.ts_val))
        logger.debug('RCV | rx_datarate: {}'.format(self.rx_datarate))
        logger.debug('RCV +--------------------------------------------------------------+')

    async def state_IDLE(self, ev):
        logger.debug('RCV | state_IDLE: {}'.format(ev['id']))
        if ev["id"] == RxEvent.AddressPdu:
            # Initialize Reception Phase
            address_pdu = ev['address_pdu']
            self.dests = address_pdu.get_dest_list()
            self.total = address_pdu.total
            self.start_timestamp = datetime.now()
            self.cwnd = address_pdu.cwnd
            self.seqnohi = address_pdu.seqnohi
            self.ts_val = address_pdu.tsval
            self.tvalue = 0
            self.received = {}
            self.ack_retry_count = 0
            self.update_max_address_pdu_len(address_pdu.length())
            self.log()

            if len(address_pdu.payload) > 0:    
                # TrafficMode.Message
                self.received[0] = len(address_pdu.payload)
                self.save_fragment(0, address_pdu.payload)

                if len(self.dests) > 1: 
                    # Multicast - Wait random time before sending AckPdu
                    self.mcast_ack_timeout = round(random.random() * (len(self.dests) * ACK_PDU_DELAY_MSEC))
                    logger.debug("RCV | start LAST_PDU timer with a {} msec timeout')".format(self.mcast_ack_timeout))
                    self.start_last_pdu_delay_timer(self.mcast_ack_timeout)
                    logger.debug("RCV | IDLE - Change state to RECEIVING_DATA")
                    self.tran(RxState.ReceivingData)
                else:
                    # Unicast -> Send AckPdu
                    self.tvalue = self.calc_tvalue()
                    missed = self.get_missing_fragments()
                    nbytes = self.send_ack(self.seqnohi, missed, self.tvalue, self.ts_val)
                    timeout = self.calc_ack_pdu_timeout(len(self.dests), self.rx_datarate)
                    logger.debug("RCV | Start ACK_PDU timer with a {} msec timeout".format(timeout))
                    self.start_ack_pdu_timer(timeout)
                    # Change state to SENT_ACK
                    self.cwnd = 00  # Reset RxPhase - FIXME??*/
                    logger.debug('RCV | RECEIVING_DATA - Change state to SENT_ACK')
                    self.tran(RxState.SentAck)
            else:
                # TrafficMode.Bulk - Start Last PDU Timer
                remaining_bytes = (address_pdu.cwnd+1) * self.mtu # Additional AddressPdu
                if self.rx_datarate == 0:
                    timeout = calc_remaining_time(remaining_bytes, 5000)
                else:
                    timeout = calc_remaining_time(remaining_bytes, self.rx_datarate)
                if len(self.dests) > 1:
                    # At multicast the AckPdu will be randomly delayed to avoid collisions
                    self.mcast_ack_timeout = round(random.random() * (len(self.dests) * ACK_PDU_DELAY_MSEC))
                    timeout += self.mcast_ack_timeout
                logger.debug('RCV | start LAST_PDU timer with a {} msec timeout'.format(timeout))
                self.start_last_pdu_delay_timer(timeout)
                # Change state to RECEIVING_DATA
                logger.debug('RCV | IDLE - change state to RECEIVING_DATA')
                self.tran(RxState.ReceivingData)

        elif ev["id"] == RxEvent.ExtraAddressPdu:
            # Initialize Reception Phase
            address_pdu = ev['address_pdu']
            self.dests = address_pdu.get_dest_list()
            self.total = address_pdu.total
            self.start_timestamp = datetime.now()
            self.cwnd = address_pdu.cwnd
            self.seqnohi = address_pdu.seqnohi
            self.tvalue = 0
            self.received = {}
            self.ack_retry_count = 0
            self.update_max_address_pdu_len(address_pdu.length())
            self.log()

            if len(self.dests) > 1: 
                # Multicast - Wait random time before sending AckPdu
                self.mcast_ack_timeout = round(random.random() * (len(self.dests) * ACK_PDU_DELAY_MSEC))
                logger.debug("RCV | start LAST_PDU timer with a {} msec timeout')".format(self.mcast_ack_timeout))
                self.start_last_pdu_delay_timer(self.mcast_ack_timeout)
                logger.debug("RCV | IDLE - Change state to RECEIVING_DATA")
                self.tran(RxState.ReceivingData)
            else:
                # Unicast -> Send AckPdu
                self.tvalue = self.calc_tvalue()
                missed = self.get_missing_fragments()
                nbytes = self.send_ack(self.seqnohi, missed, self.tvalue, self.ts_val)
                timeout = self.calc_ack_pdu_timeout(len(self.dests), self.rx_datarate)
                logger.debug("RCV | Start ACK_PDU timer with a {} msec timeout".format(timeout))
                self.start_ack_pdu_timer(timeout)
                # Change state to SENT_ACK
                self.cwnd = 00  # Reset RxPhase - FIXME??*/
                logger.debug('RCV | RECEIVING_DATA - Change state to SENT_ACK')
                self.tran(RxState.SentAck)

        elif ev["id"] == RxEvent.DataPdu:
            # Initialize Reception Phase
            data_pdu = ev['data_pdu']
            self.start_timestamp = datetime.now()
            self.cwnd = data_pdu.cwnd
            self.seqnohi = data_pdu.seqnohi
            self.ts_val = 0
            self.tvalue = 0
            self.received = {}
            self.ack_retry_count = 0
            self.log()
            # Change state to RECEIVING_DATA */
            logger.debug('RCV | change state to RECEIVING_DATA')
            self.tran(RxState.ReceivingData)
        elif ev["id"] == RxEvent.LastPduTimeout:
            pass
        elif ev["id"] == RxEvent.AckPduTimeout:
            pass
        elif ev["id"] == RxEvent.ExpiryTimeout:
            pass
        else:
            pass

    async def state_RECEIVING_DATA(self, ev):
        logger.debug('RCV | state_RECEIVING_DATA: {}'.format(ev['id']))

        if ev["id"] == RxEvent.AddressPdu:
            self.cancel_last_pdu_delay_timer()

            # Initialize Reception Phase
            address_pdu = ev['address_pdu']
            self.dests = address_pdu.get_dest_list()
            self.total = address_pdu.total
            self.start_timestamp = datetime.now()
            self.cwnd = address_pdu.cwnd
            self.seqnohi = address_pdu.seqnohi
            self.ts_val = address_pdu.tsval
            self.tvalue = 0
            self.received = {}
            self.ack_retry_count = 0
            self.update_max_address_pdu_len(address_pdu.length())
            self.log()

            # TrafficMode.Bulk - Start Last PDU Timer
            remaining_bytes = (address_pdu.cwnd+1) * self.mtu # Additional AddressPdu
            if self.rx_datarate == 0:
                timeout = calc_remaining_time(remaining_bytes, 5000)
            else:
                timeout = calc_remaining_time(remaining_bytes, self.rx_datarate)
            if len(self.dests) > 1:
                # At multicast the AckPdu will be randomly delayed to avoid collisions
                self.mcast_ack_timeout = round(random.random() * (len(self.dests) * ACK_PDU_DELAY_MSEC))
                timeout += self.mcast_ack_timeout
            logger.debug('RCV | start LAST_PDU timer with a {} msec timeout'.format(timeout))
            self.start_last_pdu_delay_timer(timeout)
            
        elif ev["id"] == RxEvent.ExtraAddressPdu:
            self.cancel_last_pdu_delay_timer()
            address_pdu = ev['address_pdu']        
            # Update Reception Phase
            self.dests = address_pdu.get_dest_list()
            self.total = address_pdu.total
            self.cwnd = address_pdu.cwnd
            self.seqnohi = address_pdu.seqnohi
            self.tvalue = 0
            self.log()

            if len(self.dests) > 1: 
                # Multicast - Wait random time before sending AckPdu
                self.mcast_ack_timeout = round(random.random() * (len(self.dests) * ACK_PDU_DELAY_MSEC))
                logger.debug("RCV | start LAST_PDU timer with a {} msec timeout')".format(self.mcast_ack_timeout))
                self.start_last_pdu_delay_timer(self.mcast_ack_timeout)
            else:
                # Unicast -> Immediately send AckPdu
                self.tvalue = self.calc_tvalue()
                missed = self.get_missing_fragments()
                nbytes = self.send_ack(self.seqnohi, missed, self.tvalue, self.ts_val)
                timeout = self.calc_ack_pdu_timeout(len(self.dests), self.rx_datarate)
                logger.debug("RCV | Start ACK_PDU timer with a {} msec timeout".format(timeout))
                self.start_ack_pdu_timer(timeout)
                # Change state to SENT_ACK
                self.cwnd = 00  # Reset RxPhase - FIXME??*/
                logger.debug('RCV | RECEIVING_DATA - Change state to SENT_ACK')
                self.tran(RxState.SentAck)

        elif ev["id"] == RxEvent.DataPdu:
            self.cancel_last_pdu_delay_timer()
            data_pdu = ev['data_pdu']
            # Save the received data fragment
            self.received[data_pdu.seqno] = len(data_pdu.data)
            self.save_fragment(data_pdu.seqno, data_pdu.data)
            # Update the transmission window parameters
            self.cwnd = data_pdu.cwnd
            self.seqnohi = data_pdu.seqnohi
            self.cwnd_seqno = data_pdu.cwnd_seqno
            # Calculate rx-datarate
            self.update_rx_datarate(data_pdu.seqno)
        
            if self.cwnd > 0:
                # Calculate how many data PDUs are still awaited
                remaining = self.get_remaining_fragments(data_pdu.seqno)
                logger.debug('RCV | {} | Received DataPDU[{}] Remaining: {} RxDatarate: {} bit/s'.format(
                    self.my_ipaddr, data_pdu.seqno, remaining, self.rx_datarate))
                # Start LAST PDU Timer
                remaining += 1 # Additional ExtrAddressPdu
                timeout = calc_remaining_time(remaining * self.mtu, self.rx_datarate)
                if len(self.dests) > 1:
                    # At multicast the AckPdu will be randomly delayed to avoid collisions
                    self.mcast_ack_timeout = round(random.random() * (len(self.dests) * ACK_PDU_DELAY_MSEC))
                    timeout += self.mcast_ack_timeout
                logger.debug('RCV | start LAST_PDU timer with a {} msec timeout'.format(timeout))
                self.start_last_pdu_delay_timer(timeout)

        elif ev["id"] == RxEvent.LastPduTimeout:
            self.cancel_last_pdu_delay_timer()

            self.tvalue = self.calc_tvalue()
            if len(self.dests) > 1:
                # At multicast communication we subtract the waiting time
                self.tvalue = self.tvalue - self.mcast_ack_timeout
            missed = self.get_missing_fragments()
            nbytes = self.send_ack(self.seqnohi, missed, self.tvalue, self.ts_val)
            timeout = self.calc_ack_pdu_timeout(len(self.dests), self.rx_datarate)
            logger.debug("RCV | Start ACK_PDU timer with a {} msec timeout".format(timeout))
            self.start_ack_pdu_timer(timeout)
            # Change state to SENT_ACK
            self.cwnd = 00  # Reset RxPhase - FIXME??*/
            logger.debug('RCV | RECEIVING_DATA - Change state to SENT_ACK')
            self.tran(RxState.SentAck)
        
        elif ev["id"] == RxEvent.AckPduTimeout:
            self.cancel_ack_pdu_timer()
        elif ev["id"] == RxEvent.ExpiryTimeout:
            pass
        else:
            pass

    async def state_SENT_ACK(self, ev):
        logger.debug('RCV | state_SENT_ACK: {}'.format(ev['id']))

        if ev["id"] == RxEvent.AddressPdu:
            self.cancel_ack_pdu_timer();
            address_pdu = ev['address_pdu']

            to_me = address_pdu.find_addr(self.my_ipaddr)
            if to_me is False:
                # Change state to FINISHED
                logger.debug('SND | change state to FINISHED')
                self.tran(RxState.Finished)
                message = reassemble(self.fragments)
                self.cli._on_finished(self.msid, message, self.remote_ipaddr)
                return

            self.dests = address_pdu.get_dest_list()
            self.total = address_pdu.total
            self.start_timestamp = datetime.now()
            self.cwnd = address_pdu.cwnd
            self.seqnohi = address_pdu.seqnohi
            self.ts_val = address_pdu.tsval
            self.tvalue = 0
            self.received = {}
            self.ack_retry_count = 0
            self.update_max_address_pdu_len(address_pdu.length())
            self.log()

            if len(address_pdu.payload) > 0:    
                # TrafficMode.Message
                self.received[0] = len(address_pdu.payload)
                self.save_fragment(0, address_pdu.payload)

                if len(self.dests) > 1: 
                    # Multicast - Wait random time before sending AckPdu
                    self.mcast_ack_timeout = round(random.random() * (len(self.dests) * ACK_PDU_DELAY_MSEC))
                    logger.debug("RCV | start LAST_PDU timer with a {} msec timeout')".format(self.mcast_ack_timeout))
                    self.start_last_pdu_delay_timer(self.mcast_ack_timeout)
                    logger.debug("RCV | IDLE - Change state to RECEIVING_DATA")
                    self.tran(RxState.ReceivingData)
                else:
                    # Unicast -> Send AckPdu
                    self.tvalue = self.calc_tvalue()
                    missed = self.get_missing_fragments()
                    nbytes = self.send_ack(self.seqnohi, missed, self.tvalue, self.ts_val)
                    timeout = self.calc_ack_pdu_timeout(len(self.dests), self.rx_datarate)
                    logger.debug("RCV | Start ACK_PDU timer with a {} msec timeout".format(timeout))
                    self.start_ack_pdu_timer(timeout)
                    # Change state to SENT_ACK
                    self.cwnd = 00  # Reset RxPhase - FIXME??*/
                    logger.debug('RCV | RECEIVING_DATA - Change state to SENT_ACK')
                    self.tran(RxState.SentAck)
            else:
                # TrafficMode.Bulk - Start Last PDU Timer
                remaining_bytes = (address_pdu.cwnd+1) * self.mtu # Additional AddressPdu
                timeout = calc_remaining_time(remaining_bytes, self.rx_datarate)
                if len(self.dests) > 1:
                    # At multicast the AckPdu will be randomly delayed to avoid collisions
                    self.mcast_ack_timeout = round(random.random() * (len(self.dests) * ACK_PDU_DELAY_MSEC))
                    timeout += self.mcast_ack_timeout
                logger.debug('RCV | start LAST_PDU timer with a {} msec timeout'.format(timeout))
                self.start_last_pdu_delay_timer(timeout)
                # Change state to RECEIVING_DATA
                logger.debug('RCV | IDLE - change state to RECEIVING_DATA')

                self.tran(RxState.ReceivingData)

        elif ev["id"] == RxEvent.ExtraAddressPdu:
            pass
        elif ev["id"] == RxEvent.DataPdu:
            self.cancel_ack_pdu_timer()
            data_pdu = ev['data_pdu']
            # Save the received data fragment
            self.received[data_pdu.seqno] = len(data_pdu.data)
            self.save_fragment(data_pdu.seqno, data_pdu.data)
            self.update_mtu_size()

            if data_pdu.cwnd_seqno > self.cwnd_seqno:
                # Initialize new Reception Phase on DataPdu */
                self.start_timestamp = datetime.now()
                self.cwnd = data_pdu.cwnd
                self.seqnohi = data_pdu.seqnohi
                self.ts_val = 0
                self.tvalue = 0
                self.received = {}
                self.ack_retry_count = 0
            else:
                self.update_rx_datarate(data_pdu.seqno)
            self.log()
        
            if self.cwnd > 0:
                # Calculate how many data PDUs are still awaited
                remaining = self.get_remaining_fragments(data_pdu.seqno)
                logger.debug('RX {} | Received DataPDU[{}] Remaining: {} RxDatarate: {} bit/s'.format(
                    self.my_ipaddr, data_pdu.seqno, remaining, self.rx_datarate))
                # Start LAST PDU Timer
                remaining += 1 # Additional ExtrAddressPdu
                timeout = calc_remaining_time(remaining * self.mtu, self.rx_datarate)
                if len(self.dests) > 1:
                    # At multicast the AckPdu will be randomly delayed to avoid collisions
                    self.mcast_ack_timeout = round(random.random() * (len(self.dests) * ACK_PDU_DELAY_MSEC))
                    timeout += self.mcast_ack_timeout
                logger.debug('RCV | start LAST_PDU timer with a {} msec timeout'.format(timeout))
                self.start_last_pdu_delay_timer(timeout)
                # Change state to RECEIVING_DATA
                logger.debug('RCV | IDLE - change state to RECEIVING_DATA')
                self.tran(RxState.ReceivingData)

        elif ev["id"] == RxEvent.LastPduTimeout:
            self.cancel_last_pdu_delay_timer()

        elif ev["id"] == RxEvent.AckPduTimeout:
            self.cancel_ack_pdu_timer()
            self.ack_retry_count += 1
            logger.debug("RCV | RetryCount: {} MaxRetryCount: {}".format(self.ack_retry_count, self.cfg["max_ack_retry_count"]))
            if self.ack_retry_count > self.cfg["max_ack_retry_count"]:
                logger.debug("Aborted reception due: Maximum Ack retry count reached")
            else:
                # Resend AckPdu
                nbytes = self.send_ack(self.seqnohi, self.get_missing_fragments(), self.tvalue, self.ts_val)
                timeout = self.calc_ack_pdu_timeout(len(self.dests), self.rx_datarate)
                for i in range(0,self.ack_retry_count):
                    timeout = timeout * 2
                logger.debug("RCV | Start ACK_PDU timer with a {} msec timeout".format(timeout))
                self.start_ack_pdu_timer(timeout)

        elif ev["id"] == RxEvent.ExpiryTimeout:
            pass
        else:
            pass

    async def state_FINISHED(self, ev):
        logger.debug('RCV | state_FINISHED: {}'.format(ev['id']))
        self.cancel_last_pdu_delay_timer()
        self.cancel_ack_pdu_timer()

        if ev["id"] == RxEvent.AddressPdu:
            pass
        elif ev["id"] == RxEvent.ExtraAddressPdu:
            pass
        elif ev["id"] == RxEvent.DataPdu:
            pass
        elif ev["id"] == RxEvent.LastPduTimeout:
            pass
        elif ev["id"] == RxEvent.AckPduTimeout:
            pass
        elif ev["id"] == RxEvent.ExpiryTimeout:
            pass
        else:
            pass

class Server(asyncio.DatagramProtocol, chan.Observer):

    def __init__(self, loop, observer, conf):
        self.loop = loop
        self.observer = observer
        self.src_id = socket.inet_aton(conf["src_ipaddr"])
        self.src_ipaddr = conf["src_ipaddr"]
        self.mcast_ipaddr = conf["mcast_ipaddr"]
        self.dport = conf["dport"]
        self.aport = conf["aport"]
        self.channel_port = conf["chan_srv_port"]
        self.rx_contexts = dict()

        if self.channel_port > 0:
            self.channel = pmul.WirelessChannelClient(loop, self, self.src_ipaddr, self.dport, self.channel_port)
        else:
            self.channel = None
            # Create socket
            self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
            self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            logger.debug('socket listens to port {}'.format(self.dport))
            self.sock.bind(('', self.dport))
            #mreq = struct.pack("=4sl", socket.inet_aton(mcast_ipaddr), socket.INADDR_ANY)
            #self.sock.setsockopt(socket.IPPROTO_IP, socket.IP_ADD_MEMBERSHIP, mreq)
            self.task = asyncio.ensure_future(self.start())

    async def start(self):
        coro = self.loop.create_datagram_endpoint(lambda: self, sock=self.sock)
        await asyncio.wait_for(coro, 5)

    async def sendto(self, message, dst_addresses):
        if self.channel is not None:
            logger.debug('send message over wireless channel'.format(self.mcast_ipaddr, self.aport))
            self.channel.sendto(self.mcast_ipaddr, message)
        else:
            logger.debug('send message to addr {} port {}'.format(self.mcast_ipaddr, self.aport))
            self.transport.sendto(message.encode(), (self.mcast_ipaddr, self.aport))

    def connection_made(self, transport):
        self.transport = transport
        logger.debug('Connection is made:')

    def notify(self, message, addr):
        #logger.debug("P_MUL Server received message of len {} from {}".format(len(message), addr))
        self.datagram_received(message, addr)

    def _on_finished(self, msid, message, src_addr):
        logger.debug('RCV | Received message {} of len {} from {}'.format(msid, len(message), src_addr))
        self.observer.message_received(message, src_addr)

    def _on_data_pdu(self, data, remote): 
        data_pdu = DataPdu()
        data_pdu.from_buffer(data)

        remote_ipaddr = data_pdu.src_ipaddr
        msid = data_pdu.msid
        key = (remote_ipaddr, msid)

        if key not in self.rx_contexts:
            pass
            # FIXME:

            # A new RxContext needs to be initialized
            #ctx = RxContext(self, self.loop, cfg, self.src_ipaddr, remote_ipaddr, data_pdu.msid)
            #logger.info("created context {}".format(key))
            #self.rx_contexts[key] = ctx
            #ev = dict()
            #ev['id'] = RxEvent.DataPdu
            #ev['data_pdu'] = data_pdu
            #asyncio.ensure_future(ctx.dispatch(ev))
        else:
            # There is already a RxContext -> forward message to statemachine
            ctx = self.rx_contexts[key]
            data_pdu.log("RCV")
            ev = dict()
            ev['id'] = RxEvent.DataPdu
            ev['data_pdu'] = data_pdu
            asyncio.ensure_future(ctx.dispatch(ev))

    def _on_address_pdu(self, data, remote): 
        address_pdu = AddressPdu()
        address_pdu.from_buffer(data)

        if address_pdu.type == PduType.ExtraAddress:
            event_id = RxEvent.ExtraAddressPdu
        else:
            event_id = RxEvent.AddressPdu

        # On receipt of an Address_PDU the receiving node shall first check whether 
        # the Address_PDU with the same tuple "Source_ID, MSID" has already been received
        remote_ipaddr = address_pdu.src_ipaddr
        msid = address_pdu.msid
        key = (remote_ipaddr, msid)

        if key not in self.rx_contexts:
            # If its own ID is not in the list of Destination_Entries, 
            # the receiving node shall discard the Address_PDU
            if  address_pdu.find_addr(self.src_ipaddr) == False:
                #logger.debug('RX Silently discard AddressPdu - I am not addressed')
                return
            # A new RxContext needs to be initialized
            address_pdu.log("RCV")
            ctx = RxContext(self, self.loop, cfg, self.src_ipaddr, address_pdu.src_ipaddr, address_pdu.msid)
            #logger.info("created context {}".format(key))
            self.rx_contexts[key] = ctx
            ev = dict()
            ev['id'] = event_id
            ev['address_pdu'] = address_pdu
            asyncio.ensure_future(ctx.dispatch(ev))
        else:
            # There is already a RxContext -> forward message to statemachine
            address_pdu.log("RCV")
            ctx = self.rx_contexts[key]
            ev = dict()
            ev['id'] = event_id
            ev['address_pdu'] = address_pdu
            asyncio.ensure_future(ctx.dispatch(ev))

    def datagram_received(self, data, addr):
        pdu = Pdu()
        pdu.from_buffer(data[:MINIMUM_PACKET_LEN])
        #pdu.log("RX")

        logger.debug("RX Received packet from {} type: {} len:{}".format(addr, pdu.type, pdu.len))

        if pdu.type == int(PduType.Address):
            logger.debug("Received address PDU")
            self._on_address_pdu(data, addr)
        elif pdu.type == int(PduType.ExtraAddress):
            self._on_address_pdu(data, addr)
        elif pdu.type == int(PduType.Data):
            self._on_data_pdu(data, addr)
        elif pdu.type == int(PduType.Ack):
            ack_pdu = AckPdu()
            ack_pdu.from_buffer(data)
            ack_pdu.log("RCV")
        else:
            print("Received unkown PDU type {}".format(pdu.type))

    def error_received(self, exc):
        logger.debug('Error received:', exc)

    def connection_lost(self, exc):
        logger.debug("Socket closed, stop the event loop")
        loop = asyncio.get_event_loop()
        loop.stop()

#########################################################################
## Public interface
#
#

class PmulTransport(StatusObserver):

    def __init__(self, loop, proto, conf):
        self.__loop = loop                    # loop to process
        self.__proto = proto                  # Creator

        self.__conf = conf_init()
        # IP address to bind
        if conf["src_ipaddr"] is not None:
            self.__conf["src_ipaddr"] = conf["src_ipaddr"]
        # Multicast address used for data communication
        if conf["mcast_ipaddr"] is not None:
            self.__conf["mcast_ipaddr"] = conf["mcast_ipaddr"]
        # Multicast TTL value used for data communication
        if conf["mcast_ttl"] is not None:
            self.__conf["mcast_ttl"] = conf["mcast_ttl"]
        # UDP Port for sending data packets
        if conf["dport"] is not None:
            self.__conf["dport"] = conf["dport"]
        # UDP Port for sending ACK packets
        if conf["aport"] is not None:
            self.__conf["aport"] = conf["aport"]
        # Channel Emulation - UDP client port
        if conf["chan_cli_port"] is not None:
            self.__conf["chan_cli_port"] = conf["chan_cli_port"]
        # Channel Emulation - UDP server port
        if conf["chan_srv_port"] is not None:
            self.__conf["chan_srv_port"] = conf["chan_srv_port"]

        self.__min_bulk_size = 512            # If a message exceeds this size, it will be sent as bulk data
        # Information about the link-quality to other nodes. This includes:
        # node_info['fragment_size']    := Used fragment size for transmission. Dynamically adjusted based on loss-rate 
        # node_info['loss_rate']        := Average Percentage of lossed datagrams.
        # node_info['air_datarate']     := Measured air datarate of sending datagrams to destination. Used for bulk.
        # node_info['retry_timeout']    := For retry-timeout for single-message transmission
        # node_info['ack_timeout']      := Transmission time of AckPDU (Time between sending Ack and Receiving it)
        self.__node_info = dict()

        # Create logging system
        if conf['logfile'] != 'stdout':
            fh = logging.FileHandler(conf['logfile'])
            logger.addHandler(fh)
        if conf['loglevel'] == 'debug':
            logger.setLevel(logging.DEBUG)
        else:
            logger.setLevel(logging.ERROR)

        logger.error("created transport protocol")

        self.__client = Client(loop, self, self.__conf);        
        self.__server = Server(loop, self, self.__conf);

    def message_received(self, message, from_addr):
        print("message received")
        self.__proto.data_received(message, from_addr)

    def transmission_finished(self, msid, delivery_status, ack_status):
        for addr,val in ack_status.items():
            if addr not in self.__node_info:
                self.__node_info[addr] = dict()
                self.__node_info[addr]['air_datarate'] = val['air_datarate']
                self.__node_info[addr]['retry_timeout'] = val['retry_timeout']
                self.__node_info[addr]['ack_timeout'] = val['ack_timeout']
        self.__proto.transmission_finished(msid, delivery_status, ack_status)

    # Deliver a message to a list of receivers. The function returns the Message-ID
    # of the transmission. User is informed by the transmission_finished() callback
    # about the success of the message delivery.
    # 
    # @message_buf:     Message enocded as bytearray
    # @dst_ipaddrs:     List of IPv4 addresses in string notation
    #
    # Returns Message-ID
    #
    async def sendto_async(self, message_buf, dst_ipaddrs):
        if len(message_buf) < self.min_bulk_size:
            return await self.__client.send_message(message_buf, dst_ipaddrs, self.__node_info)
        else:
            return await self.__client.send_bulk(message_buf, dst_ipaddrs, self.__node_info)

    # Deliver a message to a list of receivers. The function blocks until
    # the message delivery has finished. The function will return a tuple
    # of delivery_status and ack_status
    # 
    # @message_buf:     Message enocded as bytearray
    # @dst_ipaddrs:     List of IPv4 addresses in string notation
    #
    # Returns tuple of (delivery_status, ack_status)
    #
    async def sendto(self, message_buf, dst_ipaddrs):
        future = asyncio.Future()
        if len(message_buf) < self.__min_bulk_size:
            logger.debug("send a message to {}".format(dst_ipaddrs))
            asyncio.ensure_future(self.__client.send_message(message_buf, dst_ipaddrs, self.__node_info, future=future))
        else:
            asyncio.ensure_future(self.__client.send_bulk(message_buf, dst_ipaddrs, self.__node_info, future=future))
        await asyncio.wait([future])
        return future.result()

#
# The P_MUL Protocol instance - User should derive from this class
#
class PmulProtocol():
    def connection_made(self, transport):
        logger.debug('P_MUL protocol is ready')

    def data_received(self, data, addr):
        logger.debug("Received a data from {}".format(addr))

    def delivery_completed(self, msid, delivery_status, ack_status):
        logger.debug('Delivery of Message-ID {} finished with {} {}'.format(msid, delivery_status, ack_status))

def conf_init():
    conf = dict()
    conf["src_ipaddr"]      = '127.0.0.1'
    conf["mcast_ipaddr"]    = "225.0.0.1"
    conf["mcast_ttl"]       = 1
    conf["dport"]           = 2740
    conf["aport"]           = 2741
    conf["chan_cli_port"]   = 0      # Optional: Only used for network emulation
    conf["chan_srv_port"]   = 0      # Optional: Only used for network emulation
    conf["loglevel"]        = "debug"
    conf["logfile"]         = "stdout"
    return conf

async def create_pmul_endpoint(protocol_factory, loop, conf):           
    protocol = protocol_factory(conf)
    transport = PmulTransport(loop, protocol, conf)
    protocol.connection_made(transport)
    await asyncio.sleep(2)
    return protocol, transport


