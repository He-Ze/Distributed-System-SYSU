import os
from pathlib import Path
import hashlib
import argparse
from xmlrpc.server import SimpleXMLRPCServer
from xmlrpc.client import ServerProxy, Binary
from config import name_server_url


def get_owner_and_backup_info(rel_path_obj):
    folder = rel_path_obj.parts[0]
    try:
        if folder.endswith('_backup'):
            return int(folder.replace('_backup', '')), 1
        else:
            return int(folder), 0
    except ValueError:
        return -1, 0


def hash_file(file_path_for_hash):
    hash_obj = hashlib.sha256()
    with open(file_path_for_hash, 'rb') as rbFile:
        while True:
            block = rbFile.read(65536)
            if not block:
                break
            hash_obj.update(block)
    return hash_obj.hexdigest()


def get_file_binary(abs_path):
    with open(abs_path, 'rb') as file:
        file_bin = Binary(file.read())
    return file_bin


def generate_file_info(server_id, os_file_path, os_file_name):
    file_last_modified = os.path.getmtime(os_file_path)
    file_hash = hash_file(os_file_path)
    file_path_rel = Path(os_file_path).relative_to(root_dir)
    whose, is_backup = get_owner_and_backup_info(file_path_rel)
    file_path_str = str(file_path_rel.relative_to(file_path_rel.parts[0]))
    return whose, server_id, file_path_str, os_file_name, is_backup, file_hash, file_last_modified


def path_check(user_id, path, backup=False):
    base_dir = root_dir / (str(user_id) + '_backup') if backup else root_dir / str(user_id)
    path_obj = (base_dir / path).resolve()
    path_exists = path_obj.exists()
    path_str = str(path_obj)
    path_valid = path_str.startswith(str(base_dir))
    rel_path_str = path_str.replace(str(base_dir), '')
    rel_path_str = rel_path_str[1:] if rel_path_str.startswith(os.sep) else rel_path_str
    return path_valid, path_exists, rel_path_str


def check_file_hash(user_id, cloud_file_path, hash_to_check, backup=False):
    path_valid, path_exists, rel_path_str = path_check(user_id, cloud_file_path)
    if not path_valid or not path_exists:
        return False, 'INVALID'
    if backup:
        path_obj = (root_dir / (str(user_id) + '_backup') / rel_path_str).resolve()
    else:
        path_obj = (root_dir / str(user_id) / rel_path_str).resolve()
    hash_of_file = hash_file(str(path_obj))
    if hash_of_file == hash_to_check:
        return True, 'MATCHED'
    else:
        return False, 'NOT_MATCHED'


def get_filenames(user_id, cloud_dir_path):
    base_dir = root_dir / str(user_id)
    path_valid, path_exists, rel_path_str = path_check(user_id, cloud_dir_path)
    cd_paths = []
    if path_valid and path_exists:
        for child in (base_dir / rel_path_str).iterdir():
            cd_paths.append((child.is_dir(), str(child.relative_to(root_dir / str(user_id)))))

    return cd_paths


def make_dirs(user_id, cloud_dir_path):
    base_dir = root_dir / str(user_id)
    path_valid, path_exists, rel_path_str = path_check(user_id, cloud_dir_path)
    path_obj = base_dir / rel_path_str
    if not path_valid or path_exists:
        return False
    path_obj.mkdir(parents=True)
    return True


def delete_file(user_id, cloud_file_path, backup=False):
    global args
    path_valid, path_exists, rel_path_str = path_check(user_id, cloud_file_path, backup=backup)
    if not path_valid or not path_exists:
        return False
    if backup:
        path_obj = (root_dir / (str(user_id) + '_backup') / rel_path_str).resolve()
    else:
        path_obj = (root_dir / str(user_id) / rel_path_str).resolve()
    if path_obj.is_file():
        os.remove(str(path_obj))
    else:
        return False
    if not backup:
        with ServerProxy(name_server_url, allow_none=True) as name_proxy:
            addresses = name_proxy.get_file_backup_servers(args.server_id, user_id, rel_path_str)
        for address in addresses:
            with ServerProxy(address, allow_none=True) as file_server_proxy:
                if not file_server_proxy.delete_file(user_id, cloud_file_path, True):
                    return False
        with ServerProxy(name_server_url, allow_none=True) as name_proxy:
            if not name_proxy.remove_file(user_id, rel_path_str):
                return False
    return True


def upload_file(user_id, file_bin, cloud_dir_path, filename, backup=False):
    global args
    path_valid, path_exists, rel_path_str = path_check(user_id, cloud_dir_path)

    if not path_valid:
        return False

    if backup:
        path_obj = (root_dir / (str(user_id) + '_backup') / rel_path_str).resolve()

        if not path_obj.exists():
            path_obj.mkdir(parents=True)

        path_obj = (path_obj / filename).resolve()
    else:
        if not path_exists:
            return False

        path_obj = (root_dir / str(user_id) / rel_path_str / filename).resolve()

    with open(str(path_obj), 'wb') as handle:
        handle.write(file_bin.data)

    if not backup:
        with ServerProxy(name_server_url, allow_none=True) as name_proxy:
            address = name_proxy.get_next_server()

        if address == '':
            return False

        with ServerProxy(address, allow_none=True) as file_server_proxy:
            if not file_server_proxy.upload_file(user_id, file_bin, cloud_dir_path, filename, True):
                return False

    with ServerProxy(name_server_url, allow_none=True) as name_proxy:
        saved = name_proxy.save_file_info([generate_file_info(args.server_id, str(path_obj), filename)])

    return saved


def fetch_file(user_id, cloud_file_path, backup=False, backup_ord=0):
    path_valid, path_exists, rel_path_str = path_check(user_id, cloud_file_path)
    if not path_valid or not path_exists:
        return False, None

    if backup:
        path_obj = (root_dir / (str(user_id) + '_backup') / rel_path_str).resolve()
    else:
        path_obj = (root_dir / str(user_id) / rel_path_str).resolve()

    if not path_obj.is_file():
        return False, None

    with ServerProxy(name_server_url, allow_none=True) as name_proxy:
        hash_info = name_proxy.get_file_hashes(user_id, rel_path_str)

    own_hash_matches, code = check_file_hash(user_id, cloud_file_path, hash_info[backup_ord][0])

    if own_hash_matches:
        return True, get_file_binary(str(path_obj))
    else:
        for i in range(1, len(hash_info)):
            file_hash, address = hash_info[i]
            with ServerProxy(address, allow_none=True) as file_server_proxy:
                success, binary = file_server_proxy.fetch_file(user_id, cloud_file_path, True, i)

                if success:
                    return True, binary

        return False, None


def delete_empty_dir(user_id, cloud_dir_path):
    path_valid, path_exists, rel_path_str = path_check(user_id, cloud_dir_path)
    path_obj = root_dir / str(user_id) / rel_path_str

    if not path_valid or not path_obj.is_dir():
        return False

    if not os.listdir(str(path_obj)):
        path_obj.rmdir()
        return True
    else:
        return False


if __name__ == '__main__':
    root_dir = Path.home() / 'rpc_server_files'

    parser = argparse.ArgumentParser()
    parser.add_argument('server_id', help='ID of the file server.', type=int)
    parser.add_argument('port', help='Port of the file server.', type=int)
    args = parser.parse_args()

    with SimpleXMLRPCServer(('localhost', args.port)) as server:
        server.register_function(path_check)
        server.register_function(check_file_hash)
        server.register_function(get_filenames)
        server.register_function(make_dirs)
        server.register_function(delete_file)
        server.register_function(upload_file)
        server.register_function(fetch_file)
        server.register_function(delete_empty_dir)

        server_url = 'http://{}:{}'.format(server.server_address[0], server.server_address[1])

        server_registered = False
        with ServerProxy(name_server_url, allow_none=True) as proxy:
            server_registered = proxy.register_file_server(args.server_id, server_url)

        if server_registered:
            root_dir = root_dir / str(args.server_id)
            if not root_dir.exists():
                root_dir.mkdir(parents=True)

            print('Initializing server for files in "{}"...'.format(str(root_dir)))

            file_list = []
            for root, dirs, files in os.walk(str(root_dir)):
                for file_name in files:
                    file_path = os.path.join(root, file_name)
                    file_info = generate_file_info(args.server_id, file_path, file_name)

                    if file_info[0] != -1:
                        print('Added file:', file_info)
                        file_list.append(file_info)

            files_registered = False
            with ServerProxy(name_server_url, allow_none=True) as proxy:
                files_registered = proxy.save_file_info(file_list)

            if files_registered:
                print('Serving file server on {}.'.format(server.server_address))
                try:
                    server.serve_forever()
                except KeyboardInterrupt:
                    with ServerProxy(name_server_url, allow_none=True) as proxy:
                        proxy.unregister_file_server(args.server_id)
            else:
                print('Failed file registration.')
        else:
            print('Failed server registration.')
