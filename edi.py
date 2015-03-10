from openerp.osv import osv, fields
from openerp.tools.translate import _
from os import listdir, path, makedirs
from os.path import isfile, join, split
from shutil import move
import re, netsvc, json, csv, StringIO
import datetime
import logging
from os import getcwd
from pytz import timezone
from openerp import SUPERUSER_ID
try:
    import xml.etree.cElementTree as ET
except ImportError:
    import xml.etree.ElementTree as ET

_logger = logging.getLogger(__name__)

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
        'name': fields.char('Flow Name', size=64, required=True, readonly=True),
        'direction': fields.selection([('in', 'Incoming'), ('out', 'Outgoing')], 'Direction', required=True, readonly=True),
        'model': fields.char('Model Name', size=64, required=True, readonly=True),
        'method': fields.char('Method Name', size=64, required=False, readonly=True),
        'validator': fields.char('Validator Name', size=64, required=False, readonly=True),
        'partner_resolver': fields.char('Partner Resolver Name', size=64, required=False, readonly=True),
        'process_after_create': fields.boolean('Automatically process after create'),
        'allow_duplicates': fields.boolean('Allow duplicate references'),
        'ignore_partner_ids': fields.many2many('res.partner', 'clubit_tools_ignore_partner_rel', 'flow_id', 'partner_id', help="A list of partners that need to be ignored. The content is retrieved from the edi document."),
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

    def create(self, cr, uid, vals, context=None):
        ''' res.partner:create()
        ------------------------
        This method overwrites the standard OpenERP create() method to make
        sure all required EDI directories are created.
        ------------------------------------------------------------------- '''
        new_id = super(res_partner, self).create(cr, uid, vals, context=context)
        self.maintain_edi_directories(cr, uid, [new_id], context)
        self.update_partner_overview_file(cr, uid, context)
        return new_id

    def write(self, cr, uid, ids, vals, context=None):
        ''' res.partner:write()
        -----------------------
        This method overwrites the standard OpenERP write() method to make
        sure all required EDI directories are created.
        ------------------------------------------------------------------ '''
        result = super(res_partner, self).write(cr, uid, ids, vals, context=context)
        self.maintain_edi_directories(cr, uid, ids, context)
        self.update_partner_overview_file(cr, uid, context)
        return result

    def maintain_edi_directories(self, cr, uid, ids, context=None):
        ''' res.partner:maintain_edi_directories()
        ------------------------------------------
        This method creates all EDI directories for a given set of partners.
        A root folder based on the partner_id is created, with a et of sub
        folders for all the EDI flows he is subscried to.
        -------------------------------------------------------------------- '''

        _logger.debug('Maintaining the EDI directories')
        _logger.debug('The present working directory is: {!s}'.format(getcwd()))

        # Only process partners that are EDI relevant
        # -------------------------------------------
        for partner in self.browse(cr, uid, ids, context=context):
            if not partner.edi_relevant:
                continue
            _logger.debug("Processing partner %d (%s)", partner.id, partner.name)

            # Find and/or create the root directory for this partner
            # ------------------------------------------------------
            root_path = join(_directory_edi_base, cr.dbname, str(partner.id))
            if not path.exists(root_path):
                _logger.debug('Required directory missing, attempting to create: {!s}'.format(root_path))
                makedirs(root_path)



            # Loop over all the EDI Flows this partner is subscribed to
            # and make sure all the necessary sub folders exist.
            # ---------------------------------------------------------
            for flow in partner.edi_flows:
                sub_path = join(root_path, str(flow.flow_id.id))
                if not path.exists(sub_path):
                    _logger.debug('Required directory missing, attempting to create: {!s}'.format(sub_path))
                    makedirs(sub_path)


                # Create folders to help the system keep track
                # --------------------------------------------
                if flow.flow_id.direction == 'in':
                    _logger.debug("Creating directories imported and archived for incoming edi documents")
                    if not path.exists(join(sub_path, 'imported')):   makedirs(join(sub_path, 'imported'))
                    if not path.exists(join(sub_path, 'archived')):   makedirs(join(sub_path, 'archived'))

    def update_partner_overview_file(self, cr, uid, context):
        ''' res.partner:update_partner_overview_file()
        ----------------------------------------------
        This method creates a file for eachin the root EDI directory to give a matching
        list of partner_id's with their current corresponding names for easier
        lookups.
        ------------------------------------------------------------------------------- '''

        _logger.debug('Updating the EDI partner overview file')
        _logger.debug('The present working directory is: {!s}'.format(getcwd()))

        # Find all active EDI partners
        # ----------------------------
        partner_db = self.pool.get('res.partner')
        pids = partner_db.search(cr, uid, [('edi_relevant', '=', True)])
        if not pids:
            return True


        # Loop over each partner and create a simple.debug list
        # ----------------------------------------------------
        partners = partner_db.browse(cr, uid, pids, None)
        content = ""
        for partner in partners:
            content += str(partner.id) + " " + partner.name + "\n"

            for flow in partner.edi_flows:
                content += "\t" + str(flow.flow_id.id) + " " + flow.flow_id.name + "\n"

        # Write this.debug to a helper file
        # --------------------------------
        if not path.exists(join(_directory_edi_base, cr.dbname)): makedirs(join(_directory_edi_base, cr.dbname))
        file_path = join(_directory_edi_base, cr.dbname, "partners.edi")
        _logger.debug('Attempting to look up the partner file at: {!s}'.format(file_path))
        f = open(file_path ,"w")
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


    def is_listening_to_flow(self, cr, uid, partner_id, flow_id):
        ''' res.partner:is_listening_to_flow()
        --------------------------------------
        This method checks wether or not a partner
        is listening to a given flow.
        ------------------------------------------ '''
        if not partner_id or not flow_id: return False

        partner = self.browse(cr, uid, partner_id)
        if not partner.edi_relevant: return False
        exists = next(flow for flow in partner.edi_flows if flow.flow_id.id == flow_id)
        if exists and exists.partnerflow_active:
            return True
        return False

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

    def _function_message_get(self, cr, uid, ids, field, arg, context=None):
        ''' clubit.tools.edi.document:_function_message_get()
        -----------------------------------------------------
        This method helps to dynamically calculate the
        message field to always show the latest OpenChatter message body.
        ----------------------------------------------------------------- '''
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

    #def unlink(self, cr, uid, ids, context=None):
    #    ''' clubit.tools.edi.document:unlink()
    #    --------------------------------------
    #    This method overwrites the default unlink/delete() method
    #    to make sure a document can only be deleted when it's
    #    in state "in_error"
    #    --------------------------------------------------------- '''
    #    assert len(ids) == 1
    #    document = self.browse(cr, uid, ids, context=context)[0]
    #    if document.state != 'in_error':
    #        raise osv.except_osv(_('Document deletion failed!'), _('You may only delete a document when it is in state error.'))
    #    return super(clubit_tools_edi_document, self).unlink(cr, uid, ids, context=context)

    def check_location(self, cr, uid, doc_id, context):
        ''' clubit.tools.edi.document:check_location()
        ----------------------------------------------
        This method checks wether or not the documents corresponding
        file is still where it's supposed to be.
        ------------------------------------------------------------ '''

        document = self.browse(cr, uid, doc_id, context=context)
        return isfile(join(document.location, document.name))

    def move(self, cr, uid, doc_id, to_folder, context):
        ''' clubit.tools.edi.document:move()
        ------------------------------------
        This method moves a file/document from a
        given state to another.
        ---------------------------------------- '''

        # Before we try to move the file, check if
        # its still there and everything is ok
        # ----------------------------------------
        if not self.check_location(cr, uid, doc_id, context ):
            _logger.debug("File for edi document %d is not at the location we expect it to be. Aborting", doc_id)
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

        _logger.debug("Moving document with id %d (%s)from folder %s to folder %s", document.id, document.name, from_path, to_path)

        # Make sure the file doesn't exist already
        # at the to_path location
        # ----------------------------------------
        #if isfile(to_path):
        #    self.message_post(cr, uid, document.id, body='Could not move file, it already exists at the destination folder.')
        #    return {'error' : self._error_file_already_exists_at_destination}


        # Actually try to move the file using shutil.move()
        # This step also includes serious error handling to validate
        # the file was actually moved so we can catch a corrupted document
        # ----------------------------------------------------------------
        try:
            move(from_path, to_path)
            _logger.debug("Move file successful")
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

    def position_document(self, cr, uid, partner_id, flow_id, content, content_type='json'):
        ''' clubit.tools.edi.document:position_document()
        -------------------------------------------------
        This method will position the given content as an EDI
        document ready to be picked up for a given partner/flow
        combination. It will make sure the partner is actually
        listening to this flow.
        ------------------------------------------------------- '''

        # Make the partner listen
        # -----------------------
        partner_db = self.pool.get('res.partner')
        partner_db.listen_to_edi_flow(cr, uid, partner_id, flow_id)

        # Create a file from the given content
        # ------------------------------------
        now = datetime.datetime.now()
        name = now.strftime("%d_%m_%Y_%H_%M_%S") + ".csv"

        path = join(_directory_edi_base, cr.dbname, str(partner_id), str(flow_id), name)
        with open(path, 'wb') as temp_file:

            if content_type == 'csv':
                writer = csv.writer(temp_file, delimiter=',', quotechar='"')
                for line in content:
                    writer.writerow(line)

            elif content_type == 'json':
                for line in content:
                    temp_file.write(line)

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

    def create_from_file(self, cr, uid, location, name):
        ''' clubit.tools.edi.document.incoming:create_from_file()
        ---------------------------------------------------------
        This method is a wrapper method for the standard
        OpenERP create() method. It will prepare the vals[] for
        the standard method based on the file's location, flow & partner.
        ----------------------------------------------------------------- '''

        _logger.debug("Creating edi document from file %s at location %s", name, location)

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
        _logger.debug("Created edi document with id %d", new_id)
        if new_id != False:
            self.move(cr, uid, new_id, 'imported', None)
        return new_id

    def create_from_web_request(self, cr, uid, partner, flow, reference, content, data_type):
        ''' clubit.tools.edi.document.incoming:create_from_web_request()
        ----------------------------------------------------------------
        This method creates a new incoming EDI document based on the
        provided input. It provides an easy way to create EDI documents using
        the web.
        -------------------------------------------------------------------- '''

        _logger.debug("Creating edi document from web request for partner %s, flow %s, reference %s", partner, flow, reference)

        # Find the correct EDI flow
        # -------------------------
        model_db = self.pool.get('ir.model.data')
        flow_id = model_db.search(cr, uid, [('name', '=', flow), ('model','=','clubit.tools.edi.flow')])
        if not flow_id or not flow: return 'Parameter "flow" could not be resolved, request aborted.'
        flow_id = model_db.browse(cr, uid, flow_id)[0]
        flow_id = flow_id.res_id
        flow_object = self.pool.get('clubit.tools.edi.flow').browse(cr, uid, flow_id)
        _logger.debug("Flow found %d (%s)", flow_id, flow_object.name)

        # Find the correct partner
        # ------------------------
        partner_id = model_db.search(cr, uid, [('name', '=', partner), ('model','=','res.partner')])
        if not partner_id or not partner: return 'Parameter "partner" could not be resolved, request aborted.'
        partner_id = model_db.browse(cr, uid, partner_id)[0]
        partner_id = partner_id.res_id
        _logger.debug("Partner found %d for name provided (%s)", partner_id, partner)

        if not reference: return 'Parameter "reference" cannot be empty, request aborted.'
        if not content:   return 'Parameter "content" cannot be empty, request aborted.'
        if data_type != 'xml' and data_type != 'json':
            return 'Parameter "data_type" should be either "xml" or "json", request aborted.'

        # Make sure the partner is listening to this flow
        # -----------------------------------------------
        partnerflow_id = self.pool.get('clubit.tools.edi.partnerflow').search(cr, uid, [('partnerflow_id','=', partner_id), ('flow_id','=', flow_id), ('partnerflow_active','=', True)])
        if not partnerflow_id: return 'The provided partner is not currently listening to the provided EDI flow, request aborted.'

        # Make sure the file doesn't already exist, unless duplicates are allowed
        # -----------------------------------------------------------------------
        filename = '.'.join([reference, data_type])
        if not flow_object.allow_duplicates:
            doc_id = self.search(cr, uid, [('flow_id', '=', flow_id), ('partner_id', '=', partner_id), ('reference', '=', reference)])
            if doc_id: return 'This reference has already been processed, request aborted.'

        location = join(_directory_edi_base, cr.dbname, str(partner_id), str(flow_id), 'imported')

        values = {
            'name'       : filename,
            'reference'  : reference,
            'partner_id' : partner_id,
            'flow_id'    : flow_id,
            'content'    : content,
            'state'      : 'new',
            'location'   : location,
        }

        # If the document creation is successful, write the file to disk
        # --------------------------------------------------------------
        doc_id = self.create(cr, uid, values)
        if not doc_id: return 'Something went wrong trying to create the EDI document, request aborted.'
        try:
            with open (join(location, filename), "w") as f:
                f.write(content.encode('utf8'))
        except Exception as e:
            self.write(cr, uid, doc_id, {'state':'in_error'})
            self.unlink(cr, uid, [doc_id])
            return 'Something went wrong writing the file to disk, request aborted. Error given: {!s}'.format(str(e))

        # Push forward the document if customized
        # ---------------------------------------
        if flow_object.process_after_create:
            wf_service = netsvc.LocalService("workflow")
            wf_service.trg_validate(uid, 'clubit.tools.edi.document.incoming', doc_id, 'button_to_ready', cr)

        return True

    def import_process(self, cr, uid):
        ''' clubit.tools.edi.document.incoming:import_process()
        -------------------------------------------------------
        This method reads the file system for all EDI active partners and
        their corresponding flows and will import the files to create active
        EDI documents. Once a file has been imported as a document, it needs
        to go through the entire EDI workflow process.
        -------------------------------------------------------------------- '''

        _logger.debug('EDI_IMPORT: Starting the EDI document import process.')

        # Find all active EDI partners
        # ----------------------------
        wf_service = netsvc.LocalService("workflow")
        partner_db = self.pool.get('res.partner')
        pids = partner_db.search(cr, uid, [('edi_relevant', '=', True)])
        if not pids:
            _logger.debug('EDI_IMPORT: No active EDI partners at the moment, processing is done.')
            return True

        # Loop over each individual partner and scrobble through their active flows
        # -------------------------------------------------------------------------
        partners = partner_db.browse(cr, uid, pids, None)
        for partner in partners:
            _logger.debug("Processing edi relevant partner %d (%s)", partner.id, partner.name)
            root_path = join(_directory_edi_base, cr.dbname, str(partner.id))
            if not path.exists(root_path):
                raise osv.except_osv(_('Error!'), _('EDI folder missing for partner {!s}'.format(str(partner.id))))
            
            if not partner.edi_flows: _logger.debug("No edi flows defined for partner %d", partner.id)

            for flow in partner.edi_flows:
                if flow.partnerflow_active == False or flow.flow_id.direction != 'in': continue
                _logger.debug("Processing active incoming flow %d (%s)", flow.id, flow.flow_id.name)

                # We've found an active flow, let's check for new files
                # A file is determined as new if it isn't assigned to a
                # workflow folder yet.
                # -----------------------------------------------------
                sub_path = join(root_path, str(flow.flow_id.id))
                if not path.exists(sub_path):
                    raise osv.except_osv(_('Error!'), _('EDI folder missing for partner {!s}, flow {!s}'.format(flow.flow_id.name)))

                files = [ f for f in listdir(sub_path) if isfile(join(sub_path, f)) ]
                if not files: 
                    _logger.debug("No files found in directory %s", sub_path)
                    continue

                # If we get all the way over here, it means we've
                # actually found some new files :)
                # -----------------------------------------------
                for f in files:
                    _logger.debug("File found in directory %s: %s", sub_path, f)
                    # Entering ultra defensive mode: make sure that this
                    # file isn't already converted to an EDI document yet!
                    # Unless this is specifically allowed by the flow
                    # ----------------------------------------------------
                    if not flow.flow_id.allow_duplicates:
                        duplicate = self.search(cr, uid, [('partner_id', '=', partner.id),
                                                          ('flow_id', '=', flow.flow_id.id),
                                                          ('name', '=', f)])
                        if len(duplicate) > 0: 
                            _logger.debug("Duplicate file. Skipping")
                            continue

                    # Actually create a new EDI Document
                    # This also triggers the workflow creation
                    # ----------------------------------------
                    new_doc = self.create_from_file(cr, uid, sub_path, f)
                    if flow.flow_id.process_after_create:
                        _logger.debug("Trigger workflow ready for edi document %d", new_doc) 
                        wf_service.trg_validate(uid, 'clubit.tools.edi.document.incoming', new_doc, 'button_to_ready', cr)

        _logger.debug('EDI_IMPORT: Document import process is done.')
        return True

    def document_process(self, cr, uid):
        ''' clubit.tools.edi.document.incoming:document_process()
        ---------------------------------------------------------
        This method is the main scheduler which will process all the
        incoming EDI documents which are currently waiting in status 'ready'.
        The process will move all the documents to the state "processing".
        --------------------------------------------------------------------- '''

        # Find all documents that are ready to be processed
        # -------------------------------------------------
        _logger.debug('DOCUMENT_PROCESS: Starting the EDI document processor.')
        documents = self.search(cr, uid, [('state', '=', 'ready')])
        if not documents:
            _logger.debug('DOCUMENT_PROCESS: No documents found, processing is done.')
            return True

        # Mark all of these documents as in 'processing' to make sure they don't
        # get picked up twice. The actual processing will be done for us by the
        # workflow method action_processed().
        # ----------------------------------------------------------------------
        wf_service = netsvc.LocalService("workflow")
        for document in documents:
            _logger.debug("Trigger workflow processing for edi document %d", document)
            wf_service.trg_validate(uid, 'clubit.tools.edi.document.incoming', document, 'document_processor_pickup', cr)

        _logger.debug('DOCUMENT_PROCESS: EDI document processor is done.')
        return True


    def valid(self, cr, uid, ids, *args):
        ''' clubit.tools.edi.document.incoming:valid()
        ----------------------------------------------
        This method checks wether or not the current document
        is valid according to the relevant EDI Flow implementation.
        If there is no implementation, it is valid by default.
        ----------------------------------------------------------- '''

        assert len(ids) == 1
        document = self.browse(cr, uid, ids[0], None)

        # Perform a basic validation, depending on the filetype
        # -----------------------------------------------------
        filetype = document.name.split('.')[-1]
        if filetype == 'csv':
            try:
                dummy_file = StringIO.StringIO(document.content)
                reader = csv.reader(dummy_file, delimiter=',', quotechar='"')
            except Exception:
                self.message_post(cr, uid, document.id, body='Error found: content is not valid CSV.')
                return False

        elif filetype == 'json':
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
        _logger.debug("Perform custom validator '%s.%s' for flow %d (%s)", document.flow_id.model, document.flow_id.validator, document.flow_id.id, document.flow_id.name)
        try:
            return validator(cr, uid, document.id, None)
        except Exception as e:
            self.message_post(cr, uid, document.id, body='Error occurred during validation, most likely due to a program error:{!s}'.format(str(e)))
            return False

    def action_new(self, cr, uid, ids):
        ''' clubit.tools.edi.document.incoming:action_new()
        ---------------------------------------------------
        This method is called when the object is created by the
        workflow engine. The object already exists at this point
        and we'll use this method to move the file into the EDI
        document system. This method will also trigger the
        automated validation workflow steps.
        -------------------------------------------------------- '''
        assert len(ids) == 1
        self.write(cr, uid, ids, { 'state' : 'new' })
        return True

    def action_in_error(self, cr, uid, ids):
        ''' clubit.tools.edi.document.incoming:action_in_error()
        --------------------------------------------------------
        This method can be called from a number of places. For example
        when a user tries to mark a document as ready, or if processing
        resulted in an error. Putting a document in error will also
        put the "processed" attribute back to false.
        --------------------------------------------------------------- '''
        assert len(ids) == 1
        self.write(cr, uid, ids, { 'state' : 'in_error', 'processed' : False })
        return True

    def action_ready(self, cr, uid, ids):
        ''' clubit.tools.edi.document.incoming:action_ready()
        -----------------------------------------------------
        This method is called when the user marks the document as
        ready. This means the document is ready to be picked up
        by the EDI Processing scheduler. Before the document is put
        to ready, it first passed through the validator() method
        *if* there's one defined in the concrete EDI Flow implementation
        ---------------------------------------------------------------- '''
        assert len(ids) == 1
        self.message_post(cr, uid, ids[0], body='EDI Document marked as ready for processing.')
        self.write(cr, uid, ids, { 'state' : 'ready' })
        return True

    def action_processing(self, cr, uid, ids):
        ''' clubit.tools.edi.document.incoming:action_processing()
        ----------------------------------------------------------
        This method is called by the document_processor to mark
        documents as in processing. This is to make sure that documents
        don't get picked up by the system twice.
        --------------------------------------------------------------- '''
        assert len(ids) == 1
        self.write(cr, uid, ids, { 'state' : 'processing' })
        return True

    def action_processed(self, cr, uid, ids):
        ''' clubit.tools.edi.document.incoming:action_processed()
        ---------------------------------------------------------
        This method is called by the document_processor to mark
        documents as having been processed. A user can't call this
        method manually.
        ---------------------------------------------------------- '''
        assert len(ids) == 1

        document = self.browse(cr, uid, ids[0], None)
        processor = getattr(self.pool.get(document.flow_id.model), document.flow_id.method)
        result = False
        try:
            result = processor(cr, uid, document.id, None)
        except Exception as e:
            self.message_post(cr, uid, document.id, body='Error occurred during processing, error given: {!s}'.format(str(e)))
            self.write(cr, uid, ids, { 'state' : 'processed' })
        if result:
            self.message_post(cr, uid, document.id, body='EDI Document successfully processed.')
            self.write(cr, uid, ids, { 'state' : 'processed', 'processed' : True })
        else:
            self.message_post(cr, uid, document.id, body='Error occurred during processing, the action was not completed.')
            self.write(cr, uid, ids, { 'state' : 'processed' })

        return True

    def action_archive(self, cr, uid, ids):
        ''' clubit.tools.edi.document.incoming:action_archive()
        -------------------------------------------------------
        This method is called when the user marks the document
        as ready for archiving. This is the final step in the
        workflow and marks it is being done.
        ------------------------------------------------------ '''
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


    def create_from_content(self, cr, uid, reference, content, partner_id, model, method, type='JSON'):
        ''' clubit.tools.edi.document.outgoing:create_from_content()
        ------------------------------------------------------------
        This method accepts content and creates an EDI document
        for each currently actively listening partner.
        ------------------------------------------------------- '''

        # Resolve the method to an EDI flow
        # ---------------------------------
        flow_db = self.pool.get('clubit.tools.edi.flow')
        flow = flow_db.search(cr, uid, [('model', '=', model),('method', '=', method)])[0]
        if not flow:
            return self._flow_not_found
        flow = flow_db.browse(cr, uid, flow, None)

        # Make sure the provided content is valid
        # ---------------------------------------
        if type == 'JSON':
            try:
                data = json.loads(json.dumps(content))
                if not data: return self._content_invalid
            except Exception:
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
        vals['flow_id'] = flow.id

        if type == 'STRING':
            vals['name'] = reference.replace("/", "_") + '_' + now.strftime("%d_%m_%Y_%H_%M_%S") + ".json"
            vals['content'] = content
        elif type == 'XML':
            vals['name'] = reference.replace("/", "_") + '_' + now.strftime("%d_%m_%Y_%H_%M_%S") + ".xml"
            vals['content'] = ET.tostring(content, encoding='UTF-8', method='xml')
        else:
            vals['name'] = reference.replace("/", "_") + '_' + now.strftime("%d_%m_%Y_%H_%M_%S") + ".json"
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
            f.write(vals['content'])
            f.close()
        except Exception as e:
            return str(e)

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

