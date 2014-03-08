from openerp.osv import osv, fields
from openerp.tools.translate import _

class clubit_tools_edi_wizard_outgoing(osv.TransientModel):
    _name = 'clubit.tools.edi.wizard.outgoing'
    _description = 'EDI Export Wizard'

    _columns = {
        'partner_id': fields.many2one('res.partner', 'Partner'),
    }




    ''' clubit.tools.edi.wizard.outgoing:resolve()
        ------------------------------------------
        This method is used to automatically find the
        partners to which to send the EDI documents to.
        ----------------------------------------------- '''
    def resolve(self, cr, uid, ids, context=None):

        # Get the selected documents
        # --------------------------
        ids = context.get('active_ids', [])
        flow_id = context.get('flow_id', False)
        if not ids:
            raise osv.except_osv(_('Warning!'), _("You did not provide any documents to archive!"))
        if not flow_id:
            raise osv.except_osv(_('Warning!'), _("Couldn't find relevant flow_id, this is probably due to a programming error."))


        # Find the resolver method
        # ------------------------
        flow_db = self.pool.get('clubit.tools.edi.flow')
        flow = flow_db.browse(cr, uid, [flow_id], context)[0]
        if not flow.partner_resolver:
            raise osv.except_osv(_('Warning!'), _("No partner_resolver defined for this EDI flow. Contact your system administrator."))

        resolver = getattr(self.pool.get(flow.model), flow.partner_resolver)
        try:
            resolved_list = resolver(cr, uid, ids, context)
        except Exception:
            raise osv.except_osv(_('Warning!'), _("Partner_resolver raised an exception. Contact your system administrator."))

        self.check_partner_allowed(cr, uid, flow_id, resolved_list, context)


        # Pass these documents to the handler method for this flow
        # --------------------------------------------------------
        if not flow.method:
            raise osv.except_osv(_('Warning!'), _("No handler defined for this EDI flow. Contact your system administrator."))

        handler = getattr(self.pool.get(flow.model), flow.method)
        try:
            handler(cr, uid, resolved_list, context)
        except Exception as e:
            raise e



    ''' clubit.tools.edi.wizard.outgoing:select()
        -----------------------------------------
        This method is used to send EDI documents to
        a specific partner of the user's choosing.
        The partner is still validated though!
        -------------------------------------------- '''
    def select(self, cr, uid, ids, context=None):


        # Get the entered partner from the wizard
        # ---------------------------------------
        wizard = self.browse(cr, uid, ids, context)[0]
        if not wizard.partner_id:
            raise osv.except_osv(_('Warning!'), _("You have to provide a partner to send these documents to."))


        # Get the selected documents
        # --------------------------
        ids = context.get('active_ids', [])
        flow_id = context.get('flow_id', False)
        if not ids:
            raise osv.except_osv(_('Warning!'), _("You did not provide any documents to archive!"))
        if not flow_id:
            raise osv.except_osv(_('Warning!'), _("Couldn't find relevant flow_id, this is probably due to a programming error."))


        # Attach the partner to a resolved list for validation
        # ----------------------------------------------------
        resolved_list = []
        for item in ids:
            resolved_list.append({'id':item, 'partner_id':wizard.partner_id.id})
        self.check_partner_allowed(cr, uid, flow_id, resolved_list, context)


        # Pass these documents to the handler method for this flow
        # --------------------------------------------------------
        flow_db = self.pool.get('clubit.tools.edi.flow')
        flow = flow_db.browse(cr, uid, [flow_id], context)[0]
        if not flow.method:
            raise osv.except_osv(_('Warning!'), _("No handler defined for this EDI flow. Contact your system administrator."))

        handler = getattr(self.pool.get(flow.model), flow.method)
        try:
            handler(cr, uid, resolved_list, context)
        except Exception as e:
            raise e







    ''' clubit.tools.edi.wizard.outgoing:check_partner_allowed()
        --------------------------------------------------------
        This method is used by the EDI wizard to check wether
        or not these documents *can* be sent to the chosen partners.
        ------------------------------------------------------------ '''
    def check_partner_allowed(self, cr, uid, flow_id, resolved_list, context=None):

        partner_db = self.pool.get('res.partner')

        # Remove duplicate partners
        # -------------------------
        partners = list(set([x['partner_id'] for x in resolved_list]))

        # Find non-EDI relevant partners
        # ------------------------------
        irrelevant = ""
        partners = partner_db.browse(cr, uid, partners, context)
        for partner in partners:
            if not partner.edi_relevant or not (flow for flow in partner.edi_flows if flow.partnerflow_active and flow.id == flow_id):
                irrelevant += partner.name + ", "

        if irrelevant:
            raise osv.except_osv(_('Warning!'), _("You tried to send EDI documents to partners that aren't defined as EDI relevant or are not listening to this EDI flow. This is the list of all non-compatible partners found: {!s} ").format(irrelevant))

        return True



























