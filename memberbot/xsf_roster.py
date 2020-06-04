import logging

from slixmpp.exceptions import XMPPError
from slixmpp.jid import JID
from slixmpp.plugins import BasePlugin, register_plugin

log = logging.getLogger(__name__)


class XSFRoster(BasePlugin):
    name = 'xsf_roster'
    description = 'XSF: Member Roster'
    dependencies = set(['xep_0050'])
    default_config = {
        'data_dir': 'data'
    }

    def plugin_init(self):
        self._load_data()

    def _load_data(self):
        _members = set()
        _admins = set()

        with open('%s/xsf_roster.txt' % self.data_dir) as roster:
            for jid in roster:
                jid = jid.strip()
                if jid:
                    _members.add(JID(jid))
        with open('%s/xsf_admins.txt' % self.data_dir) as admins:
            for jid in admins:
                jid = jid.strip()
                if jid:
                    _admins.add(JID(jid))

        self._members = _members
        self._admins = _admins

    def _save_data(self):
        with open('%s/xsf_roster.txt' % self.data_dir, 'w+') as roster:
            for member in self._members:
                roster.write('%s\n' % member.bare)

    def session_bind(self, event):
        self.xmpp['xep_0050'].add_command(
            node='admin:xsf_roster:reload',
            name='Reload XSF Member Roster',
            handler=self._reload)
        self.xmpp['xep_0050'].add_command(
            node='admin:xsf_roster:add-jid',
            name='Add XSF Member JID',
            handler=self._add_jid)
        self.xmpp['xep_0050'].add_command(
            node='admin:xsf_roster:remove-jid',
            name='Remove XSF Member JID',
            handler=self._remove_jid)

        def filtered_items(jid, node, ifrom, data=None):
            try:
                result = self.xmpp['xep_0030'].static.get_items(jid, node, ifrom, data)
                log.debug(result)

                if ifrom.bare not in self._admins:
                    items = result['substanzas']
                    for item in items:
                        if 'admin:' in item['node']:
                            result.xml.remove(item.xml)
            except Exception as e:
                log.debug(e)

            return result

        self.xmpp['xep_0030'].api.register(filtered_items, 'get_items',
                                           jid=self.xmpp.boundjid,
                                           node=self.xmpp['xep_0050'].stanza.Command.namespace)

    def get_members(self):
        return self._members

    def is_member(self, jid):
        return JID(jid).bare in self._members

    def _reload(self, iq, session):
        if iq['from'].bare not in self._admins:
            raise XMPPError('forbidden')

        self._load_data()

        session['has_next'] = False
        session['payload'] = None
        return session

    def _add_jid(self, iq, session):
        if iq['from'].bare not in self._admins:
            raise XMPPError('forbidden')

        form = self.xmpp['xep_0004'].stanza.Form()
        form['type'] = 'form'
        form['title'] = 'Add XSF Member JID'
        form['instructions'] = 'Enter a JID for an XSF Member'
        form.add_field(var='jid', ftype='jid-single', title='JID', desc='XSF Member JID', required=True)

        session['payload'] = form
        session['has_next'] = False

        def handle_result(form, session):
            jid = JID(form['values']['jid'])

            if jid.bare not in self._members:
                self._members.add(jid)
                self._save_data()
                self.xmpp.event('xsf_jid_added', jid)

            session['payload'] = None
            session['next'] = None
            return session

        session['next'] = handle_result
        return session

    def _remove_jid(self, iq, session):
        if iq['from'].bare not in self._admins:
            raise XMPPError('forbidden')

        form = self.xmpp['xep_0004'].stanza.Form()
        form['type'] = 'form'
        form['title'] = 'Remove XSF Member JID'
        form['instructions'] = 'Enter a JID for an XSF Member'
        form.add_field(var='jid', ftype='jid-single', title='JID', desc='XSF Member JID', required=True)

        session['payload'] = form
        session['has_next'] = False

        def handle_result(form, session):
            jid = JID(form['values']['jid'])

            if jid.bare in self._members:
                self._members.remove(jid)
                self._save_data()
                self.xmpp.event('xsf_jid_removed', jid)

            session['payload'] = None
            session['next'] = None
            return session

        session['next'] = handle_result
        return session


register_plugin(XSFRoster)
