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

How powerful does the server need to be?
========================================

From experience, it is possible to run the server and database on a host with
4 processors (no hyperthreading) and 8 GB of RAM without issue. However, some
settings may need to be changed in order to prevent the server from crashing
due to a consumption of memory from results waiting to be sent to the database.

When you run the server-side of this project, please set the following flags:

============== =========
CPUs available ``-a`` 
============== =========
1              10
2              5
4+             Don't set
============== =========

If you use multiple querying clients to collect data, you will need to be able
to scale the server as well. If you are stuck with a limited number of
resources, you can use the ``-a`` flag and increase the number of helpers per
process spawned. If you have a different server for your database, you can also
increase the number of processes using the ``-p`` flag (defaults to number of
physical cores + virtual cores - 1), though I would increase both of these
incrementally.

Do you have a live example?
===========================

Unfortunately not. Previously, a live instance was running with data being sent
to ElasticSearch for all to view. Funding for that ceased after a few months
when cost had to come out of pocket. I am instead considering creating a
Twitter bot to post daily analysis where all can view it.

How can I help?
===============

If you'd like to volunteer some processing power, send an email to
wotbattletracker@gmail.com.

If you'd like to donate for the time I've put into this project, feel free to
leave any amount at the following PayPal link.

.. image:: https://www.paypalobjects.com/en_US/i/btn/btn_donateCC_LG.gif
   :target: https://www.paypal.com/cgi-bin/webscr?cmd=_s-xclick&hosted_button_id=RNZ669CEAQCJY
