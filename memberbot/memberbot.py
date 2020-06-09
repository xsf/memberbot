#!/usr/bin/env python3
import logging
import getpass
import math
import slixmpp

from optparse import OptionParser

# from slixmpp.jid import JID
# from slixmpp.xmlstream import ET
# from slixmpp.exceptions import XMPPError
# from slixmpp.plugins import BasePlugin, register_plugin
# from slixmpp.stanza.roster import Roster, RosterItem

import xsf_roster
import voting
import adhoc_voting
import chat_voting

logging.basicConfig(level=logging.DEBUG,
                    format='%(asctime)s %(levelname)-8s %(message)s')


class MemberBot(slixmpp.ClientXMPP):

    def __init__(self, jid, password, ballot):
        super(MemberBot, self).__init__(jid, password)

        self.auto_authorize = None
        self.auto_subscribe = None

        self.whitespace_keepalive = True

        self.register_plugin('xep_0012')
        self.register_plugin('xep_0030')
        self.register_plugin('xep_0045')
        self.register_plugin('xep_0050')
        self.register_plugin('xep_0054')
        self.register_plugin('xep_0071')
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
        self.add_event_handler('roster_subscription_request',
                               self.roster_subscription_request)
        self.add_event_handler('quorum_reached', self.quorum_reached)

        self.plugin.enable('xsf_roster')
        self.plugin.enable('xsf_voting')
        # self.plugin.enable('xsf_voting_adhoc')
        self.plugin.enable('xsf_voting_chat')

        quorum = math.ceil(len(self['xsf_roster'].get_members()) / 3)
        self['xsf_voting'].load_ballot(ballot, quorum)

    def session_start(self, event):
        self.get_roster()
        self.send_presence(ppriority='100')

        self['xep_0012'].set_last_activity(seconds=0)
        self['xep_0172'].publish_nick('XSF Memberbot')
        self['xep_0108'].publish_activity('working')

        if self['xsf_voting'].has_quorum():
            self['xep_0107'].publish_mood('happy')
        else:
            self['xep_0107'].publish_mood('serious')

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
        if self['xsf_roster'].is_member(pres['from']):
            self.send_presence(pto=pres['from'], ptype='subscribed')
            if self.client_roster[pres['from']]['subscription'] != 'both':
                self.send_presence(pto=pres['from'], ptype='subscribe')
            self.client_roster.send_last_presence()
        else:
            self.send_presence(pto=pres['from'], ptype='unsubscribed')

    def quorum_reached(self, event):
        self['xep_0107'].publish_mood('happy')


if __name__ == '__main__':
    # Setup the command line arguments.
    optp = OptionParser()

    # Output verbosity options.
    optp.add_option('-q', '--quiet', help='set logging to ERROR',
                    action='store_const', dest='loglevel',
                    const=logging.ERROR, default=logging.INFO)
    optp.add_option('-d', '--debug', help='set logging to DEBUG',
                    action='store_const', dest='loglevel',
                    const=logging.DEBUG, default=logging.INFO)
    optp.add_option('-v', '--verbose', help='set logging to COMM',
                    action='store_const', dest='loglevel',
                    const=5, default=logging.INFO)

    # JID and password options.
    optp.add_option("-j", "--jid", dest="jid",
                    help="JID to use")
    optp.add_option("-p", "--password", dest="password",
                    help="password to use")
    optp.add_option("-b", "--ballot", dest="ballot",
                    help="name of the ballot")

    opts, args = optp.parse_args()

    # Setup logging.
    logging.basicConfig(level=opts.loglevel,
                        format='%(levelname)-8s %(message)s')

    if opts.jid is None:
        opts.jid = input("Username: ")
    if opts.password is None:
        opts.password = getpass.getpass("Password: ")
    if opts.ballot is None:
        opts.ballot = input("Ballot: ")

    bot = MemberBot(opts.jid, opts.password, opts.ballot)
    bot.connect()
    bot.process(forever=True)
