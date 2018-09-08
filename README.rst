=====================================
WoT Console: Player Battle Tracker v2
=====================================

*100% Arty-free. Guaranteed*

About
=====

First there was the WoT Console Player battle counter. An effort to make a
database that counted how many players were active and to what degree. It was
simple, cheap, and effecient.

Now we're rebooting the project, but this time we're enlisting help from the
community. Instead of having just one server poll for data, we're distributing
the work.

How it works
============

One server acts as the brain. Using PostgreSQL, it prepares and tracks the
work of all nodes. It distributes script updates, stores collected statistics,
and allows people to view progress. It doesn't matter if there is just one node
or one hundred. It can scale to whatever level it needs to in order to support
however many people wish to help.

Nodes interact with Wargaming's database. The server provides the API key
required to authorize access and distributes the player IDs that they need to
query. The results are then forwarded to the Tracker server for processing.

Nodes can pull updates from the server each time they start up. This allows a
contributor to simply install the script, ensure it runs properly at least once
and then promptly forget it. No need to check for updates in code, no need to
keep an eye out for announcement emails.

How can I run it?
=================

The goal of the project is to allow the script to run on any operating system:
Linux, MacOS, or Windows. Scripts to run for setting up code directories,
scheduled tasks, and checking for port connectivity will (hopefully) be
provided. Instructions for setting up Python, Pip, and Virtual environments are
planned.

All that is necessary is the operating system, Python, and a network connection
that you don't mind being used. While you can install this on your own personal
workstation, we advise not to for the reason that the script *may* use enough
CPU to cut into important tasks (video watching, gaming, Microsoft Word, etc.)
and may have a noticable performance impact. While we will try to minimize the
noticable impact as much as possible, we do want to remind you that this is
intended to run in a manner to finish the work as fast as possible.

Do you have a live example?
===========================

A public-facing server is available at https://tanks.kamikaze.codes. Please
note that you need the following to login in:

* User: `guest`
* Pass: `wargaming`

Please do not abuse the account by changing the password. This is shared by
everyone in the community.

How can I help?
===============

If you'd like to volunteer some processing power, send an email to
wotbattletracker@gmail.com.

If you'd like to contribute to the ElasticSearch/Kibana service, please
consider leaving a donation. All contributions go towards costs of the Elastic
Cloud service.

.. image:: https://www.paypalobjects.com/en_US/i/btn/btn_donateCC_LG.gif
   :target: https://www.paypal.com/cgi-bin/webscr?cmd=_s-xclick&hosted_button_id=RNZ669CEAQCJY
