#!/usr/bin/env python3

import argparse
import codecs
import datetime
import logging
import os
import re
import time
import sys
import platform
import unicodedata
import email.message
import sqlite3
import mailbox


__author__ = "Nicolas SAPA"
__credits__ = ["Nicolas SAPA", "Authors of https://github.com/IgnoredAmbience/yahoo-group-archiver"]
__license__ = "CECILL-2.1"
__version__ = "0.2"
__maintainer__ = "Nicolas SAPA"
__email__ = "nico@byme.at"
__status__ = "Alpha"

def return_pseudomail(person):
    value = str(person[2])
    value = unicodedata.normalize('NFKD', value).encode('ascii', 'ignore').decode('ascii')
    value = re.sub(r'[^\w\s.-@]', '', value).strip().strip('.')
    value = re.sub(r'[-\s]+', '_', value)
    if len(value.split('@')) == 1:
        value = value + '_uid' + str(person[0]) + '@yahoogroups.invalid'
    return value

def group2mbox(group_info,persons):
    logger = logging.getLogger(name="group2mbox")
    group_name = group_info[1]
    count_messages = conn.execute('SELECT id FROM group_message WHERE discussion_group = ? ORDER BY topic_id',(group_info[0],))
    count_messages = count_messages.fetchall()
    logger.info('Found %i message(s) in group %s', len(count_messages), group_name)


    # Creating the first mbox file
    try:
        mbox = mailbox.mbox(group_name+'.mbox', create=True)
    except:
        logger.error('Failed to create mbox for group %s', group_name)
        return False
    logger.debug('Created mbox file %s', group_name+'.mbox')
    try:
        mbox.lock()
        current_mbox_number = 0
        messages_done = 0
    except:
        logger.error("Cannot lock the mbox, did this script crash during a conversion? If so delete the .lock file and retry")
        return False

    for id_to_get in count_messages:
        # Get the content of the message
        id_to_get = id_to_get[0]
        ymessages = conn.execute('SELECT id,number,date,subject,content,person,topic_id,parent_id FROM group_message WHERE discussion_group = ? AND id = ? ORDER BY topic_id',(group_info[0],id_to_get))
        ymessages = ymessages.fetchall()

        # Sanity check
        if len(ymessages) != 1:
            # Should never happen!
            logger.error("Trying to get content of message %s but got %i values! Database probably corrupted.",id_to_get,len(ymessages))
            return False
        ymessage = ymessages[0]
        del ymessages

        # Let's parse create the message object
        mail = email.message.EmailMessage()
        yfrom = return_pseudomail(persons[ymessage[5]-1])
        ydate = time.strptime(ymessage[2], "%Y-%m-%d %H:%M:%S")
        ydatetime = datetime.datetime.fromtimestamp(time.mktime(ydate))
        ysubject = ymessage[3]
        mail['Subject'] = ysubject
        mail['From'] = persons[ymessage[5]-1][1] + " <" + yfrom + ">"
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
        logger.debug('Created an EmailMessage for message %i; from %s with subject %s on %s', ymessage[1], yfrom, ysubject, ydatetime.strftime("%a, %d %b %Y %H:%M:%S %z"))

        # Do we have an attachment for this message ?
        attachments = conn.execute("SELECT * FROM attachment WHERE message_id = ?",(ymessage[0],)).fetchall()
        logger.debug("Found %i attachment(s) for message_id %i",len(attachments),ymessage[0])
    
        if len(attachments) > 0:
            mail.make_mixed()
            for attachment in attachments:
                attachname = attachment[3]
                attachcontent = attachment[4]
                logger.debug("Attachment id %i: name %s", attachment[0], attachname) 
                mail.add_attachment(attachcontent, maintype='application', subtype='octet-stream', filename=attachname)

        mboxmail = mailbox.mboxMessage(mail)
        del mail

        mboxmail.set_from(yfrom,ydate)
        mbox.add(mboxmail)

        messages_done += 1  

        if(never_flush == False):
            if((messages_done % args.flush_after == 0)):
                mbox.flush()
                logger.info("%s messages converted, flushing mbox to disk",messages_done)
                if(never_split == False):
                    try:                    
                        mbox_size = os.stat(mbox._file.name).st_size
                    except:
                        logging.error("Cannot obtain size of mbox file, something is really wrong here.")
                        return False # Should really never happen       
             
                    logger.info("Current mbox is %s, size %i bytes", os.path.basename(mbox._file.name), mbox_size)
                    if (mbox_size >= (args.max_size * 1024 * 1024)):
                            current_mbox_number += 1
                            new_mbox_name = group_name + '_' + str(current_mbox_number) + '.mbox'
                            mbox.unlock()
                            try:
                                mbox = mailbox.mbox(new_mbox_name, create=True)
                            except:
                                logger.error('Creation of mbox %s failed.', new_mbox_name)
                                return False
                            logger.debug('Switching to new mbox file %s', new_mbox_name)
                            try:
                                mbox.lock()
                            except:
                                logger.error("Cannot lock the mbox %s", new_mbox_name)
                                return False                       
    mbox.flush() 
    mbox.unlock()
   
    return True

def convertpgo():
    logger = logging.getLogger(name="convertpgo")
    version = int(conn.execute("SELECT value FROM options WHERE key = 'database_version'").fetchone()[0])
    logger.debug("This PGO file is version %i",version)

    persons = conn.execute('SELECT id,name,email FROM person ORDER BY id').fetchall()
    logger.debug('Found %i person(s) in this file', len(persons))

    groups = conn.execute('SELECT id,name FROM discussion_group ORDER BY id').fetchall()
    logger.debug('Found %i group(s) in this file', len(groups))

    convert_success = True

    for group in groups:
        if(group2mbox(group,persons)):
            logger.info("Group %s have been successfully converted to mbox.", group[1])
        else:
            convert_success = False

    return convert_success


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

    p.add_argument('--flush-after', type=int, default=500,
		help='Flush to disk after this number of messages. Default is 500, -1 to disable flushing.')

    p.add_argument('--max-size', type=int, default=-1,
		help='Try to keep mbox near this size (in megabytes). Default is unlimited.')

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

    # Sanity checks
    try:
        source_file = os.path.realpath(args.src_file)
    except:
        logging.error("Cannot find %s", args.src_file)
        exit(1)

    if(args.flush_after == 0):
        logging.error("Argument --flush-after cannot be 0")
        exit(1)

    if(args.max_size == 0):
        logging.error("Argument --max-size cannot be 0")
        exit(1)

    never_flush = False
    if(args.flush_after < 0):
        never_flush = True

    never_split = True
    if(args.max_size > 0):
        never_split = False

    if ((never_flush == True) and (never_split == False)):
        logging.error("Incompatible combinaison of --flush-after and --max-size: we check mbox size when we flush to disk") 
        exit(1)

    with Mkchdir(os.path.basename(source_file).replace('.','_'), False):
        log_file_handler = logging.FileHandler('pgo2mbox.log', 'a', 'utf-8')
        log_file_handler.setFormatter(log_formatter)
        root_logger.addHandler(log_file_handler)
        logging.info("pgo2mailbox version %s by %s <%s>",__version__,__author__,__email__)
        logging.info("This %s software is licensed under %s",__status__, __license__)
        logging.info("Running under Python %i.%i.%i on %s %s",sys.version_info.major,sys.version_info.minor,sys.version_info.micro,platform.uname().system,platform.uname().release)
        logging.debug("Python version: %s", sys.version.strip('\n'))

        if ((sys.version_info.major == 3) and (sys.version_info.minor < 7)):
            logging.warn("Please upgrade to at least Python 3.7 because older versions have a known issue!")            

        # Log some config
        if(never_flush):
           logging.debug("Periodic flushing to disk disabled")
        else:
           logging.debug("Flush after every %i message(s)",args.flush_after)

        if(never_split):
           logging.debug("Spliting is disabled")
        else:
           logging.debug("Trying to keep max Mbox size near %i megabyte(s)",args.max_size)

        try:
            conn = sqlite3.connect(source_file)
        except:
            logging.error("Cannot open %s as SQLite database", source_file)
            exit(1)

        logging.info("Connected to the SQLite database %s, starting conversion",source_file)

        if(convertpgo()):
            logging.info("Conversion completed, closing database")
        conn.close()

