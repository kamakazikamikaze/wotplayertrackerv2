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

One server acts as the brain. Using MariaDB/MySQL, it prepares and tracks the
work of all nodes. It distributes script updates, stores collected statistics,
and allows people to view progress. It doesn't matter if there is just one node
or one hundred. It can scale to whatever level it needs to in order to support
however many people wish to help.

Nodes interact with Wargaming's database. Utilizing Wargaming's Client API Key
model, each node can query the database up to 10 times per second. With up to
100 players per request, each Node can potentially pull hundreds of thousands
of entries each hour. They simply forward the information on to the Tracker
server for storage.

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

How can I trust you?
====================

The original programmer (OP) is a software developer with networking experience
who is also a security-minded sysadmin. Here's his simple response:

"You can't."

Seriously. You're running open-source code that's being published by someone
who you don't personally know and probably can't be held legally responsible
for you running their code on your workstation.

That's why we're going to be as transparent as possible with our code.

What does the script collect from my machine?
---------------------------------------------

There are only two items that we need to gather:

1. Your IP - This is to track work done per Node
2. Your OS - This is to ensure that the proper script is passed for updates

We wish to emphasize the fact that despite gathering this, your IP is **not**
saved anywhere nor shared with anyone. If we share any statistics for tracking
progress, your IP is masked by generating a UUID and using that for **all**
pages.

Your OS is needed in order to determine what line endings are needed for the
script to run properly on your operating system. If you are not familiar with
line endings, please Google "Linux vs Windows line endings"

How are updates delivered?
--------------------------

Communications between the server and client will be encrypted over SSL.

At the start of each run, the starter script is invoked. This script checks
several items:

1. Can I contact the server? If so,
2. Send my current file version and OS. If the server tells me to update,
3. Download the update. Once confirmed,
4. Proceed with data polling

Your OS is used to determine what line-ending style to use. A SHA1 hash of the
polling script is created and sent to the server. If the server's file hash is
different, it is assumed that the polling script has been updated and needs to
be pushed out. The starter script retrieves this file and overwrites the
existing poller script.

Can you control my machine?
---------------------------

No. In fact, we encourage that you run this script with as minimal permissions
as possible. While we do not include any code that would be able to manipulate
your machine, you should still do your due diligence and compartmentalize the
script as much as possible. The setup script will (hopefully) create a new,
temporary user that you can remove when you wish to take the script off your
system.
