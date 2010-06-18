# -*- coding: utf-8 -*-
# Copyright (C) 2006 Ashwin Phatak
# Copyright (C) 2007 Dave Gynn

from trac.core import *
from trac.config import Option, ListOption
from trac.perm import IPermissionRequestor
from trac.ticket import TicketSystem, Ticket
from trac.ticket.query import QueryModule
from trac.web.api import ITemplateStreamFilter
from trac.web.chrome import ITemplateProvider, Chrome
from trac.web.main import IRequestFilter
from trac.util.datefmt import to_datetime, to_utimestamp
from genshi.filters.transform import Transformer
import re

__all__ = ['BatchModifyModule']

class BatchModifyModule(Component):
    implements(IPermissionRequestor, ITemplateProvider, IRequestFilter, ITemplateStreamFilter)

    fields_as_list = ListOption("batchmod", "fields_as_list", default="keywords", 
                                doc="field names modified as a value list(separated by ',')")
    list_separator_regex = Option("batchmod", "list_separator_regex", default='[,\s]+',
                                  doc="separator regex used for 'list' fields")
    list_connecter_string = Option("batchmod", "list_connector_string", default=',',
                                   doc="connecter string for 'list' fields")

    # IPermissionRequestor methods
    def get_permission_actions(self):
        yield 'TICKET_BATCH_MODIFY'

    # ITemplateProvider methods
    def get_htdocs_dirs(self):
        return []

    def get_templates_dirs(self):
        from pkg_resources import resource_filename
        return [resource_filename(__name__, 'templates')]

    # IRequestFilter methods
    def pre_process_request(self, req, handler):
        """Look for QueryHandler posts and hijack them"""
        if req.path_info == '/query' and req.method=='POST' and \
            req.args.get('batchmod') and self._has_permission(req):
            self.log.debug('BatchModifyModule: executing')
            self._batch_modify(req)
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
    
    # Internal methods 
    def _batch_modify(self, req):
        tickets = req.session['query_tickets'].split(' ')
        comment = req.args.get('bmod_value_comment', '')
        modify_changetime = bool(req.args.get('bmod_modify_changetime', False))
        values = {} 

        # TODO: improve validation and better handle advanced statuses
        for field in TicketSystem(self.env).get_ticket_fields():
            name = field['name']
            if name not in ('summary', 'reporter', 'description'):
                if req.args.has_key('bmod_flag_' + name):
                    values[name] = req.args.get('bmod_value_' + name)

        selectedTickets = req.args.get('selectedTickets')
        self.log.debug('BatchModifyPlugin: selected tickets: %s', selectedTickets)
        selectedTickets = isinstance(selectedTickets, list) and selectedTickets or selectedTickets.split(',')
        if not selectedTickets:
            raise TracError, 'No Tickets selected'
        
        for id in selectedTickets:
            if id in tickets:
                t = Ticket(self.env, int(id))
                
                log_msg = ""
                if not modify_changetime:
                  original_changetime = to_utimestamp(t.time_changed)
                
                _values = values.copy()
                for field in [f for f in values.keys() if f in self.fields_as_list]:
                    _values[field] = self._merge_keywords(t.values[field], values[field])
                
                t.populate(_values)
                t.save_changes(req.authname, comment)

                if not modify_changetime:
                  log_msg = "(changetime not modified)"
                  db = self.env.get_db_cnx()
                  db.cursor().execute("UPDATE ticket set changetime=%s where id=%s" % (original_changetime, t.id))
                  db.commit()

                self.log.debug('BatchModifyPlugin: saved changes to #%s %s' % (id, log_msg))

                # TODO: Send email notifications - copied from ticket.web_ui
                #try:
                #    tn = TicketNotifyEmail(self.env)
                #    tn.notify(ticket, newticket=False, modtime=now)
                #except Exception, e:
                #    self.log.exception("Failure sending notification on change to "
                #                       "ticket #%s: %s" % (ticket.id, e))
    
                # TODO: deal with actions and side effects - copied from ticket.web_ui
                #for controller in self._get_action_controllers(req, ticket,
                #                                               action):
                #    controller.apply_action_side_effects(req, ticket, action)

    def _merge_keywords(self, original_keywords, new_keywords):
        """Prevent duplicate keywords by merging the two lists."""
        self.log.debug('BatchModifyPlugin: existing keywords are %s', original_keywords)
        self.log.debug('BatchModifyPlugin: new keywords are %s', new_keywords)
        
        regexp = re.compile(self.list_separator_regex)
        
        new_keywords = [k.strip() for k in regexp.split(new_keywords) if k]
        combined_keywords = [k.strip() for k in regexp.split(original_keywords) if k]
        
        for keyword in new_keywords:
            if keyword.startswith('-'):
                keyword = keyword[1:]
                while keyword in combined_keywords:
                    combined_keywords.remove(keyword)
            else:
                if keyword not in combined_keywords:
                    combined_keywords.append(keyword)
        
        self.log.debug('BatchModifyPlugin: combined keywords are %s', combined_keywords)
        return self.list_connecter_string.join(combined_keywords)

    # ITemplateStreamFilter methods
    def filter_stream(self, req, method, filename, stream, formdata):
        """Adds BatchModify form to the query page"""
        if filename == 'query.html' and self._has_permission(req):
            return stream | Transformer('//div[@id="help"]'). \
                                before(self._generate_form(req, formdata) )
        return stream

    
    def _generate_form(self, req, data):
        batchFormData = dict(data)
        batchFormData['query_href']= req.session['query_href'] or req.href.query()
        
        ticketSystem = TicketSystem(self.env)
        fields = []
        for field in ticketSystem.get_ticket_fields():
            if field['name'] not in ('summary', 'reporter', 'description'):
                fields.append(field)
            if field['name'] == 'owner' and hasattr(ticketSystem, 'eventually_restrict_owner'):
                ticketSystem.eventually_restrict_owner(field)
        batchFormData['fields']=fields

        stream = Chrome(self.env).render_template(req, 'batchmod.html',
              batchFormData, fragment=True)
        return stream.select('//form[@id="batchmod-form"]')
        
    # Helper methods
    def _has_permission(self, req):
        return req.perm.has_permission('TICKET_ADMIN') or \
                req.perm.has_permission('TICKET_BATCH_MODIFY')
