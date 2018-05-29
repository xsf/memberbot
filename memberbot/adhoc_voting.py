import random
from collections import deque

from slixmpp.plugins import BasePlugin, register_plugin


class XSFVotingAdhoc(BasePlugin):
    name = 'xsf_voting_adhoc'
    description = 'XSF: Proxy voting plugin via Adhoc Commands'
    dependencies = set(['xep_0004', 'xep_0050', 'xsf_voting'])

    def session_bind(self, event):
        ballot = self.xmpp['xsf_voting'].get_ballot()
        for section in ballot['sections']:
            self.xmpp['xep_0050'].add_command(node=section['title'],
                                              name=section['title'],
                                              handler=self._start_voting)

    def _start_voting(self, iq, session):
        if iq['from'].bare not in self.xmpp.xsf_members:
            self.xmpp['xep_0050'].terminate_command(session)
            raise XMPPError('forbidden')

        ballot = self.xmpp['xsf_voting'].get_ballot()
        existing_voting_session = self.xmpp['xsf_voting'].get_session(iq['from'])

        form = self.xmpp['xep_0004'].stanza.Form()
        form['type'] = 'form'
        form['title'] = 'XSF Elections: %s' % iq['command']['node']
        form['instructions'] = ('By proceeding, you affirm that you wish to have your '
                                'vote count as a proxy vote in the official meeting to '
                                'be held on %s' % ballot['date'])
        session['ballot'] = ballot
        for section in ballot['sections']:
            if section['title'] == iq['command']['node']:
                session['ballot_section'] = section
                break
        session['payload'] = form
        session['has_next'] = True
        if session['ballot_section']['limit']:
            session['next'] = self._handle_limited_voting
        else:
            session['next'] = self._handle_voting
        return session

    def _handle_voting(self, iq, session):
        voting_session = self.xmpp['xsf_voting'].start_voting(session['from'])
        section = session['ballot_section']

        form = self.xmpp['xep_0004'].stanza.Form()
        form['type'] = 'form'
        form['title'] = 'XSF Election: %s' % section['title']
        form['instructions'] = 'Select the applicants you approve for XSF membership.'

        random.shuffle(section['items'])

        form.add_field(var='members',
                ftype='list-multi',
                label='Approved Members')
        for item in section['items']:
            form.field['members'].add_option(value=item['name'])

        session['payload'] = form
        session['next'] = self._handle_voting
        return session

    def _handle_limited_voting(self, iq, session):
        voting_session = self.xmpp['xsf_voting'].start_voting(session['from'])
        section = session['ballot_section']

        form = self.xmpp['xep_0004'].stanza.Form()
        form['type'] = 'form'
        form['title'] = 'XSF Election: %s' % section['title']
        form['instructions'] = 'Select the applicants you approve for %s.' % section['title']

        random.shuffle(section['items'])
        items = deque(section['items'])

        for i in range(0, int(section['limit'])):
            form.add_field(var='choice-%s' % i,
                    ftype='list-single',
                    label='Seat %s' % str(i+1))
            for item in items:
                form.field['choice-%s' % i].add_option(value=item['name'])
            items.rotate(1)

        session['payload'] = form
        session['next'] = self._handle_limited_voting
        return session



register_plugin(XSFVotingAdhoc)
