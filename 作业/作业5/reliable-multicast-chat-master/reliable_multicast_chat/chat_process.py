from queue import PriorityQueue
import random
import socket
import config
import threading
import sys
import time
import os

from helpers.unicast_helper import pack_message, unpack_message, calculate_send_time
from helpers.unicast_helper import stringify_vector_timestamp, parse_vector_timestamp


class ChatProcess:
    def __init__(self, process_id, delay_time, drop_rate, num_processes):
        self.my_id = process_id
        self.delay_time = delay_time
        self.drop_rate = drop_rate

        self.message_max_size = 2048
        self.message_id_counter = 0
        self.has_received = {}
        self.has_acknowledged = {}
        self.unack_messages = []
        self.holdback_queue = []

        self.holdback_queue_markers = []
        self.holdback_sequence_counter = 0
        self.sequence_counter = 0
        self.SEQUENCER_ID = 0

        self.queue = PriorityQueue()
        self.mutex = threading.Lock()
        self.my_timestamp = [0] * num_processes

        # Initialize the UDP socket.
        ip, port = config.config['hosts'][process_id]
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEPORT, 1)
        self.sock.bind((ip, port))
        self.sock.settimeout(0.01)

    def unicast_send(self, destination, message, msg_id=None, is_ack=False, is_order_marker=False, timestamp=None):
        """ Push an outgoing message to the message queue. """
        if timestamp is None:
            timestamp = self.my_timestamp[:]

        is_msg_id_specified = msg_id is not None
        if msg_id is None:
            msg_id = self.message_id_counter

        message = pack_message([self.my_id, msg_id, is_ack, is_order_marker, stringify_vector_timestamp(timestamp), message])

        if not is_ack and not is_msg_id_specified:
            with self.mutex:
                self.unack_messages.append((destination, message))

        if random.random() <= self.drop_rate:
            return

        dest_ip, dest_port = config.config['hosts'][destination]
        send_time = calculate_send_time(self.delay_time)
        self.queue.put((send_time, message, dest_ip, dest_port))

    def unicast_receive(self):
        """ Receive UDP messages from other chat processes and store them in the holdback queue.
            Returns True if new message was received. """

        data, _ = self.sock.recvfrom(self.message_max_size)
        [sender, message_id, is_ack, is_order_marker, message_timestamp, message] = unpack_message(data)

        if is_ack:
            self.has_acknowledged[(sender, message_id)] = True
        else:
            # send acknowledgement to the sender
            self.unicast_send(int(sender), "", message_id, True)
            if (sender, message_id) not in self.has_received:
                self.has_received[(sender, message_id)] = True
                if config.config['ordering'] == 'casual':
                    self.holdback_queue.append((sender, message_timestamp[:], message))
                    self.update_holdback_queue_casual()
                    return True
                else:
                    if is_order_marker:
                        m_sequencer, m_sender, m_id = [int(x) for x in message.split(';')]
                        self.holdback_queue_markers.append((m_sender, m_id, m_sequencer))
                        self.update_holdback_queue_total()
                    else:
                        if self.my_id == self.SEQUENCER_ID:
                            marker_message = ';'.join([str(x) for x in [self.sequence_counter, sender, message_id]])
                            self.multicast(marker_message, is_order_marker=True)
                            self.sequence_counter += 1

                        self.holdback_queue.append((sender, message_id, message))
                        self.update_holdback_queue_total()
                        return True
        return False

    def update_holdback_queue_casual(self):
        """ Compare message timestamps to ensure casual ordering. """
        while True:
            new_holdback_queue = []
            removed_messages = []
            for sender, v, message in self.holdback_queue:
                should_remove = True
                for i in range(len(v)):
                    if i == sender:
                        if v[i] != self.my_timestamp[i] + 1:
                            should_remove = False
                    else:
                        if v[i] > self.my_timestamp[i]:
                            should_remove = False
                if not should_remove:
                    new_holdback_queue.append((sender, v, message))
                else:
                    removed_messages.append((sender, v, message))

            for sender, v, message in removed_messages:
                self.my_timestamp[sender] += 1
                self.deliver(sender, message)

            self.holdback_queue = new_holdback_queue

            if not removed_messages:
                break

    def update_holdback_queue_total(self):
        while True:
            # TODO: reduce marker list size
            new_holdback_queue = []
            is_ever_delivered = False
            for sender, message_id, message in self.holdback_queue:
                is_delivered = False
                for m_sender, m_message_id, m_sequence in self.holdback_queue_markers:
                    m_sequence_int = int(m_sequence)
                    if sender == m_sender and message_id == m_message_id and self.holdback_sequence_counter == m_sequence_int:
                        self.deliver(sender, message)
                        is_delivered = True
                        is_ever_delivered = True
                        self.holdback_sequence_counter += 1
                        break

                if not is_delivered:
                    new_holdback_queue.append((sender, message_id, message))

            self.holdback_queue = new_holdback_queue

            if not is_ever_delivered:
                break

    def multicast(self, message, is_order_marker=False):
        """ Unicast the message to all known clients. """
        for process_id, host in enumerate(config.config['hosts']):
            self.unicast_send(process_id, message, is_order_marker=is_order_marker)
        self.message_id_counter += 1

    def deliver(self, sender, message):
        """ Do something with the received message. """
        print(sender, "says: ", message)

    def message_queue_handler(self):
        """ Thread that actually sends out messages when send time <= current_time. """
        while True:
            (send_time, message, ip, port) = self.queue.get(block=True)
            if send_time <= time.time():
                self.sock.sendto(message, (ip, port))
            else:
                self.queue.put((send_time, message, ip, port))
                time.sleep(0.01)

    def ack_handler(self):
        """ Thread that re-sends all unacknowledged messages. """
        while True:
            time.sleep(0.2)

            with self.mutex:
                new_unack_messages = []
                for dest_id, packed_message in self.unack_messages:
                    [_, message_id, is_ack, is_order_marker, message_timestamp, message] = unpack_message(packed_message)
                    if (dest_id, message_id) not in self.has_acknowledged:
                        new_unack_messages.append((dest_id, packed_message))
                        self.unicast_send(dest_id, message, msg_id=message_id, is_ack=is_ack,
                                          is_order_marker=is_order_marker, timestamp=message_timestamp)
                self.unack_messages = new_unack_messages

    def user_input_handler(self):
        """ Thread that waits for user input and multicasts to other processes. """
        for line in sys.stdin:
            line = line[:-1]
            self.my_timestamp[self.my_id] += 1
            self.multicast(line)

    def incoming_message_handler(self):
        """ Thread that listens for incoming UDP messages """
        while True:
            try:
                self.unicast_receive()
            except (socket.timeout, BlockingIOError) as e:
                pass

    def run(self):
        """ Initialize and start all threads. """
        thread_routines = [
            self.ack_handler,
            self.message_queue_handler,
            self.incoming_message_handler,
            self.user_input_handler,
        ]

        threads = []
        for thread_routine in thread_routines:
            thread = threading.Thread(target=thread_routine)
            thread.daemon = True
            thread.start()
            threads.append(thread)

        for thread in threads:
            thread.join()
