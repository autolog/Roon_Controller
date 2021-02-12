from __future__ import unicode_literals
import logging
ServiceRegistry     = "com.roonlabs.registry:1"
ServiceTransport    = "com.roonlabs.transport:2"
ServiceStatus       = "com.roonlabs.status:1"
ServicePairing      = "com.roonlabs.pairing:1"
ServicePing         = "com.roonlabs.ping:1"
ServiceImage        = "com.roonlabs.image:1"
ServiceBrowse       = "com.roonlabs.browse:1"
ServiceSettings     = "com.roonlabs.settings:1"
ControlVolume       = "com.roonlabs.volumecontrol:1"
ControlSource       = "com.roonlabs.sourcecontrol:1"

MessageRequest      = "REQUEST"
MessageComplete     = "COMPLETE"
MessageContinue     = "CONTINUE"

REGISTERED = "Registered"

# logformat = logging.Formatter('%(asctime)-15s %(levelname)-5s  %(module)s -- %(message)s')
# LOGGER = logging.getLogger("roonapi")
# consolehandler = logging.StreamHandler()
# consolehandler.setFormatter(logformat)
# LOGGER.addHandler(consolehandler)
# LOGGER.setLevel(logging.INFO)