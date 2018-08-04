import json
from tornado import ioloop, websocket
from tornado.escape import json_decode, json_encode
from tornado.httpclient import AsyncHTTPClient
from tornado.queues import Queue
# TODO: Add async capability to wotconsole, limiting to Python 3.5+, using aiohttp
from wotconsole import player_data, WOTXResponseError


class TrackerClientNode:
	# The API limits the number of requests per IP. Unless we develop a
	# solution for clients with multiple public IP addresses, which is
	# unlikely, we'll bind this to the class to share the work queue
	workqueue = Queue()

	def __init__(self, config):
		self.server = config['server']
		self.throttle = config['throttle']
		self.key = config['application_id']

	def query(self):
		pass

	def send_results(self, result):
		self.conn.send_message(json_encode(result))

	def connect(self):
		self.conn = await tornado.websocket.websocket_connect(self.server + '/wswork')
		status = await self.conn.read_message()
		if '{' in status:
			TrackerClientNode.workqueue.put_nowait(json_decode(status))
		else:
			# TODO: Handle wait instructions
			pass

	def start(self):
		# Query the API no more than $throttle times per second
		ioloop.PeriodicCallback(self.query, self.throttle)
		ioloop.IOLoop.current().start()