from openerp.osv import osv, fields
from openerp.tools.translate import _

##############################################################################
#
#    This file defines the EDI Street concept. The idea of a street is
#    centered around the ability to link several EDI Flows in a logical
#    sequence. Linking flows into a street helps the end user to visually
#    keep track of the current state of a particular EDI chain.
#
##############################################################################

class clubit_tools_edi_street(osv.Model):
    _name = "clubit.tools.edi.street"
    _columns = {
        'name' : fields.char('Street Name', size=64, required=True),
        'steps': fields.one2many('clubit.tools.edi.street.step', 'street', 'Steps'),
    }

class clubit_tools_edi_street_step(osv.Model):
    _name = "clubit.tools.edi.street.step"
    _columns = {
        'sequence': fields.integer('Sequence', required=True),
        'desired_response_time': fields.integer('Desired Response Time'),
        'desired_response_unit': fields.selection([('seconds','Seconds'),('minutes','Minutes'),('hours','Hours'),('days','Days')], 'Response Time Unit'),
        'description' : fields.char('Description', size=64),
        'flow': fields.many2one('clubit.tools.edi.flow', 'Flow', required=True, select=True),
        'street': fields.many2one('clubit.tools.edi.street', 'EDI Street', ondelete='cascade', required=True, select=True),
    }



    #def calculate_street_report(self, cr, uid, street_id, context=None):

    #		flow_db = self.pool.get('clubit.tools.edi.flow')
    #		street = self.browse(cr, uid, street_id, context=context)

    #		for step in street.steps:

    #	return meta
