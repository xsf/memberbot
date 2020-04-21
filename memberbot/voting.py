import json
import os

from slixmpp.xmlstream import ET, ElementBase, register_stanza_plugin
from slixmpp.plugins import BasePlugin, register_plugin


class Ballot(ElementBase):
    name = 'ballot'
    namespace = 'http://xmpp.org/protocol/xsf'
    plugin_attrib = name
    interfaces = set(['date'])
    sub_interfaces = interfaces

    def findSection(self, title):
        for section in self['sections']:
            if section['title'] == title:
                return section


class BallotSection(ElementBase):
    name = 'section'
    namespace = 'http://xmpp.org/protocol/xsf'
    plugin_attrib = name
    plugin_multi_attrib = 'sections'
    interfaces = set(['title', 'limit'])


class BallotItem(ElementBase):
    name = 'item'
    namespace = 'http://xmpp.org/protocol/xsf'
    plugin_attrib = name
    plugin_multi_attrib = 'items'
    interfaces = set(['jid', 'name', 'url'])


register_stanza_plugin(Ballot, BallotSection, iterable=True)
register_stanza_plugin(BallotSection, BallotItem, iterable=True)


import sys
class Redis:
    def __init__(self):
        self.data = {}
    def scard(self, myhash):
        print('scard', myhash, file=sys.stderr)
        if myhash not in self.data:
            return 0
        return len(self.data[myhash])
    def hgetall(self, myhash):
        print('hgetall', myhash, file=sys.stderr)
        if myhash not in self.data:
            return None
        return self.data[myhash]
    def hset(self, myhash, field, value):
        print('hset', myhash, field, value, file=sys.stderr)
        thing = self.data.setdefault(myhash, {})
        ret = int(field not in thing)
        thing[field] = value
        return ret
    def sadd(self, myhash, *members):
        print('sadd', myhash, file=sys.stderr)
        thing = self.data.setdefault(myhash, set())
        thing.add(members)
        return 1

class XSFVoting(BasePlugin):
    name = 'xsf_voting'
    description = 'XSF: Proxy voting'
    dependencies = set()
    default_config = {
        'key_prefix': 'xsf:memberbot',
        'current_ballot': '',
        'data_dir': 'data',
    }

    def plugin_init(self):
        self.redis = Redis()
        self._ballot_data = None

    def load_ballot(self, name, quorum):
        self.quorum = quorum
        self.current_ballot = name

        with open('%s/ballot_%s.xml' % (self.data_dir, name)) as ballot_file:
            self._ballot_data = Ballot(xml=ET.fromstring(ballot_file.read()))
        try:
            os.makedirs('%s/results/%s' % (self.data_dir, name))
        except:
            pass

    def has_quorum(self):
        return self.redis.scard('%s:voters:%s' % (self.key_prefix, self.current_ballot)) >= self.quorum

    def get_ballot(self):
        return self._ballot_data

    def get_session(self, jid):
        session = self.redis.hgetall('%s:session:%s:%s' % (self.key_prefix, self.current_ballot, jid.bare))
        if not session:
            session = {'status': '', 'votes': '{}', 'fulfilled': '{}'}
        session['votes'] = json.loads(session['votes'])
        session['fulfilled'] = json.loads(session['fulfilled'])
        return session

    def start_voting(self, jid):
        self.redis.hset('%s:session:%s:%s' % (self.key_prefix, self.current_ballot, jid.bare), 'status', 'started')
        ballot = self.get_ballot()
        votes = {}
        fulfilled = {}
        for section in ballot['sections']:
            votes[section['title']] = {}
            fulfilled[section['title']] = 0
        self.redis.hset('%s:session:%s:%s' % (self.key_prefix, self.current_ballot, jid.bare), 'votes', json.dumps(votes))
        self.redis.hset('%s:session:%s:%s' % (self.key_prefix, self.current_ballot, jid.bare), 'fulfilled', json.dumps(fulfilled))
        return self.get_session(jid)

    def restart_voting(self, jid):
        self.redis.hset('%s:session:%s:%s' % (self.key_prefix, self.current_ballot, jid.bare), 'status', 'started')
        return self.get_session(jid)

    def end_voting(self, jid):
        self.redis.hset('%s:session:%s:%s' % (self.key_prefix, self.current_ballot, jid.bare), 'status', 'completed')

        pre_quorum = self.has_quorum()
        self.redis.sadd('%s:voters:%s' % (self.key_prefix, self.current_ballot), jid)
        if not pre_quorum and self.has_quorum():
            self.xmpp.event('quorum_reached')

        # HACK: Make this just work with the old format. We will adjust this later once the tallying stuff is updated.
        session = self.get_session(jid)
        with open('%s/results/%s/%s.xml' % (self.data_dir, self.current_ballot, jid.bare), 'w+') as result:
            result.write('<?xml version="1.0"?>')
            result.write('<respondent jid="%s">' % jid.bare)
            for section in session['votes']:
                membervotes = session['votes'][section]
                print(json.dumps(membervotes))
                if section == 'Board':
                    yesvotes = set()
                    for position, name in membervotes.items():
                        yesvotes.add(name)
                    result.write('<board>')
                    for item in self._ballot_data.findSection(section)['items']:
                        vote = 'yes' if item['name'] in yesvotes else 'no'
                        result.write('<item name="%s">%s</item>' % (item['name'], vote))
                    result.write('</board>')
                elif section == 'Council':
                    yesvotes = set()
                    for position, name in membervotes.items():
                        yesvotes.add(name)
                    result.write('<council>')
                    for item in self._ballot_data.findSection(section)['items']:
                        vote = 'yes' if item['name'] in yesvotes else 'no'
                        result.write('<item name="%s">%s</item>' % (item['name'], vote))
                    result.write('</council>')
                elif section == 'XSF Membership':
                    for i, item in enumerate(self._ballot_data.findSection(section)['items']):
                        vote = membervotes[item['name']]
                        result.write('<!-- %s -->' % item['name'])
                        result.write('<answer%s>%s</answer%s>' % (i, vote, i))
                else:
                    for i, item in enumerate(self._ballot_data.findSection(section)['items']):
                        vote = membervotes[item['name']]
                        result.write('<!-- %s -->' % item['name'])
                        result.write('<answer%s>%s</answer%s>' % (i, vote, i))

            result.write('</respondent>')

    def record_vote(self, jid, section, item, answer):
        session = self.get_session(jid)
        votes = session['votes']
        votes[section][item] = answer
        fulfilled = session['fulfilled']
        fulfilled[section] = sum([1 for (name, vote) in votes[section].items() if vote == 'yes'])
        self.redis.hset('%s:session:%s:%s' % (self.key_prefix, self.current_ballot, jid.bare), 'votes', json.dumps(votes))
        self.redis.hset('%s:session:%s:%s' % (self.key_prefix, self.current_ballot, jid.bare), 'fulfilled', json.dumps(fulfilled))
        return self.get_session(jid)

    def abstain_vote(self, jid, section, item):
        session = self.get_session(jid)
        votes = session['votes']
        if item in votes[section]:
            del votes[section][item]
        fulfilled = session['fulfilled']
        fulfilled[section] = sum([1 for (name, vote) in votes[section].items() if vote == 'yes'])
        self.redis.hset('%s:session:%s:%s' % (self.key_prefix, self.current_ballot, jid.bare), 'votes', json.dumps(votes))
        self.redis.hset('%s:session:%s:%s' % (self.key_prefix, self.current_ballot, jid.bare), 'fulfilled', json.dumps(fulfilled))
        return self.get_session(jid)


register_plugin(XSFVoting)
