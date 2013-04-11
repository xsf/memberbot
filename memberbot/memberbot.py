import logging
import threading
import sleekxmpp

from sleekxmpp.jid import JID
from sleekxmpp.xmlstream import ET
from sleekxmpp.exceptions import XMPPError
from sleekxmpp.plugins import BasePlugin, register_plugin
from sleekxmpp.stanza.roster import Roster, RosterItem

import voting
import adhoc_voting
import chat_voting


logging.basicConfig(level=logging.DEBUG,
                    format='%(asctime)s %(levelname)-8s %(message)s')


class MemberBot(sleekxmpp.ClientXMPP):

    def __init__(self, jid, password, ballot):
        super(MemberBot, self).__init__(jid, password)

        self.auto_authorize = None
        self.auto_subscribe = None

        self.xsf_members = set()

        with open('data/xsf_roster.txt') as xsf_roster:
            for jid in xsf_roster:
                jid = jid.strip()
                if jid:
                    self.xsf_members.add(JID(jid))

        self.whitespace_keepalive = True

        self.register_plugin('xep_0012')
        self.register_plugin('xep_0030')
        self.register_plugin('xep_0045')
        self.register_plugin('xep_0050')
        self.register_plugin('xep_0054')
        self.register_plugin('xep_0084')
        self.register_plugin('xep_0085')
        self.register_plugin('xep_0092')
        self.register_plugin('xep_0106')
        self.register_plugin('xep_0107')
        self.register_plugin('xep_0108')
        self.register_plugin('xep_0115')
        self.register_plugin('xep_0153')
        self.register_plugin('xep_0172')
        self.register_plugin('xep_0184')
        self.register_plugin('xep_0198')
        self.register_plugin('xep_0199', {'keepalive': True})
        self.register_plugin('xep_0202')
        self.register_plugin('xep_0221')
        self.register_plugin('xep_0231')
        self.register_plugin('xep_0308')

        self['xep_0092'].software_name = 'XSF Memberbot'
        self['xep_0092'].version = '2.0'

        self.add_event_handler('session_start', self.session_start)
        #self.add_event_handler('message', self.echo)
        self.add_event_handler('roster_subscription_request',
                self.roster_subscription_request)

        #self.plugin.enable('xsf_roster')
        self.plugin.enable('xsf_voting')
        #self.plugin.enable('xsf_voting_adhoc')
        self.plugin.enable('xsf_voting_chat')

        self['xsf_voting'].load_ballot(ballot)

    def session_start(self, event):
        self.get_roster()
        self.send_presence()

        self['xep_0012'].set_last_activity(seconds=0)
        self['xep_0172'].publish_nick('XSF Memberbot')
        self['xep_0108'].publish_activity('working')
        self['xep_0107'].publish_mood('excited')

        vcard = self['xep_0054'].stanza.VCardTemp()
        vcard['FN'] = 'XSF Memberbot'
        vcard['NICKNAME'] = 'XSF Memberbot'
        vcard['JABBERID'] = self.boundjid.bare
        vcard['ORG']['ORGNAME'] = 'XMPP Standards Foundation'
        vcard['URL'] = 'http://xmpp.org/about-xmpp/xsf/xsf-voting-procedure/'
        vcard['DESC'] = (
           "Most XSF members vote via proxy rather than attending the "
           "scheduled meetings. This makes life much easier for all "
           "concerned. The proxy voting happens by chatting with "
           "MemberBot. MemberBot's roster is maintained by the Secretary "
           "of the XSF so that only XSF members are allowed to chat "
           "with the bot.\n\n"
           "XSF members can begin the voting process by sending a random "
           "message to MemberBot (e.g., 'hello'). The bot will then send "
           "you a series of questions about the current topics, asking "
           "you to vote yes or no to each one."
        )
        self['xep_0054'].publish_vcard(vcard)

        avatar_data = None
        self.avatar_cid = ''
        with open('data/xmpp.png', 'rb') as avatar_file:
            avatar_data = avatar_file.read()
        if avatar_data:
            avatar_id = self['xep_0084'].generate_id(avatar_data)
            info = {
                'id': avatar_id,
                'type': 'image/png',
                'bytes': len(avatar_data)
            }
            self['xep_0084'].publish_avatar(avatar_data)
            self['xep_0084'].publish_avatar_metadata(items=[info])
            self['xep_0153'].set_avatar(avatar=avatar_data, mtype='image/png')
            self.avatar_cid = self['xep_0231'].set_bob(avatar_data, 'image/png')

    def roster_subscription_request(self, pres):
        if pres['from'].bare in self.xsf_members:
            self.send_presence(pto=pres['from'], ptype='subscribed')
            if self.client_roster[pres['from']]['subscription'] != 'both':
                self.send_presence(pto=pres['from'], ptype='subscribe')
            self.client_roster.send_last_presence()
        else:
            self.send_presence(pto=pres['from'], ptype='unsubscribed')


m = MemberBot('memberbot@lance.im/Voting', 'secret', 'sample')
m.connect()
m.process(block=True)
