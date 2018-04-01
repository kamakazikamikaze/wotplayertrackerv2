from hashlib import sha1

BUF_SIZE = 65536


def getsha1(filename):
    sha1hash = sha1()
    with open(filename, 'rb') as f:
        while True:
            data = f.read(BUF_SIZE)
            if not data:
                break
            sha1hash.update(data)
    return sha1hash.hexdigest()
