import random
import time


def pack_message(message_list):
    return (','.join([str(x) for x in message_list])).encode('utf-8')


def unpack_message(message):
    message = message.decode('utf-8')
    sender, message_id, is_ack, is_order_marker, vector_str, message = message.split(',', 5)

    sender = int(sender)
    message_id = int(message_id)
    timestamp = parse_vector_timestamp(vector_str)
    is_ack = is_ack in ['True', 'true', '1']
    is_order_marker = is_order_marker in ['True', 'true', '1']

    return [sender, message_id, is_ack, is_order_marker, timestamp, message]


def parse_vector_timestamp(vector_str):
    return [int(x) for x in vector_str.split(';')]


def stringify_vector_timestamp(vector):
    return ';'.join([str(x) for x in vector])


def calculate_send_time(delay_time):
    """ delay_time in seconds """
    delay_time = random.uniform(0, 2 * delay_time)
    return time.time() + delay_time
