import random
import logging

from slixmpp.plugins import BasePlugin, register_plugin

log = logging.getLogger(__name__)


class XSFVotingChat(BasePlugin):
    name = 'xsf_voting_chat'
    description = 'XSF: Proxy voting via chat sessions'
    dependencies = set(['xsf_voting'])

    def plugin_init(self):
        self.xmpp.add_event_handler('message', self.on_message)
        self.sessions = {}

    def on_message(self, msg):
        user = msg['from']

        if msg['type'] not in ('normal', 'chat'):
            return
        if not self.xmpp['xsf_roster'].is_member(user):
            log.warn('Unknown user: %s', user)
            return

        if user not in self.sessions:
            self.sessions[user] = VotingSession(self.xmpp, user)
        session = self.sessions[user]
        try:
            session.process(msg['body'], )
        except StopIteration:
            pass


register_plugin(XSFVotingChat)


class VotingSession(object):

    def __init__(self, xmpp, user):
        self.xmpp = xmpp
        self.user = user
        self._session = self._process()
        next(self._session)

    def end(self):
        self.xmpp.client_roster[self.user]['name'] or self.user.bare
        self.send('end')
        del self.xmpp['xsf_voting_chat'].sessions[self.user]

    def process(self, user_resp):
        self._session.send(user_resp)

    def _process(self):
        _ = (yield)  # Needed to startup the coroutine

        composing = self.xmpp.Message(sto=self.user)
        composing['chat_state'] = 'composing'
        composing.send()

        self.send('welcome')

        ballot = self.xmpp['xsf_voting'].get_ballot()

        if not ballot:
            self.send('no_elections')
            return
        else:
            self.send('elections', titles=[s['title'] for s in ballot['sections']])

        self.send('meeting_notice', date=ballot['date'])

        # ----------------------------------------------------------------------------
        # Setup the voting session, based on any previous sessions from this election.
        # ----------------------------------------------------------------------------

        session = self.xmpp['xsf_voting'].get_session(self.user)
        if session['status'] == 'completed':
            self.send('already_voted')
            vote = (yield)
            vote = vote.strip().lower()
            while vote not in ('yes', 'no'):
                self.send('invalid_yesno')
                vote = (yield)
                vote = vote.strip().lower()
            if vote == 'no':
                self.end()
                return
            session = self.xmpp['xsf_voting'].restart_voting(self.user)
        elif session['status'] == 'started':
            self.send('resume_voting')
            vote = (yield)
            vote = vote.strip().lower()
            while vote not in ('yes', 'no'):
                self.send('invalid_yesno')
                vote = (yield)
                vote = vote.strip().lower()
            if vote == 'no':
                self.end()
                return
        else:
            self.send('start_voting')
            vote = (yield)
            vote = vote.strip().lower()
            while vote not in ('yes', 'no'):
                self.send('invalid_yesno')
                vote = (yield)
                vote = vote.strip().lower()
            if vote == 'no':
                self.end()
                return
            session = self.xmpp['xsf_voting'].start_voting(self.user)

        # ----------------------------------------------------------------------------
        # Collect votes for each ballot section.
        # ----------------------------------------------------------------------------

        for section in ballot['sections']:
            title = section['title']

            self.send('ballot_section', title=title)

            # Since some people just vote for the top entries on the ballot, shuffle
            # the items around to remove that bias.
            items = section['items']
            random.shuffle(items)

            if section['limit']:
                # --------------------------------------------------------------------
                # Election for XSF Board or Council.
                # --------------------------------------------------------------------
                self.send('num_candidates_limited',
                          candidates=len(items),
                          limit=section['limit'])

                # Calculate the acceptable user responses.
                options = [str(i + 1) for i, item in enumerate(items)]

                for i, item in enumerate(items):
                    self.send('limited_candidate',
                              index=str(i + 1),
                              name=item['name'],
                              jid=item['jid'],
                              url=item['url'])

                if session['votes'][title]:
                    self.send('previous_limited_votes')
                    for _, candidate in session['votes'][title].items():
                        self.send('previous_limited_candidate', candidate=candidate)

                # Track selections made this session, to provide
                # better error messages.
                selections = set()
                abstain = False

                for i in range(0, min(int(section['limit']), len(items))):
                    if abstain:
                        session = self.xmpp['xsf_voting'].abstain_vote(self.user, title, str(i + 1))
                        break

                    self.send('limited_choice',
                              index=str(i + 1),
                              title=title,
                              options=options,
                              selections=selections,
                              names=[item['name'] for item in items])
                    vote = (yield)
                    vote = vote.strip().lower()
                    while (vote not in options and vote not in ('0', 'none')) or vote in selections:
                        if vote not in options:
                            self.send('invalid_index', max=len(options))
                        else:
                            name = items[int(vote) - 1]['name']
                            self.send('duplicate_index', index=vote, name=name)
                        vote = (yield)
                        vote = vote.strip().lower()
                    if vote in ('0', 'none'):
                        abstain = True
                        session = self.xmpp['xsf_voting'].abstain_vote(self.user, title, str(i + 1))
                        self.send('abstain')
                    else:
                        name = items[int(vote) - 1]['name']
                        self.send('chosen_limited_candidate', name=name)
                        selections.add(vote)
                        session = self.xmpp['xsf_voting'].record_vote(self.user, title, str(i + 1), name)
            else:
                # --------------------------------------------------------------------
                # XSF Membership Elections
                # --------------------------------------------------------------------
                self.send('num_candidates', candidates=len(items))
                for item in items:
                    name = item['name']

                    self.send('candidate', **item)
                    if item['name'] in session['votes'][title]:
                        self.send('previous_vote',
                                  vote=session['votes'][title][name],
                                  name=name)
                    self.send('approve_candidate')
                    vote = (yield)
                    vote = vote.strip().lower()
                    while vote not in ('yes', 'no'):
                        self.send('invalid_yesno')
                        vote = (yield)
                        vote = vote.strip().lower()
                    session = self.xmpp['xsf_voting'].record_vote(self.user, section['title'], item['name'], vote)

        # ----------------------------------------------------------------------------
        # Display final results
        # ----------------------------------------------------------------------------
        for title, votes in session['votes'].items():
            self.send('vote_results', title=title, votes=votes.items())
            if not votes:
                self.send('no_vote_results')

        self.xmpp['xsf_voting'].end_voting(self.user)
        self.end()

    def send(self, template, **data):
        text = ''
        html = ''

        if template == 'welcome':
            name = self.xmpp.client_roster[self.user]['name'] or self.user.bare
            text = 'Hi, %s!' % name
        elif template == 'end':
            name = self.xmpp.client_roster[self.user]['name'] or self.user.bare
            text = 'Thank you for voting, %s! If you wish to recast your votes later, just start a new voting session.' % name
            data['chat_state'] = 'gone'
        elif template == 'no_elections':
            text = 'No elections are being held at this time.'
        elif template == 'elections':
            titles = data['titles']
            text = 'Voting has begun for: %s' % ', '.join(titles)
            titles = ['<strong>%s</strong>' % title for title in titles]
            html = '<p>Voting has begun for: %s</p>' % ', '.join(titles)
        elif template == 'meeting_notice':
            text = ('By proceeding, you affirm that you wish to have your'
                    ' vote count as a proxy vote in the official meeting'
                    ' to be held on %s in xsf@muc.xmpp.org.')
            html = ('<p><em>By proceeding, you affirm that you wish to have'
                    ' your vote count as a proxy vote in the official'
                    ' meeting to be held on <strong>%s</strong> in'
                    ' <a href="xmpp:xsf@muc.xmpp.org?join">xsf@muc.xmpp.org</a>.</em></p>')
            text = text % data['date']
            html = html % data['date']
        elif template == 'invalid_yesno':
            text = 'Please respond with "yes" or "no".'
            html = '<p>Please respond with <strong>yes</strong> or <strong>no</strong>.</p>'
        elif template == 'already_voted':
            text = ('You have already participated in this election.'
                    ' Would you like to recast your votes? (yes/no)')
            html = ('<p>You have already participated in this election.'
                    ' Would you like to recast your votes? ('
                    '<a href="xmpp:{0}?message;type=chat;body=yes">yes</a> /'
                    ' <a href="xmpp:{0}?message;type=chat;body=no">no</a>)</p>')
            html = html.format(self.xmpp.boundjid)
        elif template == 'resume_voting':
            text = ('You started voting, but have not finished.'
                    ' Would you like to resume voting? (yes/no)')
            html = ('<p>You started voting, but have not finished.'
                    ' Would you like to resume voting? ('
                    '<a href="xmpp:{0}?message;type=chat;body=yes">yes</a> /'
                    ' <a href="xmpp:{0}?message;type=chat;body=no">no</a>)</p>')
            html = html.format(self.xmpp.boundjid)
        elif template == 'start_voting':
            text = 'Would you like to cast your votes now? (yes/no)'
            html = ('<p>Would you like to cast your votes now? ('
                    '<a href="xmpp:{0}?message;type=chat;body=yes">yes</a> /'
                    ' <a href="xmpp:{0}?message;type=chat;body=no">no</a>)</p>')
            html = html.format(self.xmpp.boundjid)
        elif template == 'approve_candidate':
            text = 'Approve? (yes/no)'
            html = ('<p>Approve? ('
                    '<a href="xmpp:{0}?message;type=chat;body=yes">yes</a> /'
                    ' <a href="xmpp:{0}?message;type=chat;body=no">no</a>)</p>')
            html = html.format(self.xmpp.boundjid)
        elif template == 'ballot_section':
            text = '%s:' % data['title']
            html = '<p><strong>%s</strong>:</p>' % data['title']
        elif template == 'num_candidates_limited':
            text = 'There are {candidates} candidates. You may vote for up to {limit}.'
            html = '<p><em>There are {candidates} candidates. You may vote for up to {limit}.</em></p>'

            text = text.format(**data)
            html = html.format(**data)
        elif template == 'limited_candidate':
            text = '{index}) {name} ({jid}) -- {url}'.format(**data)
            html = ('<p>{index}) <strong><a href="xmpp:{jid}?message">{name}</a></strong>'
                    ' (<a href="{url}">View application</a>)</p>')
            html = html.format(**data)
        elif template == 'previous_limited_votes':
            text = 'You previously voted for:'
            html = '<p><em>You previously voted for:</em></p>'
        elif template == 'previous_limited_candidate':
            text = '- %s' % data['candidate']
            html = '<p><em>- %s</em></p>' % data['candidate']
        elif template == 'limited_choice':
            text = 'Choice {index} for {title}: ({formatted_options}), or 0 to abstain'
            opts = []
            for option in data['options']:
                if option not in data['selections']:
                    opts.append(option)
            data['formatted_options'] = ' / '.join(opts)
            text = text.format(**data)

            html = '<p>Choice {index} for <strong>{title}</strong>: {formatted_options}, or 0 to abstain</p>'
            opts = []
            for option in data['options']:
                if option in data['selections']:
                    continue
                index = int(option) - 1
                name = data['names'][index]
                opt = '%s) <a href="xmpp:%s?message;type=chat;body=%s">%s</a>'
                opts.append(opt % (option, self.xmpp.boundjid, option, name))
            data['formatted_options'] = ' / '.join(opts)
            html = html.format(**data)
        elif template == 'invalid_index':
            text = ('Please respond with the number (1 through %s) of the'
                    ' candidate you wish to select (or 0 to abstain).') % data['max']
        elif template == 'duplicate_index':
            text = ('You have already chosen {index} ({name}).'
                    ' Please select another candidate.').format(**data)
        elif template == 'chosen_limited_candidate':
            text = 'You chose %s.' % data['name']
            html = '<p><em>You chose %s.</em></p>' % data['name']
        elif template == 'num_candidates':
            text = 'There are %s matters subject to vote.' % data['candidates']
            html = '<p><em>There are %s matters subject to vote.</em></p>' % data['candidates']
        elif template == 'candidate':
            if (data['jid']):
                text = '{name} ({jid}) -- {url}'.format(**data)
                html = ('<p><strong><a href="xmpp:{jid}?message">{name}</a></strong>'
                        ' (<a href="{url}">More information</a>)</p>').format(**data)
            else:
                text = '{name} -- {url}'.format(**data)
                html = ('<p><strong>{name}</strong> '
                        ' (<a href="{url}">More information</a>)</p>').format(**data)
        elif template == 'previous_vote':
            text = 'You previously voted {vote} for: {name}.'.format(**data)
            html = ('<p><em>You previously voted <strong>{vote}</strong>'
                    ' for: <strong>{name}</strong></em></p>').format(**data)
        elif template == 'vote_results':
            votes = '\n'.join(f'{name} -- {vote}' for name, vote in data['votes'])
            text = 'Your votes for %s:\n%s' % (data['title'], votes)
            votes = ''.join(f'<li><strong>{name}</strong> - <em>{vote}</em></li>' for name, vote in data['votes'])
            html = '<p>Your votes for <strong>%s</strong>:</p><ul>%s</ul>' % (data['title'], votes)
        elif template == 'no_vote_results':
            text = 'You abstained from all choices for this topic'
            html = '<p>You abstained from all choices for this topic</p>'
        elif template == 'abstain':
            text = 'You have abstained from further votes for this topic.'
            html = '<p>You have abstained from further votes for this topic.</p>'

        reply = self.xmpp.Message()
        reply['to'] = self.user
        reply['type'] = 'chat'
        reply['body'] = text
        if html and self.has_feature(feature='http://jabber.org/protocol/xhtml-im'):
            reply['html']['body'] = html
        if self.has_feature(feature='http://jabber.org/protocol/chatstates'):
            reply['chat_state'] = data.get('chat_state', 'active')
        reply.send()

    def has_feature(self, feature: str) -> bool:
        info = yield from self.xmpp['xep_0030'].get_info(self.user, cached=True)
        return feature in info['features']
