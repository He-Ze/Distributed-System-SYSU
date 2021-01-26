from xmlrpc.client import ServerProxy, Binary
import base64
import bcrypt
from pathlib import Path
from config import name_server_url
import argparse
import datetime
import os
from cryptography.fernet import Fernet
from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC


def sign_up(username, password):
    if len(password) > 72:
        print('Password must be less than 72 characters.')
        return
    salt = bcrypt.gensalt()
    hash_password = bcrypt.hashpw(bytes(password, 'utf-8'), salt)
    print(salt, hash_password)

    if proxy.save_user(username, str(base64.b64encode(hash_password), 'utf-8'), str(base64.b64encode(salt), 'utf-8')):
        print('User {} created successfully.'.format(username))
    else:
        print('Could not create user {}.'.format(username))


def login(username, password):
    results = proxy.get_user_credentials(username)
    if results is None:
        print('Username does not exist.')
    else:
        user_id = int(results[0])
        hash_password = bytes(results[1], 'utf-8')

        if bcrypt.checkpw(bytes(password, 'utf-8'), hash_password):
            print('Logged in as {}.'.format(username))
            return App(user_id, username)
        else:
            print('Wrong password.')
    return None


def list_file_names(user_id, cloud_file_path):
    addresses = proxy.get_server_addresses(user_id)
    dir_paths = set()
    info_queries = set()
    print('=' * 80)
    print('{0:45s} {1:7s} {2}'.format('File Name', 'Type', 'Last Update'))
    print('=' * 80)

    for address in addresses:
        with ServerProxy(address, allow_none=True) as new_proxy:
            for is_dir, file_path in new_proxy.get_filenames(user_id, cloud_file_path):
                if is_dir:
                    dir_paths.add(file_path)
                else:
                    info_queries.add(file_path)

    for dir_path in dir_paths:
        print('{0:45s} <DIR>'.format(Path(dir_path).name + '/'))

    for file_name, mod_date in proxy.get_file_infos(user_id, list(info_queries)):
        print('{0:45s} {1:7s} {2}'.format(file_name, Path(file_name).suffix[1:].upper(),
                                          datetime.datetime.fromtimestamp(mod_date)))

    print('=' * 80)


def can_change_dir(user_id, cloud_dir_path):
    for address in proxy.get_server_addresses(user_id):
        with ServerProxy(address, allow_none=True) as new_proxy:
            path_valid, path_exists, rel_path_str = new_proxy.path_check(user_id, cloud_dir_path)
        if not path_valid:
            return False, ''
        elif path_exists:
            return True, rel_path_str
    return False, ''


def make_dirs(user_id, cloud_dir_path):
    addresses = proxy.get_server_addresses(user_id)
    exists = False
    for address in addresses:
        with ServerProxy(address, allow_none=True) as new_proxy:
            path_valid, path_exists, rel_path_str = new_proxy.path_check(user_id, cloud_dir_path)
            if path_valid and path_exists:
                exists = True
    if exists:
        return False
    address = proxy.get_next_server()
    with ServerProxy(address, allow_none=True) as new_proxy:
        made = new_proxy.make_dirs(user_id, cloud_dir_path)
    return made


def del_dir(user_id, cloud_dir_path):
    addresses = proxy.get_server_addresses(user_id)
    for address in addresses:
        with ServerProxy(address, allow_none=True) as new_proxy:
            path_valid, path_exists, rel_path_str = new_proxy.path_check(user_id, cloud_dir_path)
            if path_valid and path_exists:
                if not new_proxy.delete_empty_dir(user_id, cloud_dir_path):
                    return False
    return True


def delete_file(user_id, cloud_file_path):
    addresses = proxy.get_server_addresses(user_id)
    existing_servers = []
    for address in addresses:
        with ServerProxy(address, allow_none=True) as new_proxy:
            path_valid, path_exists, rel_path_str = new_proxy.path_check(user_id, cloud_file_path)
            if path_valid and path_exists:
                existing_servers.append(address)
    if len(existing_servers) != 1:
        return False
    with ServerProxy(existing_servers[0], allow_none=True) as new_proxy:
        success = new_proxy.delete_file(user_id, cloud_file_path)
    return success


def upload_file(user_id, file_bin, cloud_file_path, filename):
    addresses = proxy.get_server_addresses(user_id)
    file_path_with_filename = str(Path(cloud_file_path) / filename)

    existing_servers = []
    for address in addresses:
        with ServerProxy(address, allow_none=True) as new_proxy:
            path_valid, path_exists, rel_path_str = new_proxy.path_check(user_id, file_path_with_filename)

            if path_valid and path_exists:
                existing_servers.append(address)

    if len(existing_servers) > 1:
        return False
    elif len(existing_servers) == 1:
        deleted = delete_file(user_id, file_path_with_filename)

        if not deleted:
            return False

    address = proxy.get_next_server()

    with ServerProxy(address, allow_none=True) as new_proxy:
        added = new_proxy.upload_file(user_id, file_bin, cloud_file_path, filename)

    return added


def fetch_file(user_id, username, cloud_file_path, local_path_obj):
    addresses = proxy.get_server_addresses(user_id)

    flag = False
    file_bin = None
    for address in addresses:
        with ServerProxy(address, allow_none=True) as new_proxy:
            path_valid, path_exists, rel_path_str = new_proxy.path_check(user_id, cloud_file_path)

            if path_valid and path_exists:
                flag, file_bin = new_proxy.fetch_file(user_id, cloud_file_path)

    filename = Path(cloud_file_path).name

    if not flag:
        return False

    with open(str((local_path_obj / filename).resolve()), 'wb') as handle:
        decrypted = decrypt_file(username, file_bin)
        try:
            handle.write(decrypted)
        except IOError:
            return False

    return True


def get_file_binary(local_path):
    with open(local_path, 'rb') as file:
        file_bin = Binary(file.read())
    return file_bin


def decrypt_file(username, file_bin):
    _, password, salt = proxy.get_user_credentials(username)
    kdf = PBKDF2HMAC(
        algorithm=hashes.SHA256(),
        length=32,
        salt=bytes(salt, 'utf-8'),
        iterations=100000,
        backend=default_backend()
    )
    pass_as_bytes = bytes(password, 'utf-8')
    key = base64.urlsafe_b64encode(kdf.derive(pass_as_bytes))
    f = Fernet(key)
    decrypted = Binary(f.decrypt(file_bin.data))

    return decrypted.data


def encrypt_file(username, file_bin):
    _, password, salt = proxy.get_user_credentials(username)
    kdf = PBKDF2HMAC(
        algorithm=hashes.SHA256(),
        length=32,
        salt=bytes(salt, 'utf-8'),
        iterations=100000,
        backend=default_backend()
    )
    pass_as_bytes = bytes(password, 'utf-8')
    key = base64.urlsafe_b64encode(kdf.derive(pass_as_bytes))
    f = Fernet(key)
    encrypted = f.encrypt(file_bin.data)

    return encrypted


class App(object):
    def __init__(self, user_id, username):
        self.user_id = user_id
        self.username = username
        self.cd = ''

    def main_loop(self):
        while True:
            print('Current directory:', self.username + os.sep + self.cd)
            list_file_names(self.user_id, str(self.cd))

            print('OPTIONS')
            print('- changedir <dir-path>')
            print('- makedir <dir-path>')
            print('- deletedir <dir-path>')
            print('- upload <file-path> <cloud-path-to-upload> <filename>')
            print('- delete <path-of-file>')
            print('- fetch <path-on-cloud> <local-path-to-save>')
            print('- exit')
            command = str(input('$ ')).split(' ')

            if command[0] == 'changedir' and len(command) == 2:
                target_dir = Path(self.cd) / command[1].strip()
                can_change, rel_path = can_change_dir(self.user_id, str(target_dir))

                if can_change:
                    self.cd = rel_path
                else:
                    print('Invalid file path.')

            elif command[0] == 'makedir' and len(command) == 2:
                target_dir_str = str(Path(self.cd) / command[1].strip())

                if make_dirs(self.user_id, target_dir_str):
                    print('Successfully created "{}".'.format(target_dir_str))
                else:
                    print('Could not create directory.')

            elif command[0] == 'deletedir' and len(command) == 2:
                target_dir_str = str(Path(self.cd) / command[1].strip())

                if del_dir(self.user_id, target_dir_str):
                    print('Successfully deleted "{}".'.format(target_dir_str))
                else:
                    print('Could not delete directory.')
            elif command[0] == 'upload' and len(command) == 4:
                local_file_path_obj = Path(command[1].strip()).resolve()
                cloud_file_path = str(Path(self.cd) / command[2].strip())
                filename = command[3].strip()

                can_change, rel_path = can_change_dir(self.user_id, cloud_file_path)

                if can_change:
                    if local_file_path_obj.is_file():
                        file_bin = encrypt_file(self.username, get_file_binary(str(local_file_path_obj)))

                        if upload_file(self.user_id, file_bin, cloud_file_path, filename):
                            print('Uploaded "{}" to "{}" successfully.'.format(filename,
                                                                               self.username + os.sep + rel_path))
                        else:
                            print('Upload failed.')
                else:
                    print('Invalid cloud path.')

            elif command[0] == 'delete' and len(command) == 2:
                target_dir_str = str(Path(self.cd) / command[1].strip())

                if delete_file(self.user_id, target_dir_str):
                    print('File at "{}" deleted successfully.'.format(target_dir_str))
                else:
                    print('Could not delete file.')

            elif command[0] == 'fetch' and len(command) == 3:
                cloud_file_path = str(Path(self.cd) / command[1].strip())
                local_path_to_save_obj = Path(command[2].strip()).resolve()

                if not local_path_to_save_obj.is_dir():
                    print('Invalid local directory.')
                else:
                    if fetch_file(self.user_id, self.username, cloud_file_path, local_path_to_save_obj):
                        print('File saved to {}.'.format(str(local_path_to_save_obj)))
                    else:
                        print('Fetching failed.')

            elif command[0] == 'exit':
                break
            else:
                print('Invalid Command.')


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('mode', help='Client run mode. Either "signup" or "login".', type=str)
    parser.add_argument('username', help='Username of the user.', type=str)
    parser.add_argument('password', help='Password of the user.', type=str)
    args = parser.parse_args()

    proxy = ServerProxy(name_server_url, allow_none=True)

    if args.mode == 'signup':
        sign_up(args.username, args.password)
    elif args.mode == 'login':
        app = login(args.username, args.password)

        if app is not None:
            app.main_loop()
    else:
        print('Invalid operation.')
