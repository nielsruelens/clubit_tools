from openerp.osv import osv, fields
from openerp.tools.translate import _


class clubit_tools_settings_connection(osv.Model):

    _name = "clubit.tools.settings.connection"
    _columns = {
        'setting': fields.many2one('clubit.tools.settings', 'Settings', ondelete='cascade', required=True, select=True),
        'partner': fields.many2one('res.partner', 'Partner', ondelete='cascade', required=True, select=True),
        'active': fields.boolean('Active'),
        'name': fields.char('Name', size=50),
        'url': fields.char('Address', size=256, required=True),
        'port': fields.integer('Port', required=True),
        'user': fields.char('User', size=50, required=True),
        'password': fields.char('Password', size=100, required=True, password=True),
    }


class clubit_tools_settings(osv.Model):

    _name = "clubit.tools.settings"
    _description = "Settings model for Clubit Tools"

    _columns = {
        'no_of_processes': fields.integer('Number of processes', required=True),
        'connections': fields.one2many('clubit.tools.settings.connection', 'setting', 'Connections'),
    }

    def create(self, cr, uid, vals, context=None):
        if self.search(cr, uid, []):
            raise osv.except_osv(_('Error!'), _("Only 1 settings record allowed."))
        return super(clubit_tools_settings, self).create(cr, uid, vals, context)

    def get_settings(self, cr, uid):
        ids = self.search(cr, uid, [])
        if ids:
            return self.browse(cr, uid, ids[0])
        return False

    def get_connection(self, cr, uid, partner_id, name=False):
        settings = self.get_settings(cr, uid)
        if name:
            return next((x for x in settings.connections if x.partner.id == partner_id and x.name == name),None)
        return next((x for x in settings.connections if x.partner.id == partner_id),None)

















