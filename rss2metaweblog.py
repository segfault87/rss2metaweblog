#!/usr/bin/env python

# rss2metaweblog
# automatically transfer RSS feeds into other blog with MetaWeblog support.
#
# Copyright (c) 2011 Park "segfault" Joon-Kyu <mastermind@planetmono.org>
#
# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:
#
# The above copyright notice and this permission notice shall be included in
# all copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN
# THE SOFTWARE.

import sys
import time
from datetime import datetime
import signal
import getopt
import feedparser
import xmlrpclib
import json

feedparser.SANITIZE_HTML = 0

guids = {}
weblogs = {}

# logging
def log(category, string):
    print '%s [%s] %s' % (datetime.now().isoformat(' '), category, string)

def logn(string):
    log('NOTIFY ', string)

def logw(string):
    log('WARNING', string)

def loge(string):
    log('ERROR  ', string)

# read configuration from json
def read_config(filename):
    global conf, guids

    try:
        conf = json.loads(open(filename, 'r').read())
    except IOError, e:
        loge('could not open configuration file %s for reading.' % filename)
        return False
    except ValueError, e:
        loge('failed parsing configuration file %s: %s' % (filename, e))
        return False
    
    return True

# initialize xmlrpc connection
def init_weblogs():
    global conf, weblogs

    for i in conf['target']:
        weblogs[i['id']] = xmlrpclib.ServerProxy(i['url'].encode('utf-8'))
        logn('%s: initialized XMLRPC connection %s.' % (i['id'], i['url']))

def read_guids():
    global conf, guids

    try:
        guids = json.loads(open('guids.json', 'r').read())
    except IOError:
        for i in conf['feeds']:
            guids[i['id']] = []

def write_guids():
    global guids

    open('guids.json', 'w').write(json.dumps(guids))

exitflag = False
def inthandler():
    global exitflag
    exitflag = True

# main loop
def do_loop():
    global conf, guids, weblogs, exitflag

    posts = []

    for i in conf['feeds']:
        if exitflag:
            return False

        try:
            feed = feedparser.parse(i['url'])
            cid = i['id']
            
            olist = guids[cid]
            nlist = []
            
            for j in feed.entries:
                # if fetched earlier, skip.
                nlist.append(j.guid)
                if j.guid in olist:
                    break
                
                newpost = {}
                newpost['id'] = i['id']
                newpost['title'] = j.title
                newpost['date'] = j.updated_parsed
                try:
                    newpost['description'] = j.content[0].value
                except:
                    newpost['description'] = j.summary

                if conf['preferences'].has_key('postfix'):
                    newpost['description'] += conf['preferences']['postfix'].replace('{link}', j.link)
                    
                posts.append(newpost)

            guids[cid] = nlist
        except Exception, e:
            loge('malformed RSS: %s' % i['url'])
            continue

    # sort post in particular order
    posts = sorted(posts, key=lambda x: x['date'])

    for i in conf['target']:
        blogid = i['blogid']
        userid = i['userid']
        passwd = i['password']

        for j in posts:
            data = {}

            if exitflag:
                return False

            if conf['category_map'].has_key(i['id']):
                if conf['category_map'][i['id']].has_key(j['id']):
                    data['categories'] = conf['category_map'][i['id']][j['id']]
                        
            data['title'] = j['title']
            data['description'] = j['description']

            try:
                weblogs[i['id']].metaWeblog.newPost(blogid, userid, passwd, data, True)
            except Exception, e:
                loge('failed posting %s into %s: %s' % (j['title'], i['id'], e))
                continue
            
            logn('successfully posted %s into %s' % (j['title'], i['id']))
            
    write_guids()

    return True

def main():
    global conf, guids

    if '--help' in sys.argv or '-h' in sys.argv:
        print 'usage: %s (-c <file>)' % sys.argv[0]
        return 0

    optlist, args = getopt.getopt(sys.argv[1:], 'c:')

    cfn = 'config.json'

    for o, a in optlist:
        if o == '-c':
            cfn = a

    if not read_config(cfn):
        return 1

    if not conf['preferences'].has_key('update_interval'):
        conf['preferences']['update_interval'] = '10m'

    if len(conf['feeds']) + len(conf['twitter']) == 0:
        loge('feed list is empty.')
        return 1

    try:
        interval = int(conf['preferences']['update_interval']) * 60
    except ValueError:
        interval = eval(conf['preferences']['update_interval'].replace('m', '*60+').replace('h', '*3600+').replace('s', '*1+') + '0')

    read_guids()
    init_weblogs()

    if len(weblogs) == 0:
        loge('no available target.')
        return 0

    while True:
        # do not accept keyboard interrupt
        signal.signal(signal.SIGINT, inthandler)
        ret = do_loop()
        signal.signal(signal.SIGINT, signal.default_int_handler)

        if not ret:
            return 1
        
        try:
            time.sleep(interval)
        except KeyboardInterrupt:
            return 0

if __name__ == '__main__':
    sys.exit(main())

