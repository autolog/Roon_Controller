#! /usr/bin/env python
# -*- coding: utf-8 -*-
#
# Roon Controller © Autolog 2019

try:
    # noinspection PyUnresolvedReferences
    import indigo
except ImportError:
    pass

import copy
import datetime
import inspect
import logging
import os
import platform
from PIL import Image
try:
    # noinspection PyUnresolvedReferences
    import requests
except ImportError:
    pass
from shutil import copyfile
import socket
import sys

from constants import *
from roon import RoonApi


def mkdir_with_mode(directory):
    # Forces Read | Write on creation so that the plugin can delete the folder id required
    if not os.path.isdir(directory):
        oldmask = os.umask(000)
        os.makedirs(directory, 0o777)
        os.umask(oldmask)


# noinspection PyUnresolvedReferences,PyAttributeOutsideInit,PyPep8
class Plugin(indigo.PluginBase):

    # noinspection PyStringFormat,PyStringFormat
    def __init__(self, plugin_id, plugin_display_name, plugin_version, plugin_prefs):

        indigo.PluginBase.__init__(self, plugin_id, plugin_display_name, plugin_version, plugin_prefs)

        # Initialise dictionary to store plugin Globals
        self.globals = dict()

        # Initialise Indigo plugin info
        self.globals['pluginInfo'] = dict()
        self.globals['pluginInfo']['pluginId'] = plugin_id
        self.globals['pluginInfo']['pluginDisplayName'] = plugin_display_name
        self.globals['pluginInfo']['pluginVersion'] = plugin_version
        self.globals['pluginInfo']['path'] = indigo.server.getInstallFolderPath()  # e.g. '/Library/Application Support/Perceptive Automation/Indigo 7.2'
        self.globals['pluginInfo']['apiVersion'] = indigo.server.apiVersion
        self.globals['pluginInfo']['address'] = indigo.server.address

        # Initialise dictionary for debug in plugin Globals
        self.globals['debug'] = dict()
        self.globals['debug']['general'] = logging.INFO  # For general debugging of the main thread
        self.globals['debug']['methodTrace'] = logging.INFO  # For displaying method invocations i.e. trace method

        self.globals['debug']['previousGeneral'] = logging.INFO  # For general debugging of the main thread
        self.globals['debug']['previousMethodTrace'] = logging.INFO  # For displaying method invocations i.e. trace method

        self.globals['debug']['methodTraceActive'] = False

        # Setup Logging
        logformat = logging.Formatter('%(asctime)s.%(msecs)03d\t%(levelname)-12s\t%(name)s.%(funcName)-25s %(msg)s', datefmt='%Y-%m-%d %H:%M:%S')
        self.plugin_file_handler.setFormatter(logformat)
        self.plugin_file_handler.setLevel(logging.INFO)  # Master Logging Level for Plugin Log file
        self.indigo_log_handler.setLevel(logging.INFO)   # Logging level for Indigo Event Log
        self.general_logger = logging.getLogger("Plugin.general")
        self.general_logger.setLevel(self.globals['debug']['general'])
        self.method_tracer = logging.getLogger("Plugin.method")  
        self.method_tracer.setLevel(self.globals['debug']['methodTrace'])

        # Now logging is set-up, output Initialising message

        startup_message_ui = '\n'  # Start with a line break
        startup_message_ui += u'{:=^130}\n'.format(' Initializing Roon Controller Plugin for Indigo 7.3 ')
        startup_message_ui += u'{:<31} {}\n'.format('Plugin Name:', self.globals['pluginInfo']['pluginDisplayName'])
        startup_message_ui += u'{:<31} {}\n'.format('Plugin Version:', self.globals['pluginInfo']['pluginVersion'])
        startup_message_ui += u'{:<31} {}\n'.format('Plugin ID:', self.globals['pluginInfo']['pluginId'])
        startup_message_ui += u'{:<31} {}\n'.format('Indigo Version:', indigo.server.version)
        startup_message_ui += u'{:<31} {}\n'.format('Indigo API Version:', indigo.server.apiVersion)
        startup_message_ui += u'{:<31} {}\n'.format('Python Version:', sys.version.replace('\n', ''))
        startup_message_ui += u'{:<31} {}\n'.format('Mac OS Version:', platform.mac_ver()[0])
        startup_message_ui += u'{:=^130}\n'.format('')
        self.general_logger.info(startup_message_ui)

        # Initialise dictionary to store configuration info
        self.globals['config'] = dict()
        self.globals['config']['printOutputsSummary'] = True  
        self.globals['config']['printOutput'] = True  
        self.globals['config']['printZonesSummary'] = True  
        self.globals['config']['printZone'] = True  
        self.globals['config']['roonDeviceFolderName'] = ''
        self.globals['config']['roonDeviceFolderId'] = 0 
        self.globals['config']['roonCoreIpAddress'] = '' 
               
        # Initialise dictionary to store internal details about Roon
        self.globals['roon'] = dict()
        self.globals['roon']['indigoDeviceBeingDeleted'] = dict()
        self.globals['roon']['zones'] = dict()
        self.globals['roon']['outputs'] = dict()

        self.globals['roon']['mapZone'] = dict()  
        self.globals['roon']['mapOutput'] = dict()
        self.globals['roon']['zoneUniqueIdentityKeyToZoneId'] = dict()
        self.globals['roon']['zoneUniqueIdentityKeyToDevId'] = dict()
        self.globals['roon']['outputIdToDevId'] = dict()

        self.globals['roon']['pluginPrefsFolder'] = '{}/Preferences/Plugins/com.autologplugin.indigoplugin.rooncontroller'.format(self.globals['pluginInfo']['path'])
        if not os.path.exists(self.globals['roon']['pluginPrefsFolder']):
            mkdir_with_mode(self.globals['roon']['pluginPrefsFolder'])

        self.globals['roon']['availableOutputNumbers'] = OUTPUT_MAP_NUMBERS
        self.globals['roon']['availableZoneAlphas'] = ZONE_MAP_ALPHAS

        for dev in indigo.devices.iter("self"):
            if dev.deviceTypeId == 'roonOutput':
                output_number = dev.address.split('-')[1]  # dev.address = e.g. 'OUTPUT-6' which gives '6'
                if len(output_number) == 1:
                    output_number = ' {}'.format(output_number)
                output_id = dev.pluginProps.get('roonOutputId', '')
                if output_id != '':
                    self.globals['roon']['outputIdToDevId'][output_id] = dev.id
                try:
                    self.globals['roon']['availableOutputNumbers'].remove(output_number)
                except ValueError:
                    self.general_logger.error(u'Roon Output \'{}\' device with address \'{}\' invalid:  Address number \'{}\' already allocated!:\n{}\n'.format(dev.name, dev.address, output_number, self.globals['roon']['availableOutputNumbers']))

                self.disconnectRoonOutputDevice(dev.id)

            elif dev.deviceTypeId == 'roonZone':
                zone_alpha = dev.address.split('-')[1]  # dev.address = e.g. 'ZONE-A-2' which gives 'A'
                if len(zone_alpha) == 1:
                    zone_alpha = ' {}'.format(zone_alpha)
                zone_unique_identity_key = dev.pluginProps.get('roonZoneUniqueIdentityKey', '')
                if zone_unique_identity_key != '':
                    self.globals['roon']['zoneUniqueIdentityKeyToDevId'][zone_unique_identity_key] = dev.id
                try:
                    self.globals['roon']['availableZoneAlphas'].remove(zone_alpha)
                except ValueError:
                    self.general_logger.error(u'Roon Zone \'{}\' device with address \'{}\' invalid:  Address letter \'{}\' already allocated!:\n{}\n'.format(dev.name, dev.address, zone_alpha, self.globals['roon']['availableZoneAlphas']))

                self.disconnectRoonZoneDevice(dev.id)

        # Remove image  files for deleted or renamed Indigo Roon Zone devices
        dir_list = [d for d in os.listdir(self.globals['roon']['pluginPrefsFolder']) if os.path.isdir(os.path.join(self.globals['roon']['pluginPrefsFolder'], d))]
        for dir_name in dir_list:
            dir_alpha = dir_name.split('-')[1]  # dev.address = e.g. 'ZONE-A-2' which gives 'A' or 'ZONE-CD-1' which gives 'CD'
            if len(dir_alpha) == 1:
                dir_alpha = ' {}'.format(dir_alpha)
            if dir_alpha in self.globals['roon']['availableZoneAlphas']:
                dir_path_and_name = os.path.join(self.globals['roon']['pluginPrefsFolder'], dir_name)
                file_list = os.listdir(dir_path_and_name)
                for fileName in file_list:
                    os.remove(os.path.join(dir_path_and_name, fileName))
                os.rmdir(dir_path_and_name)    

        self.globals['devicesToRoonControllerTable'] = dict()

        # Initialise dictionary for constants
        self.globals['constant'] = dict()
        self.globals['constant']['defaultDatetime'] = datetime.datetime.strptime('2000-01-01', '%Y-%m-%d')

        # Initialise info to register with the Roon API
        self.globals['roon']['extensionInfo'] = dict()
        self.globals['roon']['extensionInfo']['extension_id'] = 'indigo_plugin_roon'
        self.globals['roon']['extensionInfo']['display_name'] = 'Indigo Plugin for Roon'
        self.globals['roon']['extensionInfo']['display_version'] = '1.0.0'
        self.globals['roon']['extensionInfo']['publisher'] = 'autolog'
        self.globals['roon']['extensionInfo']['email'] = 'my@email.com'

        # Set Plugin Config Values
        self.getPrefsConfigUiValues()
        self.closedPrefsConfigUi(plugin_prefs, False)
 
    def __del__(self):

        indigo.PluginBase.__del__(self)

    def startup(self):
        if self.globals['debug']['methodTraceActive']: self.method_tracer.threaddebug(u'Method Start: Line {}'.format(inspect.currentframe().f_lineno))

        try:
            indigo.devices.subscribeToChanges()

            self.general_logger.debug(u'Roon \'availableOutputNumbers\':\n{}\n'.format(self.globals['roon']['availableOutputNumbers']))

            self.general_logger.debug(u'Roon \'availableZoneAlphas\':\n{}\n'.format(self.globals['roon']['availableZoneAlphas']))

            self.globals['roon']['token'] = None

            self.globals['roon']['tokenFile'] = '{}/roon_token.txt'.format(self.globals['roon']['pluginPrefsFolder'])

            if os.path.isfile(self.globals['roon']['tokenFile']):
                with open(self.globals['roon']['tokenFile']) as f:
                    self.globals['roon']['token'] = f.read()

            self.general_logger.debug(u'\'Roon Controller\' token [0]: {}'.format(self.globals['roon']['token']))

            if self.globals['config']['roonCoreIpAddress'] == '':
                self.general_logger.error(u'\'Roon Controller\' has no Roon Core IP Address specified in Plugin configuration - correct and then restart plugin.')
                return False

            self.globals['roon']['api'] = RoonApi(self.globals['roon']['extensionInfo'], self.globals['roon']['token'], self.globals['config']['roonCoreIpAddress'])
            self.globals['roon']['api'].register_state_callback(self.processRoonStateCallback)
            # self.globals['roon']['api'].register_queue_callback(self.processRoonQueueCallback)

            # self.globals['roon']['api'].register_volume_control('Indigo', 'Indigo', self.processRoonVolumeControl)

            self.general_logger.debug(u'\'Roon Controller\' token [1]: {}'.format(self.globals['roon']['token']))

            self.globals['roon']['token'] = self.globals['roon']['api'].token
            self.general_logger.debug(u'\'Roon Controller\' token [2]: {}'.format(self.globals['roon']['token']))

            if self.globals['roon']['token']:
                with open(self.globals['roon']['tokenFile'], "w") as f:
                    f.write(self.globals['roon']['token'])

            self.globals['roon']['zones'] = copy.deepcopy(self.globals['roon']['api'].zones)
            self.globals['roon']['outputs'] = copy.deepcopy(self.globals['roon']['api'].outputs)

            self.processOutputs(self.globals['roon']['outputs'])
            self.processZones(self.globals['roon']['zones'])

            # self.printKnownZonesSummary('INITIALISATION')

            self.general_logger.info(u'\'Roon Controller\' initialization complete.')

        except StandardError as e:
            self.general_logger.error(u'\'startup\' error detected. Line \'{}\' has error=\'{}\''.format(sys.exc_traceback.tb_lineno, e))   

        finally:
            if self.globals['debug']['methodTraceActive']: self.method_tracer.threaddebug(u'Method End: Line {}'.format(inspect.currentframe().f_lineno))

    def getPrefsConfigUiValues(self):
        if self.globals['debug']['methodTraceActive']: self.method_tracer.threaddebug(u'Method Start: Line {}'.format(inspect.currentframe().f_lineno))

        prefsConfigUiValues = self.pluginPrefs

        if "roonVariableFolderName" not in prefsConfigUiValues:
            prefsConfigUiValues["roonVariableFolderName"] = ''

        self.general_logger.debug(u'ROONVARIABLEFOLDERNAME = {}'.format(prefsConfigUiValues["roonVariableFolderName"]))


        if "roonCoreIpAddress" not in prefsConfigUiValues:
            prefsConfigUiValues["roonCoreIpAddress"] = ''
        if "autoCreateDevices" not in prefsConfigUiValues:
            prefsConfigUiValues["autoCreateDevices"] = False
        if "roonDeviceFolderName" not in prefsConfigUiValues:
            prefsConfigUiValues["roonDeviceFolderName"] = 'Roon'
        if "dynamicGroupedZonesRename" not in prefsConfigUiValues:
            prefsConfigUiValues["dynamicGroupedZonesRename"] = True

        if self.globals['debug']['methodTraceActive']: self.method_tracer.threaddebug(u'Method End: Line {}'.format(inspect.currentframe().f_lineno))

        return prefsConfigUiValues

    def validatePrefsConfigUi(self, valuesDict):
        if self.globals['debug']['methodTraceActive']: self.method_tracer.threaddebug(u'Method Start: Line {}'.format(inspect.currentframe().f_lineno))

        try:
            ipAddress = valuesDict.get('roonCoreIpAddress', '')
        
            try:
                socket.inet_aton(ipAddress)
            except:
                errorDict = indigo.Dict()
                errorDict["roonCoreIpAddress"] = "Roon Core IP Address is invalid"
                errorDict["showAlertText"] = "You must enter a valid Roon Core IP Addres to be able to connect to the Roon Core."
                return False, valuesDict, errorDict

        except StandardError as e:
            self.general_logger.error(u'\'validatePrefsConfigUi\' error detected. Line \'{}\' has error=\'{}\''.format(sys.exc_traceback.tb_lineno, e))   

        finally:
            if self.globals['debug']['methodTraceActive']: self.method_tracer.threaddebug(u'Method End: Line {}'.format(inspect.currentframe().f_lineno))

            return True, valuesDict


    def closedPrefsConfigUi(self, valuesDict, userCancelled):
        if self.globals['debug']['methodTraceActive']: self.method_tracer.threaddebug(u'Method Start: Line {}'.format(inspect.currentframe().f_lineno))

        try:
            self.general_logger.debug(u'\'closePrefsConfigUi\' called with userCancelled = {}'.format(str(userCancelled)))  

            if userCancelled:
                return

            # ### IP Address ###

            self.globals['config']['roonCoreIpAddress'] = valuesDict.get('roonCoreIpAddress', '')

            # ### AUTO-CREATE DEVICES + DEVICE FOLDER ###
            self.globals['config']['autoCreateDevices'] = valuesDict.get("autoCreateDevices", False)
            self.globals['config']['roonDeviceFolderName'] = valuesDict.get("roonDeviceFolderName", 'Roon')
            self.globals['config']['dynamicGroupedZonesRename'] = valuesDict.get("dynamicGroupedZonesRename", True)

            # Create Roon Device folder name (if specific device folder required)
            if self.globals['config']['roonDeviceFolderName'] == '':
                self.globals['config']['roonDeviceFolderId'] = 0  # No specific device folder required
            else:
                if self.globals['config']['roonDeviceFolderName'] not in indigo.devices.folders:
                    indigo.devices.folder.create(self.globals['config']['roonDeviceFolderName'])
                self.globals['config']['roonDeviceFolderId'] = indigo.devices.folders.getId(self.globals['config']['roonDeviceFolderName'])

            # Create Roon Variable folder name (if required)
            self.globals['config']['roonVariableFolderName'] = valuesDict.get("roonVariableFolderName", '')

            self.globals['config']['roonVariableFolderId'] = 0  # Not required

            
            if self.globals['config']['roonVariableFolderName'] != '':

                if self.globals['config']['roonVariableFolderName'] not in indigo.variables.folders:
                    indigo.variables.folder.create(self.globals['config']['roonVariableFolderName'])

                self.globals['config']['roonVariableFolderId'] = indigo.variables.folders[self.globals['config']['roonVariableFolderName']].id

            self.general_logger.debug(u'ROONVARIABLEFOLDERID = {}, ROONVARIABLEFOLDERNAME = {}'.format(self.globals['config']['roonVariableFolderId'], self.globals['config']['roonVariableFolderName']))

            # Check monitoring / debug options  
            self.setDebuggingLevels(valuesDict)

        except StandardError as e:
            self.general_logger.error(u'\'closedPrefsConfigUi\' error detected. Line \'{}\' has error=\'{}\''.format(sys.exc_traceback.tb_lineno, e))   

        finally:
            if self.globals['debug']['methodTraceActive']: self.method_tracer.threaddebug(u'Method End: Line {}'.format(inspect.currentframe().f_lineno))

            return True

    def setDebuggingLevels(self, valuesDict):

        if self.globals['debug']['methodTraceActive']: self.method_tracer.threaddebug(u'Method Start: Line {}'.format(inspect.currentframe().f_lineno))

        try:
            self.globals['debug']['enabled'] = bool(valuesDict.get("debugEnabled", False))

            self.globals['debug']['general'] = logging.INFO  # For general debugging of the main thread
            self.globals['debug']['roonHandler'] = logging.INFO  # For debugging messages
            self.globals['debug']['methodTrace'] = logging.INFO  # For displaying method invocations i.e. trace method
            self.globals['debug']['polling'] = logging.INFO  # For polling debugging

            self.globals['debug']['methodTraceActive'] = False

            if not self.globals['debug']['enabled']:
                self.plugin_file_handler.setLevel(logging.INFO)
            else:
                self.plugin_file_handler.setLevel(logging.THREADDEBUG)

            debugGeneral = bool(valuesDict.get("debugGeneral", False))
            debugRoonHandler = bool(valuesDict.get("debugRoonHandler", False))
            debugMethodTrace = bool(valuesDict.get("debugMethodTrace", False))

            if debugGeneral:
                self.globals['debug']['general'] = logging.DEBUG  # For general debugging of the main thread
                self.general_logger.setLevel(self.globals['debug']['general'])
            if debugRoonHandler:
                self.globals['debug']['roonHandler'] = logging.DEBUG  # For debugging Roon handler thread
            if debugMethodTrace:
                self.globals['debug']['methodTrace'] = logging.THREADDEBUG  # For displaying method invocations i.e. trace method
                # self.globals['debug']['methodTrace'] = logging.DEBUG  # For displaying method invocations i.e. trace method
                self.method_tracer.setLevel(self.globals['debug']['methodTrace'])

            self.globals['debug']['active'] = debugGeneral or debugRoonHandler or debugMethodTrace or debugPolling

            if not self.globals['debug']['enabled'] or not self.globals['debug']['active']:
                self.general_logger.info(u'No debugging requested for Roon plugin')
            else:
                debugTypes = []
                if debugGeneral:
                    debugTypes.append('General')
                if debugRoonHandler:
                    debugTypes.append('Roon Handler')
                if debugMethodTrace:
                    debugTypes.append('Method Trace')
                    self.globals['debug']['methodTraceActive'] = True
                message = self.listActiveDebugging(debugTypes)   
                self.general_logger.warning(u'The debugging options enabled for the Roon plugin are: {}'.format(message))

        except StandardError as e:
            self.general_logger.error(u'\'setDebuggingLevels\' error detected. Line \'{}\' has error=\'{}\''.format(sys.exc_traceback.tb_lineno, e))   

        finally:
            if self.globals['debug']['methodTraceActive']: self.method_tracer.threaddebug(u'Method End: Line {}'.format(inspect.currentframe().f_lineno))

    def listActiveDebugging(self, monitorDebugTypes):            
        if self.globals['debug']['methodTraceActive']: self.method_tracer.threaddebug(u'Method Start: Line {}'.format(inspect.currentframe().f_lineno))

        try:
            loop = 0
            listedTypes = ''
            for monitorDebugType in monitorDebugTypes:
                if loop == 0:
                    listedTypes = listedTypes + monitorDebugType
                else:
                    listedTypes = listedTypes + ', ' + monitorDebugType
                loop += 1
            return listedTypes

        except StandardError as e:
            self.general_logger.error(u'\'listActiveDebugging\' error detected. Line \'{}\' has error=\'{}\''.format(sys.exc_traceback.tb_lineno, e))   

        finally:
            if self.globals['debug']['methodTraceActive']: self.method_tracer.threaddebug(u'Method End: Line {}'.format(inspect.currentframe().f_lineno))

    def uiTime(self, seconds):
        # if self.globals['debug']['methodTraceActive']: self.method_tracer.threaddebug(u'Method Start: Line {}'.format(inspect.currentframe().f_lineno))

        try:
            m, s = divmod(seconds, 60)
            h, m = divmod(m, 60)
            if h == 0:
                return u'{:d}:{:02d}'.format(m, s)
            else:
                return u'{:d}:{:02d}:{:02d}'.format(h, m, s)

        except StandardError as e:
            self.general_logger.error(u'\'uiTime\' error detected. Line \'{}\' has error=\'{}\''.format(sys.exc_traceback.tb_lineno, e))   

        # finally:
        #     if self.globals['debug']['methodTraceActive']: self.method_tracer.threaddebug(u'Method End: Line {}'.format(inspect.currentframe().f_lineno))

    def processRoonVolumeControl(self, control_key, event, data):

        try:
            self.general_logger.error('\'processRoonVolumeControl\' --> control_key: \'{}\', event: \'{}\' - data: \'{}\''.format(control_key, event, data))
            # just echo back the new value to set it
            # if event == "set_mute":
            #     roonapi.update_volume_control(control_key, mute=data)
            # elif event == "set_volume":
            #     roonapi.update_volume_control(control_key, volume=data)
        except StandardError as e:
            self.general_logger.error(u'\'processRoonVolumeControl\' error detected. Line \'{}\' has error=\'{}\''.format(sys.exc_traceback.tb_lineno, e))   


    def processRoonStateCallback(self, event, changed_items):
        # if self.globals['debug']['methodTraceActive']: self.method_tracer.threaddebug(u'Method Start: Line {}'.format(inspect.currentframe().f_lineno))

        try:

            if event == 'zones_seek_changed':
                self.processZonesSeekChanged(event, changed_items)

            elif event == 'zones_changed':
                self.processZonesChanged(event, changed_items)

            elif event == 'zones_added':
                self.processZonesAdded(event, changed_items)

            elif  event == 'zones_removed':
                self.processZonesRemoved(event, changed_items)

            elif  event == 'outputs_changed':
                self.processOutputsChanged(event, changed_items)

            elif  event == 'outputs_added':
                self.processOutputsAdded(event, changed_items)

            elif  event == 'outputs_removed':
                self.processOutputsRemoved(event, changed_items)

        except StandardError as e:
            self.general_logger.error(u'\'processRoonStateCallback\' error detected. Line \'{}\' has error=\'{}\''.format(sys.exc_traceback.tb_lineno, e))   

        # finally:
        #     if self.globals['debug']['methodTraceActive']: self.method_tracer.threaddebug(u'Method End: Line {}'.format(inspect.currentframe().f_lineno))

    def printKnownZonesSummary(self, title):
        if self.globals['debug']['methodTraceActive']: self.method_tracer.threaddebug(u'Method Start: Line {}'.format(inspect.currentframe().f_lineno))

        try:
            if self.globals['config']['printZonesSummary']:
                logout = u'\n#################### {} ####################'.format(title)
                logout = logout + u'\nInternal Zone table\n'
                for zone_id in self.globals['roon']['zones']:
                    if 'display_name' in self.globals['roon']['zones'][zone_id]:
                        zone_display_name = self.globals['roon']['zones'][zone_id]['display_name']
                    else:
                        zone_display_name = 'NONE'
                    logout = logout + u'\nZone \'{}\' - Zone ID = \'{}\''.format(zone_display_name, zone_id)
                logout = logout + u'\nIndigo Zone Devices\n'
                for dev in indigo.devices.iter("self"):
                    if dev.deviceTypeId == 'roonZone':
                        zone_id = dev.pluginProps.get('roonZoneId', '-- Zone ID not set!')
                        logout = logout + u'\nIndigo Device \'{}\' - Zone ID = \'{}\', Status =  \'{}\''.format(dev.name, zone_id, dev.states['zone_status'])
                logout = logout + u'\n####################\n'
                self.general_logger.info(logout)

        except StandardError as e:
            self.general_logger.error(u'\'printKnownZonesSummary\' error detected. Line \'{}\' has error=\'{}\''.format(sys.exc_traceback.tb_lineno, e))   

        finally:
            if self.globals['debug']['methodTraceActive']: self.method_tracer.threaddebug(u'Method End: Line {}'.format(inspect.currentframe().f_lineno))

    def printKnownOutputsSummary(self, title):
        if self.globals['debug']['methodTraceActive']: self.method_tracer.threaddebug(u'Method Start: Line {}'.format(inspect.currentframe().f_lineno))

        try:
            if self.globals['config']['printOutputsSummary']:
                logout = '\n#################### {} ####################\n'.format(title)
                for output_id in self.globals['roon']['outputs']:
                    if 'display_name' in self.globals['roon']['outputs'][output_id]:
                        outputdisplay_name = self.globals['roon']['outputs'][output_id]['display_name']
                    else:
                        outputdisplay_name = 'NONE'
                    logout = logout + 'Output \'{}\' - Output ID = \'{}\''.format(outputdisplay_name, output_id)
                logout = logout + '####################\n'
                self.general_logger.debug(logout)

        except StandardError as e:
            self.general_logger.error(u'\'printKnownOutputsSummary\' error detected. Line \'{}\' has error=\'{}\''.format(sys.exc_traceback.tb_lineno, e))   

        finally:
            if self.globals['debug']['methodTraceActive']: self.method_tracer.threaddebug(u'Method End: Line {}'.format(inspect.currentframe().f_lineno))

    def processZonesSeekChanged(self, event, changed_items):
        # if self.globals['debug']['methodTraceActive']: self.method_tracer.threaddebug(u'Method Start: Line {}'.format(inspect.currentframe().f_lineno))

        zoneData = None
        try:
            for zone_id in changed_items:
                zoneData = copy.deepcopy(self.globals['roon']['api'].zone_by_zone_id(zone_id))

                self.globals['roon']['zones'][zone_id]['queue_items_remaining'] = zoneData['queue_items_remaining']
                self.globals['roon']['zones'][zone_id]['queue_time_remaining'] = zoneData['queue_time_remaining']
                if 'seek_position' in zoneData:
                    self.globals['roon']['zones'][zone_id]['seek_position'] = zoneData['seek_position']
                    if self.globals['roon']['zones'][zone_id]['seek_position'] is None:
                        self.globals['roon']['zones'][zone_id]['seek_position'] = 0
                        self.globals['roon']['zones'][zone_id]['remaining'] = 0
                    else:
                        if 'now_playing' in zoneData and 'length' in zoneData['now_playing']:
                            self.globals['roon']['zones'][zone_id]['remaining'] = int(zoneData['now_playing']['length']) - int(self.globals['roon']['zones'][zone_id]['seek_position'])
                        else:
                            self.globals['roon']['zones'][zone_id]['remaining'] = 0
                else:
                    self.globals['roon']['zones'][zone_id]['seek_position'] = 0
                    self.globals['roon']['zones'][zone_id]['remaining'] = 0

                self.globals['roon']['zones'][zone_id]['state'] = zoneData.get('state', '-stopped-')
                # if zone_id != '12345678':
                    # self.general_logger.error(u'==> ROON SEEK CHANGE ZONE \'{}\' DATA STATE <== :{}'.format(zone_id, self.globals['roon']['zones'][zone_id]['state']))             
                    # self.general_logger.error(u'==> ROON SEEK CHANGE ZONE \'{}\' DATA <== :{}'.format(zone_id, zoneData))             

                if 'zoneUniqueIdentityKey' in self.globals['roon']['zones'][zone_id]:
                    zone_unique_identity_key = self.globals['roon']['zones'][zone_id]['zoneUniqueIdentityKey']
                else:
                    zone_unique_identity_key = 'NONE'
                if zone_unique_identity_key in self.globals['roon']['zoneUniqueIdentityKeyToDevId'] and zone_unique_identity_key != 'NONE':
                    roonZoneDevId = self.globals['roon']['zoneUniqueIdentityKeyToDevId'][zone_unique_identity_key]

                    ui_queue_time_remaining = self.uiTime(self.globals['roon']['zones'][zone_id]['queue_time_remaining'])
                    ui_seek_position = self.uiTime(self.globals['roon']['zones'][zone_id]['seek_position'])
                    ui_remaining = self.uiTime(self.globals['roon']['zones'][zone_id]['remaining'])

                    zone_dev = indigo.devices[roonZoneDevId]
                    key_value_list = [
                        {'key': 'queue_items_remaining', 'value': self.globals['roon']['zones'][zone_id]['queue_items_remaining']},
                        {'key': 'queue_time_remaining', 'value': self.globals['roon']['zones'][zone_id]['queue_time_remaining']},
                        {'key': 'seek_position', 'value': self.globals['roon']['zones'][zone_id]['seek_position']},
                        {'key': 'remaining', 'value': self.globals['roon']['zones'][zone_id]['remaining']},
                        {'key': 'state', 'value': self.globals['roon']['zones'][zone_id]['state']},
                        {'key': 'ui_queue_time_remaining', 'value': ui_queue_time_remaining},
                        {'key': 'ui_seek_position', 'value': ui_seek_position},
                        {'key': 'ui_remaining', 'value': ui_remaining}
                    ]

                    if zone_dev.states['state'] != self.globals['roon']['zones'][zone_id]['state']:
                        key_value_list.append({'key': 'state', 'value': self.globals['roon']['zones'][zone_id]['state']})
                        if self.globals['roon']['zones'][zone_id]['state'] == 'playing':
                            zone_dev.updateStateImageOnServer(indigo.kStateImageSel.AvPlaying)
                        elif self.globals['roon']['zones'][zone_id]['state'] == 'paused':
                            zone_dev.updateStateImageOnServer(indigo.kStateImageSel.AvPaused)
                        else:
                            zone_dev.updateStateImageOnServer(indigo.kStateImageSel.AvStopped)
                    if zone_dev.states['zone_status'] != self.globals['roon']['zones'][zone_id]['state']:
                        key_value_list.append({'key': 'zone_status', 'value': self.globals['roon']['zones'][zone_id]['state']})

                    zone_dev.updateStatesOnServer(key_value_list)

        except StandardError as e:
            self.general_logger.error(u'\'processZonesSeekChanged\' error detected. Line \'{}\' has error=\'{}\'\nZoneData:\n{}\n'.format(sys.exc_traceback.tb_lineno, e, zoneData))

        # finally:
        #     if self.globals['debug']['methodTraceActive']: self.method_tracer.threaddebug(u'Method End: Line {}'.format(inspect.currentframe().f_lineno))

    def processZonesChanged(self, event, changed_items):
        if self.globals['debug']['methodTraceActive']: self.method_tracer.threaddebug(u'Method Start: Line {}'.format(inspect.currentframe().f_lineno))

        try:
            # self.printKnownZonesSummary('PROCESS ZONES CHANGED')

            for zone_id in changed_items:

                zoneData = copy.deepcopy(self.globals['roon']['api'].zone_by_zone_id(zone_id))
                self.processZone(zone_id, zoneData)

                zoneUniqueIdentityKey = self.globals['roon']['zones'][zone_id]['zoneUniqueIdentityKey']
                if zoneUniqueIdentityKey in self.globals['roon']['zoneUniqueIdentityKeyToDevId']:
                    roonZoneDevId = self.globals['roon']['zoneUniqueIdentityKeyToDevId'][zoneUniqueIdentityKey]
                    self.updateRoonZoneDevice(roonZoneDevId, zone_id)
                    self.general_logger.debug(u'\'ZONE CHANGED\' - Zone \'{}\'. Indigo Device = \'{}\', Unique ID = \'{}\''.format(self.globals['roon']['zones'][zone_id]['display_name'], indigo.devices[roonZoneDevId].name, zoneUniqueIdentityKey))
                else:
                    self.general_logger.debug(u'\'ZONE CHANGED\' - Zone \'{}\' no matching Indigo device. Unique ID = \'{}\''.format(self.globals['roon']['zones'][zone_id]['display_name'], zoneUniqueIdentityKey))

        except StandardError as e:
            self.general_logger.error(u'\'processZonesChanged\' error detected. Line \'{}\' has error=\'{}\''.format(sys.exc_traceback.tb_lineno, e))   

        finally:
            if self.globals['debug']['methodTraceActive']: self.method_tracer.threaddebug(u'Method End: Line {}'.format(inspect.currentframe().f_lineno))

    def processZonesAdded(self, event, changed_items):
        if self.globals['debug']['methodTraceActive']: self.method_tracer.threaddebug(u'Method Start: Line {}'.format(inspect.currentframe().f_lineno))

        try:
            # self.printKnownZonesSummary('PROCESS ZONES ADDED')

            for zone_id in changed_items:
                zoneData = copy.deepcopy(self.globals['roon']['api'].zone_by_zone_id(zone_id))
                self.processZone(zone_id, zoneData)
                zoneUniqueIdentityKey = self.globals['roon']['zones'][zone_id]['zoneUniqueIdentityKey']
                self.general_logger.debug(u'\'processZonesAdded\' - Zone \'{}\'. Zone ID = \'{}\', Unique ID = \'{}\'\nZoneData:\n{}\n'.format(self.globals['roon']['zones'][zone_id]['display_name'], zone_id, zoneUniqueIdentityKey, zoneData))

                if zoneUniqueIdentityKey in self.globals['roon']['zoneUniqueIdentityKeyToDevId']:
                    roonZoneDevId = self.globals['roon']['zoneUniqueIdentityKeyToDevId'][zoneUniqueIdentityKey]
                    self.updateRoonZoneDevice(roonZoneDevId, zone_id)
                    self.general_logger.debug(u'\'processZonesAdded\' - Zone \'{}\'. Indigo Device = \'{}\', Zone ID = \'{}\', Unique ID = \'{}\''.format(self.globals['roon']['zones'][zone_id]['display_name'], indigo.devices[roonZoneDevId].name, zone_id, zoneUniqueIdentityKey))
                else:
                    self.general_logger.debug(u'\'processZonesAdded\' - Zone \'{}\' no matching Indigo device. Zone ID = \'{}\', Unique ID = \'{}\''.format(self.globals['roon']['zones'][zone_id]['display_name'], zone_id, zoneUniqueIdentityKey))

                    if self.globals['config']['autoCreateDevices']:
                        self.autoCreateZoneDevice(zone_id, zoneUniqueIdentityKey)

        except StandardError as e:
            self.general_logger.error(u'\'processZonesAdded\' error detected. Line \'{}\' has error=\'{}\''.format(sys.exc_traceback.tb_lineno, e))   

        finally:
            if self.globals['debug']['methodTraceActive']: self.method_tracer.threaddebug(u'Method End: Line {}'.format(inspect.currentframe().f_lineno))

    def autoCreateZoneDevice(self, zone_id, zoneUniqueIdentityKey):
        if self.globals['debug']['methodTraceActive']: self.method_tracer.threaddebug(u'Method Start: Line {}'.format(inspect.currentframe().f_lineno))

        try:
            self.general_logger.debug(u'Roon \'availableZoneAlphas\':\n{}\n'.format(self.globals['roon']['availableZoneAlphas']))

            outputCount = self.globals['roon']['zones'][zone_id]['outputs_count']
            addressAlpha = self.globals['roon']['availableZoneAlphas'].pop(0)
            if addressAlpha[0:1] == ' ':
                addressAlpha = addressAlpha[1:2]
            if outputCount > 0:              
                address = 'ZONE-{}-{}'.format(addressAlpha, outputCount)
            else:
                address = 'ZONE-{}'.format(addressAlpha)

            zone_name = u'{}'.format(self.globals['roon']['zones'][zone_id]['display_name'])



            if outputCount == 0:
                device_name = u'Roon Zone - {}'.format(zone_name)
            else:
                temp_zone_name = self.globals['roon']['zones'][zone_id]['outputs'][1]['display_name']
                for i in range(2, outputCount + 1):
                    temp_zone_name = '{} + {}'.format(temp_zone_name, self.globals['roon']['zones'][zone_id]['outputs'][i]['display_name'])
                device_name = u'Roon Zone - {}'.format(temp_zone_name)



            self.general_logger.debug(u'\'autoCreateZoneDevice\' - Creating Indigo Zone Device with Name: \'{}\', Zone Name: \'{}\',\nZone Unique Identity Key: \'{}\''.format(device_name, zone_name, zoneUniqueIdentityKey))

            defaultdynamicGroupedZonesRename = self.globals['config']['dynamicGroupedZonesRename']

            zone_dev = (indigo.device.create(protocol=indigo.kProtocol.Plugin,
                   address=address,
                   name=device_name,
                   description='Roon Zone',
                   pluginId="com.autologplugin.indigoplugin.rooncontroller",
                   deviceTypeId="roonZone",
                   props={"roonZoneName": zone_name,
                          "roonZoneId": zone_id,
                          "roonZoneUniqueIdentityKey": zoneUniqueIdentityKey,
                          "roonZoneUniqueIdentityKeyUi": zoneUniqueIdentityKey,
                          "autoNameNewRoonZone": True,
                          "dynamicGroupedZoneRename": defaultdynamicGroupedZonesRename},
                   folder=self.globals['config']['roonDeviceFolderId']))

            self.globals['roon']['zoneUniqueIdentityKeyToDevId'][zoneUniqueIdentityKey] = zone_dev.id

        except StandardError as e:
            self.general_logger.error(u'\'autoCreateZoneDevice\' error detected. Line \'{}\' has error=\'{}\''.format(sys.exc_traceback.tb_lineno, e))   

        finally:
            if self.globals['debug']['methodTraceActive']: self.method_tracer.threaddebug(u'Method End: Line {}'.format(inspect.currentframe().f_lineno))

    def processZonesRemoved(self, event, changed_items):
        if self.globals['debug']['methodTraceActive']: self.method_tracer.threaddebug(u'Method Start: Line {}'.format(inspect.currentframe().f_lineno))

        try:
            self.general_logger.debug(u'\'ZONE REMOVED\' INVOKED')
            # self.printKnownZonesSummary('PROCESS ZONES REMOVED [START]')
            
            for zone_id in changed_items:
                zone_display_name = 'Unknown Zone'
                zone_unique_identity_key = 'None'
                if zone_id in self.globals['roon']['zones']:
                    self.general_logger.debug(u'\'processZonesRemoved\' - Zone:\n{}'.format(self.globals['roon']['zones'][zone_id]))

                    if 'display_name' in self.globals['roon']['zones'][zone_id]:
                        zone_display_name = self.globals['roon']['zones'][zone_id]['display_name']
                    if 'zoneUniqueIdentityKey' in self.globals['roon']['zones'][zone_id]:
                        zone_unique_identity_key = self.globals['roon']['zones'][zone_id]['zoneUniqueIdentityKey']
                        if zone_unique_identity_key in self.globals['roon']['zoneUniqueIdentityKeyToDevId']:
                            roonZoneDevId = self.globals['roon']['zoneUniqueIdentityKeyToDevId'][zone_unique_identity_key]
                            self.disconnectRoonZoneDevice(roonZoneDevId)
                            self.general_logger.debug(u'\'processZonesRemoved\' - Zone \'{}\'. Indigo Device = \'{}\', Zone ID = \'{}\', Unique ID = \'{}\''.format(self.globals['roon']['zones'][zone_id]['display_name'], indigo.devices[roonZoneDevId].name, zone_id, zone_unique_identity_key))
                        else:
                            self.general_logger.debug(u'\'processZonesRemoved\' - Zone \'{}\' no matching Indigo device. Unique ID = \'{}\''.format(zone_display_name, zone_unique_identity_key))
                    else:
                        self.general_logger.debug(u'\'processZonesRemoved\' - Zone \'{}\', Zone ID = \'{}\' no matching Indigo device. Unique ID = \'{}\''.format(zone_display_name, zone_id, zone_unique_identity_key))

                    del self.globals['roon']['zones'][zone_id]

                    # self.printKnownZonesSummary('PROCESS ZONES REMOVED [ZONE REMOVED]')

                else:
                    self.general_logger.debug(u'\'processZonesRemoved\' - All Zones:\n{}'.format(self.globals['roon']['zones']))

                self.general_logger.debug(u'\'processZonesRemoved\' - Zone \'{}\'. Zone ID =  \'{}\', Unique ID = \'{}\''.format(zone_display_name, zone_id, zone_unique_identity_key))

        except StandardError as e:
            self.general_logger.error(u'\'processZonesRemoved\' error detected. Line \'{}\' has error=\'{}\''.format(sys.exc_traceback.tb_lineno, e))   

        finally:
            if self.globals['debug']['methodTraceActive']: self.method_tracer.threaddebug(u'Method End: Line {}'.format(inspect.currentframe().f_lineno))

    def processOutputsChanged(self, event, changed_items):
        if self.globals['debug']['methodTraceActive']: self.method_tracer.threaddebug(u'Method Start: Line {}'.format(inspect.currentframe().f_lineno))

        try:
            for output_id in changed_items:
                if output_id == '1701b9ea8b0814189098501722daf1427ea9':
                    tempOutputs = self.globals['roon']['api'].outputs
                    self.general_logger.debug(u'\'processOutputsChanged\' - ALL OUTPUTS = \n\n{}\n\n.'.format(tempOutputs))


                output_data = copy.deepcopy(self.globals['roon']['api'].output_by_output_id(output_id))
                processOutput_successful = self.processOutput(output_id, output_data)

                if processOutput_successful:
                    if output_id in self.globals['roon']['outputIdToDevId']:
                        roonOutputDevId = self.globals['roon']['outputIdToDevId'][output_id]
                        self.updateRoonOutputDevice(roonOutputDevId, output_id)
                        self.general_logger.debug(u'\'processOutputsChanged\' - Output \'{}\'. Indigo Device = \'{}\', Output ID = \'{}\'\nOutput Data:\n{}\n'.format(self.globals['roon']['outputs'][output_id]['display_name'], indigo.devices[roonOutputDevId].name, output_id, output_data))
                    else:
                        self.general_logger.debug(u'\'processOutputsChanged\' - Output \'{}\'. Output ID = \'{}\'\n{}'.format(self.globals['roon']['outputs'][output_id]['display_name'], output_id, output_data))

        except StandardError as e:
            self.general_logger.error(u'\'processOutputsChanged\' error detected. Line \'{}\' has error=\'{}\''.format(sys.exc_traceback.tb_lineno, e))   

        finally:
            if self.globals['debug']['methodTraceActive']: self.method_tracer.threaddebug(u'Method End: Line {}'.format(inspect.currentframe().f_lineno))

    def processOutputsAdded(self, event, changed_items):
        if self.globals['debug']['methodTraceActive']: self.method_tracer.threaddebug(u'Method Start: Line {}'.format(inspect.currentframe().f_lineno))

        try:
            for output_id in changed_items:
                if output_id == '1701b9ea8b0814189098501722daf1427ea9':
                    tempOutputs = self.globals['roon']['api'].outputs
                    self.general_logger.debug(u'\'processOutputsChanged\' - ALL OUTPUTS = \n\n{}\n\n.'.format(tempOutputs))

                output_data = copy.deepcopy(self.globals['roon']['api'].output_by_output_id(output_id))
                processOutput_successful = self.processOutput(output_id, output_data)
                # self.general_logger.debug(u'\'OUTPUTS ADDED\' - Output \'{}\'. Output ID = \'{}\'\n{}'.format(self.globals['roon']['outputs'][output_id]['display_name'], output_id, output_data))
                self.general_logger.debug(u'\'processOutputsAdded\' - Output \'{}\'. Output ID = \'{}\'\n{}'.format('TEMPORARY DEBUG NAME', output_id, output_data))

                if processOutput_successful:
                    if output_id in self.globals['roon']['outputIdToDevId']:
                        roonOutputDevId = self.globals['roon']['outputIdToDevId'][output_id]
                        self.updateRoonOutputDevice(roonOutputDevId, output_id)
                        self.general_logger.debug(u'\'processOutputsAdded\' - Output \'{}\'. Indigo Device = \'{}\', Output ID = \'{}\''.format(self.globals['roon']['outputs'][output_id]['display_name'], indigo.devices[roonOutputDevId].name, output_id))
                    else:
                        self.general_logger.debug(u'\'processOutputsAdded\' - Output \'{}\' no matching Indigo device. Output ID = \'{}\''.format(self.globals['roon']['outputs'][output_id]['display_name'], output_id))

                        if self.globals['config']['autoCreateDevices']:
                            self.autoCreateOutputDevice(output_id)

        except StandardError as e:
            self.general_logger.error(u'\'processOutputsAdded\' error detected. Line \'{}\' has error=\'{}\''.format(sys.exc_traceback.tb_lineno, e))   

        finally:
            if self.globals['debug']['methodTraceActive']: self.method_tracer.threaddebug(u'Method End: Line {}'.format(inspect.currentframe().f_lineno))

    def nowPlayingVariables(self, filter="", valuesDict=None, typeId="", targetId=0):
        if self.globals['debug']['methodTraceActive']: self.method_tracer.threaddebug(u'Method Start: Line {}'.format(inspect.currentframe().f_lineno))

        try:
            myArray = []
            for var in indigo.variables:
                if self.globals['config']['roonVariableFolderId'] == 0:
                    myArray.append((var.id, var.name))
                else:
                    if var.folderId == self.globals['config']['roonVariableFolderId']:
                        myArray.append((var.id, var.name))

            myArraySorted = sorted(myArray, key=lambda varname: varname[1].lower())   # sort by variable name
            myArraySorted.insert(0, (0, 'NO NOW PLAYING VARIABLE'))
            myArraySorted.insert(0, (-1, '-- Select Now Playing Variable --'))

            return myArraySorted

        except StandardError as e:
            self.general_logger.error(u'\'nowPlayingVariables\' error detected. Line \'{}\' has error=\'{}\''.format(sys.exc_traceback.tb_lineno, e))   

        finally:
            if self.globals['debug']['methodTraceActive']: self.method_tracer.threaddebug(u'Method End: Line {}'.format(inspect.currentframe().f_lineno))

    def autoCreateOutputDevice(self, output_id):
        if self.globals['debug']['methodTraceActive']: self.method_tracer.threaddebug(u'Method Start: Line {}'.format(inspect.currentframe().f_lineno))

        try:
            self.general_logger.debug(u'Roon \'availableOutputNumbers\':\n{}\n'.format(self.globals['roon']['availableOutputNumbers']))

            addressNumber = self.globals['roon']['availableOutputNumbers'].pop(0)
            if addressNumber[0:1] == ' ':
                addressNumber = addressNumber[1:2]
            address = 'OUT-{}'.format(addressNumber)

            output_name = u'Roon Output - {}'.format(self.globals['roon']['outputs'][output_id]['display_name'])

            output_dev = (indigo.device.create(protocol=indigo.kProtocol.Plugin,
                   address=address,
                   name=output_name,
                   description='Roon Output',
                   pluginId="com.autologplugin.indigoplugin.rooncontroller",
                   deviceTypeId="roonOutput",
                   props={"roonOutputId": output_id,
                          "roonOutputIdUi": output_id,
                          "autoNameNewRoonOutput": True},
                   folder=self.globals['config']['roonDeviceFolderId']))

            self.globals['roon']['outputIdToDevId'][output_id] = output_dev.id             

        except StandardError as e:
            self.general_logger.error(u'\'autoCreateOutputDevice\' error detected. Line \'{}\' has error=\'{}\''.format(sys.exc_traceback.tb_lineno, e))   

        finally:
            if self.globals['debug']['methodTraceActive']: self.method_tracer.threaddebug(u'Method End: Line {}'.format(inspect.currentframe().f_lineno))

    def processOutputsRemoved(self, event, changed_items):
        if self.globals['debug']['methodTraceActive']: self.method_tracer.threaddebug(u'Method Start: Line {}'.format(inspect.currentframe().f_lineno))

        try:
            self.general_logger.debug(u'\'OUTPUT REMOVED\' INVOKED')
            self.printKnownOutputsSummary('PROCESS OUTPUT REMOVED [START]')
            
            for output_id in changed_items:
                if output_id in self.globals['roon']['outputs']:
                    output_display_name = 'Unknown Output'
                    self.general_logger.debug(u'\'OUTPUT REMOVED\' - Output:\n{}'.format(self.globals['roon']['outputs'][output_id]))
                    if 'display_name' in self.globals['roon']['outputs'][output_id]:
                        output_display_name = self.globals['roon']['outputs'][output_id]['display_name']
                    if output_id in self.globals['roon']['outputIdToDevId']:
                        roonOutputDevId = self.globals['roon']['outputIdToDevId'][output_id]
                        self.disconnectRoonOutputDevice(roonOutputDevId)
                        self.general_logger.debug(u'\'OUTPUT REMOVED\' - Output \'{}\'. Indigo Device = \'{}\', Output ID = \'{}\''.format(output_display_name, indigo.devices[roonOutputDevId].name, output_id))
                    else:
                        self.general_logger.debug(u'\'OUTPUT REMOVED\' - Output \'{}\' no matching Indigo device.'.format(output_display_name))

                del self.globals['roon']['outputs'][output_id]

                self.printKnownOutputsSummary('PROCESS OUTPUTS REMOVED [OUTPUT REMOVED]')

            else:
                self.general_logger.debug(u'\'OUTPUT REMOVED\' - All Output:\n{}'.format(self.globals['roon']['outputs']))

        except StandardError as e:
            self.general_logger.error(u'\'processOutputsRemoved\' error detected. Line \'{}\' has error=\'{}\''.format(sys.exc_traceback.tb_lineno, e))   

        finally:
            if self.globals['debug']['methodTraceActive']: self.method_tracer.threaddebug(u'Method End: Line {}'.format(inspect.currentframe().f_lineno))

    def processRoonQueueCallback(self):
        if self.globals['debug']['methodTraceActive']: self.method_tracer.threaddebug(u'Method Start: Line {}'.format(inspect.currentframe().f_lineno))

        try:
            self.general_logger.debug(u'\'Roon [SELF] Queue Callback\' \'{}\': {}'.format(event, changed_items))

        except StandardError as e:
            self.general_logger.error(u'\'processRoonQueueCallback\' error detected. Line \'{}\' has error=\'{}\''.format(sys.exc_traceback.tb_lineno, e))   

        finally:
            if self.globals['debug']['methodTraceActive']: self.method_tracer.threaddebug(u'Method End: Line {}'.format(inspect.currentframe().f_lineno))

    def processZones(self, zones):
        if self.globals['debug']['methodTraceActive']: self.method_tracer.threaddebug(u'Method Start: Line {}'.format(inspect.currentframe().f_lineno))

        try:
            for zone_id, zoneData in zones.iteritems():
                self.processZone(zone_id, zoneData)
                if self.globals['config']['printZone']:  
                    self.printZone(zone_id)

        except StandardError as e:
            self.general_logger.error(u'\'processZones\' error detected. Line \'{}\' has error=\'{}\''.format(sys.exc_traceback.tb_lineno, e))   

        finally:
            if self.globals['debug']['methodTraceActive']: self.method_tracer.threaddebug(u'Method End: Line {}'.format(inspect.currentframe().f_lineno))

    def processZone(self, zone_id, zoneData):
        if self.globals['debug']['methodTraceActive']: self.method_tracer.threaddebug(u'Method Start: Line {}'.format(inspect.currentframe().f_lineno))

        try:
            self.globals['roon']['zones'][zone_id] = dict()

            self.globals['roon']['zones'][zone_id]['zone_id'] = ''
            self.globals['roon']['zones'][zone_id]['queue_items_remaining'] = 0
            self.globals['roon']['zones'][zone_id]['queue_time_remaining'] = 0
            self.globals['roon']['zones'][zone_id]['display_name'] = ''
            self.globals['roon']['zones'][zone_id]['settings'] = dict()
            self.globals['roon']['zones'][zone_id]['settings']['auto_radio'] = False
            self.globals['roon']['zones'][zone_id]['settings']['shuffle'] = False
            self.globals['roon']['zones'][zone_id]['settings']['loop'] = u'disabled'
            self.globals['roon']['zones'][zone_id]['zoneUniqueIdentityKey'] = ''
            self.globals['roon']['zones'][zone_id]['outputs'] = dict()
            self.globals['roon']['zones'][zone_id]['outputs_count'] = 0
            self.globals['roon']['zones'][zone_id]['now_playing'] = dict()
            self.globals['roon']['zones'][zone_id]['now_playing']['artist_image_keys'] = dict()
            self.globals['roon']['zones'][zone_id]['now_playing']['artist_image_keys_Count'] = 0
            self.globals['roon']['zones'][zone_id]['now_playing']['image_key'] = ''
            self.globals['roon']['zones'][zone_id]['now_playing']['one_line'] = dict()
            self.globals['roon']['zones'][zone_id]['now_playing']['one_line']['line1'] = ''
            self.globals['roon']['zones'][zone_id]['now_playing']['two_line'] = dict()
            self.globals['roon']['zones'][zone_id]['now_playing']['two_line']['line1'] = ''
            self.globals['roon']['zones'][zone_id]['now_playing']['two_line']['line2'] = ''
            self.globals['roon']['zones'][zone_id]['now_playing']['three_line'] = dict()
            self.globals['roon']['zones'][zone_id]['now_playing']['three_line']['line1'] = ''
            self.globals['roon']['zones'][zone_id]['now_playing']['three_line']['line2'] = ''
            self.globals['roon']['zones'][zone_id]['now_playing']['three_line']['line3'] = ''
            self.globals['roon']['zones'][zone_id]['now_playing']['length'] = 0
            self.globals['roon']['zones'][zone_id]['now_playing']['seek_position'] = 0
            self.globals['roon']['zones'][zone_id]['is_previous_allowed'] = False               
            self.globals['roon']['zones'][zone_id]['is_pause_allowed'] = False               
            self.globals['roon']['zones'][zone_id]['is_seek_allowed'] = False               
            self.globals['roon']['zones'][zone_id]['state'] = 'stopped'             
            self.globals['roon']['zones'][zone_id]['is_play_allowed'] = False               
            self.globals['roon']['zones'][zone_id]['is_next_allowed'] = False

            for zoneKey, zoneValue in zoneData.iteritems():

                if zoneKey == 'zone_id':
                    self.globals['roon']['zones'][zone_id]['zone_id'] = zoneValue
                if zoneKey == 'queue_items_remaining':
                    self.globals['roon']['zones'][zone_id]['queue_items_remaining'] = zoneValue
                elif zoneKey == 'queue_time_remaining':
                    self.globals['roon']['zones'][zone_id]['queue_time_remaining'] = zoneValue
                elif zoneKey == 'display_name':
                    self.globals['roon']['zones'][zone_id]['display_name'] = zoneValue
                elif zoneKey == 'settings':
                    self.globals['roon']['zones'][zone_id]['settings'] = dict()
                    for zoneKey2, zoneValue2 in zoneValue.iteritems():
                        if zoneKey2 == 'auto_radio':
                            self.globals['roon']['zones'][zone_id]['settings']['auto_radio'] = bool(zoneValue2)
                        elif zoneKey2 == 'shuffle':
                            self.globals['roon']['zones'][zone_id]['settings']['shuffle'] = bool(zoneValue2)
                        elif zoneKey2 == 'loop':
                            self.globals['roon']['zones'][zone_id]['settings']['loop'] = zoneValue2
                elif zoneKey == 'outputs':
                    self.globals['roon']['zones'][zone_id]['outputs'] = dict()
                    outputCount = 0
                    outputsList = list()
                    for output in zoneValue:
                        outputCount += 1
                        self.globals['roon']['zones'][zone_id]['outputs'][outputCount] = dict()
                        for outputKey, outputData in output.iteritems():
                            if outputKey == 'output_id':
                                self.globals['roon']['zones'][zone_id]['outputs'][outputCount]['output_id'] = outputData
                                outputsList.append(outputData)
                            elif outputKey == 'display_name':
                                self.globals['roon']['zones'][zone_id]['outputs'][outputCount]['display_name'] = outputData
                            elif outputKey == 'zone_id':
                                self.globals['roon']['zones'][zone_id]['outputs'][outputCount]['zone_id'] = outputData
                            elif outputKey == 'source_controls':
                                self.globals['roon']['zones'][zone_id]['outputs'][outputCount]['source_controls'] = dict()
                                sourceControlsCount = 0
                                for sourceControls in outputData:
                                    sourceControlsCount += 1
                                    self.globals['roon']['zones'][zone_id]['outputs'][outputCount]['source_controls'][sourceControlsCount] = dict()
                                    for sourceControlKey, sourceControlData in sourceControls.iteritems():
                                        if sourceControlKey == 'status':
                                            self.globals['roon']['zones'][zone_id]['outputs'][outputCount]['source_controls'][sourceControlsCount]['status'] = sourceControlData
                                        elif sourceControlKey == 'display_name':
                                            self.globals['roon']['zones'][zone_id]['outputs'][outputCount]['source_controls'][sourceControlsCount]['display_name'] = sourceControlData
                                        elif sourceControlKey == 'control_key':
                                            self.globals['roon']['zones'][zone_id]['outputs'][outputCount]['source_controls'][sourceControlsCount]['control_key'] = sourceControlData
                                        elif sourceControlKey == 'supports_standby':
                                            self.globals['roon']['zones'][zone_id]['outputs'][outputCount]['source_controls'][sourceControlsCount]['supports_standby'] = bool(sourceControlData)
                                self.globals['roon']['zones'][zone_id]['outputs'][outputCount]['source_controls_count'] = sourceControlsCount
                            elif outputKey == 'volume':
                                self.globals['roon']['zones'][zone_id]['outputs'][outputCount]['volume'] = dict()
                                for volumeKey, volumeData in outputData.iteritems():
                                    if volumeKey == 'hard_limit_min':
                                        self.globals['roon']['zones'][zone_id]['outputs'][outputCount]['volume']['hard_limit_min'] = volumeData
                                    elif volumeKey == 'min':
                                        self.globals['roon']['zones'][zone_id]['outputs'][outputCount]['volume']['min'] = volumeData
                                    elif volumeKey == 'is_muted':
                                        self.globals['roon']['zones'][zone_id]['outputs'][outputCount]['volume']['is_muted'] = volumeData
                                    elif volumeKey == 'max':
                                        self.globals['roon']['zones'][zone_id]['outputs'][outputCount]['volume']['max'] = volumeData
                                    elif volumeKey == 'value':
                                        self.globals['roon']['zones'][zone_id]['outputs'][outputCount]['volume']['value'] = volumeData
                                    elif volumeKey == 'step':
                                        self.globals['roon']['zones'][zone_id]['outputs'][outputCount]['volume']['step'] = volumeData
                                    elif volumeKey == 'hard_limit_max':
                                        self.globals['roon']['zones'][zone_id]['outputs'][outputCount]['volume']['hard_limit_max'] = volumeData
                                    elif volumeKey == 'soft_limit':
                                        self.globals['roon']['zones'][zone_id]['outputs'][outputCount]['volume']['soft_limit'] = volumeData
                                    elif volumeKey == 'type':
                                        self.globals['roon']['zones'][zone_id]['outputs'][outputCount]['volume']['type'] = volumeData

                            elif outputKey == 'can_group_with_output_ids':
                                self.globals['roon']['zones'][zone_id]['outputs'][outputCount]['can_group_with_output_ids'] = dict()
                                canGroupCount = 0
                                for can_group_with_output_id in outputData:
                                    canGroupCount += 1
                                    self.globals['roon']['zones'][zone_id]['outputs'][outputCount]['can_group_with_output_ids'][canGroupCount] = can_group_with_output_id
                                self.globals['roon']['zones'][zone_id]['outputs'][outputCount]['can_group_with_output_ids_count'] = canGroupCount   
                    self.globals['roon']['zones'][zone_id]['outputs_count'] = outputCount
                    outputsList.sort()
                    self.globals['roon']['zones'][zone_id]['zoneUniqueIdentityKey'] = self.convertOutputIdListToString(outputsList)

                elif zoneKey == 'now_playing':
                    for zoneKey2, zoneValue2 in zoneValue.iteritems():
                        if zoneKey2 == 'artist_image_keys':
                            artistImageCount = 0
                            for artist_image_key in zoneValue2:
                                artistImageCount += 1
                                self.globals['roon']['zones'][zone_id]['now_playing']['artist_image_keys'][artistImageCount] = artist_image_key
                            self.globals['roon']['zones'][zone_id]['now_playing']['artist_image_keys_Count'] = artistImageCount
                        elif zoneKey2 == 'image_key':
                            self.globals['roon']['zones'][zone_id]['now_playing']['image_key'] = zoneValue2
                        elif zoneKey2 == 'one_line':
                            self.globals['roon']['zones'][zone_id]['now_playing']['one_line'] = dict()
                            for zoneKey3, zoneValue3 in zoneValue2.iteritems():
                                if zoneKey3 == 'line1':
                                    self.globals['roon']['zones'][zone_id]['now_playing']['one_line']['line1'] = zoneValue3
                        elif zoneKey2 == 'two_line':
                            self.globals['roon']['zones'][zone_id]['now_playing']['two_line'] = dict()
                            for zoneKey3, zoneValue3 in zoneValue2.iteritems():
                                if zoneKey3 == 'line1':
                                    self.globals['roon']['zones'][zone_id]['now_playing']['two_line']['line1'] = zoneValue3
                                elif zoneKey3 == 'line2':
                                    self.globals['roon']['zones'][zone_id]['now_playing']['two_line']['line2'] = zoneValue3
                        elif zoneKey2 == 'three_line':
                            self.globals['roon']['zones'][zone_id]['now_playing']['three_line'] = dict()
                            for zoneKey3, zoneValue3 in zoneValue2.iteritems():
                                if zoneKey3 == 'line1':
                                    self.globals['roon']['zones'][zone_id]['now_playing']['three_line']['line1'] = zoneValue3
                                elif zoneKey3 == 'line2':
                                    self.globals['roon']['zones'][zone_id]['now_playing']['three_line']['line2'] = zoneValue3
                                elif zoneKey3 == 'line3':
                                    self.globals['roon']['zones'][zone_id]['now_playing']['three_line']['line3'] = zoneValue3
                        if zoneKey2 == 'length':
                            self.globals['roon']['zones'][zone_id]['now_playing']['length'] = zoneValue2
                        if zoneKey2 == 'seek_position':
                            if zoneValue2 is None:
                                self.globals['roon']['zones'][zone_id]['now_playing']['seek_position'] = 0
                            else:
                                self.globals['roon']['zones'][zone_id]['now_playing']['seek_position'] = zoneValue2

                elif zoneKey == 'is_previous_allowed':
                    self.globals['roon']['zones'][zone_id]['is_previous_allowed'] = bool(zoneValue)               
                elif zoneKey == 'is_pause_allowed':
                    self.globals['roon']['zones'][zone_id]['is_pause_allowed'] = bool(zoneValue)               
                elif zoneKey == 'is_seek_allowed':
                    self.globals['roon']['zones'][zone_id]['is_seek_allowed'] = bool(zoneValue)               
                elif zoneKey == 'state':
                    self.globals['roon']['zones'][zone_id]['state'] = zoneValue              
                elif zoneKey == 'is_play_allowed':
                    self.globals['roon']['zones'][zone_id]['is_play_allowed'] = bool(zoneValue)               
                elif zoneKey == 'is_next_allowed':
                    self.globals['roon']['zones'][zone_id]['is_next_allowed'] = bool(zoneValue)

            #### SPECIAL ANNOUCEMENT CODE - START ####
            if self.globals['roon']['zones'][zone_id]['now_playing']['three_line']['line1'] != '':
                zone_state = self.globals['roon']['zones'][zone_id]['state']
                self.general_logger.debug(u'STC. STATE = {}'.format(zone_state))

                if zone_state == u'playing':
                    announcement_track = self.globals['roon']['zones'][zone_id]['now_playing']['three_line']['line1']
                    work_artist = self.globals['roon']['zones'][zone_id]['now_playing']['three_line']['line2']
                    work_artist = work_artist.replace(' / Various Artists', '')
                    work_artist = work_artist.replace(' / ', ' and ')
                    work_artist = work_artist.replace(' & ', ' and ')
                    work_artist = work_artist.replace(', Jr.', ' junior')
                    announcement_artist = work_artist
                    announcement_album = self.globals['roon']['zones'][zone_id]['now_playing']['three_line']['line3']
                    work_announcement = (u'Now playing {}'.format(announcement_track))
                    if announcement_artist != '':
                        work_announcement = (u'{}, by {}'.format(work_announcement, announcement_artist))
                    if announcement_album != '':
                        work_announcement = (u'{}, from the album, {}'.format(work_announcement, announcement_album))
                    announcement = work_announcement.replace(' & ', ' and ')
                else:
                    announcement = ''  

                self.general_logger.debug(u'STC. Announcement = {}'.format(announcement))

                self.general_logger.debug(u'STC. OUTPUT ID TO DEV ID = {}'.format(self.globals['roon']['outputIdToDevId']))

                for key, output in self.globals['roon']['zones'][zone_id]['outputs'].iteritems():
                    self.general_logger.debug(u'STC. Key = {}, Output ID = {}'.format(key, output))
                    if 'output_id' in output:
                        roonOutputDevId = self.globals['roon']['outputIdToDevId'][output['output_id']]
                        self.general_logger.debug(u'STC. ROONOUTPUTDEVID = {}'.format(roonOutputDevId))

                        roonOutputDev = indigo.devices[roonOutputDevId]
                        # self.general_logger.debug(u'STC. INDIGO OUTPUT DEV [{}]: ENABLED = {}, Connected = [{}]/{}'.format(roonOutputDev.name, roonOutputDev.enabled, type(roonOutputDev.states["output_connected"]), roonOutputDev.states["output_connected"]))
                        # self.general_logger.debug(u'STC. \'{}\' OUTPUT:\n{}'.format(indigo.devices[roonOutputDev.name, roonOutputDevId]))
                        #  if roonOutputDev.enabled and roonOutputDev.states["output_connected"]:  # output_connected check doesn't work ????????
                        if roonOutputDev.enabled:
                            nowPlayingVarId = int(roonOutputDev.pluginProps.get('nowPlayingVarId', 0))
                            self.general_logger.debug(u'STC. INDIGO OUTPUT DEV [{}]: NOWPLAYINGVARID = {}'.format(roonOutputDev.name, nowPlayingVarId))
                            if nowPlayingVarId != 0:
                                indigo.variable.updateValue(nowPlayingVarId, value=announcement)

            #### SPECIAL ANNOUCEMENT CODE - END ####

            if self.globals['roon']['zones'][zone_id]['zone_id'] != '' and self.globals['roon']['zones'][zone_id]['zoneUniqueIdentityKey'] != '':
                self.globals['roon']['zoneUniqueIdentityKeyToZoneId'][self.globals['roon']['zones'][zone_id]['zoneUniqueIdentityKey']] = self.globals['roon']['zones'][zone_id]['zone_id']

                if self.globals['roon']['zones'][zone_id]['zoneUniqueIdentityKey'] not in self.globals['roon']['zoneUniqueIdentityKeyToDevId']:
                    self.autoCreateZoneDevice(zone_id, self.globals['roon']['zones'][zone_id]['zoneUniqueIdentityKey'])

            else:
                self.general_logger.error(u'\'processZone\' unable to set up \'zoneUniqueIdentityKeyToZoneId\' entry: Zone_id = \'{}\', zone_unique_identity_key = \'{}\''.format(zone_id, self.globals['roon']['zones'][zone_id]['zoneUniqueIdentityKey']))   

        except StandardError as e:
            self.general_logger.error(u'\'processZone\' error detected. Line \'{}\' has error=\'{}\''.format(sys.exc_traceback.tb_lineno, e))   

        finally:
            if self.globals['debug']['methodTraceActive']: self.method_tracer.threaddebug(u'Method End: Line {}'.format(inspect.currentframe().f_lineno))

    def printZone(self, zone_id):
        if self.globals['debug']['methodTraceActive']: self.method_tracer.threaddebug(u'Method Start: Line {}'.format(inspect.currentframe().f_lineno))

        try:
            zonePrint = u'\n\nROON ZONE PRINT: \'{}\'\n'.format(self.globals['roon']['zones'][zone_id]['display_name'])
            zonePrint = zonePrint         + u'\nZone: {}'.format(self.globals['roon']['zones'][zone_id]['zone_id'])
            zonePrint = zonePrint         + u'\n    Queue Items Remaining: {}'.format(self.globals['roon']['zones'][zone_id]['queue_items_remaining'])
            zonePrint = zonePrint         + u'\n    Queue Time Remaining: {}'.format(self.globals['roon']['zones'][zone_id]['queue_time_remaining'])
            zonePrint = zonePrint         + u'\n    Display Name: {}'.format(self.globals['roon']['zones'][zone_id]['display_name'])
            zonePrint = zonePrint         + u'\n    Settings:'
            zonePrint = zonePrint         + u'\n        Auto Radio: {}'.format(self.globals['roon']['zones'][zone_id]['settings']['auto_radio'])
            zonePrint = zonePrint         + u'\n        Shuffle: {}'.format(self.globals['roon']['zones'][zone_id]['settings']['shuffle'])
            zonePrint = zonePrint         + u'\n        Loop: {}'.format(self.globals['roon']['zones'][zone_id]['settings']['loop'])
            zonePrint = zonePrint         + u'\n    zone_id Unique Identity Key: {}'.format(self.globals['roon']['zones'][zone_id]['zoneUniqueIdentityKey'])
            zonePrint = zonePrint         + u'\n    Outputs: Count = {}'.format(self.globals['roon']['zones'][zone_id]['outputs_count'])

            for key, value in self.globals['roon']['zones'][zone_id]['outputs'].iteritems():
                keyInt = int(key)
                zonePrint = zonePrint     + u'\n        Output \'{}\''.format(key)
                zonePrint = zonePrint     + u'\n            Output Id: {}'.format(self.globals['roon']['zones'][zone_id]['outputs'][keyInt]['output_id'])
                zonePrint = zonePrint     + u'\n            Display Name: {}'.format(self.globals['roon']['zones'][zone_id]['outputs'][keyInt]['display_name'])
                zonePrint = zonePrint     + u'\n            Zone Id: {}'.format(self.globals['roon']['zones'][zone_id]['outputs'][keyInt]['zone_id'])

                zonePrint = zonePrint     + u'\n            Source Controls: Count = {}'.format(self.globals['roon']['zones'][zone_id]['outputs'][keyInt]['source_controls_count'])
                for key2, value2 in self.globals['roon']['zones'][zone_id]['outputs'][keyInt]['source_controls'].iteritems():
                    key2Int = int(key2)
                    zonePrint = zonePrint + u'\n                Source Controls \'{}\''.format(key2)
                    zonePrint = zonePrint + u'\n                    Status: {}'.format(self.globals['roon']['zones'][zone_id]['outputs'][keyInt]['source_controls'][key2Int]['status'])
                    zonePrint = zonePrint + u'\n                    Display Name: {}'.format(self.globals['roon']['zones'][zone_id]['outputs'][keyInt]['source_controls'][key2Int]['display_name'])
                    zonePrint = zonePrint + u'\n                    Control Key: {}'.format(self.globals['roon']['zones'][zone_id]['outputs'][keyInt]['source_controls'][key2Int]['control_key'])
                    zonePrint = zonePrint + u'\n                    Supports Standby: {}'.format(self.globals['roon']['zones'][zone_id]['outputs'][keyInt]['source_controls'][key2Int]['supports_standby'])
                zonePrint = zonePrint     + u'\n            Volume:'
                zonePrint = zonePrint     + u'\n                Hard Limit Min: {}'.format(self.globals['roon']['zones'][zone_id]['outputs'][keyInt]['volume']['hard_limit_min'])
                zonePrint = zonePrint     + u'\n                Min: {}'.format(self.globals['roon']['zones'][zone_id]['outputs'][keyInt]['volume']['min'])
                zonePrint = zonePrint     + u'\n                Is Muted: {}'.format(self.globals['roon']['zones'][zone_id]['outputs'][keyInt]['volume']['is_muted'])
                zonePrint = zonePrint     + u'\n                Max: {}'.format(self.globals['roon']['zones'][zone_id]['outputs'][keyInt]['volume']['max'])
                zonePrint = zonePrint     + u'\n                Value: {}'.format(self.globals['roon']['zones'][zone_id]['outputs'][keyInt]['volume']['value'])
                zonePrint = zonePrint     + u'\n                Step: {}'.format(self.globals['roon']['zones'][zone_id]['outputs'][keyInt]['volume']['step'])
                zonePrint = zonePrint     + u'\n                Hard Limit Max: {}'.format(self.globals['roon']['zones'][zone_id]['outputs'][keyInt]['volume']['hard_limit_max'])
                zonePrint = zonePrint     + u'\n                Soft Limit: {}'.format(self.globals['roon']['zones'][zone_id]['outputs'][keyInt]['volume']['soft_limit'])
                zonePrint = zonePrint     + u'\n                Type: {}'.format(self.globals['roon']['zones'][zone_id]['outputs'][keyInt]['volume']['type'])


                zonePrint = zonePrint     + u'\n            Can Group With Output Ids: Count = {}'.format(self.globals['roon']['zones'][zone_id]['outputs'][keyInt]['can_group_with_output_ids_count'])
                for key2, value2 in self.globals['roon']['zones'][zone_id]['outputs'][keyInt]['can_group_with_output_ids'].iteritems():
                    key2Int = int(key2)
                    zonePrint = zonePrint + u'\n                Output Id [{}]: {}'.format(key2, self.globals['roon']['zones'][zone_id]['outputs'][keyInt]['can_group_with_output_ids'][key2Int])

            zonePrint = zonePrint         + u'\n    Now Playing:'
            if 'artist_image_keys' in self.globals['roon']['zones'][zone_id]['now_playing']:
                zonePrint = zonePrint     + u'\n        Artist Image Keys: Count = {}'.format(self.globals['roon']['zones'][zone_id]['now_playing']['artist_image_keys_Count'])
                for key, value in self.globals['roon']['zones'][zone_id]['now_playing']['artist_image_keys'].iteritems():
                    keyInt = int(key)
                    zonePrint = zonePrint + u'\n            Artist Image Key: {}'.format(self.globals['roon']['zones'][zone_id]['now_playing']['artist_image_keys'][keyInt])

            if 'image_key' in self.globals['roon']['zones'][zone_id]['now_playing']:
                zonePrint = zonePrint     + u'\n        Image Key: {}'.format(self.globals['roon']['zones'][zone_id]['now_playing']['image_key'])
            if 'length' in self.globals['roon']['zones'][zone_id]['now_playing']: 
                zonePrint = zonePrint     + u'\n        Length: {}'.format(self.globals['roon']['zones'][zone_id]['now_playing']['length'])
            zonePrint = zonePrint         + u'\n        Seek Position: {}'.format(self.globals['roon']['zones'][zone_id]['now_playing']['seek_position'])
            zonePrint = zonePrint         + u'\n        One Line:'
            zonePrint = zonePrint         + u'\n            Line 1: {}'.format(self.globals['roon']['zones'][zone_id]['now_playing']['one_line']['line1'])
            zonePrint = zonePrint         + u'\n        Two Line:'
            zonePrint = zonePrint         + u'\n            Line 1: {}'.format(self.globals['roon']['zones'][zone_id]['now_playing']['two_line']['line1'])
            zonePrint = zonePrint         + u'\n            Line 2: {}'.format(self.globals['roon']['zones'][zone_id]['now_playing']['two_line']['line2'])
            zonePrint = zonePrint         + u'\n        Three Line:'
            zonePrint = zonePrint         + u'\n            Line 1: {}'.format(self.globals['roon']['zones'][zone_id]['now_playing']['three_line']['line1'])
            zonePrint = zonePrint         + u'\n            Line 2: {}'.format(self.globals['roon']['zones'][zone_id]['now_playing']['three_line']['line2'])
            zonePrint = zonePrint         + u'\n            Line 3: {}'.format(self.globals['roon']['zones'][zone_id]['now_playing']['three_line']['line3'])

            zonePrint = zonePrint         + u'\n    Is Previous Allowed: {}'.format(self.globals['roon']['zones'][zone_id]['is_previous_allowed'])
            zonePrint = zonePrint         + u'\n    Is Pause Allowed: {}'.format(self.globals['roon']['zones'][zone_id]['is_pause_allowed'])
            zonePrint = zonePrint         + u'\n    Is Seek Allowed: {}'.format(self.globals['roon']['zones'][zone_id]['is_seek_allowed'])
            zonePrint = zonePrint         + u'\n    State: {}'.format(self.globals['roon']['zones'][zone_id]['state'])
            zonePrint = zonePrint         + u'\n    Is Play Allowed: {}'.format(self.globals['roon']['zones'][zone_id]['is_play_allowed'])
            zonePrint = zonePrint         + u'\n    Is Next Allowed: {}'.format(self.globals['roon']['zones'][zone_id]['is_next_allowed'])

            self.general_logger.debug(zonePrint)

        except StandardError as e:
            self.general_logger.error(u'\'printZone\' error detected. Line \'{}\' has error=\'{}\''.format(sys.exc_traceback.tb_lineno, e))   

    def processOutputs(self, outputs):
        if self.globals['debug']['methodTraceActive']: self.method_tracer.threaddebug(u'Method Start: Line {}'.format(inspect.currentframe().f_lineno))

        try:
            for output_id, output_data in outputs.iteritems():
                self.processOutput(output_id, output_data)
                if self.globals['config']['printOutput']:
                    self.printOutput(output_id)

        except StandardError as e:
            self.general_logger.error(u'\'processOutputs\' error detected. Line \'{}\' has error=\'{}\''.format(sys.exc_traceback.tb_lineno, e))

        finally:
            if self.globals['debug']['methodTraceActive']: self.method_tracer.threaddebug(u'Method End: Line {}'.format(inspect.currentframe().f_lineno))

    def processOutput(self, output_id, outputData):
        if self.globals['debug']['methodTraceActive']: self.method_tracer.threaddebug(u'Method Start: Line {}'.format(inspect.currentframe().f_lineno))

        processOutput_return_state = False

        try:
            self.globals['roon']['outputs'][output_id] = dict()
            self.globals['roon']['outputs'][output_id]['source_controls'] = dict()
            self.globals['roon']['outputs'][output_id]['source_controls_count'] = 0
            self.globals['roon']['outputs'][output_id]['volume'] = dict()
            self.globals['roon']['outputs'][output_id]['can_group_with_output_ids'] = dict()

            for outputKey, outputValue in outputData.iteritems():
                if outputKey == 'output_id':
                    self.globals['roon']['outputs'][output_id]['output_id'] = outputValue
                elif outputKey == 'display_name':
                    self.globals['roon']['outputs'][output_id]['display_name'] = outputValue
                elif outputKey == 'zone_id':
                    self.globals['roon']['outputs'][output_id]['zone_id'] = outputValue
                elif outputKey == 'source_controls':
                    sourceControlsCount = 0
                    for sourceControls in outputValue:
                        sourceControlsCount += 1
                        self.globals['roon']['outputs'][output_id]['source_controls'][sourceControlsCount] = dict()
                        for sourceControlKey, sourceControlData in sourceControls.iteritems():
                            if sourceControlKey == 'status':
                                self.globals['roon']['outputs'][output_id]['source_controls'][sourceControlsCount]['status'] = sourceControlData
                            elif sourceControlKey == 'display_name':
                                self.globals['roon']['outputs'][output_id]['source_controls'][sourceControlsCount]['display_name'] = sourceControlData
                            elif sourceControlKey == 'control_key':
                                self.globals['roon']['outputs'][output_id]['source_controls'][sourceControlsCount]['control_key'] = sourceControlData
                            elif sourceControlKey == 'supports_standby':
                                self.globals['roon']['outputs'][output_id]['source_controls'][sourceControlsCount]['supports_standby'] = bool(sourceControlData)
                    self.globals['roon']['outputs'][output_id]['source_controls_count'] = sourceControlsCount

                elif outputKey == 'volume':
                    for volumeKey, volumeData in outputValue.iteritems():
                        if volumeKey == 'hard_limit_min':
                            self.globals['roon']['outputs'][output_id]['volume']['hard_limit_min'] = volumeData
                        elif volumeKey == 'min':
                            self.globals['roon']['outputs'][output_id]['volume']['min'] = volumeData
                        elif volumeKey == 'is_muted':
                            self.globals['roon']['outputs'][output_id]['volume']['is_muted'] = volumeData
                        elif volumeKey == 'max':
                            self.globals['roon']['outputs'][output_id]['volume']['max'] = volumeData
                        elif volumeKey == 'value':
                            self.globals['roon']['outputs'][output_id]['volume']['value'] = volumeData
                        elif volumeKey == 'step':
                            self.globals['roon']['outputs'][output_id]['volume']['step'] = volumeData
                        elif volumeKey == 'hard_limit_max':
                            self.globals['roon']['outputs'][output_id]['volume']['hard_limit_max'] = volumeData
                        elif volumeKey == 'soft_limit':
                            self.globals['roon']['outputs'][output_id]['volume']['soft_limit'] = volumeData
                        elif volumeKey == 'type':
                            self.globals['roon']['outputs'][output_id]['volume']['type'] = volumeData

                elif outputKey == 'can_group_with_output_ids':
                    canGroupCount = 0
                    for can_group_with_output_id in outputValue:
                        canGroupCount += 1
                        self.globals['roon']['outputs'][output_id]['can_group_with_output_ids'][canGroupCount] = can_group_with_output_id
                    self.globals['roon']['outputs'][output_id]['can_group_with_output_ids_count'] = canGroupCount   

            if output_id not in self.globals['roon']['outputIdToDevId']:
                self.autoCreateOutputDevice(output_id)

            if len(self.globals['roon']['outputs'][output_id]['source_controls']) > 0:
            # if len(self.globals['roon']['outputs'][output_id]['volume']) > 0:
                processOutput_return_state = True
            else:
                self.globals['roon']['outputs'][output_id] = dict()
                self.globals['roon']['outputs'][output_id]['source_controls'] = dict()
                self.globals['roon']['outputs'][output_id]['source_controls_count'] = 0
                self.globals['roon']['outputs'][output_id]['volume'] = dict()
                self.globals['roon']['outputs'][output_id]['can_group_with_output_ids'] = dict()
                if output_id in self.globals['roon']['outputIdToDevId']:
                    self.disconnectRoonOutputDevice(self.globals['roon']['outputIdToDevId'][output_id])
                processOutput_return_state = False

        except StandardError as e:
            self.general_logger.error(u'\'processOutput\' error detected. Line \'{}\' has error=\'{}\''.format(sys.exc_traceback.tb_lineno, e))

        finally:
            if self.globals['debug']['methodTraceActive']: self.method_tracer.threaddebug(u'Method End: Line {}'.format(inspect.currentframe().f_lineno))

            return processOutput_return_state   

    def printOutput(self, output_id):
        if self.globals['debug']['methodTraceActive']: self.method_tracer.threaddebug(u'Method Start: Line {}'.format(inspect.currentframe().f_lineno))

        try:
            outputPrint = u'\n\nROON OUTPUT PRINT\n'
            outputPrint = outputPrint + u'\nOutput: {}'.format(self.globals['roon']['outputs'][output_id]['output_id'])
            outputPrint = outputPrint + u'\n    Display Name: {}'.format(self.globals['roon']['outputs'][output_id]['display_name'])
            outputPrint = outputPrint + u'\n    Zone Id: {}'.format(self.globals['roon']['outputs'][output_id]['zone_id'])

            if 'source_controls' in self.globals['roon']['outputs'][output_id]:

                outputPrint = outputPrint + u'\n    Source Controls: Count = {}'.format(self.globals['roon']['outputs'][output_id]['source_controls_count'])
                for key2, value2 in self.globals['roon']['outputs'][output_id]['source_controls'].iteritems():
                    key2Int = int(key2)
                    outputPrint = outputPrint + u'\n        Source Controls \'{}\''.format(key2)
                    outputPrint = outputPrint + u'\n            Status: {}'.format(self.globals['roon']['outputs'][output_id]['source_controls'][key2Int]['status'])
                    outputPrint = outputPrint + u'\n            Display Name: {}'.format(self.globals['roon']['outputs'][output_id]['source_controls'][key2Int]['display_name'])
                    outputPrint = outputPrint + u'\n            Control Key: {}'.format(self.globals['roon']['outputs'][output_id]['source_controls'][key2Int]['control_key'])
                    outputPrint = outputPrint + u'\n            Supports Standby: {}'.format(self.globals['roon']['outputs'][output_id]['source_controls'][key2Int]['supports_standby'])

            if 'volume' in self.globals['roon']['outputs'][output_id] and len(self.globals['roon']['outputs'][output_id]['volume']) > 0:
                outputPrint = outputPrint + u'\n    Volume:'
                outputPrint = outputPrint + u'\n        Hard Limit Min: {}'.format(self.globals['roon']['outputs'][output_id]['volume']['hard_limit_min'])
                outputPrint = outputPrint + u'\n        Min: {}'.format(self.globals['roon']['outputs'][output_id]['volume']['min'])
                outputPrint = outputPrint + u'\n        Is Muted: {}'.format(self.globals['roon']['outputs'][output_id]['volume']['is_muted'])
                outputPrint = outputPrint + u'\n        Max: {}'.format(self.globals['roon']['outputs'][output_id]['volume']['max'])
                outputPrint = outputPrint + u'\n        Value: {}'.format(self.globals['roon']['outputs'][output_id]['volume']['value'])
                outputPrint = outputPrint + u'\n        Step: {}'.format(self.globals['roon']['outputs'][output_id]['volume']['step'])
                outputPrint = outputPrint + u'\n        Hard Limit Max: {}'.format(self.globals['roon']['outputs'][output_id]['volume']['hard_limit_max'])
                outputPrint = outputPrint + u'\n        Soft Limit: {}'.format(self.globals['roon']['outputs'][output_id]['volume']['soft_limit'])
                outputPrint = outputPrint + u'\n        Type: {}'.format(self.globals['roon']['outputs'][output_id]['volume']['type'])

            outputPrint = outputPrint + u'\n    Can Group With Output Ids: Count = {}'.format(self.globals['roon']['outputs'][output_id]['can_group_with_output_ids_count'])
            for key2, value2 in self.globals['roon']['outputs'][output_id]['can_group_with_output_ids'].iteritems():
                key2Int = int(key2)
                outputPrint = outputPrint + u'\n        Output Id [{}]: {}'.format(key2, self.globals['roon']['outputs'][output_id]['can_group_with_output_ids'][key2Int])

            self.general_logger.debug(outputPrint)
 
        except StandardError as err:
            self.general_logger.error(u'\'printOutput\' error detected. Line \'{}\' has error=\'{}\''.format(indigo.devices[devId].name, sys.exc_traceback.tb_lineno, err))   

        finally:
            if self.globals['debug']['methodTraceActive']: self.method_tracer.threaddebug(u'Method End: Line {}'.format(inspect.currentframe().f_lineno))

    def listRoonZoneUniqueIdentityKeys(self, filter="", valuesDict=None, typeId="", targetId=0):
        if self.globals['debug']['methodTraceActive']: self.method_tracer.threaddebug(u'Method Start: Line {}'.format(inspect.currentframe().f_lineno))

        try:
            self.general_logger.debug(u'TYPE_ID = {}, TARGET_ID = {}'.format(typeId, targetId))

            allocatedRoonZoneUniqueIdentityKeys = []
            for dev in indigo.devices.iter("self"):
                if dev.deviceTypeId == 'roonZone' and targetId != dev.id:
                    zone_unique_identity_key = dev.pluginProps.get('roonZoneUniqueIdentityKey', '')
                    if zone_unique_identity_key != '':
                        allocatedRoonZoneUniqueIdentityKeys.append(zone_unique_identity_key)

            zone_unique_identity_keys_list = list()

            for zone_id in self.globals['roon']['zones']:
                if self.globals['roon']['zones'][zone_id]['zoneUniqueIdentityKey'] not in allocatedRoonZoneUniqueIdentityKeys:
                    zone_unique_identity_keys_list.append((self.globals['roon']['zones'][zone_id]['zoneUniqueIdentityKey'], self.globals['roon']['zones'][zone_id]['display_name']))

            if len(zone_unique_identity_keys_list) == 0:
                zone_unique_identity_keys_list.append(('-', '-- No Available Zones --'))
                return zone_unique_identity_keys_list
            else:
                zone_unique_identity_keys_list.append(('-', '-- Select Zone --'))

            return sorted(zone_unique_identity_keys_list, key=lambda zone_name: zone_name[1].lower())   # sort by Zone name

        except StandardError as err:
            self.general_logger.error(u'\'listRoonZoneUniqueIdentityKeys\' error detected. Line \'{}\' has error=\'{}\''.format(indigo.devices[devId].name, sys.exc_traceback.tb_lineno, err))   

        finally:
            if self.globals['debug']['methodTraceActive']: self.method_tracer.threaddebug(u'Method End: Line {}'.format(inspect.currentframe().f_lineno))

    def roonZoneUniqueIdentityKeySelected(self, valuesDict, typeId, devId):
        if self.globals['debug']['methodTraceActive']: self.method_tracer.threaddebug(u'Method Start: Line {}'.format(inspect.currentframe().f_lineno))

        try:
            zone_unique_identity_key = valuesDict.get('roonZoneUniqueIdentityKey', '-')
            if zone_unique_identity_key != '-': 
                valuesDict['roonZoneUniqueIdentityKeyUi'] = zone_unique_identity_key
            else: 
                valuesDict['roonZoneUniqueIdentityKeyUi'] = '** INVALID **'

            return valuesDict

        except StandardError as err:
            self.general_logger.error(u'\'roonZoneUniqueIdentityKeySelected\' error detected. Line \'{}\' has error=\'{}\''.format(indigo.devices[devId].name, sys.exc_traceback.tb_lineno, err))   

        finally:
            if self.globals['debug']['methodTraceActive']: self.method_tracer.threaddebug(u'Method End: Line {}'.format(inspect.currentframe().f_lineno))

    def listRoonOutputIds(self, filter="", valuesDict=None, typeId="", targetId=0):
        if self.globals['debug']['methodTraceActive']: self.method_tracer.threaddebug(u'Method Start: Line {}'.format(inspect.currentframe().f_lineno))

        self.general_logger.debug(u'typeId = {}, targetId = {}'.format(typeId, targetId))

        try:
            outputs_list = list()

            allocated_output_ids = []
            for dev in indigo.devices.iter("self"):
                if dev.deviceTypeId == 'roonOutput':
                    roonOutputId = dev.pluginProps.get('roonOutputId', '')
                    allocated_output_ids.append(roonOutputId)
                    if dev.id == targetId and roonOutputId != '':
                        if dev.states['output_status'] == 'connected':
                            outputs_list.append((roonOutputId, self.globals['roon']['outputs'][roonOutputId]['display_name']))  # Append self
                        else:
                            display_name = dev.states['display_name']
                            if display_name != '':
                                display_name = display_name + ' '
                            outputs_list.append((roonOutputId, '{}[Output disconnected]'.format(display_name)))  # Append self

            for output_id in self.globals['roon']['outputs']:
                if output_id not in allocated_output_ids:
                    outputs_list.append((self.globals['roon']['outputs'][output_id]['output_id'], self.globals['roon']['outputs'][output_id]['display_name']))

            if len(outputs_list) == 0:
                outputs_list.append(('-', '-- No Available Outputs --'))
                return outputs_list
            else:
                outputs_list.append(('-', '-- Select Output --'))

            return sorted(outputs_list, key=lambda output_name: output_name[1].lower())   # sort by Zone name

        except StandardError as err:
            self.general_logger.error(u'\'listRoonOutputIds\' error detected. Line \'{}\' has error=\'{}\''.format(indigo.devices[targetId].name, sys.exc_traceback.tb_lineno, err))   

        finally:
            if self.globals['debug']['methodTraceActive']: self.method_tracer.threaddebug(u'Method End: Line {}'.format(inspect.currentframe().f_lineno))

    def roonOutputIdSelected(self, valuesDict, typeId, devId):
        if self.globals['debug']['methodTraceActive']: self.method_tracer.threaddebug(u'Method Start: Line {}'.format(inspect.currentframe().f_lineno))

        try:
            output_id = valuesDict.get('roonOutputId', '-')
            if output_id != '-': 
                valuesDict['roonOutputId'] = valuesDict.get('roonOutputId', '**INVALID**') 
                valuesDict['roonOutputIdUi'] = output_id
            else: 
                valuesDict['roonOutputIdUi'] = '** INVALID **'

        except StandardError as err:
            self.general_logger.error(u'\'roonOutputIdSelected\' error detected for device \'{}\']. Line \'{}\' has error=\'{}\''.format(indigo.devices[devId].name, sys.exc_traceback.tb_lineno, err))   

        finally:
            if self.globals['debug']['methodTraceActive']: self.method_tracer.threaddebug(u'Method End: Line {}'.format(inspect.currentframe().f_lineno))

            return valuesDict

    def stopConcurrentThread(self):
        if self.globals['debug']['methodTraceActive']: self.method_tracer.threaddebug(u'Method Start: Line {}'.format(inspect.currentframe().f_lineno))

        self.general_logger.debug(u'Thread shutdown called')

        self.stopThread = True

        if self.globals['debug']['methodTraceActive']: self.method_tracer.threaddebug(u'Method End: Line {}'.format(inspect.currentframe().f_lineno))

    def shutdown(self):
        if self.globals['debug']['methodTraceActive']: self.method_tracer.threaddebug(u'Method Start: Line {}'.format(inspect.currentframe().f_lineno))

        self.general_logger.debug(u'Shutdown called')

        self.general_logger.info(u'\'Roon Controller\' Plugin shutdown complete')

        if self.globals['debug']['methodTraceActive']: self.method_tracer.threaddebug(u'Method End: Line {}'.format(inspect.currentframe().f_lineno))

    def deviceUpdated(self, origDev, newDev):
        # if self.globals['debug']['methodTraceActive']: self.method_tracer.threaddebug(u'Method Start: Line {}'.format(inspect.currentframe().f_lineno))

        try:
            if newDev.deviceTypeId == 'roonController' and newDev.configured and newDev.id in self.globals['roon'] and self.globals['roon'][newDev.id]['deviceStarted']:  # IGNORE THESE UPDATES TO AVOID LOOP!!!
                pass

        except StandardError as err:
            self.general_logger.error(u'\'deviceUpdated\' error detected for device \'{}\']. Line \'{}\' has error=\'{}\''.format(newDev.name, sys.exc_traceback.tb_lineno, err))   

        finally:
            indigo.PluginBase.deviceUpdated(self, origDev, newDev)

    def getActionConfigUiValues(self, pluginProps, typeId, actionId):
        if self.globals['debug']['methodTraceActive']: self.method_tracer.threaddebug(u'Method Start: Line {}'.format(inspect.currentframe().f_lineno))

        try:
            errorDict = indigo.Dict()
            valuesDict = pluginProps

            if typeId == "groupOutputs":  # <Action id="groupOuputs" deviceFilter="self.roonOutput" uiPath="DeviceActions" alwaysUseInDialogHeightCalc="true">

                # self.general_logger.error(u'\'getActionConfigUiValues\' Action: \n\'{}\\n'.format(indigo.actions[actionId]))

                roonOutputToGroupToName = indigo.devices[actionId].name
                valuesDict["roonOutputToGroupTo"] = roonOutputToGroupToName

            return valuesDict, errorDict

        except StandardError as err:
            self.general_logger.error(u'\'getActionConfigUiValues\' error detected. Line \'{}\' has error=\'{}\''.format(sys.exc_traceback.tb_lineno, err))   

        finally:
            if self.globals['debug']['methodTraceActive']: self.method_tracer.threaddebug(u'Method End: Line {}'.format(inspect.currentframe().f_lineno))

    def validateActionConfigUi(self, valuesDict, typeId, actionId):
        if self.globals['debug']['methodTraceActive']: self.method_tracer.threaddebug(u'Method Start: Line {}'.format(inspect.currentframe().f_lineno))

        try:
            if self.globals['debug']['methodTraceActive']: self.method_tracer.threaddebug(u'Method Start: Line {}'.format(inspect.currentframe().f_lineno))

            self.general_logger.debug(u'Validate Action Config UI: typeId = \'{}\', actionId = \'{}\', ValuesDict =\n{}\n'.format(typeId, actionId, valuesDict))

            if typeId == "qwerty":
                pass
            return True, valuesDict

        except StandardError as err:
            self.general_logger.error(u'\'validateActionConfigUi\' error detected for Action \'{}\'. Line \'{}\' has error=\'{}\''.format(indigo.devices[actionId].name, sys.exc_traceback.tb_lineno, err))   

        finally:
            if self.globals['debug']['methodTraceActive']: self.method_tracer.threaddebug(u'Method End: Line {}'.format(inspect.currentframe().f_lineno))

    def processPrintZoneSummary(self, pluginAction):
        if self.globals['debug']['methodTraceActive']: self.method_tracer.threaddebug(u'Method Start: Line {}'.format(inspect.currentframe().f_lineno))

        try:
            self.printKnownZonesSummary('PROCESS PRINT ZONE SUMMARY ACTION')

        except StandardError as err:
            self.general_logger.error(u'\'processPrintZoneSummary\' error detected. Line \'{}\' has error=\'{}\''.format(sys.exc_traceback.tb_lineno, err))   

    
        finally:
            if self.globals['debug']['methodTraceActive']: self.method_tracer.threaddebug(u'Method End: Line {}'.format(inspect.currentframe().f_lineno))

    def processPlay(self, pluginAction, zone_dev):
        if self.globals['debug']['methodTraceActive']: self.method_tracer.threaddebug(u'Method Start: Line {}'.format(inspect.currentframe().f_lineno))

        try:
            if self.processPlaybackControl('processPlay', pluginAction, zone_dev):
                self.general_logger.info(u'Zone \'{}\' playback started.'.format(zone_dev.name))   

        except StandardError as err:
            zone_dev_name = 'Unknown Device'
            if zone_dev is not None:
                zone_dev_name = zone_dev.name
            self.general_logger.error(u'\'processPlay\' error detected for device \'{}\'. Line \'{}\' has error=\'{}\''.format(zone_dev_name, sys.exc_traceback.tb_lineno, err))   

        finally:
            if self.globals['debug']['methodTraceActive']: self.method_tracer.threaddebug(u'Method End: Line {}'.format(inspect.currentframe().f_lineno))

    def processPause(self, pluginAction, zone_dev):
        if self.globals['debug']['methodTraceActive']: self.method_tracer.threaddebug(u'Method Start: Line {}'.format(inspect.currentframe().f_lineno))

        try:
            if self.processPlaybackControl('processPause', pluginAction, zone_dev):
                self.general_logger.info(u'Zone \'{}\' playback paused.'.format(zone_dev.name))   

        except StandardError as err:
            zone_dev_name = 'Unknown Device'
            if zone_dev is not None:
                zone_dev_name = zone_dev.name
            self.general_logger.error(u'\'processPause\' error detected for device \'{}\'. Line \'{}\' has error=\'{}\''.format(zone_dev_name, sys.exc_traceback.tb_lineno, err))   

        finally:
            if self.globals['debug']['methodTraceActive']: self.method_tracer.threaddebug(u'Method End: Line {}'.format(inspect.currentframe().f_lineno))

    def processPlayPause(self, pluginAction, zone_dev):
        if self.globals['debug']['methodTraceActive']: self.method_tracer.threaddebug(u'Method Start: Line {}'.format(inspect.currentframe().f_lineno))

        try:
            if self.processPlaybackControl('processPlayPause', pluginAction, zone_dev):
                self.general_logger.info(u'Zone \'{}\' playback toggled.'.format(zone_dev.name))   

        except StandardError as err:
            zone_dev_name = 'Unknown Device'
            if zone_dev is not None:
                zone_dev_name = zone_dev.name
            self.general_logger.error(u'\'processPlayPause\' error detected for device \'{}\'. Line \'{}\' has error=\'{}\''.format(zone_dev_name, sys.exc_traceback.tb_lineno, err))   

        finally:
            if self.globals['debug']['methodTraceActive']: self.method_tracer.threaddebug(u'Method End: Line {}'.format(inspect.currentframe().f_lineno))

    def processStop(self, pluginAction, zone_dev):
        if self.globals['debug']['methodTraceActive']: self.method_tracer.threaddebug(u'Method Start: Line {}'.format(inspect.currentframe().f_lineno))

        try:
            if self.processPlaybackControl('processStop', pluginAction, zone_dev):
                self.general_logger.info(u'Zone \'{}\' playback stopped.'.format(zone_dev.name))   

        except StandardError as err:
            zone_dev_name = 'Unknown Device'
            if zone_dev is not None:
                zone_dev_name = zone_dev.name
            self.general_logger.error(u'\'processStop\' error detected for device \'{}\'. Line \'{}\' has error=\'{}\''.format(zone_dev_name, sys.exc_traceback.tb_lineno, err))   

        finally:
            if self.globals['debug']['methodTraceActive']: self.method_tracer.threaddebug(u'Method End: Line {}'.format(inspect.currentframe().f_lineno))

    def processPrevious(self, pluginAction, zone_dev):
        if self.globals['debug']['methodTraceActive']: self.method_tracer.threaddebug(u'Method Start: Line {}'.format(inspect.currentframe().f_lineno))

        try:
            if self.processPlaybackControl('processPrevious', pluginAction, zone_dev):
                self.general_logger.info(u'Zone \'{}\' gone to start of track or previous track.'.format(zone_dev.name))   

        except StandardError as err:
            zone_dev_name = 'Unknown Device'
            if zone_dev is not None:
                zone_dev_name = zone_dev.name
            self.general_logger.error(u'\'processPrevious\' error detected for device \'{}\'. Line \'{}\' has error=\'{}\''.format(zone_dev_name, sys.exc_traceback.tb_lineno, err))   

        finally:
            if self.globals['debug']['methodTraceActive']: self.method_tracer.threaddebug(u'Method End: Line {}'.format(inspect.currentframe().f_lineno))

    def processNext(self, pluginAction, zone_dev):
        if self.globals['debug']['methodTraceActive']: self.method_tracer.threaddebug(u'Method Start: Line {}'.format(inspect.currentframe().f_lineno))

        try:
            if self.processPlaybackControl('processNext', pluginAction, zone_dev):
                self.general_logger.info(u'Zone \'{}\' advanced to next track.'.format(zone_dev.name))   

        except StandardError as err:
            zone_dev_name = 'Unknown Device'
            if zone_dev is not None:
                zone_dev_name = zone_dev.name
            self.general_logger.error(u'\'processNext\' error detected for device \'{}\'. Line \'{}\' has error=\'{}\''.format(zone_dev_name, sys.exc_traceback.tb_lineno, err))   

        finally:
            if self.globals['debug']['methodTraceActive']: self.method_tracer.threaddebug(u'Method End: Line {}'.format(inspect.currentframe().f_lineno))

    def processPlaybackControl(self, invoking_process_name, plugin_action, zone_dev):
        if self.globals['debug']['methodTraceActive']: self.method_tracer.threaddebug(u'Method Start: Line {}'.format(inspect.currentframe().f_lineno))

        try:
            if zone_dev is None:
                self.general_logger.error(u'Roon Controller Action \'{}\' ignored as no Zone device specified in Action.'.format(plugin_action.pluginTypeId))
                return False 

            # self.general_logger.error(u'Roon Controller plugin method \'processNext\' Plugin Action:\n{}\n'.format(plugin_action))   

            if not zone_dev.states['zone_connected']:
                self.general_logger.error(u'Roon Controller Action \'{}\' ignored as Zone \'{}\' is disconnected.'.format(plugin_action.pluginTypeId, zone_dev.name))
                return False

            zone_id = zone_dev.states['zone_id']
            if zone_id == '':
                self.general_logger.error(u'Roon Controller Action \'{}\' ignored as Zone \'{}\' is not connected to the Roon Core.'.format(plugin_action.pluginTypeId, zone_dev.name))
                return False

            self.globals['roon']['api'].playback_control(zone_id, plugin_action.pluginTypeId.lower())

            return True

        except StandardError as err:
            zone_dev_name = 'Unknown Device'
            if zone_dev is not None:
                zone_dev_name = zone_dev.name
            self.general_logger.error(u'\'processPlaybackControl\' error detected for device \'{}\' while invoked from \'{}\'. Line \'{}\' has error=\'{}\''.format(zone_dev_name, invoking_process_name, sys.exc_traceback.tb_lineno, err))   

        finally:
            if self.globals['debug']['methodTraceActive']: self.method_tracer.threaddebug(u'Method End: Line {}'.format(inspect.currentframe().f_lineno))

    def processMuteAll(self, plugin_action, zone_dev):
        if self.globals['debug']['methodTraceActive']: self.method_tracer.threaddebug(u'Method Start: Line {}'.format(inspect.currentframe().f_lineno))

        try:
            for zone_dev in indigo.devices.iter("self"):
                if zone_dev.deviceTypeId == 'roonZone':

                    if not zone_dev.states['zone_connected']:
                        self.general_logger.debug(u'Roon Controller Action \'{}\' ignored as Zone \'{}\' is disconnected.'.format(plugin_action.pluginTypeId, zone_dev.name))
                        continue

                    zone_id = zone_dev.states['zone_id']
                    if zone_id == '':
                        self.general_logger.debug(u'Roon Controller Action \'{}\' ignored as Zone \'{}\' is not connected to the Roon Core.'.format(plugin_action.pluginTypeId, zone_dev.name))
                        continue

                    if self.globals['roon']['zones'][zone_id]['outputs_count'] > 0:
                        for output_number in self.globals['roon']['zones'][zone_id]['outputs']:
                            output_id = self.globals['roon']['zones'][zone_id]['outputs'][output_number]['output_id']
                            self.globals['roon']['api'].mute(output_id, True)

        except StandardError as err:
            zone_dev_name = 'Unknown Device'
            if zone_dev is not None:
                zone_dev_name = zone_dev.name
            self.general_logger.error(u'\'processMuteAll\' error detected for device \'{}\'. Line \'{}\' has error=\'{}\''.format(zone_dev_name, sys.exc_traceback.tb_lineno, err))   

        finally:
            if self.globals['debug']['methodTraceActive']: self.method_tracer.threaddebug(u'Method End: Line {}'.format(inspect.currentframe().f_lineno))

    def processMute(self, plugin_action, zone_dev):
        if self.globals['debug']['methodTraceActive']: self.method_tracer.threaddebug(u'Method Start: Line {}'.format(inspect.currentframe().f_lineno))

        try:
            if zone_dev is None:
                self.general_logger.error(u'Roon Controller Action \'{}\' ignored as no Zone device specified in Action.'.format(plugin_action.pluginTypeId))
                return 

            # self.general_logger.error(u'Roon Controller plugin method \'processNext\' Plugin Action:\n{}\n'.format(plugin_action))   

            if not zone_dev.states['zone_connected']:
                self.general_logger.error(u'Roon Controller Action \'{}\' ignored as Zone \'{}\' is disconnected.'.format(plugin_action.pluginTypeId, zone_dev.name))
                return

            zone_id = zone_dev.states['zone_id']
            if zone_id == '':
                self.general_logger.error(u'Roon Controller Action \'{}\' ignored as Zone \'{}\' is not connected to the Roon Core.'.format(plugin_action.pluginTypeId, zone_dev.name))
                return

            if self.globals['roon']['zones'][zone_id]['outputs_count'] > 0:
                for output_number in self.globals['roon']['zones'][zone_id]['outputs']:
                    output_id = self.globals['roon']['zones'][zone_id]['outputs'][output_number]['output_id']

                    toggle = not self.globals['roon']['outputs'][output_id]['volume']['is_muted']

                    self.globals['roon']['api'].mute(output_id, toggle)

        except StandardError as err:
            zone_dev_name = 'Unknown Device'
            if zone_dev is not None:
                zone_dev_name = zone_dev.name
            self.general_logger.error(u'\'processMute\' error detected for device \'{}\'. Line \'{}\' has error=\'{}\''.format(zone_dev_name, sys.exc_traceback.tb_lineno, err))   

        finally:
            if self.globals['debug']['methodTraceActive']: self.method_tracer.threaddebug(u'Method End: Line {}'.format(inspect.currentframe().f_lineno))

    def processVolumeSet(self, plugin_action, output_dev):
        if self.globals['debug']['methodTraceActive']: self.method_tracer.threaddebug(u'Method Start: Line {}'.format(inspect.currentframe().f_lineno))

        try:
            if output_dev is None:
                self.general_logger.error(u'\'processVolumeSet\' Roon Controller Action \'{}\' ignored as no Output device specified in Action.'.format(plugin_action.pluginTypeId))
                return 

            # self.general_logger.error(u'Roon Controller plugin method \'processNext\' Plugin Action:\n{}\n'.format(plugin_action))   

            if not output_dev.states['output_connected']:
                self.general_logger.error(u'\'processVolumeSet\' Roon Controller Action \'{}\' ignored as Output \'{}\' is disconnected.'.format(plugin_action.pluginTypeId, output_dev.name))
                return

            output_id = output_dev.states['output_id']
            if output_id == '':
                self.general_logger.error(u'\'processVolumeSet\' Roon Controller Action \'{}\' ignored as Output \'{}\' is not connected to the Roon Core.'.format(plugin_action.pluginTypeId, output_dev.name))
                return

            volume_level = int(plugin_action.props['volumePercentage'])

            self.globals['roon']['api'].change_volume(output_id, volume_level, method='absolute')

        except StandardError as err:
            output_dev_name = 'Unknown Device'
            if output_dev is not None:
                output_dev_name = output_dev.name
            self.general_logger.error(u'\'processVolumeSet\' error detected for device \'{}\'. Line \'{}\' has error=\'{}\''.format(output_dev_name, sys.exc_traceback.tb_lineno, err))   

        finally:
            if self.globals['debug']['methodTraceActive']: self.method_tracer.threaddebug(u'Method End: Line {}'.format(inspect.currentframe().f_lineno))

    def processVolumeIncrease(self, plugin_action, output_dev):
        if self.globals['debug']['methodTraceActive']: self.method_tracer.threaddebug(u'Method Start: Line {}'.format(inspect.currentframe().f_lineno))

        try:
            if output_dev is None:
                self.general_logger.error(u'\'processVolumeIncrease\' Roon Controller Action \'{}\' ignored as no Output device specified in Action.'.format(plugin_action.pluginTypeId))
                return 

            # self.general_logger.error(u'Roon Controller plugin method \'processNext\' Plugin Action:\n{}\n'.format(plugin_action))   

            if not output_dev.states['output_connected']:
                self.general_logger.error(u'\'processVolumeIncrease\' Roon Controller Action \'{}\' ignored as Output \'{}\' is disconnected.'.format(plugin_action.pluginTypeId, output_dev.name))
                return

            output_id = output_dev.states['output_id']
            if output_id == '':
                self.general_logger.error(u'\'processVolumeIncrease\' Roon Controller Action \'{}\' ignored as Output \'{}\' is not connected to the Roon Core.'.format(plugin_action.pluginTypeId, output_dev.name))
                return

            volume_increment = int(plugin_action.props['volumeIncrease'])
            if volume_increment > 10:
                volume_increment = 1  # SAFETY CHECK!

            self.globals['roon']['api'].change_volume(output_id, volume_increment, method='relative_step')

        except StandardError as err:
            output_dev_name = 'Unknown Device'
            if output_dev is not None:
                output_dev_name = output_dev.name
            self.general_logger.error(u'\'processVolumeIncrease\' error detected for device \'{}\'. Line \'{}\' has error=\'{}\''.format(output_dev_name, sys.exc_traceback.tb_lineno, err))   

        finally:
            if self.globals['debug']['methodTraceActive']: self.method_tracer.threaddebug(u'Method End: Line {}'.format(inspect.currentframe().f_lineno))


    def processVolumeDecrease(self, plugin_action, output_dev):
        if self.globals['debug']['methodTraceActive']: self.method_tracer.threaddebug(u'Method Start: Line {}'.format(inspect.currentframe().f_lineno))

        try:
            if output_dev is None:
                self.general_logger.error(u'\'processVolumeDecrease\' Roon Controller Action \'{}\' ignored as no Output device specified in Action.'.format(plugin_action.pluginTypeId))
                return 

            # self.general_logger.error(u'Roon Controller plugin method \'processNext\' Plugin Action:\n{}\n'.format(plugin_action))   

            if not output_dev.states['output_connected']:
                self.general_logger.error(u'\'processVolumeDecrease\' Roon Controller Action \'{}\' ignored as Output \'{}\' is disconnected.'.format(plugin_action.pluginTypeId, output_dev.name))
                return

            output_id = output_dev.states['output_id']
            if output_id == '':
                self.general_logger.error(u'\'processVolumeDecrease\' Roon Controller Action \'{}\' ignored as Output \'{}\' is not connected to the Roon Core.'.format(plugin_action.pluginTypeId, output_dev.name))
                return

            volume_decrement = -int(plugin_action.props['volumeDecrease'])
            if volume_decrement > -1:
                volume_decrement = -1  # SAFETY CHECK!

            self.globals['roon']['api'].change_volume(output_id, volume_decrement, method='relative_step')

        except StandardError as err:
            output_dev_name = 'Unknown Device'
            if output_dev is not None:
                output_dev_name = output_dev.name
            self.general_logger.error(u'\'processVolumeIncrease\' error detected for device \'{}\'. Line \'{}\' has error=\'{}\''.format(output_dev_name, sys.exc_traceback.tb_lineno, err))   

        finally:
            if self.globals['debug']['methodTraceActive']: self.method_tracer.threaddebug(u'Method End: Line {}'.format(inspect.currentframe().f_lineno))


    def processGroupOutputs(self, plugin_action, output_dev):
        if self.globals['debug']['methodTraceActive']: self.method_tracer.threaddebug(u'Method Start: Line {}'.format(inspect.currentframe().f_lineno))

        try:
            if output_dev is None:
                self.general_logger.error(u'\'processGroupOutputs\' Roon Controller Action \'{}\' ignored as no Output device specified in Action.'.format(plugin_action.pluginTypeId))
                return 

            # self.general_logger.error(u'Roon Controller plugin method \'processNext\' Plugin Action:\n{}\n'.format(plugin_action))   

            if not output_dev.states['output_connected']:
                self.general_logger.error(u'\'processGroupOutputs\' Roon Controller Action \'{}\' ignored as Output \'{}\' is disconnected.'.format(plugin_action.pluginTypeId, output_dev.name))
                return

            output_id = output_dev.states['output_id']
            if output_id == '':
                self.general_logger.error(u'\'processGroupOutputs\' Roon Controller Action \'{}\' ignored as Output \'{}\' is not connected to the Roon Core.'.format(plugin_action.pluginTypeId, output_dev.name))
                return

            forceGroupAction = bool(plugin_action.props.get('forceGroupAction', True))

            output_dev_plugin_props = output_dev.pluginProps
            output_id = output_dev_plugin_props.get('roonOutputId', '')

            outputs_to_group_list = [output_id]

            output_ids = plugin_action.props['roonOutputsList']

            for output_id in output_ids:
                outputs_to_group_list.append(output_id.strip())

            for output_id_to_group in outputs_to_group_list:
                output_dev_to_group = indigo.devices[self.globals['roon']['outputIdToDevId'][output_id_to_group]]

                if not output_dev_to_group.states['output_connected']:
                    self.general_logger.error(u'\'processGroupOutputs\' Roon Controller Action \'{}\' ignored as Output to group \'{}\' is disconnected.'.format(plugin_action.pluginTypeId, output_dev_to_group.name))
                    return

                output_id = output_dev.states['output_id']
                if output_id == '':
                    self.general_logger.debug(u'\'processGroupOutputs\' Roon Controller Action \'{}\' ignored as Output \'{}\' is not connected to the Roon Core.'.format(plugin_action.pluginTypeId, output_dev_to_group.name))
                    return




            if len(outputs_to_group_list) > 0:
                self.globals['roon']['api'].group_outputs(outputs_to_group_list)

        except StandardError as err:
            output_dev_name = 'Unknown Device'
            if output_dev is not None:
                output_dev_name = output_dev.name
            self.general_logger.error(u'\'processGroupOutputs\' error detected for device \'{}\'. Line \'{}\' has error=\'{}\''.format(output_dev_name, sys.exc_traceback.tb_lineno, err))   

        finally:
            if self.globals['debug']['methodTraceActive']: self.method_tracer.threaddebug(u'Method End: Line {}'.format(inspect.currentframe().f_lineno))


    def _supplyAvailableRoonOutputsList(self, filter, valuesDict, type_id, output_dev_id):
        if self.globals['debug']['methodTraceActive']: self.method_tracer.threaddebug(u'Method Start: Line {}'.format(inspect.currentframe().f_lineno))

        try:
            roonOutputToGroupToName = indigo.devices[output_dev_id].name
            valuesDict["roonOutputToGroupTo"] = roonOutputToGroupToName

            availableRoonOutputsDevicesList = list()

            for output_dev in indigo.devices:
                if output_dev.deviceTypeId == 'roonOutput' and output_dev.id != output_dev_id and output_dev.states['output_connected']:

                    output_dev_plugin_props = output_dev.pluginProps
                    output_id = output_dev_plugin_props.get('roonOutputId', '')


                    availableRoonOutputsDevicesList.append((output_id, output_dev.name))

            def getRoonOutputName(roonOutputNameItem):
                return roonOutputNameItem[1]

            return sorted(availableRoonOutputsDevicesList, key=getRoonOutputName)

        except StandardError as err:
            # output_dev_name = 'Unknown Device'
            # if output_dev is not None:
            #     output_dev_name = output_dev.name
            # self.general_logger.error(u'\'processGroupOutputs\' error detected for device \'{}\'. Line \'{}\' has error=\'{}\''.format(output_dev_name, sys.exc_traceback.tb_lineno, err))   
            self.general_logger.error(u'\'_supplyAvailableRoonOutputsList\' error detected. Line \'{}\' has error=\'{}\''.format(sys.exc_traceback.tb_lineno, err))   

        finally:
            if self.globals['debug']['methodTraceActive']: self.method_tracer.threaddebug(u'Method End: Line {}'.format(inspect.currentframe().f_lineno))


    def roonZonesSelection(self, valuesDict, type_id, zone_dev_id):
        if self.globals['debug']['methodTraceActive']: self.method_tracer.threaddebug(u'Method Start: Line {}'.format(inspect.currentframe().f_lineno))

        try:
            self.general_logger.error(u'\'roonZonesSelection\' valuesdict:\n{}\n'.format(valuesDict))

            return valuesDict

        except StandardError as err:
            # zone_dev_name = 'Unknown Device'
            # if zone_dev is not None:
            #     zone_dev_name = zone_dev.name
            # self.general_logger.error(u'\'processGroupOutputs\' error detected for device \'{}\'. Line \'{}\' has error=\'{}\''.format(zone_dev_name, sys.exc_traceback.tb_lineno, err))   
            self.general_logger.error(u'\'roonZonesSelection\' error detected. Line \'{}\' has error=\'{}\''.format(sys.exc_traceback.tb_lineno, err))   

        finally:
            if self.globals['debug']['methodTraceActive']: self.method_tracer.threaddebug(u'Method End: Line {}'.format(inspect.currentframe().f_lineno))


    def getDeviceConfigUiValues(self, pluginProps, typeId, devId):
        if self.globals['debug']['methodTraceActive']: self.method_tracer.threaddebug(u'Method Start: Line {}'.format(inspect.currentframe().f_lineno))

        try:
            if self.globals['debug']['methodTraceActive']: self.method_tracer.threaddebug(u'Method Start: Line {}'.format(inspect.currentframe().f_lineno))

            if typeId == 'roonZone':
                if 'roonZoneUniqueIdentityKey' not in pluginProps:
                    pluginProps['roonZoneUniqueIdentityKey'] = '-'
                if 'autoNameNewRoonZone' not in pluginProps:
                    pluginProps['autoNameNewRoonZone'] = True 
                if 'dynamicGroupedZoneRename' not in pluginProps:
                    pluginProps['dynamicGroupedZoneRename'] = self.globals['config']['dynamicGroupedZonesRename'] 
            elif typeId == 'roonOutput':
                if 'roonOutputId' not in pluginProps:
                    pluginProps['roonOutputId'] = '-'

        except StandardError as err:
            self.general_logger.error(u'\'getDeviceConfigUiValues\' error detected for device \'{}\'. Line \'{}\' has error=\'{}\''.format(indigo.devices[devId].name, sys.exc_traceback.tb_lineno, err))   

        finally:
            if self.globals['debug']['methodTraceActive']: self.method_tracer.threaddebug(u'Method End: Line {}'.format(inspect.currentframe().f_lineno))

            return super(Plugin, self).getDeviceConfigUiValues(pluginProps, typeId, devId)

    def validateDeviceConfigUi(self, valuesDict, typeId, devId):  # Validate Roon device
        if self.globals['debug']['methodTraceActive']: self.method_tracer.threaddebug(u'Method Start: Line {}'.format(inspect.currentframe().f_lineno))

        try:
            if self.globals['debug']['methodTraceActive']: self.method_tracer.threaddebug(u'Method Start: Line {}'.format(inspect.currentframe().f_lineno))

            if typeId == 'roonZone':
                valid = False
                if 'roonZoneUniqueIdentityKey' in valuesDict and len(valuesDict['roonZoneUniqueIdentityKey']) > 5:
                    valid = True
                if not valid:
                    errorDict = indigo.Dict()
                    errorDict["roonZoneUniqueIdentityKey"] = "No Roon Zone selected or available"
                    errorDict["showAlertText"] = "You must select an available Roon Zone to be able to create the Roon Zone device."
                    return False, valuesDict, errorDict

            elif typeId == 'roonOutput':
                valid = False
                if 'roonOutputId' in valuesDict and len(valuesDict['roonOutputId']) > 5:
                    valid = True
                if not valid:
                    errorDict = indigo.Dict()
                    errorDict["roonOutputId"] = "No Roon Output selected or available"
                    errorDict["showAlertText"] = "You must select an available Roon Output to be able to create the Roon Output device."
                    return False, valuesDict, errorDict

            return True, valuesDict

        except StandardError as err:
            self.general_logger.error(u'\'validateDeviceConfigUi\' error detected for device \'{}\'. Line \'{}\' has error=\'{}\''.format(indigo.devices[devId].name, sys.exc_traceback.tb_lineno, err))   

        finally:
            if self.globals['debug']['methodTraceActive']: self.method_tracer.threaddebug(u'Method End: Line {}'.format(inspect.currentframe().f_lineno))

    def closedDeviceConfigUi(self, valuesDict, userCancelled, typeId,devId):
        if self.globals['debug']['methodTraceActive']: self.method_tracer.threaddebug(u'Method Start: Line {}'.format(inspect.currentframe().f_lineno))

        try:
            if self.globals['debug']['methodTraceActive']: self.method_tracer.threaddebug(u'Method Start: Line {}'.format(inspect.currentframe().f_lineno))

            self.general_logger.debug(u'\'closedDeviceConfigUi\' called with userCancelled = {}'.format(str(userCancelled)))  

            if userCancelled:
                return

        except StandardError as e:
            self.general_logger.error(u'\'closedDeviceConfigUi\' error detected. Line \'{}\' has error=\'{}\''.format(sys.exc_traceback.tb_lineno, e))   
            return True

    # def createOutputDevice(self, zone_id):
    #     if self.globals['debug']['methodTraceActive']: self.method_tracer.threaddebug(u'Method Start: Line {}'.format(inspect.currentframe().f_lineno))
    #     pass

    # def createZoneDevice(self, zone_id):
    #     if self.globals['debug']['methodTraceActive']: self.method_tracer.threaddebug(u'Method Start: Line {}'.format(inspect.currentframe().f_lineno))
    #     pass 

        finally:
            if self.globals['debug']['methodTraceActive']: self.method_tracer.threaddebug(u'Method End: Line {}'.format(inspect.currentframe().f_lineno))

    def didDeviceCommPropertyChange(self, origDev, newDev):
        if origDev.deviceTypeId == 'roonZone':
            if 'dynamicGroupedZoneRename' in origDev.pluginProps:
                if origDev.pluginProps['dynamicGroupedZoneRename'] != newDev.pluginProps['dynamicGroupedZoneRename']:
                    return True
        return False

    def deviceStartComm(self, dev):
        if self.globals['debug']['methodTraceActive']: self.method_tracer.threaddebug(u'Method Start: Line {}'.format(inspect.currentframe().f_lineno))

        try:
            dev.stateListOrDisplayStateIdChanged()  # Ensure latest devices.xml is being used

            if dev.deviceTypeId == 'roonZone':
                zone_dev = dev
                zone_dev_plugin_props = zone_dev.pluginProps
                zoneUniqueIdentityKey = zone_dev_plugin_props.get('roonZoneUniqueIdentityKey', '')
                if zoneUniqueIdentityKey != '':
                    self.globals['roon']['zoneUniqueIdentityKeyToDevId'][zoneUniqueIdentityKey] = zone_dev.id

                zone_id = ''
                for found_zone_id in self.globals['roon']['zones']:
                    if 'zoneUniqueIdentityKey' in self.globals['roon']['zones'][found_zone_id]:
                        if zoneUniqueIdentityKey == self.globals['roon']['zones'][found_zone_id]['zoneUniqueIdentityKey']:
                            zone_id = found_zone_id

                            # LOGIC TO HANDLE PLUGIN PROPS 'roonZoneId' ?????
                            devPluginProps = dev.pluginProps
                            devPluginProps['roonZoneId'] = zone_id
                            dev.replacePluginPropsOnServer(devPluginProps)

                            break

                try:
                    sharedProps = dev.sharedProps
                    sharedProps["sqlLoggerIgnoreStates"] = "queue_time_remaining, remaining, seek_position, ui_queue_time_remaining, ui_remaining, ui_seek_position"
                    dev.replaceSharedPropsOnServer(sharedProps)
                except:
                    pass


                if zone_dev.address[0:5] != 'ZONE-':
                    # At this point it is a brand new Roon Zone device as address not setup

                    if zone_id != '':
                        outputCount = self.globals['roon']['zones'][zone_id]['outputs_count']
                    else:
                        outputCount = 0
                    addressAlpha = self.globals['roon']['availableZoneAlphas'].pop(0)
                    if addressAlpha[0:1] == '_':
                        addressAlpha = addressAlpha[1:2]
                    if outputCount > 0:              
                        address = 'ZONE-{}-{}'.format(addressAlpha, outputCount)
                    else:
                        address = 'ZONE-{}'.format(addressAlpha)
                    zone_dev_plugin_props["address"] = address
                    zone_dev.replacePluginPropsOnServer(zone_dev_plugin_props)

                # At this point it is an existing Roon Zone device as address already setup

                if zone_id == '':
                    # Flag as disconnected as Zone doesn't exist
                    self.disconnectRoonZoneDevice(zone_dev.id)
                    return

                # Next section of logic just creates a Zone  image folder with a dummy text file with the display name of the Zone to aid in viewing the image folder structure
                zoneImageFolder = '{}/{}'.format(self.globals['roon']['pluginPrefsFolder'], zone_dev.address)
                if not os.path.exists(zoneImageFolder):
                    try:
                        mkdir_with_mode(zoneImageFolder)
                    except FileExistsError:  # Handles the situation where the folder gets created by image processing in between the check and mkdifr statements!
                        pass
                else:
                    file_list = os.listdir(zoneImageFolder)
                    for fileName in file_list:
                        if fileName.endswith(".txt"):
                            os.remove(os.path.join(zoneImageFolder, fileName))

                zone_id_file_name = u'{}/_{}.txt'.format(zoneImageFolder, zone_dev.name.upper())
                zone_id_file = open(zone_id_file_name, 'w')
                zone_id_file.write('{}'.format(zone_dev.name))
                zone_id_file.close()

                self.updateRoonZoneDevice(zone_dev.id, zone_id)

            elif dev.deviceTypeId == 'roonOutput':
                output_dev = dev
                output_id = output_dev.pluginProps.get('roonOutputId', '')

                if output_dev.address[0:4] != 'OUT-':
                    addressNumber = self.globals['roon']['availableOutputNumbers'].pop(0)
                    if addressNumber[0:1] == '_':
                        addressNumber = addressNumber[1:2]
                    address = 'OUT-{}'.format(addressNumber)
                    output_dev_plugin_props = output_dev.pluginProps
                    output_dev_plugin_props["address"] = address

                    self.globals['roon']['mapOutput'][addressNumber] = dict()
                    self.globals['roon']['mapOutput'][addressNumber]['indigoDevId'] = output_dev.id
                    self.globals['roon']['mapOutput'][addressNumber]['roonOutputId'] = output_id
                    output_dev.replacePluginPropsOnServer(output_dev_plugin_props)
                    return

                if output_id not in self.globals['roon']['outputs']:
                    key_value_list = [
                        {'key': 'output_connected', 'value': False},
                        {'key': 'output_status', 'value': 'disconnected'},
                    ]
                    output_dev.updateStatesOnServer(key_value_list)
                    output_dev.updateStateImageOnServer(indigo.kStateImageSel.PowerOff)
                    return

                self.updateRoonOutputDevice(output_dev.id, output_id)

        except StandardError as err:
            self.general_logger.error(u'\'deviceStartComm\' error detected for device \'{}\'. Line \'{}\' has error=\'{}\''.format(dev.name, sys.exc_traceback.tb_lineno, err))   

        finally:
            if self.globals['debug']['methodTraceActive']: self.method_tracer.threaddebug(u'Method End: Line {}'.format(inspect.currentframe().f_lineno))

    def convertOutputIdListToString(self, roonZoneOutputsList):
        if self.globals['debug']['methodTraceActive']: self.method_tracer.threaddebug(u'Method Start: Line {}'.format(inspect.currentframe().f_lineno))

        try:
            outputsListString = ''

            if type(roonZoneOutputsList) is list:
                for outputId in roonZoneOutputsList:
                    if outputsListString == '':
                        outputsListString = u'{}'.format(outputId)
                    else:
                        outputsListString = u'{}#{}'.format(outputsListString, outputId)

                return outputsListString
            else:
                return roonZoneOutputsList

        except StandardError as err:
            self.general_logger.error(u'\'convertOutputIdListToString\' error detected. Line \'{}\' has error=\'{}\''.format(sys.exc_traceback.tb_lineno, err))   

        finally:
            if self.globals['debug']['methodTraceActive']: self.method_tracer.threaddebug(u'Method End: Line {}'.format(inspect.currentframe().f_lineno))

    def updateRoonZoneDevice(self, roonZoneDevId, zone_id):
        if self.globals['debug']['methodTraceActive']: self.method_tracer.threaddebug(u'Method Start: Line {}'.format(inspect.currentframe().f_lineno))

        new_device_name = ''
        zone_dev = indigo.devices[roonZoneDevId]

        try:
            auto_name_new_roon_zone = bool(zone_dev.pluginProps.get('autoNameNewRoonZone', True))  
            if auto_name_new_roon_zone and zone_dev.name[0:10] == 'new device':

                zone_name = u'{}'.format(self.globals['roon']['zones'][zone_id]['display_name'])
                new_device_name = u'Roon Zone - {}'.format(zone_name)

                try:
                    zone_dev.pluginProps.update({'roonZoneName': zone_name})
                    zone_dev.replacePluginPropsOnServer(zone_dev.pluginProps)

                    outputCount = self.globals['roon']['zones'][zone_id]['outputs_count']
                    if outputCount == 0:
                        new_device_name = u'Roon Zone - {}'.format(zone_name)
                    else:
                        temp_zone_name = self.globals['roon']['zones'][zone_id]['outputs'][1]['display_name']
                        for i in range(2, outputCount + 1):
                            temp_zone_name = '{} + {}'.format(temp_zone_name, self.globals['roon']['zones'][zone_id]['outputs'][i]['display_name'])
                        new_device_name = u'Roon Zone - {}'.format(temp_zone_name)

                    self.general_logger.error(u'\'updateRoonZoneDevice\' [Auto-name - New Device]; Debug Info of rename Roon Zone from \'{}\' to \'{}\''.format(zone_dev.name, device_name))   

                    zone_dev.name = new_device_name
                    zone_dev.replaceOnServer()
                except StandardError as err:
                    self.general_logger.error(u'\'updateRoonZoneDevice\' [Auto-name]; Unable to rename Roon Zone from \'{}\' to \'{}\'. Line \'{}\' has error=\'{}\''.format(zone_dev.name, device_name, sys.exc_traceback.tb_lineno, err))   

            # Only check for a roon zone device dynamic rename if a grouped zone
            if self.globals['roon']['zones'][zone_id]['outputs_count'] > 1:
                dynamic_rename_check_required = bool(zone_dev.pluginProps.get('dynamicGroupedZoneRename', False))  # True if Dynamic Rename Check Required
                if dynamic_rename_check_required:
                    try:
                        outputCount = self.globals['roon']['zones'][zone_id]['outputs_count']
                        if outputCount > 0:
                            new_zone_name = self.globals['roon']['zones'][zone_id]['outputs'][1]['display_name']
                            for i in range(2, outputCount + 1):
                                new_zone_name = '{} + {}'.format(new_zone_name, self.globals['roon']['zones'][zone_id]['outputs'][i]['display_name'])
                            new_device_name = u'Roon Zone - {}'.format(new_zone_name)

                            old_zone_name = zone_dev.pluginProps.get('roonZoneName', '-')  # e.g. 'Study + Dining Room'



                            if new_device_name != old_zone_name:  # e.g. 'Study + Kitchen' != 'Study + Dining Room'
                                #self.general_logger.error(u'\'updateRoonZoneDevice\' [Auto-name 0]; Debug Info of rename Roon Zone device from \'{}\' to \'{}\''.format(old_zone_name, new_zone_name))   
                                zone_dev_props = zone_dev.pluginProps
                                zone_dev_props['roonZoneName'] = new_zone_name
                                zone_dev.replacePluginPropsOnServer(zone_dev_props)

                                # indigo.server.log(u'\'updateRoonZoneDevice\' [Auto-name 00]:\n{}'.format(zone_dev.ownerProps)) # "Roon Zone - Study + Master Bedroom"

                            if new_device_name != zone_dev.name:  # e.g. 'Roon Zone - Study + Kitchen'

                                # self.general_logger.error(u'\'updateRoonZoneDevice\' [Auto-name 2]; Debug Info of rename Roon Zone device from \'{}\' to \'{}\''.format(zone_dev.name, new_device_name))   
                                zone_dev.name = new_device_name
                                zone_dev.replaceOnServer()

                                # indigo.server.log(u'\'updateRoonZoneDevice\' [Auto-name 22]:\n{}'.format(zone_dev.ownerProps)) # "Roon Zone - Study + Master Bedroom"


                    except StandardError as err:
                        self.general_logger.error(u'\'updateRoonZoneDevice\' [Dynamic Rename]; Unable to rename Roon Zone from \'{}\' to \'{}\'. Line \'{}\' has error=\'{}\''.format(originalZoneDevName, new_device_name, sys.exc_traceback.tb_lineno, err))   

            if 1 in self.globals['roon']['zones'][zone_id]['outputs']:
                output_id_1 = self.globals['roon']['zones'][zone_id]['outputs'][1]['output_id']
            else:  
                output_id_1 = ''
            if 2 in self.globals['roon']['zones'][zone_id]['outputs']:
                output_id_2 = self.globals['roon']['zones'][zone_id]['outputs'][2]['output_id']
            else:  
                output_id_2 = ''
            if 3 in self.globals['roon']['zones'][zone_id]['outputs']:
                output_id_3 = self.globals['roon']['zones'][zone_id]['outputs'][3]['output_id']
            else:  
                output_id_3 = ''
            if 4 in self.globals['roon']['zones'][zone_id]['outputs']:
                output_id_4 = self.globals['roon']['zones'][zone_id]['outputs'][4]['output_id']
            else:  
                output_id_4 = ''
            if 5 in self.globals['roon']['zones'][zone_id]['outputs']:
                output_id_5 = self.globals['roon']['zones'][zone_id]['outputs'][5]['output_id']
            else:  
                output_id_5 = ''

            if 1 in self.globals['roon']['zones'][zone_id]['now_playing']['artist_image_keys']:
                artist_image_key_1 = self.globals['roon']['zones'][zone_id]['now_playing']['artist_image_keys'][1]
            else:
                artist_image_key_1 = ''
            self.processImage(ARTIST, '1', zone_dev, artist_image_key_1)

            if 2 in self.globals['roon']['zones'][zone_id]['now_playing']['artist_image_keys']:
                artist_image_key_2 = self.globals['roon']['zones'][zone_id]['now_playing']['artist_image_keys'][2]
            else:
                artist_image_key_2 = ''
            self.processImage(ARTIST, '2', zone_dev, artist_image_key_2)

            if 3 in self.globals['roon']['zones'][zone_id]['now_playing']['artist_image_keys']:
                artist_image_key_3 = self.globals['roon']['zones'][zone_id]['now_playing']['artist_image_keys'][3]
            else:
                artist_image_key_3 = ''
            self.processImage(ARTIST, '3', zone_dev, artist_image_key_3)

            if 4 in self.globals['roon']['zones'][zone_id]['now_playing']['artist_image_keys']:
                artist_image_key_4 = self.globals['roon']['zones'][zone_id]['now_playing']['artist_image_keys'][4]
            else:
                artist_image_key_4 = ''
            self.processImage(ARTIST, '4', zone_dev, artist_image_key_4)

            if 5 in self.globals['roon']['zones'][zone_id]['now_playing']['artist_image_keys']:
                artist_image_key_5 = self.globals['roon']['zones'][zone_id]['now_playing']['artist_image_keys'][5]
            else:
                artist_image_key_5 = ''
            self.processImage(ARTIST, '5', zone_dev, artist_image_key_5)

            self.processImage(ALBUM, '', zone_dev, self.globals['roon']['zones'][zone_id]['now_playing']['image_key'])

            zone_status = 'stopped'
            if self.globals['roon']['zones'][zone_id]['state'] == 'playing':
                zone_dev.updateStateImageOnServer(indigo.kStateImageSel.AvPlaying)
                zone_status = 'playing'
            elif self.globals['roon']['zones'][zone_id]['state'] == 'paused':
                zone_dev.updateStateImageOnServer(indigo.kStateImageSel.AvPaused)
                zone_status = 'Paused'
            else:
                zone_dev.updateStateImageOnServer(indigo.kStateImageSel.AvStopped)

            key_value_list = list()

            if not zone_dev.states['zone_connected']:
                key_value_list.append({'key': 'zone_connected', 'value': True})

            if zone_dev.states['zone_status'] != zone_status:
                key_value_list.append({'key': 'zone_status', 'value': zone_status})

            if zone_dev.states['zone_id'] != self.globals['roon']['zones'][zone_id]['zone_id']:
                key_value_list.append({'key': 'zone_id', 'value': self.globals['roon']['zones'][zone_id]['zone_id']})

            if zone_dev.states['display_name'] != self.globals['roon']['zones'][zone_id]['display_name']:
                key_value_list.append({'key': 'display_name', 'value': self.globals['roon']['zones'][zone_id]['display_name']})

            if zone_dev.states['auto_radio'] != self.globals['roon']['zones'][zone_id]['settings']['auto_radio']:
                key_value_list.append({'key': 'auto_radio', 'value': self.globals['roon']['zones'][zone_id]['settings']['auto_radio']})

            if zone_dev.states['shuffle'] != self.globals['roon']['zones'][zone_id]['settings']['shuffle']:
                key_value_list.append({'key': 'shuffle', 'value': self.globals['roon']['zones'][zone_id]['settings']['shuffle']})

            if zone_dev.states['loop'] != self.globals['roon']['zones'][zone_id]['settings']['loop']:
                key_value_list.append({'key': 'loop', 'value': self.globals['roon']['zones'][zone_id]['settings']['loop']})

            if zone_dev.states['number_of_outputs'] != self.globals['roon']['zones'][zone_id]['outputs_count']:
                key_value_list.append({'key': 'number_of_outputs', 'value': self.globals['roon']['zones'][zone_id]['outputs_count']})

            if zone_dev.states['output_1_id'] != output_id_1:
                key_value_list.append({'key': 'output_1_id', 'value': output_id_1})

            if zone_dev.states['output_2_id'] != output_id_2:
                key_value_list.append({'key': 'output_2_id', 'value': output_id_2})

            if zone_dev.states['output_3_id'] != output_id_3:
                key_value_list.append({'key': 'output_3_id', 'value': output_id_3})

            if zone_dev.states['output_4_id'] != output_id_4:
                key_value_list.append({'key': 'output_4_id', 'value': output_id_4})

            if zone_dev.states['output_5_id'] != output_id_5:
                key_value_list.append({'key': 'output_5_id', 'value': output_id_5})

            if zone_dev.states['number_of_artist_image_keys'] != self.globals['roon']['zones'][zone_id]['now_playing']['artist_image_keys_Count']:
                key_value_list.append({'key': 'number_of_artist_image_keys', 'value': self.globals['roon']['zones'][zone_id]['now_playing']['artist_image_keys_Count']})

            if zone_dev.states['artist_image_Key_1_id'] != artist_image_key_1:
                key_value_list.append({'key': 'artist_image_Key_1_id', 'value': artist_image_key_1})

            if zone_dev.states['artist_image_Key_2_id'] != artist_image_key_2:
                key_value_list.append({'key': 'artist_image_Key_2_id', 'value': artist_image_key_2})

            if zone_dev.states['artist_image_Key_3_id'] != artist_image_key_3:
                key_value_list.append({'key': 'artist_image_Key_3_id', 'value': artist_image_key_3})

            if zone_dev.states['artist_image_Key_4_id'] != artist_image_key_4:
                key_value_list.append({'key': 'artist_image_Key_4_id', 'value': artist_image_key_4})

            if zone_dev.states['artist_image_Key_5_id'] != artist_image_key_5:
                key_value_list.append({'key': 'artist_image_Key_5_id', 'value': artist_image_key_5})

            if zone_dev.states['image_key'] != self.globals['roon']['zones'][zone_id]['now_playing']['image_key']:
                key_value_list.append({'key': 'image_key', 'value': self.globals['roon']['zones'][zone_id]['now_playing']['image_key']})

            if zone_dev.states['one_line_1'] != self.globals['roon']['zones'][zone_id]['now_playing']['one_line']['line1']:
                key_value_list.append({'key': 'one_line_1', 'value': self.globals['roon']['zones'][zone_id]['now_playing']['one_line']['line1']})

            if zone_dev.states['two_line_1'] != self.globals['roon']['zones'][zone_id]['now_playing']['two_line']['line1']:
                key_value_list.append({'key': 'two_line_1', 'value': self.globals['roon']['zones'][zone_id]['now_playing']['two_line']['line1']})

            if zone_dev.states['two_line_2'] != self.globals['roon']['zones'][zone_id]['now_playing']['two_line']['line2']:
                key_value_list.append({'key': 'two_line_2', 'value': self.globals['roon']['zones'][zone_id]['now_playing']['two_line']['line2']})

            if zone_dev.states['three_line_1'] != self.globals['roon']['zones'][zone_id]['now_playing']['three_line']['line1']:
                key_value_list.append({'key': 'three_line_1', 'value': self.globals['roon']['zones'][zone_id]['now_playing']['three_line']['line1']})

            if zone_dev.states['three_line_2'] != self.globals['roon']['zones'][zone_id]['now_playing']['three_line']['line2']:
                key_value_list.append({'key': 'three_line_2', 'value': self.globals['roon']['zones'][zone_id]['now_playing']['three_line']['line2']})

            if zone_dev.states['three_line_3'] != self.globals['roon']['zones'][zone_id]['now_playing']['three_line']['line3']:
                key_value_list.append({'key': 'three_line_3', 'value': self.globals['roon']['zones'][zone_id]['now_playing']['three_line']['line3']})

            if zone_dev.states['length'] != self.globals['roon']['zones'][zone_id]['now_playing']['length']:
                key_value_list.append({'key': 'length', 'value': self.globals['roon']['zones'][zone_id]['now_playing']['length']})
                ui_length = self.uiTime(self.globals['roon']['zones'][zone_id]['now_playing']['length'])
                key_value_list.append({'key': 'ui_length', 'value': ui_length})

            if zone_dev.states['seek_position'] != self.globals['roon']['zones'][zone_id]['now_playing']['seek_position']:
                key_value_list.append({'key': 'seek_position', 'value': self.globals['roon']['zones'][zone_id]['now_playing']['seek_position']})

            if zone_dev.states['remaining'] != 0:
                key_value_list.append({'key': 'remaining', 'value': 0})
                key_value_list.append({'key': 'ui_remaining', 'value': '0:00'})

            if zone_dev.states['is_previous_allowed'] != self.globals['roon']['zones'][zone_id]['is_previous_allowed']:
                key_value_list.append({'key': 'is_previous_allowed', 'value': self.globals['roon']['zones'][zone_id]['is_previous_allowed']})

            if zone_dev.states['is_pause_allowed'] != self.globals['roon']['zones'][zone_id]['is_pause_allowed']:
                key_value_list.append({'key': 'is_pause_allowed', 'value': self.globals['roon']['zones'][zone_id]['is_pause_allowed']})

            if zone_dev.states['is_seek_allowed'] != self.globals['roon']['zones'][zone_id]['is_seek_allowed']:
                key_value_list.append({'key': 'is_seek_allowed', 'value': self.globals['roon']['zones'][zone_id]['is_seek_allowed']})

            if zone_dev.states['state'] != self.globals['roon']['zones'][zone_id]['state']:
                key_value_list.append({'key': 'state', 'value': self.globals['roon']['zones'][zone_id]['state']})

            if zone_dev.states['is_play_allowed'] != self.globals['roon']['zones'][zone_id]['is_play_allowed']:
                key_value_list.append({'key': 'is_play_allowed', 'value': self.globals['roon']['zones'][zone_id]['is_play_allowed']})

            if zone_dev.states['is_next_allowed'] != self.globals['roon']['zones'][zone_id]['is_next_allowed']:
                key_value_list.append({'key': 'is_next_allowed', 'value': self.globals['roon']['zones'][zone_id]['is_next_allowed']})

            if len(key_value_list) > 0:
                zone_dev.updateStatesOnServer(key_value_list)

        except StandardError as err:
            self.general_logger.error(u'\'updateRoonZoneDevice\' error detected for device \'{}\'. Line \'{}\' has error=\'{}\''.format(zone_dev.name, sys.exc_traceback.tb_lineno, err))   

        finally:
            if self.globals['debug']['methodTraceActive']: self.method_tracer.threaddebug(u'Method End: Line {}'.format(inspect.currentframe().f_lineno))

    def processImage(self, image_type, image_suffix, zone_dev, image_key):
        if self.globals['debug']['methodTraceActive']: self.method_tracer.threaddebug(u'Method Start: Line {}'.format(inspect.currentframe().f_lineno))

        try:
            # Next section of logic just creates a Zone  image folder with a dummy text file with the display name of the Zone to aid in viewing the image folder structure
            zoneImageFolder = '{}/{}'.format(self.globals['roon']['pluginPrefsFolder'], zone_dev.address)
            if not os.path.exists(zoneImageFolder):
                try:
                    mkdir_with_mode(zoneImageFolder)
                except FileExistsError:  # Handles the situation where the folder gets created by device start processing in between the check and mkdifr statements!
                    pass

            image_name = ['Artist_Image', 'Album_Image'][image_type]
            if image_suffix != '':
                image_name = '{}_{}'.format(image_name, image_suffix)
            set_default_image = True 
            if image_key != '':
                image_url = self.globals['roon']['api'].get_image(image_key, scale = 'fill')
                work_file = '{}/{}/temp.jpg'.format(self.globals['roon']['pluginPrefsFolder'], zone_dev.address)
                image_request = requests.get(image_url)
                if image_request.status_code == 200:
                    try:
                        with open(work_file, 'wb') as f:
                            f.write(image_request.content)
                        image_to_process = Image.open(work_file)
                        output_image_file = '{}/{}/{}.png'.format(self.globals['roon']['pluginPrefsFolder'], zone_dev.address, image_name)
                        image_to_process.save(output_image_file)
                        try:
                            os.remove(work_file)
                        except:  # Not sure why this doesn't always work!
                            pass
                        set_default_image = False
                    except StandardError as err:
                        # leave as default image if any problem reported but only output debug message
                        self.general_logger.debug(u'\'processImage\' [DEBUG ONLY] error detected. Line \'{}\' has error: \'{}\''.format(sys.exc_traceback.tb_lineno, err))  
            if set_default_image:
                default_image_path = '{}/Plugins/Roon.indigoPlugin/Contents/Resources/'.format(self.globals['pluginInfo']['path'])
                if image_type == ARTIST:
                    default_image_file = '{}Artist_Image.png'.format(default_image_path)
                elif image_type == ALBUM:
                    default_image_file = '{}Album_Image.png'.format(default_image_path)
                else:
                    default_image_file = '{}Unknown_Image.png'.format(default_image_path)
                output_image_file = '{}/{}/{}.png'.format(self.globals['roon']['pluginPrefsFolder'], zone_dev.address, image_name)
                copyfile(default_image_file, output_image_file)

        except StandardError as err:
            self.general_logger.error(u'\'processImage\' error detected. Line \'{}\' has error: \'{}\''.format(sys.exc_traceback.tb_lineno, err))   

        finally:
            if self.globals['debug']['methodTraceActive']: self.method_tracer.threaddebug(u'Method End: Line {}'.format(inspect.currentframe().f_lineno))

    def disconnectRoonZoneDevice(self, roonZoneDevId):
        if self.globals['debug']['methodTraceActive']: self.method_tracer.threaddebug(u'Method Start: Line {}'.format(inspect.currentframe().f_lineno))

        zone_dev = indigo.devices[roonZoneDevId]

        try:
            key_value_list = [
                {'key': 'zone_connected', 'value': False},
                {'key': 'zone_status', 'value': 'disconnected'},
                {'key': 'zone_id', 'value': ''},
                {'key': 'display_name', 'value': ''},
                {'key': 'auto_radio', 'value': False},
                {'key': 'shuffle', 'value': False},
                {'key': 'loop', 'value': False},
                {'key': 'number_of_outputs', 'value': 0},
                {'key': 'output_1_id', 'value': ''},
                {'key': 'output_2_id', 'value': ''},
                {'key': 'output_3_id', 'value': ''},
                {'key': 'output_4_id', 'value': ''},
                {'key': 'output_5_id', 'value': ''},
                {'key': 'number_of_artist_image_keys', 'value': 0},
                {'key': 'artist_image_Key_1_id', 'value': ''},
                {'key': 'artist_image_Key_2_id', 'value': ''},
                {'key': 'artist_image_Key_3_id', 'value': ''},
                {'key': 'artist_image_Key_4_id', 'value': ''},
                {'key': 'artist_image_Key_5_id', 'value': ''},
                {'key': 'image_key', 'value': ''},
                {'key': 'one_line_1', 'value': ''},
                {'key': 'two_line_1', 'value': ''},
                {'key': 'two_line_2', 'value': ''},
                {'key': 'three_line_1', 'value': ''},
                {'key': 'three_line_2', 'value': ''},
                {'key': 'three_line_3', 'value': ''},
                {'key': 'length', 'value': 0},
                {'key': 'ui_length', 'value': '0:00'},
                {'key': 'seek_position', 'value': 0},
                {'key': 'remaining', 'value': 0},
                {'key': 'ui_remaining', 'value': '0:00'},
                {'key': 'is_previous_allowed', 'value': False},
                {'key': 'is_pause_allowed', 'value': False},
                {'key': 'is_seek_allowed', 'value': False},
                {'key': 'state', 'value': False},
                {'key': 'is_play_allowed', 'value': False},
                {'key': 'is_next_allowed', 'value': False}]

            zone_dev.updateStatesOnServer(key_value_list)
            zone_dev.updateStateImageOnServer(indigo.kStateImageSel.PowerOff)

        except StandardError as err:
            self.general_logger.error(u'\'updateRoonZoneDevice\' error detected for device \'{}\'. Line \'{}\' has error=\'{}\''.format(zone_dev.name, sys.exc_traceback.tb_lineno, err))   

        finally:
            if self.globals['debug']['methodTraceActive']: self.method_tracer.threaddebug(u'Method End: Line {}'.format(inspect.currentframe().f_lineno))

    def updateRoonOutputDevice(self, roonOutputDevId, output_id):
        if self.globals['debug']['methodTraceActive']: self.method_tracer.threaddebug(u'Method Start: Line {}'.format(inspect.currentframe().f_lineno))

        output_dev = indigo.devices[roonOutputDevId]

        try:
            if 1 in self.globals['roon']['outputs'][output_id]['can_group_with_output_ids']:
                can_group_with_output_id_1 = self.globals['roon']['outputs'][output_id]['can_group_with_output_ids'][1]
            else:
                can_group_with_output_id_1 = ''
            if 2 in self.globals['roon']['outputs'][output_id]['can_group_with_output_ids']:
                can_group_with_output_id_2 = self.globals['roon']['outputs'][output_id]['can_group_with_output_ids'][2]
            else:
                can_group_with_output_id_2 = ''
            if 3 in self.globals['roon']['outputs'][output_id]['can_group_with_output_ids']:
                can_group_with_output_id_3 = self.globals['roon']['outputs'][output_id]['can_group_with_output_ids'][3]
            else:
                can_group_with_output_id_3 = ''
            if 4 in self.globals['roon']['outputs'][output_id]['can_group_with_output_ids']:
                can_group_with_output_id_4 = self.globals['roon']['outputs'][output_id]['can_group_with_output_ids'][4]
            else:
                can_group_with_output_id_4 = ''
            if 5 in self.globals['roon']['outputs'][output_id]['can_group_with_output_ids']:
                can_group_with_output_id_5 = self.globals['roon']['outputs'][output_id]['can_group_with_output_ids'][5]
            else:
                can_group_with_output_id_5 = ''

            key_value_list = list()
            if not output_dev.states['output_connected']:
                key_value_list.append({'key': 'output_connected', 'value': True})
            if output_dev.states['output_status'] != 'connected':
                key_value_list.append({'key': 'output_status', 'value': 'connected'})
            if output_dev.states['output_id'] != self.globals['roon']['outputs'][output_id]['output_id']:
                key_value_list.append({'key': 'output_id', 'value': self.globals['roon']['outputs'][output_id]['output_id']})
            if output_dev.states['display_name'] != self.globals['roon']['outputs'][output_id]['display_name']:
                if self.globals['roon']['outputs'][output_id]['display_name'] != '':  # < TEST LEAVING DISPLAY NAME UNALTERED
                    key_value_list.append({'key': 'display_name', 'value': self.globals['roon']['outputs'][output_id]['display_name']})


            if 'source_controls' in self.globals['roon']['outputs'][output_id] and self.globals['roon']['outputs'][output_id]['source_controls_count'] > 0:
                if output_dev.states['source_control_1_status'] != self.globals['roon']['outputs'][output_id]['source_controls'][1]['status']:
                    key_value_list.append({'key': 'source_control_1_status', 'value': self.globals['roon']['outputs'][output_id]['source_controls'][1]['status']})
                if output_dev.states['source_control_1_display_name'] != self.globals['roon']['outputs'][output_id]['source_controls'][1]['display_name']:
                    key_value_list.append({'key': 'source_control_1_display_name', 'value': self.globals['roon']['outputs'][output_id]['source_controls'][1]['display_name']})
                if output_dev.states['source_control_1_control_key'] != self.globals['roon']['outputs'][output_id]['source_controls'][1]['control_key']:
                    key_value_list.append({'key': 'source_control_1_control_key', 'value': self.globals['roon']['outputs'][output_id]['source_controls'][1]['control_key']})
                if output_dev.states['source_control_1_control_key'] != self.globals['roon']['outputs'][output_id]['source_controls'][1]['control_key']:
                    key_value_list.append({'key': 'source_control_1_control_key', 'value': self.globals['roon']['outputs'][output_id]['source_controls'][1]['control_key']})
                if output_dev.states['source_control_1_supports_standby'] != self.globals['roon']['outputs'][output_id]['source_controls'][1]['supports_standby']:
                    key_value_list.append({'key': 'source_control_1_supports_standby', 'value': self.globals['roon']['outputs'][output_id]['source_controls'][1]['supports_standby']})
            else:
                    key_value_list.append({'key': 'source_control_1_status', 'value': ''})
                    key_value_list.append({'key': 'source_control_1_display_name', 'value': ''})
                    key_value_list.append({'key': 'source_control_1_control_key', 'value': ''})
                    key_value_list.append({'key': 'source_control_1_control_key', 'value': ''})
                    key_value_list.append({'key': 'source_control_1_supports_standby', 'value': False})

            if 'volume' in self.globals['roon']['outputs'][output_id] and len(self.globals['roon']['outputs'][output_id]['volume']) > 0:
                if output_dev.states['volume_hard_limit_min'] != self.globals['roon']['outputs'][output_id]['volume']['hard_limit_min']:
                    key_value_list.append({'key': 'volume_hard_limit_min', 'value': self.globals['roon']['outputs'][output_id]['volume']['hard_limit_min']})
                if output_dev.states['volume_min'] != self.globals['roon']['outputs'][output_id]['volume']['min']:
                    key_value_list.append({'key': 'volume_min', 'value': self.globals['roon']['outputs'][output_id]['volume']['min']})
                if output_dev.states['volume_is_muted'] != self.globals['roon']['outputs'][output_id]['volume']['is_muted']:
                    key_value_list.append({'key': 'volume_is_muted', 'value': self.globals['roon']['outputs'][output_id]['volume']['is_muted']})
                if output_dev.states['volume_max'] != self.globals['roon']['outputs'][output_id]['volume']['max']:
                    key_value_list.append({'key': 'volume_max', 'value': self.globals['roon']['outputs'][output_id]['volume']['max']})
                if output_dev.states['volume_value'] != self.globals['roon']['outputs'][output_id]['volume']['value']:
                    key_value_list.append({'key': 'volume_value', 'value': self.globals['roon']['outputs'][output_id]['volume']['value']})
                if output_dev.states['volume_step'] != self.globals['roon']['outputs'][output_id]['volume']['step']:
                    key_value_list.append({'key': 'volume_step', 'value': self.globals['roon']['outputs'][output_id]['volume']['step']})
                if output_dev.states['volume_hard_limit_max'] != self.globals['roon']['outputs'][output_id]['volume']['hard_limit_max']:
                    key_value_list.append({'key': 'volume_hard_limit_max', 'value': self.globals['roon']['outputs'][output_id]['volume']['hard_limit_max']})
                if output_dev.states['volume_soft_limit'] != self.globals['roon']['outputs'][output_id]['volume']['soft_limit']:
                    key_value_list.append({'key': 'volume_soft_limit', 'value': self.globals['roon']['outputs'][output_id]['volume']['soft_limit']})
                if output_dev.states['volume_type'] != self.globals['roon']['outputs'][output_id]['volume']['type']:
                    key_value_list.append({'key': 'volume_type', 'value': self.globals['roon']['outputs'][output_id]['volume']['type']})
            else:
                key_value_list.append({'key': 'volume_hard_limit_min', 'value': 0})
                key_value_list.append({'key': 'volume_min', 'value': 0})
                key_value_list.append({'key': 'volume_is_muted', 'value': False})
                key_value_list.append({'key': 'volume_max', 'value': 0})
                key_value_list.append({'key': 'volume_value', 'value': 0})
                key_value_list.append({'key': 'volume_step', 'value': 0})
                key_value_list.append({'key': 'volume_hard_limit_max', 'value': 0})
                key_value_list.append({'key': 'volume_soft_limit', 'value': 0})
                key_value_list.append({'key': 'volume_type', 'value': 'number'})

            if output_dev.states['can_group_with_output_id_1'] != can_group_with_output_id_1:
                key_value_list.append({'key': 'can_group_with_output_id_1', 'value': can_group_with_output_id_1})
            if output_dev.states['can_group_with_output_id_2'] != can_group_with_output_id_2:
                key_value_list.append({'key': 'can_group_with_output_id_2', 'value': can_group_with_output_id_2})
            if output_dev.states['can_group_with_output_id_3'] != can_group_with_output_id_3:
                key_value_list.append({'key': 'can_group_with_output_id_3', 'value': can_group_with_output_id_3})
            if output_dev.states['can_group_with_output_id_4'] != can_group_with_output_id_4:
                key_value_list.append({'key': 'can_group_with_output_id_4', 'value': can_group_with_output_id_4})
            if output_dev.states['can_group_with_output_id_5'] != can_group_with_output_id_5:
                key_value_list.append({'key': 'can_group_with_output_id_5', 'value': can_group_with_output_id_5})

            if len(key_value_list) > 0:
                output_dev.updateStatesOnServer(key_value_list)
            output_dev.updateStateImageOnServer(indigo.kStateImageSel.PowerOn)

        except StandardError as err:
            self.general_logger.error(u'\'updateRoonOutputDevice\' error detected for device \'{}\'. Line \'{}\' has error=\'{}\''.format(output_dev.name, sys.exc_traceback.tb_lineno, err))   

        finally:
            if self.globals['debug']['methodTraceActive']: self.method_tracer.threaddebug(u'Method End: Line {}'.format(inspect.currentframe().f_lineno))

    def disconnectRoonOutputDevice(self, roonOutputDevId):
        if self.globals['debug']['methodTraceActive']: self.method_tracer.threaddebug(u'Method Start: Line {}'.format(inspect.currentframe().f_lineno))

        output_dev = indigo.devices[roonOutputDevId]

        try:
            key_value_list = [
                {'key': 'output_connected', 'value': False},
                {'key': 'output_status', 'value': 'disconnected'},
                {'key': 'output_id', 'value': ''},
                # {'key': 'display_name', 'value': ''},  # < TEST LEAVING DISPLAY NAME UNALTERED
                {'key': 'zone_id', 'value': ''},
                {'key': 'source_control_1_status', 'value': ''},
                {'key': 'source_control_1_display_name', 'value': ''},
                {'key': 'source_control_1_control_key', 'value': ''},
                {'key': 'source_control_1_supports_standby', 'value': ''},
                {'key': 'volume_hard_limit_min', 'value': 0},
                {'key': 'volume_min', 'value': 0},
                {'key': 'volume_is_muted', 'value': False},
                {'key': 'volume_max', 'value': 0},
                {'key': 'volume_value', 'value': 0},
                {'key': 'volume_step', 'value': 1},
                {'key': 'volume_hard_limit_max', 'value': 0},
                {'key': 'volume_soft_limit', 'value': 0},
                {'key': 'volume_type', 'value': 'number'},
                {'key': 'can_group_with_output_id_1', 'value': ''},
                {'key': 'can_group_with_output_id_2', 'value': ''},
                {'key': 'can_group_with_output_id_3', 'value': ''},
                {'key': 'can_group_with_output_id_4', 'value': ''},
                {'key': 'can_group_with_output_id_5', 'value': ''}]

            output_dev.updateStatesOnServer(key_value_list)
            output_dev.updateStateImageOnServer(indigo.kStateImageSel.PowerOff)

        except StandardError as err:
            self.general_logger.error(u'\'disconnectRoonOutputDevice\' error detected for device \'{}\'. Line \'{}\' has error=\'{}\''.format(output_dev.name, sys.exc_traceback.tb_lineno, err))   

        finally:
            if self.globals['debug']['methodTraceActive']: self.method_tracer.threaddebug(u'Method End: Line {}'.format(inspect.currentframe().f_lineno))

    # def deviceStopComm(self, dev, deviceBeingDeleted=False):
    def deviceStopComm(self, dev):
        if self.globals['debug']['methodTraceActive']: self.method_tracer.threaddebug(u'Method Start: Line {}'.format(inspect.currentframe().f_lineno))

        try:
            if dev.id in self.globals['roon']['indigoDeviceBeingDeleted']:
                deviceBeingDeletedAddress = self.globals['roon']['indigoDeviceBeingDeleted'][dev.id]
                deviceBeingDeleted = True
                del self.globals['roon']['indigoDeviceBeingDeleted'][dev.id]

                if dev.deviceTypeId == 'roonZone':
                    self.general_logger.debug(u'\'deviceStopComm\' Deleted Roon Zone device Address: {}'.format(deviceBeingDeletedAddress))
                    if deviceBeingDeletedAddress[0:5] == 'ZONE-':
                        zone_alpha = deviceBeingDeletedAddress.split('-')[1]  # deviceBeingDeletedAddress = e.g. 'ZONE-A-2' which gives 'A' or ZONE-BC-3 which gives 'BC'
                        if len(zone_alpha) == 1:
                            zone_alpha = ' {}'.format(zone_alpha)
                        self.globals['roon']['availableZoneAlphas'].append(zone_alpha)  # Make Alpha available again
                        self.globals['roon']['availableZoneAlphas'].sort()

                        self.general_logger.debug(u'Roon \'availableZoneAlphas\':\n{}\n'.format(self.globals['roon']['availableZoneAlphas']))

                elif dev.deviceTypeId == 'roonOutput':
                    self.general_logger.debug(u'\'deviceStopComm\' Deleted Roon Output device Address: {}'.format(deviceBeingDeletedAddress))
                    if deviceBeingDeletedAddress[0:7] == 'OUTPUT-':
                        output_number = deviceBeingDeletedAddress.split('-')[1]  # deviceBeingDeletedAddress = e.g. 'OUTPUT-2' which gives '2'
                        if len(output_number)  == 1:
                            output_number = ' {}'.format(output_number)
                        self.globals['roon']['availableOutputNumbers'].append(output_number)  # Make Number available again
                        self.globals['roon']['availableOutputNumbers'].sort()

                        self.general_logger.debug(u'Roon \'availableOutputNumbers\':\n{}\n'.format(self.globals['roon']['availableOutputNumbers']))

            else:
                deviceBeingDeleted = False

            if dev.deviceTypeId == 'roonZone':
                zone_dev = dev
                for zoneUniqueIdentityKey, devId in self.globals['roon']['zoneUniqueIdentityKeyToDevId'].items():
                    if devId == zone_dev.id:
                        del self.globals['roon']['zoneUniqueIdentityKeyToDevId'][zoneUniqueIdentityKey]
                if not deviceBeingDeleted:
                    self.disconnectRoonZoneDevice(zone_dev.id)

            elif dev.deviceTypeId == 'roonOutput':
                output_dev = dev
                for output_id, devId in self.globals['roon']['outputIdToDevId'].items():
                    if devId == output_dev.id:
                        del self.globals['roon']['outputIdToDevId'][output_id]
                if not deviceBeingDeleted:
                    self.disconnectRoonOutputDevice(output_dev.id)

        except StandardError as err:
            self.general_logger.error(u'\'deviceStopComm\' error detected for device \'{}\'. Line \'{}\' has error=\'{}\''.format(dev.name, sys.exc_traceback.tb_lineno, err))   

        finally:
            if self.globals['debug']['methodTraceActive']: self.method_tracer.threaddebug(u'Method End: Line {}'.format(inspect.currentframe().f_lineno))

    def deviceDeleted(self, dev):
        if self.globals['debug']['methodTraceActive']: self.method_tracer.threaddebug(u'Method Start: Line {}'.format(inspect.currentframe().f_lineno))

        try:
            self.globals['roon']['indigoDeviceBeingDeleted'][dev.id] = dev.address

        except StandardError as err:
            self.general_logger.error(u'\'deviceDeleted\' error detected for device \'{}\'. Line \'{}\' has error=\'{}\''.format(dev.name, sys.exc_traceback.tb_lineno, err))

        finally:
            if self.globals['debug']['methodTraceActive']: self.method_tracer.threaddebug(u'Method End: Line {}'.format(inspect.currentframe().f_lineno))

            super(Plugin, self).deviceDeleted(dev)  
