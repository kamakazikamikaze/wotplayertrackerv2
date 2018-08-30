from hashlib import sha1
from platform import system
from tornado.escape import json_decode, json_encode
from tornado.httpclient import HTTPClient, HTTPRequest
from urllib.parse import urljoin
from utils import load_config, write_config


def getsha1(filename, buffer_size=65536):
    sha1hash = sha1()
    try:
        with open(filename, 'rb') as f:
            while True:
                data = f.read(buffer_size)
                if not data:
                    break
                sha1hash.update(data)
        return sha1hash.hexdigest()
    except FileNotFoundError:
        return ''


# def download_file(response):
#     with open(response.effective_url.split('/')[-1], 'w') as f:
#        f.write(response.body)

def setup(configpath='./config/client.json'):
    config = load_config(configpath)
    http_client = HTTPClient()
    # async_http_client = AsyncHTTPClient()
    newconfig = json_decode(
        http_client.fetch(
            urljoin(
                config['server'],
                'setup'
            )
        ).body
    )
    if system() == 'Windows':
        plat = 'win'
    else:
        plat = 'nix'
    for filename in newconfig['files']:
        # Get hash
        sha1 = getsha1(filename)
        # Send hash in request
        j = {'os': plat, 'filename': filename, 'hash': sha1}
        req = HTTPRequest(
            urljoin(
                config['server'],
                '/updates'),
            'GET',
            body=json_encode(j),
            allow_nonstandard_methods=True
            # streaming_callback=download_file
        )
        response = http_client.fetch(req)
        if response.code == 200:
            with open(response.effective_url.split('/')[-1], 'wb') as f:
                f.write(response.body)

    del newconfig['files']
    write_config(newconfig, configpath)
    config = newconfig
    http_client.fetch(
        HTTPRequest(
            urljoin(
                config['server'],
                'setup'),
            'POST',
            allow_nonstandard_methods=True))

if __name__ == '__main__':
    from argparse import ArgumentParser
    agp = ArgumentParser()
    agp.add_argument(
        'config',
        help='Client configuration file to use',
        default='./config/client.json')
    args = agp.parse_args()
    setup(args.config)
