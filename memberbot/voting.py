import json
import redis

from sleekxmpp.plugins import BasePlugin, register_plugin


class XSFVoting(BasePlugin):
    name = 'xsf_voting'
    description = 'XSF: Proxy voting'
    dependencies = set()
    default_config = {
        'redis_host': 'localhost',
        'redis_port': 6379,
        'redis_db': 0,
        'key_prefix': 'xsf:memberbot'
    }

    def plugin_init(self):
        self.redis = redis.Redis(self.redis_host, self.redis_port, self.redis_db)
        self.current_ballot = '2013_Q1'

    def get_ballot(self):
        return {
            'date': '2013-02-01',
            'sections': [
                {
                    'title': 'XSF Membership',
                    'limit': '',
                    'items': [
                        {
                            'jid': 'lance@lance.im',
                            'name': 'Lance Stout',
                            'url': 'http://wiki.xmpp.org/Application_2013_Lance_Stout'
                        },
                        {
                            'jid': 'stpeter@stpeter.im',
                            'name': 'Peter Saint-Andre',
                            'url': 'http://wiki.xmpp.org/Application_2013_Peter_Saint-Andre'
                        }
                    ]
                }, {
                    'title': 'Council',
                    'limit': 2,
                    'items': [
                        {
                            'jid': 'lance@example.com',
                            'name': 'Lance Stout',
                            'url': 'http://wiki.xmpp.org/Application_2013_Lance_Stout'
                        },
                        {
                            'jid': 'stpeter@example.com',
                            'name': 'Peter Saint-Andre',
                            'url': 'http://wiki.xmpp.org/Application_2013_Peter_Saint-Andre'
                        },
                        {
                            'jid': 'bear@example.com',
                            'name': 'Mike Taylor (bear)',
                            'url': 'http://wiki.xmpp.org/Application_2013_Mike_Taylor'
                        },
                        {
                            'jid': 'mattj@example.com',
                            'name': 'Matthew Wild',
                            'url': 'dkjflsdjfsldj'
                        }
                    ]
                },
            ]
        }

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
