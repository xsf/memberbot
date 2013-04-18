import json
import redis
import os

from sleekxmpp.xmlstream import ET, ElementBase, register_stanza_plugin
from sleekxmpp.plugins import BasePlugin, register_plugin


class Ballot(ElementBase):
    name = 'ballot'
    namespace = 'http://xmpp.org/protocol/xsf'
    plugin_attrib = name
    interfaces = set(['date'])
    sub_interfaces = interfaces


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


class XSFVoting(BasePlugin):
    name = 'xsf_voting'
    description = 'XSF: Proxy voting'
    dependencies = set()
    default_config = {
        'redis_host': 'localhost',
        'redis_port': 6379,
        'redis_db': 0,
        'key_prefix': 'xsf:memberbot',
        'current_ballot': '',
        'data_dir': 'data',
    }

    def plugin_init(self):
        self.redis = redis.Redis(self.redis_host, self.redis_port, self.redis_db)
        self._ballot_data = None

    def load_ballot(self, name):
        self.current_ballot = name
        with open('%s/ballot_%s.xml' % (self.data_dir, name)) as ballot_file:
            self._ballot_data = Ballot(xml=ET.fromstring(ballot_file.read()))
        try:
            os.makedirs('%s/results/%s' % (self.data_dir, name))
        except:
            pass

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

        # HACK: Make this just work for member election with the old format
        session = self.get_session(jid)
        membervotes = session['votes']['XSF Membership']
        with open('%s/results/%s/%s.xml' % (self.data_dir, self.current_ballot, jid.bare), 'w+') as result:
            result.write('<?xml version="1.0"?>')
            result.write('<respondent jid="%s">' % jid.bare)
            for i, item in enumerate(self._ballot_data['section']['items']):
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


register_plugin(XSFVoting)
