# -*- coding: utf-8 -*-
# Copyright (C) 2006 Ashwin Phatak
# Copyright (C) 2007 Dave Gynn
# Copyright (C) 2010 Brian Meeker

from trac.core import *
from trac.config import Option, ListOption
from trac.perm import IPermissionRequestor
from trac.ticket import TicketSystem, Ticket
from trac.ticket.query import QueryModule
from trac.web.api import ITemplateStreamFilter
from trac.web.chrome import ITemplateProvider, Chrome, \
                            add_script, add_stylesheet
from trac.web.main import IRequestFilter
from trac.util.datefmt import to_datetime, to_utimestamp
from genshi.filters.transform import Transformer
import re

__all__ = ['BatchModifyModule']

class BatchModifyModule(Component):
    implements(IPermissionRequestor, ITemplateProvider, IRequestFilter,
               ITemplateStreamFilter)

    fields_as_list = ListOption("batchmod", "fields_as_list", 
                default="keywords", 
                doc="field names modified as a value list(separated by ',')")
    list_separator_regex = Option("batchmod", "list_separator_regex",
                default='[,\s]+',
                doc="separator regex used for 'list' fields")
    list_connector_string = Option("batchmod", "list_connector_string",
                default=',',
                doc="connecter string for 'list' fields")

    # IPermissionRequestor methods
    def get_permission_actions(self):
        yield 'TICKET_BATCH_MODIFY'

    # ITemplateProvider methods
    def get_htdocs_dirs(self):
        """Return a list of directories with static resources (such as style
        sheets, images, etc.)
    
        Each item in the list must be a `(prefix, abspath)` tuple. The
        `prefix` part defines the path in the URL that requests to these
        resources are prefixed with.
    
        The `abspath` is the absolute path to the directory containing the
        resources on the local file system.
        """
        from pkg_resources import resource_filename
        return [('batchmod', resource_filename(__name__, 'htdocs'))]

    def get_templates_dirs(self):
        from pkg_resources import resource_filename
        return [resource_filename(__name__, 'templates')]

    # IRequestFilter methods
    def pre_process_request(self, req, handler):
        """Look for QueryHandler posts and hijack them"""
        if req.path_info == '/query' and req.method=='POST' and \
            req.args.get('batchmod_submit') and self._has_permission(req):
            self.log.debug('BatchModifyModule: executing')
            
            batch_modifier = BatchModifier(self.fields_as_list, 
                                           self.list_separator_regex, 
                                           self.list_connector_string)
            batch_modifier.process_request(req, self.env, self.log)
            # redirect to original Query
            # TODO: need better way to fake QueryModule...
            req.redirect(req.args.get('query_href'))
        return handler


    def post_process_request(self, req, template, content_type):
        """No-op"""
        return (template, content_type)

    def post_process_request(self, req, template, data, content_type):
        """No-op"""
        return (template, data, content_type)

    # ITemplateStreamFilter methods
    def filter_stream(self, req, method, filename, stream, formdata):
        """Adds BatchModify form to the query page"""
        if filename == 'query.html' and self._has_permission(req):
            self.log.debug('BatchModifyPlugin: rendering template')
            return stream | Transformer('//div[@id="help"]'). \
                                before(self._generate_form(req, formdata) )
        return stream

    
    def _generate_form(self, req, data):
        batchFormData = dict(data)
        batchFormData['query_href']= req.session['query_href'] \
                                     or req.href.query()
        
        ticketSystem = TicketSystem(self.env)
        fields = []
        for field in ticketSystem.get_ticket_fields():
            if field['name'] not in ('summary', 'reporter', 'description'):
                fields.append(field)
            if field['name'] == 'owner' \
                and hasattr(ticketSystem, 'eventually_restrict_owner'):
                ticketSystem.eventually_restrict_owner(field)
        fields.sort(key=lambda f: f['name'])
        batchFormData['fields']=fields

        add_script(req, 'batchmod/js/batchmod.js')
        add_stylesheet(req, 'batchmod/css/batchmod.css')
        stream = Chrome(self.env).render_template(req, 'batchmod.html',
              batchFormData, fragment=True)
        return stream.select('//form[@id="batchmod_form"]')
        
    # Helper methods
    def _has_permission(self, req):
        return req.perm.has_permission('TICKET_ADMIN') or \
                req.perm.has_permission('TICKET_BATCH_MODIFY')

class BatchModifier:
    """Modifies a batch of tickets"""
    
    def __init__(self, fields_as_list, list_separator_regex, 
                 list_connector_string):
        """Pull all the config values in."""
        self._fields_as_list = fields_as_list
        self._list_separator_regex = list_separator_regex
        self._list_connector_string = list_connector_string
    
        # Internal methods 
    def process_request(self, req, env, log):
        tickets = req.session['query_tickets'].split(' ')
        comment = req.args.get('batchmod_value_comment', '')
        modify_changetime = bool(req.args.get(
                                              'batchmod_modify_changetime',
                                              False))
        
        values = self._get_new_ticket_values(req, env) 
        self._check_for_resolution(values)
        self._remove_resolution_if_not_closed(values)

        selectedTickets = req.args.get('selectedTickets')
        log.debug('BatchModifyPlugin: selected tickets: %s', selectedTickets)
        selectedTickets = isinstance(selectedTickets, list) \
                          and selectedTickets or selectedTickets.split(',')
        if not selectedTickets:
            raise TracError, 'No tickets selected'
        
        self._save_ticket_changes(req, env, log, selectedTickets, tickets, 
                                  values, comment, modify_changetime)

    def _get_new_ticket_values(self, req, env):
        """Pull all of the new values out of the post data."""
        values = {}
        for field in TicketSystem(env).get_ticket_fields():
            name = field['name']
            if name not in ('summary', 'reporter', 'description'):
                value = req.args.get('batchmod_value_' + name)
                if value is not None:
                    values[name] = value
        return values
    
    def _check_for_resolution(self, values):
        """If a resolution has been set the status is automatically
        set to closed."""
        if values.has_key('resolution'):
            values['status'] = 'closed'
    
    def _remove_resolution_if_not_closed(self, values):
        """If the status is set to something other than closed the
        resolution should be removed."""
        if values.has_key('status') and values['status'] is not 'closed':
            values['resolution'] = ''

    def _save_ticket_changes(self, req, env, log, selected_tickets, tickets, 
                             new_values, comment, modify_changetime):
        @with_transaction(self.env)
        def _implementation(db):
            for id in selectedTickets:
                if id in tickets:
                    t = Ticket(env, int(id))
                    
                    log_msg = ""
                    if not modify_changetime:
                        original_changetime = to_utimestamp(t.time_changed)
                    
                    _values = values.copy()
                    for field in [f for f in values.keys() \
                                  if f in self._fields_as_list]:
                        _values[field] = self._merge_keywords(t.values[field],
                                                              values[field],
                                                              log)
                    
                    t.populate(_values)
                    t.save_changes(req.authname, comment)

                    if not modify_changetime:
                        self._reset_changetime(env, original_changetime, t)
                        log_msg = "(changetime not modified)"

                    log.debug('BatchModifyPlugin: saved changes to #%s %s' % 
                              (id, log_msg))

    def _merge_keywords(self, original_keywords, new_keywords, log):
        """
        Prevent duplicate keywords by merging the two lists.
        Any keywords prefixed with '-' will be removed.
        """
        log.debug('BatchModifyPlugin: existing keywords are %s', 
                  original_keywords)
        log.debug('BatchModifyPlugin: new keywords are %s', new_keywords)
        
        regexp = re.compile(self._list_separator_regex)
        
        new_keywords = [k.strip() for k in regexp.split(new_keywords) if k]
        combined_keywords = [k.strip() for k 
                             in regexp.split(original_keywords) if k]
        
        for keyword in new_keywords:
            if keyword.startswith('-'):
                keyword = keyword[1:]
                while keyword in combined_keywords:
                    combined_keywords.remove(keyword)
            else:
                if keyword not in combined_keywords:
                    combined_keywords.append(keyword)
        
        log.debug('BatchModifyPlugin: combined keywords are %s', 
                  combined_keywords)
        return self._list_connector_string.join(combined_keywords)
    
    def _reset_changetime(self, env, original_changetime, ticket):
        db = env.get_db_cnx()
        db.cursor().execute("UPDATE ticket set changetime=%s where id=%s" 
                            % (original_changetime, ticket.id))
        db.commit()