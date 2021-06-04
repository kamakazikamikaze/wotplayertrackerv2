import aiohttp
import asyncio
from hashlib import sha1
from platform import system
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


async def setup(configpath='./config/client.json'):
    config = load_config(configpath)
    async with aiohttp.ClientSession() as http_client:
        async with http_client.get(
            urljoin(config['server'], '/setup')
        ) as response:
            newconfig = await response.json(content_type=None)
        if system() == 'Windows':
            plat = 'win'
        else:
            plat = 'nix'
        for filename in newconfig['files']:
            # Get hash
            sha1 = getsha1(filename)
            # Send hash in request
            j = {'os': plat, 'filename': filename, 'hash': sha1}
            async with http_client.request(
                'GET', urljoin(config['server'], '/updates'), json=j
            ) as response:
                if response.status == 200:
                    with open(str(response.url).split('/')[-1], 'wb') as f:
                        f.write(await response.read())

        del newconfig['files']
        write_config(newconfig, configpath)
        config = newconfig
        async with http_client.post(urljoin(config['server'], '/setup')) as __:
            pass

if __name__ == '__main__':
    from argparse import ArgumentParser
    agp = ArgumentParser()
    agp.add_argument(
        'config',
        help='Client configuration file to use',
        default='./config/client.json')
    args = agp.parse_args()
    loop = asyncio.get_event_loop()
    loop.run_until_complete(setup(args.config))
