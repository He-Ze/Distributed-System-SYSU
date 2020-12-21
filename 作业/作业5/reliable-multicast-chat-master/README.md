#Reliable Multicast Chat

## Usage

./reliable_multicast_chat [process ID] [delay time (in seconds)] [drop rate (0<=P<1)]

Execute `reliable_multicast_chat` in `./bin` folder.

## Configurations

Modify `config.py` in `reliable_mulicast_chat` directory accordingly. 
`config['hosts']` is a list of (IP address, port).
Ordering can be either 'casual' or 'total'.

## Algorithms

- **Casual Ordering**: When a process receives a multicasted message, it pushes the received message to a buffer
queue with a vector timestamp from the sender. And then `update_holdback_queue_casual()` takes care of updating the buffer
and actually delivering the message to the process. It compares the timestamps of the buffered messages with the process's timestamp to determine which messages should be kept in the buffer or be removed and delivered to the process.

- **Total Ordering**: Process 0 is always designated as the sequencer. When a process multicasts a message, other processes will hold that message in a buffer until they receive a marker message from the sequencer indicating the order of that message. When the sequencer receives a message, it increments an internal counter and assigns that number as the message's order number which will then be multicasted to all other processes.

- **Reliable Multicast**: When a process unicasts a message, it stores it in the unacknowledged messages buffer and keeps it there until an `ack` message is received. We have a thread called `ack_handler` which
periodically keeps track of received `ack` messages for each item in the buffer and either re-send the message or remove from the buffer depending on the message is asknowledged by the receiving process or not. The receiving process sends an `ack` message
every time it receives a message, but does not actually process duplicate messages (identified with message IDs).

- **Randomized Losses**: e generate a random floating point number, and if that number is
smaller than the user-specified loss rate, we don't actually send the message, however, we still keep it in the unacknowledged buffer so that the `ack_handler` thread can keep re-sending the message until the receiving process acknowledges it. See above 
_Reliable Multicast_ for details.

- **Randomized Delay**: We calculate a send_time for each outgoing message and push a tuple (send_time, message) into a queue. The `thread message_queue_handler` periodically iterates through the queue and sends out messages with current_time >= send_time.


## Requirement

* Python3
