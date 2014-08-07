from openerp.osv import osv, fields
from lxml import etree


class clubit_tools_edi_street_wizard_line(osv.TransientModel):
    _name = 'clubit.tools.edi.street.wizard.line'
    _description = 'EDI Street Wizard Line'

    _columns = {
        'reference' : fields.char('Reference', size=64),
        'step_0': fields.datetime('Step 1'),
        'step_1': fields.datetime('Step 2'),
        'step_2': fields.datetime('Step 3'),
        'step_3': fields.datetime('Step 4'),
        'step_4': fields.datetime('Step 5'),
        'step_5': fields.datetime('Step 6'),
        'step_6': fields.datetime('Step 7'),
        'step_7': fields.datetime('Step 8'),
        'step_8': fields.datetime('Step 9'),
        'step_9': fields.datetime('Step 10'),
        'wizard': fields.many2one('clubit.tools.edi.street.wizard', 'Wizard', ondelete='cascade', required=True, select=True),
    }

class clubit_tools_edi_street_wizard(osv.TransientModel):
    _name = 'clubit.tools.edi.street.wizard'
    _description = 'EDI Street Wizard'

    _columns = {
        'street': fields.many2one('clubit.tools.edi.street', 'EDI Street', required=True, select=True),
        'start_at': fields.datetime('Start at'),
        'end_at': fields.datetime('End at'),
        'lines': fields.one2many('clubit.tools.edi.street.wizard.line', 'wizard', 'Analysis'),
    }

    def start(self, cr, uid, ids, context=None):

        for wizard in self.browse(cr, uid, ids, context=context):
            result = self.calculate(cr, uid, wizard.id, context=context)
            if not result: continue
            wizard.write({'lines': result})

        model_data = self.pool.get('ir.model.data')
        model, record_id = model_data.get_object_reference(cr, uid, 'clubit_tools', 'action_edi_street_analysis')
        values = self.pool.get(model).read(cr, uid, [record_id], context=context)[0]
        values['res_id'] = ids[0]
        return values


    def calculate(self, cr, uid, id, context=None):

        result = []
        models = []
        wizard = self.browse(cr, uid, id, context=context)

        for i, step in enumerate(wizard.street.steps):
            search = []
            if wizard.start_at: search.append(('create_date', '>=', wizard.start_at))
            if wizard.end_at:   search.append(('create_date', '<', wizard.end_at))

            # Search all the EDI documents for this step
            # ------------------------------------------
            search.append(('flow_id', '=', step.flow.id))
            model_db = self.pool.get('clubit.tools.edi.document.incoming')
            if step.flow.direction != 'in':
                model_db = self.pool.get('clubit.tools.edi.document.outgoing')
            models = model_db.search(cr, uid, search, context=context)
            models = model_db.browse(cr, uid, models, context=context)

            # Map the documents to the result
            # -------------------------------
            if i == 0:
                for model in models:
                    result.append((0,0,{'reference': model.reference, 'step_0': model.create_date}))
            else:
                for model in models:
                    line = [x for x in result if x['reference'] == model.reference]
                    if line: line[2]['step_'+str(i)] = model.create_date
                    else: result.append((0,0,{'reference': model.reference, 'step_'+str(i): model.create_date}))

        return result


    def fields_view_get(self, cr, user, view_id=None, view_type='form', context=None, toolbar=False, submenu=False):
        if not context:
            context = {}
        res = super(clubit_tools_edi_street_wizard, self).fields_view_get(cr, user, view_id, view_type, context, toolbar=toolbar, submenu=submenu)
        if not context.get('active_ids'):
            return res
        wizard = self.pool.get('clubit.tools.edi.street.wizard').browse(cr, user, context['active_ids'][0])
        if not wizard.street:
            return res

        for i in xrange(10):
            if i >= len(wizard.street.steps):
                del res['fields']['lines']['views']['tree']['fields']['step_'+str(i)]
        return res






















