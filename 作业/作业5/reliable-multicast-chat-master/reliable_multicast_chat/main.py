import sys
import config
from chat_process import ChatProcess


def main():
    if len(sys.argv) != 4:
        print('Usage: {} [process ID] [delay time] [drop rate]'.format(sys.argv[0]))
        exit(1)

    process_id = int(sys.argv[1])
    delay_rate = float(sys.argv[2])
    drop_rate = float(sys.argv[3])
    num_processes = len(config.config['hosts'])

    chat_process = ChatProcess(process_id, delay_rate, drop_rate, num_processes)
    chat_process.run()

if __name__ == '__main__':
    main()