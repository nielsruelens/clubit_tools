from openerp.osv import osv
from openerp.tools.translate import _
import netsvc

class clubit_tools_edi_wizard_archive_incoming(osv.TransientModel):
    _name = 'clubit.tools.edi.wizard.archive.incoming'
    _description = 'Archive EDI Documents'

    ''' clubit.tools.edi.wizard.archive.incoming:archive()
        --------------------------------------------------
        This method is used by the EDI wizard to push
        multiple documents to the workflow "archived" state.
        ---------------------------------------------------- '''
    def archive(self, cr, uid, ids, context=None):

        # Get the selected documents
        # --------------------------
        ids = context.get('active_ids',[])
        if not ids:
            raise osv.except_osv(_('Warning!'), _("You did not provide any documents to archive!"))


        # Push each document to archived
        # ------------------------------
        wf_service = netsvc.LocalService("workflow")
        for document in self.pool.get('clubit.tools.edi.document.incoming').browse(cr, uid, ids, context):
            if document.state == 'processed':
                wf_service.trg_validate(uid, 'clubit.tools.edi.document.incoming', document.id, 'button_to_archived', cr)


