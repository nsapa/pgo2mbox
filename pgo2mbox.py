#!/usr/bin/env python3

import argparse
import codecs
import datetime
import json
import logging
import math
import os
import re
import requests.exceptions
import time
import sys
import unicodedata
import email.message
import sqlite3
import mailbox
from email.generator import BytesGenerator
from email import policy

__author__ = "Nicolas SAPA"
__credits__ = ["Nicolas SAPA", "Authors of https://github.com/IgnoredAmbience/yahoo-group-archiver"]
__license__ = "CECILL-2.1"
__version__ = "0.1"
__maintainer__ = "Nicolas SAPA"
__email__ = "nico@byme.at"
__status__ = "Alpha"

def return_pseudomail(person):
    value = str(person[2])
    value = unicodedata.normalize('NFKD', value).encode('ascii', 'ignore').decode('ascii')
    value = re.sub(r'[^\w\s.-@]', '', value).strip().strip('.')
    value = re.sub(r'[-\s]+', '_', value)
    if len(value.split('@')) == 1:
        value = value + '_m' + str(person[0]) + '@yahoogroups.invalid'
    return value

def group2mbox(conn,group_info,mbox,persons):
    logger = logging.getLogger(name="group2mbox")
    ymessages = conn.execute('SELECT id,number,date,subject,content,person,topic_id,parent_id FROM group_message WHERE discussion_group = ? ORDER BY topic_id',(group_info[0],))
    ymessages = ymessages.fetchall()
    logger.info('Found %i messages in group %s', len(ymessages), group_info[1])

    for ymessage in ymessages:
        mail = email.message.EmailMessage()
        yfrom = return_pseudomail(persons[ymessage[5]-1])
        ydate = time.strptime(ymessage[2], "%Y-%m-%d %H:%M:%S")
        ydatetime = datetime.datetime.fromtimestamp(time.mktime(ydate))
        ysubject = ymessage[3]
        logger.debug("Message from %s sent %s subject: %s", yfrom,ydatetime.strftime("%a, %d %b %Y %H:%M:%S %z"),ysubject)
        mail['Subject'] = ymessage[3]
        mail['From'] = persons[ymessage[5]-1][1] + " <" + return_pseudomail(persons[ymessage[5]-1]) + ">"
        # Date: Tue, 18 Feb 2020 15:28:42 +0000
        mail['Date'] = ydatetime.strftime("%a, %d %b %Y %H:%M:%S %z")
        mail['To'] = group_info[1] + "@yahoogroups.invalid"
        mail["Content-Type"] = 'text/html; charset="utf-8"'
        #Message-ID: <9ukpdj+v0gm@eGroups.com>
        #In-Reply-To: <9ukhe1+390p@eGroups.com>
        mail['Message-ID'] = '<' + group_info[1] + '_' + str(ymessage[1]) + '@yahoogroups.invalid>'
        if ymessage[1] != ymessage[6]:
            mail['In-Reply-To'] = '<' + group_info[1] + '_' + str(ymessage[6]) + '@yahoogroups.invalid>'
        mail.set_payload(ymessage[4])

        # Do we have an attachment for this message ?
        attachments = conn.execute("SELECT * FROM attachment WHERE message_id = ?",(ymessage[1],)).fetchall()
        logger.debug("Found %i attachment(s) for message_id %i",len(attachments),ymessage[1])
    
        if len(attachments) > 0:
            mail.make_mixed()
            for attachment in attachments:
                attachname = attachment[3]
                attachcontent = attachment[4]
                logger.debug("Attachment: %s", attachname) 
                mail.add_attachment(attachcontent, maintype='application', subtype='octet-stream', filename=attachname)

        mboxmail = mailbox.mboxMessage(mail)
        mboxmail.set_from(yfrom,ydate)
        mbox.add(mboxmail)    
    
    return None

def convertpgo(conn):
    logger = logging.getLogger(name="convertpgo")
    version = int(conn.execute("SELECT value FROM options WHERE key = 'database_version'").fetchone()[0])
    logger.debug("This PGO file is version %i",version)

    persons = conn.execute('SELECT id,name,email FROM person ORDER BY id').fetchall()
    logger.debug('Found %i person(s) in this file', len(persons))

    groups = conn.execute('SELECT id,name FROM discussion_group ORDER BY id').fetchall()
    logger.debug('Found %i group(s) in this file', len(groups))

    for group in groups:
        group_id = group[0]
        group_name = group[1]
        try:
            group_mailbox = mailbox.mbox(group_name+'.mbox', create=True)
        except:
            logger.error('Failed to create mbox for group %s', group_name)
            continue
        logger.debug('Created mbox file %s', group_name)
        try:
            group_mailbox.lock()
        except:
            logger.error("Cannot lock the mbox, did this script crash during a conversion? If so delete the .lock file and retry")
            continue
        group2mbox(conn,group,group_mailbox,persons)
        group_mailbox.unlock()
        group_mailbox.flush() 

class Mkchdir:
    d = ""

    def __init__(self, d, sanitize=True):
        self.d = sanitise_folder_name(d) if sanitize else d

    def __enter__(self):
        try:
            os.mkdir(self.d)
        except OSError:
            pass
        os.chdir(self.d)

    def __exit__(self, exc_type, exc_value, traceback):
        os.chdir('..')


class CustomFormatter(logging.Formatter):
    def formatTime(self, record, datefmt=None):
        if '%f' in datefmt:
            datefmt = datefmt.replace('%f', '%03d' % record.msecs)
        return logging.Formatter.formatTime(self, record, datefmt)



if __name__ == "__main__":
    p = argparse.ArgumentParser()

    p.add_argument('--verbose', action='store_true',
		help='Enable debug output')

    p.add_argument('src_file', type=str,
		help='Filename of the PGOffline source file')

    args = p.parse_args()

	# Setup logging
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.DEBUG)

    log_format = {'fmt': '%(asctime)s %(levelname)s %(name)s %(message)s', 'datefmt': '%Y-%m-%d %H:%M:%S.%f %Z'}
    log_formatter = CustomFormatter(**log_format)

    log_level = logging.DEBUG if args.verbose else logging.INFO

    log_stdout_handler = logging.StreamHandler(sys.stdout)
    log_stdout_handler.setLevel(log_level)
    log_stdout_handler.setFormatter(log_formatter)
    root_logger.addHandler(log_stdout_handler)

    try:
        source_file = os.path.realpath(args.src_file)
    except:
        logging.error("Cannot find %s", args.src_file)
        exit(1)

    with Mkchdir(os.path.basename(source_file), False):
        log_file_handler = logging.FileHandler('pgo2mbox.log', 'a', 'utf-8')
        log_file_handler.setFormatter(log_formatter)
        root_logger.addHandler(log_file_handler)

        try:
            conn = sqlite3.connect(source_file)
        except:
            logging.error("Cannot open %s as SQLite database", source_file)
            exit(1)

        logging.info("Connected to the SQLite database %s, starting convertion",source_file)
        convertpgo(conn)

        logging.info("Convertion completed, closing database")
        conn.close()

