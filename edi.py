from openerp.osv import osv, fields
from openerp.tools.translate import _
from os import listdir, path, makedirs
from os.path import isfile, join, split
from shutil import move
import re, netsvc, json
import datetime
from pytz import timezone
from openerp import SUPERUSER_ID


##############################################################################
#
#    This file defines the Clubit Custom EDI Framework. The Framework is
#    designed to work in a similar fashion to SAP's IDOC's.
#
#    Each EDIDocument represents an abstraction of an EDI file sent by a
#    partner that is processed by a particular flow. Each document can then
#    be processed in several ways, such as an actual submit, inline editing,...
#
#    The Framework consists out of several classes:
#
#      EDIFlow: A specific EDI flow to which documents belong. Flows cannot be
#               created manually but become available as modules implement this
#               framework to provide an EDI Flow.
#
#      Partner: An extension to the partner module to mark a partner as
#               EDI relevant, and to subscribe to a number of flows.
#
#      EDIDocument: The main class representing an abstraction of an EDI file.
#                   A document always belongs to an EDI Flow & partner and has
#                   a given state & state history and allows for several
#                   processing options.
#
##############################################################################


_directory_edi_base = "EDI"



##############################################################################
#
#    clubit.tools.edi.flow
#
#    The EDIFlow class defines the model layout for an EDI Flow. A Flow
#    has a name and a direction. A Flow cannot be directly maintained using
#    a screen in OpenERP. You define a new flow in another module together
#    with how it should be processed. Look for config.xml files in other modules.
#
##############################################################################
class clubit_tools_edi_flow(osv.Model):
    _name = "clubit.tools.edi.flow"
    _columns = {
        'name' : fields.char('Flow Name', size=64, required=True, readonly=True),
        'direction': fields.selection([('in', 'Incoming'), ('out', 'Outgoing')], 'Direction', required=True, readonly=True),
        'model': fields.char('Model Name', size=64, required=True, readonly=True),
        'method': fields.char('Method Name', size=64, required=False, readonly=True),
        'validator': fields.char('Validator Name', size=64, required=False, readonly=True),
        'partner_resolver': fields.char('Partner Resolver Name', size=64, required=False, readonly=True),
    }







##############################################################################
#
#    clubit.tools.edi.partnerflow
#
#    The PartnerFlow class defines the relation to a partner and an EDIFlow.
#    You can temporarily disable a flow so it becomes unavailable.
#
##############################################################################
class clubit_tools_edi_partnerflow(osv.Model):
    _name = "clubit.tools.edi.partnerflow"
    _columns = {
        'partnerflow_id': fields.many2one('res.partner', 'Partner Flow Name', ondelete='cascade', required=True, select=True, readonly=False),
        'flow_id': fields.many2one('clubit.tools.edi.flow', 'Flow', required=True, select=True, readonly=False),
        'partnerflow_active' : fields.boolean('Active'),
    }




##############################################################################
#
#    clubit.tools.edi.partner
#
#    The Partner class defines an extension on the basic partner model
#    to able to define a partner as being EDI relevant. You can then enter
#    the base EDI folder location where EDI document files will be maintained.
#    A partner can also subscribe to EDIFlows, and they can be temporarily
#    deactivated.
#
##############################################################################
class res_partner(osv.Model):
    _name = "res.partner"
    _inherit = "res.partner"
    _columns = {
        'edi_relevant' : fields.boolean('EDI Relevant'),
        'edi_flows': fields.one2many('clubit.tools.edi.partnerflow', 'partnerflow_id', 'EDI Flows', readonly=False),
    }


    ''' res.partner:create()
        --------------------------------------------
        This method overwrites the standard OpenERP create() method to make
        sure all required EDI directories are created.
        -------------------------------------------------------------------- '''
    def create(self, cr, uid, vals, context=None):
        new_id = super(res_partner, self).create(cr, uid, vals, context=context)
        self.maintain_edi_directories(cr, uid, [new_id], context)
        self.update_partner_overview_file(cr, uid, context)
        return new_id


    ''' res.partner:write()
        --------------------------------------------
        This method overwrites the standard OpenERP write() method to make
        sure all required EDI directories are created.
        -------------------------------------------------------------------- '''
    def write(self, cr, uid, ids, vals, context=None):
        result = super(res_partner, self).write(cr, uid, ids, vals, context=context)
        self.maintain_edi_directories(cr, uid, ids, context)
        self.update_partner_overview_file(cr, uid, context)
        return result





    ''' res.partner:maintain_edi_directories()
        --------------------------------------------
        This method creates all EDI directories for a given set of partners.
        A root folder based on the partner_id is created, with a et of sub
        folders for all the EDI flows he is subscried to.
        -------------------------------------------------------------------- '''
    def maintain_edi_directories(self, cr, uid, ids, context=None):


        # Only process partners that are EDI relevant
        # -------------------------------------------
        for partner in self.browse(cr, uid, ids, context=context):
            if not partner.edi_relevant:
                continue


            # Find and/or create the root directory for this partner
            # ------------------------------------------------------
            root_path = join(_directory_edi_base, cr.dbname, str(partner.id))
            if not path.exists(root_path):
                makedirs(root_path)



            # Loop over all the EDI Flows this partner is subscribed to
            # and make sure all the necessary sub folders exist.
            # ---------------------------------------------------------
            for flow in partner.edi_flows:
                sub_path = join(root_path, str(flow.flow_id.id))
                if not path.exists(sub_path): makedirs(sub_path)


                # Create folders to help the system keep track
                # --------------------------------------------
                if flow.flow_id.direction == 'in':
                    if not path.exists(join(sub_path, 'imported')):   makedirs(join(sub_path, 'imported'))
                    if not path.exists(join(sub_path, 'archived')):   makedirs(join(sub_path, 'archived'))




    ''' res.partner:update_partner_overview_file()
        ------------------------------------------
        This method creates a file for eachin the root EDI directory to give a matching
        list of partner_id's with their current corresponding names for easier
        lookups.
        ----------------------------------------------------------------------- '''
    def update_partner_overview_file(self, cr, uid, context):

        # Find all active EDI partners
        # ----------------------------
        partner_db = self.pool.get('res.partner')
        pids = partner_db.search(cr, uid, [('edi_relevant', '=', True)])
        if not pids:
            return True


        # Loop over each partner and create a simple info list
        # ----------------------------------------------------
        partners = partner_db.browse(cr, uid, pids, None)
        content = ""
        for partner in partners:
            content += str(partner.id) + " " + partner.name + "\n"

            for flow in partner.edi_flows:
                content += "\t" + str(flow.flow_id.id) + " " + flow.flow_id.name + "\n"

        # Write this info to a helper file
        # --------------------------------
        path = join(_directory_edi_base, cr.dbname, "partners.edi")
        f = open(path ,"w")
        f.write(content)
        f.close()


    def listen_to_edi_flow(self, cr, uid, partner_id, flow_id):
        ''' res.partner:listen_to_edi_flow()
        ------------------------------------
        This method adds an EDI flow to a partner.
        ------------------------------------------ '''
        if not partner_id or not flow_id: return False

        partner = self.browse(cr, uid, partner_id)
        exists = [flow for flow in partner.edi_flows if flow.flow_id.id == flow_id]
        if exists:
            vals = {'edi_flows': [[1, exists[0].id, {'partnerflow_active': True, 'flow_id': flow_id}]]}
            return self.write(cr, uid, [partner_id], vals)
        else:
            vals = {'edi_flows': [[0, False, {'partnerflow_active': True, 'flow_id': flow_id}]]}
            return self.write(cr, uid, [partner_id], vals)





##############################################################################
#
#    clubit.tools.edi.document
#
#    The document class is the heart of the framework. A document is an
#    abstraction of a file in a given flow for a given partner. It can be
#    processed in many ways and has a given state/state history.
#
##############################################################################
class clubit_tools_edi_document(osv.Model):
    _name = "clubit.tools.edi.document"
    _inherit = ['mail.thread']
    _description = "EDI Document"

    _error_file_already_exists_at_destination = 'file_already_exists_at_destination'
    _error_file_move_failed                   = 'file_move_failed'


    ''' clubit.tools.edi.document:_function_message_get()
        --------------------------------------------
        This method helps to dynamically calculate the
        message field to always show the latest OpenChatter message body.
        ----------------------------------------------------------------- '''
    def _function_message_get(self, cr, uid, ids, field, arg, context=None):
        res = dict.fromkeys(ids, False)
        for document in self.browse(cr, uid, ids, context=context):
            res[document.id] = re.sub('<[^<]+?>', '',document.message_ids[0].body)
        return res


    _columns = {
        'name' : fields.char('Name', size=256, required=True, readonly=True),
        'location' : fields.char('File location', size=256, required=True, readonly=False),
        'partner_id': fields.many2one('res.partner', 'Partner', readonly=True, required=True),
        'flow_id': fields.many2one('clubit.tools.edi.flow', 'EDI Flow', readonly=True, required=True),
        'message': fields.function(_function_message_get, type='char', string='Message'),
        'reference' : fields.char('Reference', size=64, required=False, readonly=True),
        'state': fields.selection([('new', 'New'),
                                   ('ready', 'Ready'),
                                   ('processing', 'Processing'),
                                   ('in_error', 'In Error'),
                                   ('processed', 'Processed'),
                                   ('archived', 'Archived')], 'State', required=True, readonly=True),
        'content' : fields.text('Content',readonly=True, states={'new': [('readonly', False)], 'in_error': [('readonly', False)]}),
        'create_date':fields.datetime('Creation date'),
    }


    ''' clubit.tools.edi.document:unlink()
        --------------------------------------------
        This method overwrites the default unlink/delete() method
        to make sure a document can only be deleted when it's
        in state "in_error"
        --------------------------------------------------------- '''
    def unlink(self, cr, uid, ids, context=None):
        assert len(ids) == 1
        document = self.browse(cr, uid, ids, context=context)[0]
        if document.state != 'in_error':
            raise osv.except_osv(_('Document deletion failed!'), _('You may only delete a document when it is in state error.'))
        return super(clubit_tools_edi_document, self).unlink(cr, uid, ids, context=context)



    ''' clubit.tools.edi.document:check_location()
        ------------------------------------------
        This method checks wether or not the documents corresponding
        file is still where it's supposed to be.
        ------------------------------------------------------------ '''
    def check_location(self, cr, uid, doc_id, context):

        document = self.browse(cr, uid, doc_id, context=context)
        return isfile(join(document.location, document.name))



    ''' clubit.tools.edi.document:move()
        --------------------------------
        This method moves a file/document from a
        given state to another.
        ---------------------------------------- '''
    def move(self, cr, uid, doc_id, to_folder, context):

        # Before we try to move the file, check if
        # its still there and everything is ok
        # ----------------------------------------
        if not self.check_location(cr, uid, doc_id, context ):
            return False


        # The moving of files should be allowed so let's carry on!
        # --------------------------------------------------------
        document = self.browse(cr, uid, doc_id, context=context)
        from_path = join(document.location, document.name)
        to_path   = False


        # Specialized path determination for state:new, given
        # that the file isn't part of the directory structure yet
        # -------------------------------------------------------
        if document.state == 'new':
            to_path = join(document.location, to_folder, document.name)

        # Path determination for archiving
        # --------------------------------
        else:
            path, dummy = split(document.location)
            to_path = join(path, to_folder, document.name)


        # Make sure the file doesn't exist already
        # at the to_path location
        # ----------------------------------------
        if isfile(to_path):
            self.message_post(cr, uid, document.id, body='Could not move file, it already exists at the destination folder.')
            return {'error' : self._error_file_already_exists_at_destination}


        # Actually try to move the file using shutil.move()
        # This step also includes serious error handling to validate
        # the file was actually moved so we can catch a corrupted document
        # ----------------------------------------------------------------
        try:
            move(from_path, to_path)
        except Exception:
            self.message_post(cr, uid, document.id, body='An unknown error occurred during the moving of the file.')
            return {'error' : self._error_file_move_failed}



        # Check if the move actually took place
        # -------------------------------------
        if isfile(join(document.location, document.name)):
            self.message_post(cr, uid, document.id, body='File moving failed, it is still present at the starting location.')
            return {'error' : self._error_file_move_failed}
        elif isfile(to_path) == False:
            self.message_post(cr, uid, document.id, body='File moving failed, it is not present at the target location.')
            return {'error' : self._error_file_move_failed}


        path, dummy = split(to_path)
        self.write(cr, uid, document.id, {'location' : path}, context)
        return True














##############################################################################
#
#    clubit.tools.edi.document.incoming
#
#    The incoming document class represents an incoming file and is subject
#    to the most complicated workflow in the EDI system.
#
##############################################################################
class clubit_tools_edi_document_incoming(osv.Model):
    _name = "clubit.tools.edi.document.incoming"
    _inherit = ['clubit.tools.edi.document']
    _description = "Incoming EDI Document"

    _columns = {
        'processed': fields.boolean('Processed', readonly=True),
    }



    ''' clubit.tools.edi.document.incoming:create_from_file()
        -----------------------------------------------------
        This method is a wrapper method for the standard
        OpenERP create() method. It will prepare the vals[] for
        the standard method based on the file's location, flow & partner.
        ----------------------------------------------------------------- '''
    def create_from_file(self, cr, uid, location, name):

        if isfile(join(location, name)) == False:
            raise osv.except_osv(_('Error!'), _('File not found: {!s}'.format(join(location, name))))

        vals = {}
        vals['name'] = name
        vals['location'] = location

        folders = []
        path = location
        while 1:
            path, folder = split(path)
            if folder != "":
                folders.append(folder)
            else:
                if path != "":
                    folders.append(path)
                break
        folders.reverse()

        vals['partner_id'] = folders[len(folders) - 2]
        vals['flow_id'] = folders[len(folders) - 1]
        vals['state'] = 'new'

        # Read the file contents
        # ----------------------
        with open (join(location, name), "r") as f:
            vals['content'] = f.read()



        # Create the actual EDI document, triggering
        # the workflow to start
        # ------------------------------------------
        new_id = self.create(cr, uid, vals, None)
        if new_id != False:
            self.move(cr, uid, new_id, 'imported', None)
        return new_id




    ''' clubit.tools.edi.document.incoming:import_process()
        ---------------------------------------------------
        This method reads the file system for all EDI active partners and
        their corresponding flows and will import the files to create active
        EDI documents. Once a file has been imported as a document, it needs
        to go through the entire EDI workflow process.
        -------------------------------------------------------------------- '''
    def import_process(self, cr, uid):

        # Find all active EDI partners
        # ----------------------------
        partner_db = self.pool.get('res.partner')
        pids = partner_db.search(cr, uid, [('edi_relevant', '=', True)])
        if not pids:
            return True



        # Loop over each individual partner and scrobble through their active flows
        # -------------------------------------------------------------------------
        partners = partner_db.browse(cr, uid, pids, None)
        for partner in partners:

            root_path = join(_directory_edi_base, cr.dbname, str(partner.id))
            if not path.exists(root_path):
                raise osv.except_osv(_('Error!'), _('EDI folder missing for partner {!s}'.format(str(partner.id))))

            for flow in partner.edi_flows:
                if flow.partnerflow_active == False or flow.flow_id.direction != 'in': continue


                # We've found an active flow, let's check for new files
                # A file is determined as new if it isn't assigned to a
                # workflow folder yet.
                # -----------------------------------------------------
                sub_path = join(root_path, str(flow.flow_id.id))
                if not path.exists(sub_path):
                    raise osv.except_osv(_('Error!'), _('EDI folder missing for partner {!s}, flow {!s}'.format(flow.flow_id.name)))

                files = [ f for f in listdir(sub_path) if isfile(join(sub_path, f)) ]
                if not files: continue


                # If we get all the way over here, it means we've
                # actually found some new files :)
                # -----------------------------------------------
                for f in files:

                    # Entering ultra defensive mode: make sure that this
                    # file isn't already converted to an EDI document yet!
                    # ----------------------------------------------------
                    duplicate = self.search(cr, uid, [('partner_id', '=', partner.id),
                                                      ('flow_id', '=', flow.flow_id.id),
                                                      ('name', '=', f)])
                    if len(duplicate) > 0: continue


                    # Actually create a new EDI Document
                    # This also triggers the workflow creation
                    # ----------------------------------------
                    self.create_from_file(cr, uid, sub_path, f)

        return True




    ''' clubit.tools.edi.document.incoming:document_process()
        -----------------------------------------------------
        This method is the main scheduler which will process all the
        incoming EDI documents which are currently waiting in status 'ready'.
        The process will move all the documents to the state "processing".
        --------------------------------------------------------------------- '''
    def document_process(self, cr, uid):

        # Find all documents that are ready to be processed
        # -------------------------------------------------
        documents = self.search(cr, uid, [('state', '=', 'ready')])
        if not documents:
            return True

        # Mark all of these documents as in 'processing' to make sure they don't
        # get picked up twice. The actual processing will be done for us by the
        # workflow method action_processed().
        # ----------------------------------------------------------------------
        wf_service = netsvc.LocalService("workflow")
        for document in documents:
            wf_service.trg_validate(uid, 'clubit.tools.edi.document.incoming', document, 'document_processor_pickup', cr)

        return True







    ''' clubit.tools.edi.document.incoming:valid()
        ------------------------------------------
        This method checks wether or not the current document
        is valid according to the relevant EDI Flow implementation.
        If there is no implementation, it is valid by default.
        ----------------------------------------------------------- '''
    def valid(self, cr, uid, ids, *args):

        assert len(ids) == 1
        document = self.browse(cr, uid, ids[0], None)


        # Perform a basic JSON validation
        # -------------------------------
        try:
            data = json.loads(document.content)
            if not data:
                self.message_post(cr, uid, document.id, body='Error found: content is not valid JSON.')
                return False
        except Exception:
            self.message_post(cr, uid, document.id, body='Error found: content is not valid JSON.')
            return False


        # Perform custom validation
        # -------------------------
        if not document.flow_id.validator:
            return True

        validator = getattr(self.pool.get(document.flow_id.model), document.flow_id.validator)
        try:
            return validator(cr, uid, document.id, None)
        except Exception as e:
            self.message_post(cr, uid, document.id, body='Error occurred during validation, most likely due to a program error:{!s}'.format(str(e)))
            #self.message_post(cr, uid, document.id, body='Error occurred during validation, most likely due to a program error')
            return False





    ''' clubit.tools.edi.document.incoming:action_new()
        -----------------------------------------------
        This method is called when the object is created by the
        workflow engine. The object already exists at this point
        and we'll use this method to move the file into the EDI
        document system. This method will also trigger the
        automated validation workflow steps.
        -------------------------------------------------------- '''
    def action_new(self, cr, uid, ids):
        assert len(ids) == 1
        self.write(cr, uid, ids, { 'state' : 'new' })
        return True



    ''' clubit.tools.edi.document.incoming:action_in_error()
        ----------------------------------------------------
        This method can be called from a number of places. For example
        when a user tries to mark a document as ready, or if processing
        resulted in an error. Putting a document in error will also
        put the "processed" attribute back to false.
        --------------------------------------------------------------- '''
    def action_in_error(self, cr, uid, ids):
        assert len(ids) == 1
        self.write(cr, uid, ids, { 'state' : 'in_error', 'processed' : False })
        return True



    ''' clubit.tools.edi.document.incoming:action_ready()
        -------------------------------------------------
        This method is called when the user marks the document as
        ready. This means the document is ready to be picked up
        by the EDI Processing scheduler. Before the document is put
        to ready, it first passed through the validator() method
        *if* there's one defined in the concrete EDI Flow implementation
        ---------------------------------------------------------------- '''
    def action_ready(self, cr, uid, ids):
        assert len(ids) == 1
        self.message_post(cr, uid, ids[0], body='EDI Document marked as ready for processing.')
        self.write(cr, uid, ids, { 'state' : 'ready' })
        return True



    ''' clubit.tools.edi.document.incoming:action_processing()
        ------------------------------------------------------
        This method is called by the document_processor to mark
        documents as in processing. This is to make sure that documents
        don't get picked up by the system twice.
        --------------------------------------------------------------- '''
    def action_processing(self, cr, uid, ids):
        assert len(ids) == 1
        self.write(cr, uid, ids, { 'state' : 'processing' })
        return True



    ''' clubit.tools.edi.document.incoming:action_processed()
        -----------------------------------------------------
        This method is called by the document_processor to mark
        documents as having been processed. A user can't call this
        method manually.
        ---------------------------------------------------------- '''
    def action_processed(self, cr, uid, ids):
        assert len(ids) == 1

        document = self.browse(cr, uid, ids[0], None)
        processor = getattr(self.pool.get(document.flow_id.model), document.flow_id.method)
        result = False
        try:
            result = processor(cr, uid, document.id, None)
        except Exception:
            self.message_post(cr, uid, document.id, body='Error occurred during processing, likely due to a program error.')
            self.write(cr, uid, ids, { 'state' : 'processed' })
        if result:
            self.message_post(cr, uid, document.id, body='EDI Document successfully processed.')
            self.write(cr, uid, ids, { 'state' : 'processed', 'processed' : True })
        else:
            self.message_post(cr, uid, document.id, body='Error occurred during processing, the action was not completed.')
            self.write(cr, uid, ids, { 'state' : 'processed' })

        return True





    ''' clubit.tools.edi.document.incoming:action_archive()
        ---------------------------------------------------
        This method is called when the user marks the document
        as ready for archiving. This is the final step in the
        workflow and marks it is being done.
        ------------------------------------------------------ '''
    def action_archive(self, cr, uid, ids):
        assert len(ids) == 1
        self.write(cr, uid, ids, { 'state' : 'archived' })
        self.move(cr, uid, ids[0], 'archived', None)
        self.message_post(cr, uid, ids[0], body='EDI Document successfully archived.')
        return True












##############################################################################
#
#    clubit.tools.edi.document.outgoing
#
#    The outgoing document class represents an outgoing file.
#
##############################################################################
class clubit_tools_edi_document_outgoing(osv.Model):
    _name = "clubit.tools.edi.document.outgoing"
    _inherit = ['clubit.tools.edi.document']
    _description = "Outgoing EDI Document"

    _flow_not_found        = 'flow_not_found'
    _content_invalid       = 'content_invalid'
    _no_listening_partners = 'no_listening_partners'
    _file_creation_error   = 'file_creation_error'


    ''' clubit.tools.edi.document.outgoing:create_from_content()
        --------------------------------------------------------
        This method accepts content and creates an EDI document
        for each currently actively listening partner.
        ------------------------------------------------------- '''
    def create_from_content(self, cr, uid, reference, content, partner_id, model, method):


        # Resolve the method to an EDI flow
        # ---------------------------------
        flow_db = self.pool.get('clubit.tools.edi.flow')
        flow = flow_db.search(cr, uid, [('model', '=', model),('method', '=', method)])[0]
        if not flow:
            return self._flow_not_found
        flow = flow_db.browse(cr, uid, flow, None)


        # Make sure the provided content is valid JSON
        # --------------------------------------------
        try:
            data = json.loads(json.dumps(content))
            if not data: return self._content_invalid
        except Exception as e:
            return self._content_invalid


        # Start preparing the document
        # ----------------------------
        vals = {}

        # get user's timezone
        user_db = self.pool.get('res.users')
        user = user_db.browse(cr, SUPERUSER_ID, uid)
        if user.partner_id.tz:
            tz = timezone(user.partner_id.tz) or timezone('UTC')
        else:
            tz = timezone('UTC')
        now = datetime.datetime.now(tz)
        vals['name'] = reference.replace("/", "_") + '_' + now.strftime("%d_%m_%Y_%H_%M_%S") + ".json"
        vals['flow_id'] = flow.id
        vals['content'] = json.dumps(content)
        vals['reference'] = reference
        vals['partner_id'] = partner_id
        vals['location']   = join(_directory_edi_base, cr.dbname, str(partner_id), str(flow.id))
        vals['state'] = 'new'

        # Create the EDI document
        # -----------------------
        super(clubit_tools_edi_document, self).create(cr, uid, vals, None)

        # Physically create the file
        # --------------------------
        try:
            f = open(join(vals['location'], vals['name']), "w")
            f.write(json.dumps(content))
            f.close()
        except Exception:
            return self._file_creation_error

        return True




    ''' clubit.tools.edi.document.outgoing:action_new()
        -----------------------------------------------
        This method is called when the object is created by the
        workflow engine. The object already exists at this point
        and we'll use this method to move the file into the EDI
        document system. This method will also trigger the
        automated validation workflow steps.
        -------------------------------------------------------- '''
    #def action_new(self, cr, uid, ids):
    #    assert len(ids) == 1
    #    self.write(cr, uid, ids, { 'state' : 'new' })
    #    return True

    ''' clubit.tools.edi.document.outgoing:action_archive()
        ---------------------------------------------------
        This method is called when the user marks the document
        as ready for archiving. This is the final step in the
        workflow and marks it is being done.
        ------------------------------------------------------ '''
    #def action_archive(self, cr, uid, ids):
    #    assert len(ids) == 1
    #    self.write(cr, uid, ids, { 'state' : 'archived' })
    #    self.move(cr, uid, ids[0], 'archived', None)
    #    self.message_post(cr, uid, ids[0], body='EDI Document successfully archived.')
    #    return True






























