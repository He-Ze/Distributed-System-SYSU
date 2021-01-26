import sqlite3
from xmlrpc.server import SimpleXMLRPCServer
import base64
from config import name_server_info


def init_user_table():
    cursor.execute(
    )


def init_server_table():
    cursor.execute('DROP TABLE IF EXISTS SERVERS;')
    connection.commit()
    cursor.execute(
    )


def init_file_table():
    cursor.execute('DROP TABLE IF EXISTS FILES;')
    connection.commit()
    cursor.execute(
    )


def init_db():
    init_user_table()
    init_server_table()
    init_file_table()
    connection.commit()


def get_next_server():
    global server_counter

    try:
        cursor.execute('SELECT COUNT(*) FROM SERVERS;')
        result = cursor.fetchone()
        server_counter = (server_counter + 1) % result[0]
        cursor.execute('SELECT ADDRESS FROM SERVERS WHERE SERVERID = ?;', (server_counter + 1, ))
        address = cursor.fetchone()
        return address[0]
    except sqlite3.Error:
        return ''


def save_user(username, hash_password, salt):
    try:
        cursor.execute('INSERT INTO USERS (USERNAME, PASSWORD, SALT) VALUES (?, ?, ?);',
                       (username, str(base64.b64decode(hash_password), 'utf-8'), str(base64.b64decode(salt), 'utf-8')))
        connection.commit()
        return True
    except sqlite3.Error:
        return False


def get_user_credentials(username):
    try:
        cursor.execute('SELECT USERID, PASSWORD, SALT FROM USERS WHERE USERNAME = ?;', (username, ))
        results = cursor.fetchone()
        return results
    except sqlite3.Error:
        return None


def get_server_addresses(user_id):
    try:
        cursor.execute('''SELECT DISTINCT ADDRESS FROM FILES JOIN SERVERS USING (SERVERID) 
                            WHERE ISBACKUP = 0 AND USERID = ?;''', (user_id, ))
        results = cursor.fetchall()

        return [address for (address, ) in results]
    except sqlite3.Error:
        return []


def register_file_server(server_id, address):
    try:
        cursor.execute('INSERT INTO SERVERS (SERVERID, ADDRESS) VALUES (?, ?);', (server_id, address))
        connection.commit()
        return True
    except sqlite3.Error:
        return False


def unregister_file_server(server_id):
    cursor.execute('DELETE FROM SERVERS WHERE SERVERID = ?;', (server_id, ))
    cursor.execute('DELETE FROM FILES WHERE SERVERID = ?;', (server_id, ))
    connection.commit()


def save_file_info(file_list):
    try:
        cursor.executemany('''INSERT INTO FILES (USERID, SERVERID, PATH, FILENAME, ISBACKUP, FILEHASH, LASTMODIFIED) 
                              VALUES (?, ?, ?, ?, ?, ?, ?)''', file_list)
        connection.commit()
        return True
    except sqlite3.Error:
        return False


def get_file_infos(user_id, cloud_dir_paths):
    try:
        all_results = []
        for dir_path in cloud_dir_paths:
            cursor.execute('''SELECT FILENAME, LASTMODIFIED FROM FILES 
                                WHERE ISBACKUP = 0 AND USERID = ? AND PATH LIKE ?;''', (user_id, dir_path + '%'))
            all_results += cursor.fetchall()
        return all_results
    except sqlite3.Error:
        return []


def get_file_backup_servers(server_id, user_id, cloud_file_rel_path):
    try:
        cursor.execute('''SELECT ADDRESS FROM FILES JOIN SERVERS USING (SERVERID) 
                            WHERE ISBACKUP = 1 AND SERVERID != ? AND USERID = ? AND PATH = ?''',
                       (server_id, user_id, cloud_file_rel_path))
        results = cursor.fetchall()
        return [address for (address, ) in results]
    except sqlite3.Error:
        return []


def remove_file(user_id, cloud_file_rel_path):
    try:
        cursor.execute('DELETE FROM FILES WHERE USERID = ? AND PATH = ?;', (user_id, cloud_file_rel_path))
        connection.commit()
        return True
    except sqlite3.Error:
        return False


def get_file_hashes(user_id, cloud_file_rel_path):
    try:
        cursor.execute('''SELECT ISBACKUP, FILEHASH, ADDRESS FROM FILES JOIN SERVERS USING (SERVERID) 
                            WHERE USERID = ? AND PATH = ? ORDER BY ISBACKUP DESC;''', (user_id, cloud_file_rel_path))
        results = cursor.fetchall()

        return [(file_hash, address) for _, file_hash, address in results]
    except sqlite3.Error:
        return []


if __name__ == '__main__':
    server_counter = 0
    connection = sqlite3.connect('info.db')
    cursor = connection.cursor()
    init_db()
    with SimpleXMLRPCServer(name_server_info, allow_none=True) as server:
        server.register_function(get_next_server)
        server.register_function(save_user)
        server.register_function(get_user_credentials)
        server.register_function(get_server_addresses)
        server.register_function(register_file_server)
        server.register_function(unregister_file_server)
        server.register_function(save_file_info)
        server.register_function(get_file_infos)
        server.register_function(get_file_backup_servers)
        server.register_function(remove_file)
        server.register_function(get_file_hashes)
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            connection.close()
