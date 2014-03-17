{
    'name': 'clubit_tools',
    'version': '1.0',
    'category': 'Cross-Module',
    'description': "General Purpose Toolbox",
    'author': 'Niels Ruelens',
    'website': 'http://clubit.be',
    'summary': 'General Purpose Toolbox',
    'sequence': 9,
    'depends': ['base', 'mail'],
    'data': [
        'security.xml',
        'edi_view.xml',
        'edi_schedulers.xml',
        'wizard/edi_wizard_ready.xml',
        'wizard/edi_wizard_archive_incoming.xml',
        'wizard/edi_wizard_outgoing.xml',
        'edi_workflow_incoming.xml',
    ],
    'demo': [],
    'test': [],
    'css': [],
    'images': [],
    'installable': True,
    'application': False,
    'auto_install': False,
}