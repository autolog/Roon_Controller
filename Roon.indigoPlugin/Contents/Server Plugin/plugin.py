#! /usr/bin/env python
# -*- coding: utf-8 -*-
#
# Roon Controller © Autolog 2019-2020

# noinspection PyUnresolvedReferences
# ============================== Native Imports ===============================
import copy
import logging
import os
import platform
from PIL import Image
try:
    import requests
except ImportError:
    pass
from shutil import copyfile
import socket
import sys

# ============================== Custom Imports ===============================
try:
    import indigo
except ImportError:
    pass

# ============================== Plugin Imports ===============================
from constants import *
from roon import RoonApi


# noinspection PyUnresolvedReferences
class Plugin(indigo.PluginBase):

    # =============================================================================
    def __init__(self, plugin_id, plugin_display_name, plugin_version, plugin_prefs):

        indigo.PluginBase.__init__(self, plugin_id, plugin_display_name, plugin_version, plugin_prefs)

        # Initialise dictionary to store plugin Globals
        self.globals = dict()

        # Initialise Indigo plugin info
        self.globals[K_PLUGIN_INFO] = dict()
        self.globals[K_PLUGIN_INFO][K_PLUGIN_ID] = plugin_id
        self.globals[K_PLUGIN_INFO][K_PLUGIN_DISPLAY_NAME] = plugin_display_name
        self.globals[K_PLUGIN_INFO][K_PLUGIN_VERSION] = plugin_version
        self.globals[K_PLUGIN_INFO][K_PATH] = indigo.server.getInstallFolderPath()
        self.globals[K_PLUGIN_INFO][K_API_VERSION] = indigo.server.apiVersion
        self.globals[K_PLUGIN_INFO][K_INDIGO_SERVER_ADDRESS] = indigo.server.address

        # Initialise dictionary for debug log levels in plugin Globals
        self.globals[K_DEBUG] = dict()

        # Setup Logging - Logging info:
        #   self.indigo_log_handler - writes log messages to Indigo Event Log
        #   self.plugin_file_handler - writes log messages to the plugin log

        log_format = logging.Formatter("%(asctime)s.%(msecs)03d\t%(levelname)-12s\t%(name)s.%(funcName)-25s %(msg)s",
                                       datefmt="%Y-%m-%d %H:%M:%S")
        self.plugin_file_handler.setFormatter(log_format)
        self.plugin_file_handler.setLevel(K_LOG_LEVEL_INFO)  # Logging Level for plugin log file
        self.indigo_log_handler.setLevel(K_LOG_LEVEL_INFO)   # Logging level for Indigo Event Log

        self.logger = logging.getLogger("Plugin.ROON")

        # Now logging is set-up, output Initialising message

        startup_message_ui = "\n"  # Start with a line break
        startup_message_ui += u"{0:={1}130}\n".format(" Initialising Roon Controller Plugin ", "^")
        startup_message_ui += u"{0:<31} {1}\n".format("Plugin Name:",
                                                      self.globals[K_PLUGIN_INFO][K_PLUGIN_DISPLAY_NAME])
        startup_message_ui += u"{0:<31} {1}\n".format("Plugin Version:", self.globals[K_PLUGIN_INFO][K_PLUGIN_VERSION])
        startup_message_ui += u"{0:<31} {1}\n".format("Plugin ID:", self.globals[K_PLUGIN_INFO][K_PLUGIN_ID])
        startup_message_ui += u"{0:<31} {1}\n".format("Indigo Version:", indigo.server.version)
        startup_message_ui += u"{0:<31} {1}\n".format("Indigo API Version:", indigo.server.apiVersion)
        startup_message_ui += u"{0:<31} {1}\n".format("Python Version:", sys.version.replace("\n", ""))
        startup_message_ui += u"{0:<31} {1}\n".format("Mac OS Version:", platform.mac_ver()[0])
        startup_message_ui += u"{0:={1}130}\n".format("", "^")
        self.logger.info(startup_message_ui)

        # Initialise dictionary to store configuration info
        self.globals[K_CONFIG] = dict()
        self.globals[K_CONFIG][K_PRINT_OUTPUTS_SUMMARY] = True  
        self.globals[K_CONFIG][K_PRINT_OUTPUT] = True
        self.globals[K_CONFIG][K_PRINT_ZONES_SUMMARY] = True  
        self.globals[K_CONFIG][K_PRINT_ZONE] = True
        self.globals[K_CONFIG][K_ROON_DEVICE_FOLDER_NAME] = ""
        self.globals[K_CONFIG][K_ROON_DEVICE_FOLDER_ID] = 0 
        self.globals[K_CONFIG][K_ROON_CORE_IP_ADDRESS] = ""
               
        # Initialise dictionary to store internal details about Roon
        self.globals[K_ROON] = dict()
        self.globals[K_ROON][K_INDIGO_DEVICE_BEING_DELETED] = dict()
        self.globals[K_ROON][K_ZONES] = dict()
        self.globals[K_ROON][K_OUTPUTS] = dict()

        self.globals[K_ROON][K_MAP_ZONE] = dict()  
        self.globals[K_ROON][K_MAP_OUTPUT] = dict()  # TODO: Not sure this is being used in a meaningful way?
        self.globals[K_ROON][K_ZONE_UNIQUE_IDENTITY_KEY_TO_ZONE_ID] = dict()
        self.globals[K_ROON][K_ZONE_UNIQUE_IDENTITY_KEY_TO_DEV_ID] = dict()
        self.globals[K_ROON][K_OUTPUT_ID_TO_DEV_ID] = dict()

        self.globals[K_ROON][K_PLUGIN_PREFS_FOLDER] = "{0}/Preferences/Plugins/com.autologplugin.indigoplugin.rooncontroller".format(self.globals[K_PLUGIN_INFO][K_PATH])
        if not os.path.exists(self.globals[K_ROON][K_PLUGIN_PREFS_FOLDER]):
            self.mkdir_with_mode(self.globals[K_ROON][K_PLUGIN_PREFS_FOLDER])

        self.globals[K_ROON][K_AVAILABLE_OUTPUT_NUMBERS] = OUTPUT_MAP_NUMBERS
        self.globals[K_ROON][K_AVAILABLE_ZONE_ALPHAS] = ZONE_MAP_ALPHAS

        # Initialise info to register with the Roon API
        self.globals[K_ROON][K_EXTENSION_INFO] = dict()
        self.globals[K_ROON][K_EXTENSION_INFO]['extension_id'] = "indigo_plugin_roon"
        self.globals[K_ROON][K_EXTENSION_INFO]['display_name'] = "Indigo Plugin for Roon"
        self.globals[K_ROON][K_EXTENSION_INFO]['display_version'] = "1.0.0"
        self.globals[K_ROON][K_EXTENSION_INFO]['publisher'] = "autolog"
        self.globals[K_ROON][K_EXTENSION_INFO]['email'] = "my@email.com"

        # Set Plugin Config Values
        self.getPrefsConfigUiValues()
        self.closedPrefsConfigUi(plugin_prefs, False)

        self.globals[K_DEVICES_TO_ROON_CONTROLLER_TABLE] = dict()  # TODO: Is this used?

        for dev in indigo.devices.iter("self"):
            if dev.deviceTypeId == 'roonOutput':
                output_number = dev.address.split('-')[1]  # dev.address = e.g. 'OUTPUT-6' which gives '6'
                if len(output_number) == 1:
                    output_number = " {0}".format(output_number)
                output_id = dev.pluginProps.get('roonOutputId', '')
                if output_id != '':
                    self.globals[K_ROON][K_OUTPUT_ID_TO_DEV_ID][output_id] = dev.id
                try:
                    self.globals[K_ROON][K_AVAILABLE_OUTPUT_NUMBERS].remove(output_number)
                except ValueError:
                    self.logger.error(u"Roon Output '{0}' device with address '{1}' invalid:"
                                      u"  Address number '{2}' already allocated!:\n{3}\n"
                                      .format(dev.name, dev.address, output_number,
                                              self.globals[K_ROON][K_AVAILABLE_OUTPUT_NUMBERS]))

                self.disconnect_roon_output_device(dev.id)

            elif dev.deviceTypeId == 'roonZone':
                zone_alpha = dev.address.split('-')[1]  # dev.address = e.g. 'ZONE-A-2' which gives 'A'
                if len(zone_alpha) == 1:
                    zone_alpha = " {0}".format(zone_alpha)
                zone_unique_identity_key = dev.pluginProps.get('roonZoneUniqueIdentityKey', '')
                if zone_unique_identity_key != '':
                    self.globals[K_ROON][K_ZONE_UNIQUE_IDENTITY_KEY_TO_DEV_ID][zone_unique_identity_key] = dev.id
                try:
                    self.globals[K_ROON][K_AVAILABLE_ZONE_ALPHAS].remove(zone_alpha)
                except ValueError:
                    self.logger.error(u"Roon Zone '{0}' device with address '{1}' invalid:"
                                      u"  Address letter '{2}' already allocated!:\n{3}\n"
                                      .format(dev.name, dev.address, zone_alpha,
                                              self.globals[K_ROON][K_AVAILABLE_ZONE_ALPHAS]))

                self.disconnect_roon_zone_device(dev.id)

        # Remove image  files for deleted or renamed Indigo Roon Zone devices
        dir_list = [d for d in os.listdir(self.globals[K_ROON][K_PLUGIN_PREFS_FOLDER]) if os.path.isdir(
            os.path.join(self.globals[K_ROON][K_PLUGIN_PREFS_FOLDER], d))]
        for dir_name in dir_list:
            dir_alpha = dir_name.split('-')[1]  # dev.address = e.g. 'ZONE-A-2' which gives 'A' or 'ZONE-CD-1' which gives 'CD'
            if len(dir_alpha) == 1:
                dir_alpha = " {0}".format(dir_alpha)
            if dir_alpha in self.globals[K_ROON][K_AVAILABLE_ZONE_ALPHAS]:
                dir_path_and_name = os.path.join(self.globals[K_ROON][K_PLUGIN_PREFS_FOLDER], dir_name)
                file_list = os.listdir(dir_path_and_name)
                for fileName in file_list:
                    os.remove(os.path.join(dir_path_and_name, fileName))
                os.rmdir(dir_path_and_name)    

    def __del__(self):

        indigo.PluginBase.__del__(self)

    def closedDeviceConfigUi(self, values_dict, userCancelled, type_id, dev_id):
        try:
            self.logger.debug(u"'closedDeviceConfigUi' called with userCancelled = {0}".format(str(userCancelled)))

            if userCancelled:
                return

        except StandardError as e:
            self.logger.error(u"'closedDeviceConfigUi' error detected. Line '{0}' has error='{1}'"
                              .format(sys.exc_traceback.tb_lineno, e))

    # def createOutputDevice(self, zone_id):
    #     pass

    # def createZoneDevice(self, zone_id):
    #     pass

    def closedPrefsConfigUi(self, values_dict, userCancelled):
        try:
            self.logger.debug(
                u"'closePrefsConfigUi' called with userCancelled = {0}".format(str(userCancelled)))

            if userCancelled:
                return

            # Get required Event Log and Plugin Log logging levels
            plugin_log_level = int(values_dict.get("pluginLogLevel", K_LOG_LEVEL_INFO))
            event_log_level = int(values_dict.get("eventLogLevel", K_LOG_LEVEL_INFO))

            # Ensure following logging level messages are output
            self.indigo_log_handler.setLevel(K_LOG_LEVEL_INFO)
            self.plugin_file_handler.setLevel(K_LOG_LEVEL_INFO)

            # Output required logging levels and TP Message Monitoring requirement to logs
            self.logger.info(u"Logging to Indigo Event Log at the '{0}' level"
                             .format(K_LOG_LEVEL_TRANSLATION[event_log_level]))
            self.logger.info(u"Logging to Plugin Event Log at the '{0}' level"
                             .format(K_LOG_LEVEL_TRANSLATION[plugin_log_level]))

            # Now set required logging levels
            self.indigo_log_handler.setLevel(event_log_level)
            self.plugin_file_handler.setLevel(plugin_log_level)

            # ### IP Address ###

            self.globals[K_CONFIG][K_ROON_CORE_IP_ADDRESS] = values_dict.get('roonCoreIpAddress', '')

            # ### AUTO-CREATE DEVICES + DEVICE FOLDER ###
            self.globals[K_CONFIG][K_AUTO_CREATE_DEVICES] = values_dict.get("autoCreateDevices", False)
            self.globals[K_CONFIG][K_ROON_DEVICE_FOLDER_NAME] = values_dict.get("roonDeviceFolderName", 'Roon')
            self.globals[K_CONFIG][K_DYNAMIC_GROUPED_ZONES_RENAME] = values_dict.get("dynamicGroupedZonesRename", True)

            # Create Roon Device folder name (if specific device folder required)
            if self.globals[K_CONFIG][K_ROON_DEVICE_FOLDER_NAME] == '':
                self.globals[K_CONFIG][K_ROON_DEVICE_FOLDER_ID] = 0  # No specific device folder required
            else:
                if self.globals[K_CONFIG][K_ROON_DEVICE_FOLDER_NAME] not in indigo.devices.folders:
                    indigo.devices.folder.create(self.globals[K_CONFIG][K_ROON_DEVICE_FOLDER_NAME])
                self.globals[K_CONFIG][K_ROON_DEVICE_FOLDER_ID] = indigo.devices.folders.getId(
                    self.globals[K_CONFIG][K_ROON_DEVICE_FOLDER_NAME])

            # Create Roon Variable folder name (if required)
            self.globals[K_CONFIG][K_ROON_VARIABLE_FOLDER_NAME] = values_dict.get("roonVariableFolderName", '')

            self.globals[K_CONFIG][K_ROON_VARIABLE_FOLDER_ID] = 0  # Not required

            if self.globals[K_CONFIG][K_ROON_VARIABLE_FOLDER_NAME] != '':

                if self.globals[K_CONFIG][K_ROON_VARIABLE_FOLDER_NAME] not in indigo.variables.folders:
                    indigo.variables.folder.create(self.globals[K_CONFIG][K_ROON_VARIABLE_FOLDER_NAME])

                self.globals[K_CONFIG][K_ROON_VARIABLE_FOLDER_ID] = indigo.variables.folders[
                    self.globals[K_CONFIG][K_ROON_VARIABLE_FOLDER_NAME]].id

            self.logger.debug(u"Roon Variable Folder Id: {0}, Roon Variable Folder Name: {1}"
                              .format(self.globals[K_CONFIG][K_ROON_VARIABLE_FOLDER_ID],
                                      self.globals[K_CONFIG][K_ROON_VARIABLE_FOLDER_NAME]))

        except StandardError as e:
            self.logger.error(u"'closedPrefsConfigUi' error detected. Line '{0}' has error='{1}'"
                              .format(sys.exc_traceback.tb_lineno, e))

    def deviceDeleted(self, dev):
        try:
            self.globals[K_ROON][K_INDIGO_DEVICE_BEING_DELETED][dev.id] = dev.address

        except StandardError as err:
            self.logger.error(u"'deviceDeleted' error detected for device '{0}'. Line '{1}' has error='{2}'"
                              .format(dev.name, sys.exc_traceback.tb_lineno, err))

        finally:
            super(Plugin, self).deviceDeleted(dev)

    def deviceStartComm(self, dev):
        try:
            dev.stateListOrDisplayStateIdChanged()  # Ensure latest devices.xml is being used

            if dev.deviceTypeId == 'roonZone':
                zone_dev = dev
                zone_dev_plugin_props = zone_dev.pluginProps
                zone_unique_identity_key = zone_dev_plugin_props.get('roonZoneUniqueIdentityKey', '')
                if zone_unique_identity_key != '':
                    self.globals[K_ROON][K_ZONE_UNIQUE_IDENTITY_KEY_TO_DEV_ID][zone_unique_identity_key] = zone_dev.id

                zone_id = ""
                for found_zone_id in self.globals[K_ROON][K_ZONES]:
                    if K_ZONE_UNIQUE_IDENTITY_KEY in self.globals[K_ROON][K_ZONES][found_zone_id]:
                        if zone_unique_identity_key == self.globals[K_ROON][K_ZONES][found_zone_id][K_ZONE_UNIQUE_IDENTITY_KEY]:
                            zone_id = found_zone_id

                            # LOGIC TO HANDLE PLUGIN PROPS 'roonZoneId' ?????
                            dev_plugin_props = dev.pluginProps
                            dev_plugin_props['roonZoneId'] = zone_id
                            dev.replacePluginPropsOnServer(dev_plugin_props)

                            break

                try:
                    shared_props = dev.sharedProps
                    shared_props["sqlLoggerIgnoreStates"] = "queue_time_remaining, remaining, seek_position, ui_queue_time_remaining, ui_remaining, ui_seek_position"
                    dev.replaceSharedPropsOnServer(shared_props)
                except:
                    pass

                if zone_dev.address[0:5] != 'ZONE-':
                    # At this point it is a brand new Roon Zone device as address not setup

                    if zone_id != '':
                        output_count = self.globals[K_ROON][K_ZONES][zone_id][K_OUTPUTS_COUNT]
                    else:
                        output_count = 0
                    address_alpha = self.globals[K_ROON][K_AVAILABLE_ZONE_ALPHAS].pop(0)
                    if address_alpha[0:1] == '_':
                        address_alpha = address_alpha[1:2]
                    if output_count > 0:
                        address = "ZONE-{0}-{1}".format(address_alpha, output_count)
                    else:
                        address = "ZONE-{0}".format(address_alpha)
                    zone_dev_plugin_props["address"] = address
                    zone_dev.replacePluginPropsOnServer(zone_dev_plugin_props)

                # At this point it is an existing Roon Zone device as address already setup

                if zone_id == '':
                    # Flag as disconnected as Zone doesn't exist
                    self.disconnect_roon_zone_device(zone_dev.id)
                    return

                # Next section of logic just creates a Zone  image folder
                # with a dummy text file with the display name of the Zone to aid in viewing the image folder structure
                zone_image_folder = "{0}/{1}".format(self.globals[K_ROON][K_PLUGIN_PREFS_FOLDER], zone_dev.address)
                if not os.path.exists(zone_image_folder):
                    try:
                        self.mkdir_with_mode(zone_image_folder)
                    except FileExistsError:  # Handles the situation where the folder gets created by image processing in between the check and mkdir statements!
                        pass
                else:
                    file_list = os.listdir(zone_image_folder)
                    for file_name in file_list:
                        if file_name.endswith(".txt"):
                            os.remove(os.path.join(zone_image_folder, file_name))

                zone_id_file_name = u"{0}/_{1}.txt".format(zone_image_folder, zone_dev.name.upper())
                zone_id_file = open(zone_id_file_name, 'w')
                zone_id_file.write("{0}".format(zone_dev.name))
                zone_id_file.close()

                self.update_roon_zone_device(zone_dev.id, zone_id)

            elif dev.deviceTypeId == 'roonOutput':
                output_dev = dev
                output_id = output_dev.pluginProps.get('roonOutputId', '')

                if output_dev.address[0:4] != 'OUT-':
                    address_number = self.globals[K_ROON][K_AVAILABLE_OUTPUT_NUMBERS].pop(0)
                    if address_number[0:1] == '_':
                        address_number = address_number[1:2]
                    address = "OUT-{0}".format(address_number)
                    output_dev_plugin_props = output_dev.pluginProps
                    output_dev_plugin_props["address"] = address

                    self.globals[K_ROON][K_MAP_OUTPUT][address_number] = dict()
                    self.globals[K_ROON][K_MAP_OUTPUT][address_number][K_INDIGO_DEV_ID] = output_dev.id
                    self.globals[K_ROON][K_MAP_OUTPUT][address_number][K_ROON_OUTPUT_ID] = output_id
                    output_dev.replacePluginPropsOnServer(output_dev_plugin_props)
                    return

                if output_id not in self.globals[K_ROON][K_OUTPUTS]:
                    key_value_list = [
                        {'key': 'output_connected', 'value': False},
                        {'key': 'output_status', 'value': 'disconnected'},
                    ]
                    output_dev.updateStatesOnServer(key_value_list)
                    output_dev.updateStateImageOnServer(indigo.kStateImageSel.PowerOff)
                    return

                self.update_roon_output_device(output_dev.id, output_id)

        except StandardError as err:
            self.logger.error(u"'deviceStartComm' error detected for device '{0}'. Line '{1}' has error='{2}'"
                              .format(dev.name, sys.exc_traceback.tb_lineno, err))

    # def deviceStopComm(self, dev, deviceBeingDeleted=False):  TODO: What is this?
    def deviceStopComm(self, dev):
        try:
            if dev.id in self.globals[K_ROON][K_INDIGO_DEVICE_BEING_DELETED]:
                device_being_deleted_address = self.globals[K_ROON][K_INDIGO_DEVICE_BEING_DELETED][dev.id]
                device_being_deleted = True
                del self.globals[K_ROON][K_INDIGO_DEVICE_BEING_DELETED][dev.id]

                if dev.deviceTypeId == 'roonZone':
                    self.logger.debug(u"'deviceStopComm' Deleted Roon Zone device Address: {0}"
                                      .format(device_being_deleted_address))
                    if device_being_deleted_address[0:5] == 'ZONE-':
                        # device_being_deleted_address = e.g. 'ZONE-A-2' which gives 'A' or ZONE-BC-3 which gives 'BC'
                        zone_alpha = device_being_deleted_address.split('-')[1]
                        if len(zone_alpha) == 1:
                            zone_alpha = " {0}".format(zone_alpha)
                        self.globals[K_ROON][K_AVAILABLE_ZONE_ALPHAS].append(zone_alpha)  # Make Alpha available again
                        self.globals[K_ROON][K_AVAILABLE_ZONE_ALPHAS].sort()

                        self.logger.debug(u"Roon 'availableZoneAlphas':\n{0}\n"
                                          .format(self.globals[K_ROON][K_AVAILABLE_ZONE_ALPHAS]))

                elif dev.deviceTypeId == 'roonOutput':
                    self.logger.debug(u"'deviceStopComm' Deleted Roon Output device Address: {0}"
                                      .format(device_being_deleted_address))
                    if device_being_deleted_address[0:7] == 'OUTPUT-':
                        # device_being_deleted_address = e.g. 'OUTPUT-2' which gives '2'
                        output_number = device_being_deleted_address.split('-')[1]
                        if len(output_number)  == 1:
                            output_number = " {0}".format(output_number)
                        # Make Number available again
                        self.globals[K_ROON][K_AVAILABLE_OUTPUT_NUMBERS].append(output_number)
                        self.globals[K_ROON][K_AVAILABLE_OUTPUT_NUMBERS].sort()

                        self.logger.debug(u"Roon 'availableOutputNumbers':\n{0}\n"
                                          .format(self.globals[K_ROON][K_AVAILABLE_OUTPUT_NUMBERS]))

            else:
                device_being_deleted = False

            if dev.deviceTypeId == 'roonZone':
                zone_dev = dev
                for zoneUniqueIdentityKey, devId in self.globals[K_ROON][K_ZONE_UNIQUE_IDENTITY_KEY_TO_DEV_ID].items():
                    if devId == zone_dev.id:
                        del self.globals[K_ROON][K_ZONE_UNIQUE_IDENTITY_KEY_TO_DEV_ID][zoneUniqueIdentityKey]
                if not device_being_deleted:
                    self.disconnect_roon_zone_device(zone_dev.id)

            elif dev.deviceTypeId == 'roonOutput':
                output_dev = dev
                for output_id, devId in self.globals[K_ROON][K_OUTPUT_ID_TO_DEV_ID].items():
                    if devId == output_dev.id:
                        del self.globals[K_ROON][K_OUTPUT_ID_TO_DEV_ID][output_id]
                if not device_being_deleted:
                    self.disconnect_roon_output_device(output_dev.id)

        except StandardError as err:
            self.logger.error(u"'deviceStopComm' error detected for device '{0}'. Line '{1}' has error='{2}'"
                              .format(dev.name, sys.exc_traceback.tb_lineno, err))

    def deviceUpdated(self, origDev, newDev):
        # TODO: IS THIS METHOD NEEDED?
        try:
            if (newDev.deviceTypeId == 'roonController' and
                    newDev.configured and
                    newDev.id in self.globals[K_ROON] and
                    self.globals[K_ROON][newDev.id][K_DEVICE_STARTED]):  # IGNORE THESE UPDATES TO AVOID LOOP!!!
                pass

        except StandardError as err:
            self.logger.error(u"'deviceUpdated' error detected for device '{0}']. Line '{1}' has error='{2}'"
                              .format(newDev.name, sys.exc_traceback.tb_lineno, err))

        finally:
            indigo.PluginBase.deviceUpdated(self, origDev, newDev)

    def didDeviceCommPropertyChange(self, orig_dev, new_dev):
        if orig_dev.deviceTypeId == 'roonZone':
            if 'dynamicGroupedZoneRename' in orig_dev.pluginProps:
                if orig_dev.pluginProps['dynamicGroupedZoneRename'] != new_dev.pluginProps['dynamicGroupedZoneRename']:
                    return True
        return False

    def getActionConfigUiValues(self, plugin_props, type_id, action_id):
        try:
            error_dict = indigo.Dict()
            values_dict = plugin_props

            if type_id == "groupOutputs":  # <Action id="groupOutputs" deviceFilter="self.roonOutput" uiPath="DeviceActions" alwaysUseInDialogHeightCalc="true">

                roon_output_to_group_to_name = indigo.devices[action_id].name
                values_dict["roonOutputToGroupTo"] = roon_output_to_group_to_name

            return values_dict, error_dict

        except StandardError as err:
            self.logger.error(u"'getActionConfigUiValues' error detected. Line '{0}' has error='{1}'"
                              .format(sys.exc_traceback.tb_lineno, err))

    def getDeviceConfigUiValues(self, plugin_props, type_id, dev_id):
        try:
            if type_id == 'roonZone':
                if 'roonZoneUniqueIdentityKey' not in plugin_props:
                    plugin_props['roonZoneUniqueIdentityKey'] = "-"
                if 'autoNameNewRoonZone' not in plugin_props:
                    plugin_props['autoNameNewRoonZone'] = True
                if 'dynamicGroupedZoneRename' not in plugin_props:
                    plugin_props['dynamicGroupedZoneRename'] = self.globals[K_CONFIG][K_DYNAMIC_GROUPED_ZONES_RENAME]
            elif type_id == 'roonOutput':
                if 'roonOutputId' not in plugin_props:
                    plugin_props['roonOutputId'] = "-"

        except StandardError as err:
            self.logger.error(u"'getDeviceConfigUiValues' error detected for device '{0}'. Line '{1}' has error='{2}'"
                              .format(indigo.devices[dev_id].name, sys.exc_traceback.tb_lineno, err))

        finally:
            return super(Plugin, self).getDeviceConfigUiValues(plugin_props, type_id, dev_id)

    def getPrefsConfigUiValues(self):
        prefs_config_ui_values = self.pluginPrefs

        if "roonVariableFolderName" not in prefs_config_ui_values:
            prefs_config_ui_values["roonVariableFolderName"] = ""

        self.logger.debug(u"ROONVARIABLEFOLDERNAME = {0}".format(prefs_config_ui_values["roonVariableFolderName"]))

        if "roonCoreIpAddress" not in prefs_config_ui_values:
            prefs_config_ui_values["roonCoreIpAddress"] = ""
        if "autoCreateDevices" not in prefs_config_ui_values:
            prefs_config_ui_values["autoCreateDevices"] = False
        if "roonDeviceFolderName" not in prefs_config_ui_values:
            prefs_config_ui_values["roonDeviceFolderName"] = "Roon"
        if "dynamicGroupedZonesRename" not in prefs_config_ui_values:
            prefs_config_ui_values["dynamicGroupedZonesRename"] = True

        return prefs_config_ui_values

    def shutdown(self):
        self.logger.debug(u"Shutdown called")

        self.logger.info(u"'Roon Controller' Plugin shutdown complete")

    def startup(self):
        try:
            # indigo.devices.subscribeToChanges()  # TODO: Don't think this is needed!

            self.logger.threaddebug(u"Roon 'availableOutputNumbers':\n{0}\n"
                                    .format(self.globals[K_ROON][K_AVAILABLE_OUTPUT_NUMBERS]))

            self.logger.threaddebug(u"Roon 'availableZoneAlphas':\n{0}\n"
                                    .format(self.globals[K_ROON][K_AVAILABLE_ZONE_ALPHAS]))

            self.globals[K_ROON][K_TOKEN] = None

            self.globals[K_ROON][K_TOKEN_FILE] = "{0}/roon_token.txt".format(self.globals[K_ROON][K_PLUGIN_PREFS_FOLDER])

            if os.path.isfile(self.globals[K_ROON][K_TOKEN_FILE]):
                with open(self.globals[K_ROON][K_TOKEN_FILE]) as f:
                    self.globals[K_ROON][K_TOKEN] = f.read()

            self.logger.debug(u"'Roon Controller' token [0]: {0}".format(self.globals[K_ROON][K_TOKEN]))

            if self.globals[K_CONFIG][K_ROON_CORE_IP_ADDRESS] == '':
                self.logger.error(u"'Roon Controller' has no Roon Core IP Address specified in Plugin configuration"
                                  u" - correct and then restart plugin.")
                return False

            self.globals[K_ROON][K_API] = RoonApi(self.globals[K_ROON][K_EXTENSION_INFO], self.globals[K_ROON][K_TOKEN],
                                                  self.globals[K_CONFIG][K_ROON_CORE_IP_ADDRESS])
            self.globals[K_ROON][K_API].register_state_callback(self.process_roon_callback_state)
            # self.globals[K_ROON][K_API].register_queue_callback(self.process_roon_callback_queue)

            # self.globals[K_ROON][K_API].register_volume_control('Indigo', 'Indigo', self.process_roon_volume_control)

            self.logger.debug(u"'Roon Controller' token [1]: {0}".format(self.globals[K_ROON][K_TOKEN]))

            self.globals[K_ROON][K_TOKEN] = self.globals[K_ROON][K_API].token
            self.logger.debug(u"'Roon Controller' token [2]: {0}".format(self.globals[K_ROON][K_TOKEN]))

            if self.globals[K_ROON][K_TOKEN]:
                with open(self.globals[K_ROON][K_TOKEN_FILE], "w") as f:
                    f.write(self.globals[K_ROON][K_TOKEN])

            self.globals[K_ROON][K_ZONES] = copy.deepcopy(self.globals[K_ROON][K_API].zones)
            self.globals[K_ROON][K_OUTPUTS] = copy.deepcopy(self.globals[K_ROON][K_API].outputs)

            self.process_outputs(self.globals[K_ROON][K_OUTPUTS])
            self.process_zones(self.globals[K_ROON][K_ZONES])

            # self.print_known_zones_summary('INITIALISATION')

            self.logger.info(u"'Roon Controller' initialization complete.")

        except StandardError as e:
            self.logger.error(u"'startup' error detected. Line '{0}' has error='{1}'"
                              .format(sys.exc_traceback.tb_lineno, e))   

    def stopConcurrentThread(self):
        self.logger.debug(u"Thread shutdown called")

        self.stopThread = True

    def validateActionConfigUi(self, values_dict, type_id, actionId):
        try:
            self.logger.debug(u"Validate Action Config UI: type_id = '{0}', actionId = '{1}', values_dict =\n{2}\n"
                              .format(type_id, actionId, values_dict))

            if type_id == "qwerty":
                pass
            return True, values_dict

        except StandardError as err:
            self.logger.error(u"'validateActionConfigUi' error detected for Action '{0}'. Line '{1} has error='{2}'"
                              .format(indigo.devices[actionId].name, sys.exc_traceback.tb_lineno, err))

    def validateDeviceConfigUi(self, values_dict, type_id, dev_id):  # Validate Roon device
        try:
            if type_id == 'roonZone':
                valid = False
                if 'roonZoneUniqueIdentityKey' in values_dict and len(values_dict['roonZoneUniqueIdentityKey']) > 5:
                    valid = True
                if not valid:
                    error_dict = indigo.Dict()
                    error_dict["roonZoneUniqueIdentityKey"] = "No Roon Zone selected or available"
                    error_dict["showAlertText"] = "You must select an available Roon Zone to be able to create the Roon Zone device."
                    return False, values_dict, error_dict

            elif type_id == 'roonOutput':
                valid = False
                if 'roonOutputId' in values_dict and len(values_dict['roonOutputId']) > 5:
                    valid = True
                if not valid:
                    error_dict = indigo.Dict()
                    error_dict["roonOutputId"] = "No Roon Output selected or available"
                    error_dict["showAlertText"] = "You must select an available Roon Output to be able to create the Roon Output device."
                    return False, values_dict, error_dict

            return True, values_dict

        except StandardError as err:
            self.logger.error(u"'validateDeviceConfigUi' error detected for device '{0}'. Line '{1}' has error='{2}'"
                              .format(indigo.devices[dev_id].name, sys.exc_traceback.tb_lineno, err))

    def validatePrefsConfigUi(self, values_dict):
        try:
            ip_address = values_dict.get('roonCoreIpAddress', '')

            try:
                socket.inet_aton(ip_address)
            except:
                error_dict = indigo.Dict()
                error_dict["roonCoreIpAddress"] = "Roon Core IP Address is invalid"
                error_dict["showAlertText"] = ("You must enter a valid Roon Core IP Address"
                                               " to be able to connect to the Roon Core.")
                return False, values_dict, error_dict

        except StandardError as e:
            self.logger.error(u"'validatePrefsConfigUi' error detected. Line '{0}' has error='{1}'"
                              .format(sys.exc_traceback.tb_lineno, e))

        finally:
            return True, values_dict

    def auto_create_output_device(self, output_id):
        try:
            self.logger.debug(u"Roon 'availableOutputNumbers':\n{0}\n"
                              .format(self.globals[K_ROON][K_AVAILABLE_OUTPUT_NUMBERS]))

            address_number = self.globals[K_ROON][K_AVAILABLE_OUTPUT_NUMBERS].pop(0)
            if address_number[0:1] == ' ':
                address_number = address_number[1:2]
            address = "OUT-{0}".format(address_number)

            output_name = u"Roon Output - {0}".format(self.globals[K_ROON][K_OUTPUTS][output_id][K_DISPLAY_NAME])

            output_dev = (indigo.device.create(protocol=indigo.kProtocol.Plugin,
                          address=address,
                          name=output_name,
                          description='Roon Output',
                          pluginId="com.autologplugin.indigoplugin.rooncontroller",
                          deviceTypeId="roonOutput",
                          props={"roonOutputId": output_id,
                                 "roonOutputIdUi": output_id,
                                 "autoNameNewRoonOutput": True},
                          folder=self.globals[K_CONFIG][K_ROON_DEVICE_FOLDER_ID]))

            self.globals[K_ROON][K_OUTPUT_ID_TO_DEV_ID][output_id] = output_dev.id

        except StandardError as e:
            self.logger.error(u"'auto_create_output_device' error detected. Line '{0}' has error='{1}'"
                              .format(sys.exc_traceback.tb_lineno, e))

    def auto_create_zone_device(self, zone_id, zoneUniqueIdentityKey):
        try:
            self.logger.debug(u"Roon 'availableZoneAlphas':\n{0}\n".format(self.globals[K_ROON][K_AVAILABLE_ZONE_ALPHAS]))

            outputCount = self.globals[K_ROON][K_ZONES][zone_id][K_OUTPUTS_COUNT]
            addressAlpha = self.globals[K_ROON][K_AVAILABLE_ZONE_ALPHAS].pop(0)
            if addressAlpha[0:1] == ' ':
                addressAlpha = addressAlpha[1:2]
            if outputCount > 0:
                address = "ZONE-{0}-{1}".format(addressAlpha, outputCount)
            else:
                address = "ZONE-{0}".format(addressAlpha)

            zone_name = u"{0}".format(self.globals[K_ROON][K_ZONES][zone_id][K_DISPLAY_NAME])

            if outputCount == 0:
                device_name = u"Roon Zone - {0}".format(zone_name)
            else:
                temp_zone_name = self.globals[K_ROON][K_ZONES][zone_id][K_OUTPUTS][1][K_DISPLAY_NAME]
                for i in range(2, outputCount + 1):
                    temp_zone_name = "{0} + {1}".format(temp_zone_name, self.globals[K_ROON][K_ZONES][zone_id][K_OUTPUTS][i][K_DISPLAY_NAME])
                device_name = u"Roon Zone - {0}".format(temp_zone_name)

            self.logger.debug(u"'auto_create_zone_device' - Creating Indigo Zone Device with Name: '{0}', Zone Name: '{1}',\nZone Unique Identity Key: '{2}'".format(device_name, zone_name, zoneUniqueIdentityKey))

            defaultdynamicGroupedZonesRename = self.globals[K_CONFIG][K_DYNAMIC_GROUPED_ZONES_RENAME]

            zone_dev = (indigo.device.create(
                        protocol=indigo.kProtocol.Plugin,
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
                        folder=self.globals[K_CONFIG][K_ROON_DEVICE_FOLDER_ID]))

            self.globals[K_ROON][K_ZONE_UNIQUE_IDENTITY_KEY_TO_DEV_ID][zoneUniqueIdentityKey] = zone_dev.id

        except StandardError as e:
            self.logger.error(u"'auto_create_zone_device' error detected. Line '{0}' has error='{1}'"
                              .format(sys.exc_traceback.tb_lineno, e))

    def convert_output_id_list_to_string(self, roonZoneOutputsList):
        try:
            outputs_list_string = ""

            if type(roonZoneOutputsList) is list:
                for outputId in roonZoneOutputsList:
                    if outputs_list_string == '':
                        outputs_list_string = u"{0}".format(outputId)
                    else:
                        outputs_list_string = u"{0}#{1}".format(outputs_list_string, outputId)

                return outputs_list_string
            else:
                return roonZoneOutputsList

        except StandardError as err:
            self.logger.error(u"'convert_output_id_list_to_string' error detected. Line '{0}' has error='{1}'"
                              .format(sys.exc_traceback.tb_lineno, err))

    def disconnect_roon_output_device(self, roonOutputDevId):
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
            self.logger.error(u"'disconnect_roon_output_device' error detected for device '{0}'."
                              u" Line '{1}' has error='{2}'"
                              .format(output_dev.name, sys.exc_traceback.tb_lineno, err))

    def disconnect_roon_zone_device(self, roonZoneDevId):
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
            self.logger.error(u"'update_roon_zone_device' error detected for device '{0}'. Line '{1}' has error='{2}'"
                              .format(zone_dev.name, sys.exc_traceback.tb_lineno, err))

    def list_roon_output_ids(self, filter="", values_dict=None, type_id="", targetId=0):
        self.logger.debug(u"type_id = {0}, targetId = {1}".format(type_id, targetId))

        try:
            outputs_list = list()

            allocated_output_ids = []
            for dev in indigo.devices.iter("self"):
                if dev.deviceTypeId == 'roonOutput':
                    roonOutputId = dev.pluginProps.get('roonOutputId', '')
                    allocated_output_ids.append(roonOutputId)
                    if dev.id == targetId and roonOutputId != '':
                        if dev.states['output_status'] == 'connected':
                            # Append self
                            outputs_list.append((roonOutputId,
                                                 self.globals[K_ROON][K_OUTPUTS][roonOutputId][K_DISPLAY_NAME]))
                        else:
                            display_name = dev.states['display_name']
                            if display_name != '':
                                display_name = display_name + ' '
                            # Append self
                            outputs_list.append((roonOutputId, "{0}[Output disconnected]".format(display_name)))

            for output_id in self.globals[K_ROON][K_OUTPUTS]:
                if output_id not in allocated_output_ids:
                    outputs_list.append((self.globals[K_ROON][K_OUTPUTS][output_id][K_OUTPUT_ID],
                                         self.globals[K_ROON][K_OUTPUTS][output_id][K_DISPLAY_NAME]))

            if len(outputs_list) == 0:
                outputs_list.append(('-', '-- No Available Outputs --'))
                return outputs_list
            else:
                outputs_list.append(('-', '-- Select Output --'))

            return sorted(outputs_list, key=lambda output_name: output_name[1].lower())   # sort by Output name

        except StandardError as err:
            self.logger.error(u"'list_roon_output_ids' error detected. Line '{0}' has error='{1}'"
                              .format(indigo.devices[targetId].name, sys.exc_traceback.tb_lineno, err))

    def list_roon_zone_unique_identity_keys(self, filter="", values_dict=None, type_id="", targetId=0):
        try:
            self.logger.debug(u"TYPE_ID = {0}, TARGET_ID = {1}".format(type_id, targetId))

            allocatedRoonZoneUniqueIdentityKeys = []
            for dev in indigo.devices.iter("self"):
                if dev.deviceTypeId == 'roonZone' and targetId != dev.id:
                    zone_unique_identity_key = dev.pluginProps.get('roonZoneUniqueIdentityKey', '')
                    if zone_unique_identity_key != '':
                        allocatedRoonZoneUniqueIdentityKeys.append(zone_unique_identity_key)

            zone_unique_identity_keys_list = list()

            for zone_id in self.globals[K_ROON][K_ZONES]:
                if self.globals[K_ROON][K_ZONES][zone_id][K_ZONE_UNIQUE_IDENTITY_KEY] not in allocatedRoonZoneUniqueIdentityKeys:
                    zone_unique_identity_keys_list.append((self.globals[K_ROON][K_ZONES][zone_id][K_ZONE_UNIQUE_IDENTITY_KEY], self.globals[K_ROON][K_ZONES][zone_id][K_DISPLAY_NAME]))

            if len(zone_unique_identity_keys_list) == 0:
                zone_unique_identity_keys_list.append(('-', '-- No Available Zones --'))
                return zone_unique_identity_keys_list
            else:
                zone_unique_identity_keys_list.append(('-', '-- Select Zone --'))

            return sorted(zone_unique_identity_keys_list, key=lambda zone_name: zone_name[1].lower())   # sort by Zone name

        except StandardError as err:
            self.logger.error(u"'list_roon_zone_unique_identity_keys' error detected. Line '{0}' has error='{1}'".format(indigo.devices[devId].name, sys.exc_traceback.tb_lineno, err))

    def mkdir_with_mode(self, directory):
        try:
            # Forces Read | Write on creation so that the plugin can delete the folder id required
            if not os.path.isdir(directory):
                oldmask = os.umask(000)
                os.makedirs(directory, 0o777)
                os.umask(oldmask)
        except StandardError as err:
            self.logger.error(u"'mkdir_with_mode' error detected. Line '{0}' has error='{1}'".format(indigo.devices[devId].name, sys.exc_traceback.tb_lineno, err))

    def now_playing_variables(self, filter="", values_dict=None, type_id="", targetId=0):
        try:
            myArray = []
            for var in indigo.variables:
                if self.globals[K_CONFIG][K_ROON_VARIABLE_FOLDER_ID] == 0:
                    myArray.append((var.id, var.name))
                else:
                    if var.folderId == self.globals[K_CONFIG][K_ROON_VARIABLE_FOLDER_ID]:
                        myArray.append((var.id, var.name))

            myArraySorted = sorted(myArray, key=lambda varname: varname[1].lower())   # sort by variable name
            myArraySorted.insert(0, (0, 'NO NOW PLAYING VARIABLE'))
            myArraySorted.insert(0, (-1, '-- Select Now Playing Variable --'))

            return myArraySorted

        except StandardError as e:
            self.logger.error(u"'now_playing_variables' error detected. Line '{0}' has error='{1}'".format(sys.exc_traceback.tb_lineno, e))

    def print_known_outputs_summary(self, title):
        try:
            if self.globals[K_CONFIG][K_PRINT_OUTPUTS_SUMMARY]:
                logout = "\n#################### {0} ####################\n".format(title)
                for output_id in self.globals[K_ROON][K_OUTPUTS]:
                    if 'display_name' in self.globals[K_ROON][K_OUTPUTS][output_id]:
                        outputdisplay_name = self.globals[K_ROON][K_OUTPUTS][output_id][K_DISPLAY_NAME]
                    else:
                        outputdisplay_name = "NONE"
                    logout = logout + "Output '{0}' - Output ID = '{1}'".format(outputdisplay_name, output_id)
                logout = logout + '####################\n'
                self.logger.debug(logout)

        except StandardError as e:
            self.logger.error(u"'print_known_outputs_summary' error detected. Line '{0}' has error='{1}'".format(sys.exc_traceback.tb_lineno, e))

    def print_known_zones_summary(self, title):
        try:
            if self.globals[K_CONFIG][K_PRINT_ZONES_SUMMARY]:
                logout = u"\n#################### {0} ####################".format(title)
                logout = logout + u"\nInternal Zone table\n"
                for zone_id in self.globals[K_ROON][K_ZONES]:
                    if 'display_name' in self.globals[K_ROON][K_ZONES][zone_id]:
                        zone_display_name = self.globals[K_ROON][K_ZONES][zone_id][K_DISPLAY_NAME]
                    else:
                        zone_display_name = "NONE"
                    logout = logout + u"\nZone '{0}' - Zone ID = '{1}'".format(zone_display_name, zone_id)
                logout = logout + u"\nIndigo Zone Devices\n"
                for dev in indigo.devices.iter("self"):
                    if dev.deviceTypeId == 'roonZone':
                        zone_id = dev.pluginProps.get('roonZoneId', '-- Zone ID not set!')
                        logout = logout + u"\nIndigo Device '{0}' - Zone ID = '{1}', Status =  '{2}'".format(dev.name, zone_id, dev.states['zone_status'])
                logout = logout + u"\n####################\n"
                self.logger.info(logout)

        except StandardError as e:
            self.logger.error(u"'print_known_zones_summary' error detected. Line '{0}' has error='{1}'".format(sys.exc_traceback.tb_lineno, e))

    def print_output(self, output_id):
        try:
            outputPrint = u"\n\nROON OUTPUT PRINT\n"
            outputPrint = outputPrint + u"\nOutput: {0}".format(self.globals[K_ROON][K_OUTPUTS][output_id][K_OUTPUT_ID])
            outputPrint = outputPrint + u"\n    Display Name: {0}".format(
                self.globals[K_ROON][K_OUTPUTS][output_id][K_DISPLAY_NAME])
            outputPrint = outputPrint + u"\n    Zone Id: {0}".format(
                self.globals[K_ROON][K_OUTPUTS][output_id][K_ZONE_ID])

            if 'source_controls' in self.globals[K_ROON][K_OUTPUTS][output_id]:

                outputPrint = outputPrint + u"\n    Source Controls: Count = {0}".format(
                    self.globals[K_ROON][K_OUTPUTS][output_id][K_SOURCE_CONTROLS_COUNT])
                for key2, value2 in self.globals[K_ROON][K_OUTPUTS][output_id][K_SOURCE_CONTROLS].iteritems():
                    key2Int = int(key2)
                    outputPrint = outputPrint + u"\n        Source Controls '{0}'".format(key2)
                    outputPrint = outputPrint + u"\n            Status: {0}".format(
                        self.globals[K_ROON][K_OUTPUTS][output_id][K_SOURCE_CONTROLS][key2Int][K_STATUS])
                    outputPrint = outputPrint + u"\n            Display Name: {0}".format(
                        self.globals[K_ROON][K_OUTPUTS][output_id][K_SOURCE_CONTROLS][key2Int][K_DISPLAY_NAME])
                    outputPrint = outputPrint + u"\n            Control Key: {0}".format(
                        self.globals[K_ROON][K_OUTPUTS][output_id][K_SOURCE_CONTROLS][key2Int][K_CONTROL_KEY])
                    outputPrint = outputPrint + u"\n            Supports Standby: {0}".format(
                        self.globals[K_ROON][K_OUTPUTS][output_id][K_SOURCE_CONTROLS][key2Int][K_SUPPORTS_STANDBY])

            if 'volume' in self.globals[K_ROON][K_OUTPUTS][output_id] and len(
                    self.globals[K_ROON][K_OUTPUTS][output_id][K_VOLUME]) > 0:
                outputPrint = outputPrint + u"\n    Volume:"
                outputPrint = outputPrint + u"\n        Hard Limit Min: {0}".format(
                    self.globals[K_ROON][K_OUTPUTS][output_id][K_VOLUME][K_VOLUME_HARD_LIMIT_MIN])
                outputPrint = outputPrint + u"\n        Min: {0}".format(
                    self.globals[K_ROON][K_OUTPUTS][output_id][K_VOLUME][K_VOLUME_MIN])
                outputPrint = outputPrint + u"\n        Is Muted: {0}".format(
                    self.globals[K_ROON][K_OUTPUTS][output_id][K_VOLUME][K_VOLUME_IS_MUTED])
                outputPrint = outputPrint + u"\n        Max: {0}".format(
                    self.globals[K_ROON][K_OUTPUTS][output_id][K_VOLUME][K_VOLUME_MAX])
                outputPrint = outputPrint + u"\n        Value: {0}".format(
                    self.globals[K_ROON][K_OUTPUTS][output_id][K_VOLUME][K_VOLUME_VALUE])
                outputPrint = outputPrint + u"\n        Step: {0}".format(
                    self.globals[K_ROON][K_OUTPUTS][output_id][K_VOLUME][K_VOLUME_STEP])
                outputPrint = outputPrint + u"\n        Hard Limit Max: {0}".format(
                    self.globals[K_ROON][K_OUTPUTS][output_id][K_VOLUME][K_VOLUME_HARD_LIMIT_MAX])
                outputPrint = outputPrint + u"\n        Soft Limit: {0}".format(
                    self.globals[K_ROON][K_OUTPUTS][output_id][K_VOLUME][K_VOLUME_SOFT_LIMIT])
                outputPrint = outputPrint + u"\n        Type: {0}".format(
                    self.globals[K_ROON][K_OUTPUTS][output_id][K_VOLUME][K_VOLUME_TYPE])

            outputPrint = outputPrint + u"\n    Can Group With Output Ids: Count = {0}".format(
                self.globals[K_ROON][K_OUTPUTS][output_id][K_CAN_GROUP_WITH_OUTPUT_IDS_COUNT])
            for key2, value2 in self.globals[K_ROON][K_OUTPUTS][output_id][K_CAN_GROUP_WITH_OUTPUT_IDS].iteritems():
                key2Int = int(key2)
                outputPrint = outputPrint + u"\n        Output Id [{0}]: {1}".format(key2,
                                                                                     self.globals[K_ROON][K_OUTPUTS][
                                                                                       output_id][
                                                                                       K_CAN_GROUP_WITH_OUTPUT_IDS][
                                                                                       key2Int])

            self.logger.debug(outputPrint)

        except StandardError as err:
            self.logger.error(u"'print_output' error detected. Line '{0}' has error='{1}'"
                              .format(sys.exc_traceback.tb_lineno, err))

    def print_zone(self, zone_id):
        try:
            zone_print = u"\n\nROON ZONE PRINT: '{0}'\n".format(self.globals[K_ROON][K_ZONES][zone_id][K_DISPLAY_NAME])
            zone_print = zone_print         + u"\nZone: {0}".format(self.globals[K_ROON][K_ZONES][zone_id][K_ZONE_ID])
            zone_print = zone_print         + u"\n    Queue Items Remaining: {0}".format(self.globals[K_ROON][K_ZONES][zone_id][K_QUEUE_ITEMS_REMAINING])
            zone_print = zone_print         + u"\n    Queue Time Remaining: {0}".format(self.globals[K_ROON][K_ZONES][zone_id][K_QUEUE_TIME_REMAINING])
            zone_print = zone_print         + u"\n    Display Name: {0}".format(self.globals[K_ROON][K_ZONES][zone_id][K_DISPLAY_NAME])
            zone_print = zone_print         + u"\n    Settings:"
            zone_print = zone_print         + u"\n        Auto Radio: {0}".format(self.globals[K_ROON][K_ZONES][zone_id][K_SETTINGS][K_AUTO_RADIO])
            zone_print = zone_print         + u"\n        Shuffle: {0}".format(self.globals[K_ROON][K_ZONES][zone_id][K_SETTINGS][K_SHUFFLE])
            zone_print = zone_print         + u"\n        Loop: {0}".format(self.globals[K_ROON][K_ZONES][zone_id][K_SETTINGS][K_LOOP])
            zone_print = zone_print         + u"\n    zone_id Unique Identity Key: {0}".format(self.globals[K_ROON][K_ZONES][zone_id][K_ZONE_UNIQUE_IDENTITY_KEY])
            zone_print = zone_print         + u"\n    Outputs: Count = {0}".format(self.globals[K_ROON][K_ZONES][zone_id][K_OUTPUTS_COUNT])

            for key, value in self.globals[K_ROON][K_ZONES][zone_id][K_OUTPUTS].iteritems():
                keyInt = int(key)
                zone_print = zone_print     + u"\n        Output '{0}'".format(key)
                zone_print = zone_print     + u"\n            Output Id: {0}".format(self.globals[K_ROON][K_ZONES][zone_id][K_OUTPUTS][keyInt][K_OUTPUT_ID])
                zone_print = zone_print     + u"\n            Display Name: {0}".format(self.globals[K_ROON][K_ZONES][zone_id][K_OUTPUTS][keyInt][K_DISPLAY_NAME])
                zone_print = zone_print     + u"\n            Zone Id: {0}".format(self.globals[K_ROON][K_ZONES][zone_id][K_OUTPUTS][keyInt][K_ZONE_ID])

                zone_print = zone_print     + u"\n            Source Controls: Count = {0}".format(self.globals[K_ROON][K_ZONES][zone_id][K_OUTPUTS][keyInt][K_SOURCE_CONTROLS_COUNT])
                for key2, value2 in self.globals[K_ROON][K_ZONES][zone_id][K_OUTPUTS][keyInt][K_SOURCE_CONTROLS].iteritems():
                    key2Int = int(key2)
                    zone_print = zone_print + u"\n                Source Controls '{0}'".format(key2)
                    zone_print = zone_print + u"\n                    Status: {0}".format(self.globals[K_ROON][K_ZONES][zone_id][K_OUTPUTS][keyInt][K_SOURCE_CONTROLS][key2Int][K_STATUS])
                    zone_print = zone_print + u"\n                    Display Name: {0}".format(self.globals[K_ROON][K_ZONES][zone_id][K_OUTPUTS][keyInt][K_SOURCE_CONTROLS][key2Int][K_DISPLAY_NAME])
                    zone_print = zone_print + u"\n                    Control Key: {0}".format(self.globals[K_ROON][K_ZONES][zone_id][K_OUTPUTS][keyInt][K_SOURCE_CONTROLS][key2Int][K_CONTROL_KEY])
                    zone_print = zone_print + u"\n                    Supports Standby: {0}".format(self.globals[K_ROON][K_ZONES][zone_id][K_OUTPUTS][keyInt][K_SOURCE_CONTROLS][key2Int][K_SUPPORTS_STANDBY])
                zone_print = zone_print     + u"\n            Volume:"
                zone_print = zone_print     + u"\n                Hard Limit Min: {0}".format(self.globals[K_ROON][K_ZONES][zone_id][K_OUTPUTS][keyInt][K_VOLUME][K_VOLUME_HARD_LIMIT_MIN])
                zone_print = zone_print     + u"\n                Min: {0}".format(self.globals[K_ROON][K_ZONES][zone_id][K_OUTPUTS][keyInt][K_VOLUME][K_VOLUME_MIN])
                zone_print = zone_print     + u"\n                Is Muted: {0}".format(self.globals[K_ROON][K_ZONES][zone_id][K_OUTPUTS][keyInt][K_VOLUME][K_VOLUME_IS_MUTED])
                zone_print = zone_print     + u"\n                Max: {0}".format(self.globals[K_ROON][K_ZONES][zone_id][K_OUTPUTS][keyInt][K_VOLUME][K_VOLUME_MAX])
                zone_print = zone_print     + u"\n                Value: {0}".format(self.globals[K_ROON][K_ZONES][zone_id][K_OUTPUTS][keyInt][K_VOLUME][K_VOLUME_VALUE])
                zone_print = zone_print     + u"\n                Step: {0}".format(self.globals[K_ROON][K_ZONES][zone_id][K_OUTPUTS][keyInt][K_VOLUME][K_VOLUME_STEP])
                zone_print = zone_print     + u"\n                Hard Limit Max: {0}".format(self.globals[K_ROON][K_ZONES][zone_id][K_OUTPUTS][keyInt][K_VOLUME][K_VOLUME_HARD_LIMIT_MAX])
                zone_print = zone_print     + u"\n                Soft Limit: {0}".format(self.globals[K_ROON][K_ZONES][zone_id][K_OUTPUTS][keyInt][K_VOLUME][K_VOLUME_SOFT_LIMIT])
                zone_print = zone_print     + u"\n                Type: {0}".format(self.globals[K_ROON][K_ZONES][zone_id][K_OUTPUTS][keyInt][K_VOLUME][K_VOLUME_TYPE])

                zone_print = zone_print     + u"\n            Can Group With Output Ids: Count = {0}".format(self.globals[K_ROON][K_ZONES][zone_id][K_OUTPUTS][keyInt][K_CAN_GROUP_WITH_OUTPUT_IDS_COUNT])
                for key2, value2 in self.globals[K_ROON][K_ZONES][zone_id][K_OUTPUTS][keyInt][K_CAN_GROUP_WITH_OUTPUT_IDS].iteritems():
                    key2Int = int(key2)
                    zone_print = zone_print + u"\n                Output Id [{0}]: {1}".format(key2, self.globals[K_ROON][K_ZONES][zone_id][K_OUTPUTS][keyInt][K_CAN_GROUP_WITH_OUTPUT_IDS][key2Int])

            zone_print = zone_print         + u"\n    Now Playing:"
            if 'artist_image_keys' in self.globals[K_ROON][K_ZONES][zone_id][K_NOW_PLAYING]:
                zone_print = zone_print     + u"\n        Artist Image Keys: Count = {0}".format(self.globals[K_ROON][K_ZONES][zone_id][K_NOW_PLAYING][K_ARTIST_IMAGE_KEYS_COUNT])
                for key, value in self.globals[K_ROON][K_ZONES][zone_id][K_NOW_PLAYING][K_ARTIST_IMAGE_KEYS].iteritems():
                    keyInt = int(key)
                    zone_print = zone_print + u"\n            Artist Image Key: {0}".format(self.globals[K_ROON][K_ZONES][zone_id][K_NOW_PLAYING][K_ARTIST_IMAGE_KEYS][keyInt])

            if 'image_key' in self.globals[K_ROON][K_ZONES][zone_id][K_NOW_PLAYING]:
                zone_print = zone_print     + u"\n        Image Key: {0}".format(self.globals[K_ROON][K_ZONES][zone_id][K_NOW_PLAYING][K_IMAGE_KEY])
            if 'length' in self.globals[K_ROON][K_ZONES][zone_id][K_NOW_PLAYING]:
                zone_print = zone_print     + u"\n        Length: {0}".format(self.globals[K_ROON][K_ZONES][zone_id][K_NOW_PLAYING][K_LENGTH])
            zone_print = zone_print         + u"\n        Seek Position: {0}".format(self.globals[K_ROON][K_ZONES][zone_id][K_NOW_PLAYING][K_SEEK_POSITION])
            zone_print = zone_print         + u"\n        One Line:"
            zone_print = zone_print         + u"\n            Line 1: {0}".format(self.globals[K_ROON][K_ZONES][zone_id][K_NOW_PLAYING][K_ONE_LINE][K_LINE_1])
            zone_print = zone_print         + u"\n        Two Line:"
            zone_print = zone_print         + u"\n            Line 1: {0}".format(self.globals[K_ROON][K_ZONES][zone_id][K_NOW_PLAYING][K_TWO_LINE][K_LINE_1])
            zone_print = zone_print         + u"\n            Line 2: {0}".format(self.globals[K_ROON][K_ZONES][zone_id][K_NOW_PLAYING][K_TWO_LINE][K_LINE_2])
            zone_print = zone_print         + u"\n        Three Line:"
            zone_print = zone_print         + u"\n            Line 1: {0}".format(self.globals[K_ROON][K_ZONES][zone_id][K_NOW_PLAYING][K_THREE_LINE][K_LINE_1])
            zone_print = zone_print         + u"\n            Line 2: {0}".format(self.globals[K_ROON][K_ZONES][zone_id][K_NOW_PLAYING][K_THREE_LINE][K_LINE_2])
            zone_print = zone_print         + u"\n            Line 3: {0}".format(self.globals[K_ROON][K_ZONES][zone_id][K_NOW_PLAYING][K_THREE_LINE][K_LINE_3])

            zone_print = zone_print         + u"\n    Is Previous Allowed: {0}".format(self.globals[K_ROON][K_ZONES][zone_id][K_IS_PREVIOUS_ALLOWED])
            zone_print = zone_print         + u"\n    Is Pause Allowed: {0}".format(self.globals[K_ROON][K_ZONES][zone_id][K_IS_PAUSE_ALLOWED])
            zone_print = zone_print         + u"\n    Is Seek Allowed: {0}".format(self.globals[K_ROON][K_ZONES][zone_id][K_IS_SEEK_ALLOWED])
            zone_print = zone_print         + u"\n    State: {0}".format(self.globals[K_ROON][K_ZONES][zone_id][K_STATE])
            zone_print = zone_print         + u"\n    Is Play Allowed: {0}".format(self.globals[K_ROON][K_ZONES][zone_id][K_IS_PLAY_ALLOWED])
            zone_print = zone_print         + u"\n    Is Next Allowed: {0}".format(self.globals[K_ROON][K_ZONES][zone_id][K_IS_NEXT_ALLOWED])

            self.logger.debug(zone_print)

        except StandardError as e:
            self.logger.error(u"'print_zone' error detected. Line '{0}' has error='{1}'".format(sys.exc_traceback.tb_lineno, e))

    def print_zone_summary(self, pluginAction):
        try:
            self.print_known_zones_summary('PROCESS PRINT ZONE SUMMARY ACTION')

        except StandardError as err:
            self.logger.error(
                u"'print_zone_summary' error detected. Line '{0}' has error='{1}'".format(
                    sys.exc_traceback.tb_lineno, err))

    def process_group_outputs(self, plugin_action, output_dev):
        try:
            if output_dev is None:
                self.logger.error(u"'process_group_outputs' Roon Controller Action '{0}' ignored as no Output device specified in Action.".format(plugin_action.pluginTypeId))
                return

            if not output_dev.states['output_connected']:
                self.logger.error(u"'process_group_outputs' Roon Controller Action '{0}' ignored as Output '{1}' is disconnected.".format(plugin_action.pluginTypeId, output_dev.name))
                return

            output_id = output_dev.states['output_id']
            if output_id == '':
                self.logger.error(u"'process_group_outputs' Roon Controller Action '{0}' ignored as Output '{1}' is not connected to the Roon Core.".format(plugin_action.pluginTypeId, output_dev.name))
                return

            forceGroupAction = bool(plugin_action.props.get('forceGroupAction', True))

            output_dev_plugin_props = output_dev.pluginProps
            output_id = output_dev_plugin_props.get('roonOutputId', '')

            outputs_to_group_list = [output_id]

            output_ids = plugin_action.props['roonOutputsList']

            for output_id in output_ids:
                outputs_to_group_list.append(output_id.strip())

            for output_id_to_group in outputs_to_group_list:
                output_dev_to_group = indigo.devices[self.globals[K_ROON][K_OUTPUT_ID_TO_DEV_ID][output_id_to_group]]

                if not output_dev_to_group.states['output_connected']:
                    self.logger.error(u"'process_group_outputs' Roon Controller Action '{0}' ignored as Output to group '{1}' is disconnected.".format(plugin_action.pluginTypeId, output_dev_to_group.name))
                    return

                output_id = output_dev.states['output_id']
                if output_id == '':
                    self.logger.debug(u"'process_group_outputs' Roon Controller Action '{0}' ignored as Output '{1}' is not connected to the Roon Core.".format(plugin_action.pluginTypeId, output_dev_to_group.name))
                    return

            if len(outputs_to_group_list) > 0:
                self.globals[K_ROON][K_API].group_outputs(outputs_to_group_list)

        except StandardError as err:
            output_dev_name = "Unknown Device"
            if output_dev is not None:
                output_dev_name = output_dev.name
            self.logger.error(u"'process_group_outputs' error detected for device '{0}'. Line '{1}' has error='{2}'".format(output_dev_name, sys.exc_traceback.tb_lineno, err))

    def process_image(self, image_type, image_suffix, zone_dev, image_key):
        try:
            # Next section of logic just creates a Zone  image folder with a dummy text file with the display name of the Zone to aid in viewing the image folder structure
            zone_image_folder = "{0}/{1}".format(self.globals[K_ROON][K_PLUGIN_PREFS_FOLDER], zone_dev.address)
            if not os.path.exists(zone_image_folder):
                try:
                    self.mkdir_with_mode(zone_image_folder)
                except FileExistsError:  # Handles the situation where the folder gets created by device start processing in between the check and mkdifr statements!
                    pass

            image_name = ['Artist_Image', 'Album_Image'][image_type]
            if image_suffix != '':
                image_name = "{0}_{1}".format(image_name, image_suffix)
            set_default_image = True
            if image_key != '':
                image_url = self.globals[K_ROON][K_API].get_image(image_key, scale = "fill")
                work_file = "{0}/{1}/temp.jpg".format(self.globals[K_ROON][K_PLUGIN_PREFS_FOLDER], zone_dev.address)
                image_request = requests.get(image_url)
                if image_request.status_code == 200:
                    try:
                        with open(work_file, 'wb') as f:
                            f.write(image_request.content)
                        image_to_process = Image.open(work_file)
                        output_image_file = "{0}/{1}/{2}.png".format(self.globals[K_ROON][K_PLUGIN_PREFS_FOLDER], zone_dev.address, image_name)
                        image_to_process.save(output_image_file)
                        try:
                            os.remove(work_file)
                        except:  # Not sure why this doesn't always work!
                            pass
                        set_default_image = False
                    except StandardError as err:
                        # leave as default image if any problem reported but only output debug message
                        self.logger.debug(u"'process_image' [DEBUG ONLY] error detected. Line '{0}' has error: '{1}'".format(sys.exc_traceback.tb_lineno, err))
            if set_default_image:
                default_image_path = "{0}/Plugins/Roon.indigoPlugin/Contents/Resources/".format(self.globals[K_PLUGIN_INFO][K_PATH])
                if image_type == ARTIST:
                    default_image_file = "{0}Artist_Image.png".format(default_image_path)
                elif image_type == ALBUM:
                    default_image_file = "{0}Album_Image.png".format(default_image_path)
                else:
                    default_image_file = "{0}Unknown_Image.png".format(default_image_path)
                output_image_file = "{0}/{1}/{2}.png".format(self.globals[K_ROON][K_PLUGIN_PREFS_FOLDER], zone_dev.address, image_name)
                copyfile(default_image_file, output_image_file)

        except StandardError as err:
            self.logger.error(u"'process_image' error detected. Line '{0}' has error: '{1}'".format(sys.exc_traceback.tb_lineno, err))

    def process_output(self, output_id, outputData):
        process_output_return_state = False

        try:
            self.globals[K_ROON][K_OUTPUTS][output_id] = dict()
            self.globals[K_ROON][K_OUTPUTS][output_id][K_SOURCE_CONTROLS] = dict()
            self.globals[K_ROON][K_OUTPUTS][output_id][K_SOURCE_CONTROLS_COUNT] = 0
            self.globals[K_ROON][K_OUTPUTS][output_id][K_VOLUME] = dict()
            self.globals[K_ROON][K_OUTPUTS][output_id][K_CAN_GROUP_WITH_OUTPUT_IDS] = dict()

            for outputKey, outputValue in outputData.iteritems():
                if outputKey == 'output_id':
                    self.globals[K_ROON][K_OUTPUTS][output_id][K_OUTPUT_ID] = outputValue
                elif outputKey == 'display_name':
                    self.globals[K_ROON][K_OUTPUTS][output_id][K_DISPLAY_NAME] = outputValue
                elif outputKey == 'zone_id':
                    self.globals[K_ROON][K_OUTPUTS][output_id][K_ZONE_ID] = outputValue
                elif outputKey == 'source_controls':
                    sourceControlsCount = 0
                    for sourceControls in outputValue:
                        sourceControlsCount += 1
                        self.globals[K_ROON][K_OUTPUTS][output_id][K_SOURCE_CONTROLS][sourceControlsCount] = dict()
                        for sourceControlKey, sourceControlData in sourceControls.iteritems():
                            if sourceControlKey == 'status':
                                self.globals[K_ROON][K_OUTPUTS][output_id][K_SOURCE_CONTROLS][sourceControlsCount][K_STATUS] = sourceControlData
                            elif sourceControlKey == 'display_name':
                                self.globals[K_ROON][K_OUTPUTS][output_id][K_SOURCE_CONTROLS][sourceControlsCount][K_DISPLAY_NAME] = sourceControlData
                            elif sourceControlKey == 'control_key':
                                self.globals[K_ROON][K_OUTPUTS][output_id][K_SOURCE_CONTROLS][sourceControlsCount][K_CONTROL_KEY] = sourceControlData
                            elif sourceControlKey == 'supports_standby':
                                self.globals[K_ROON][K_OUTPUTS][output_id][K_SOURCE_CONTROLS][sourceControlsCount][K_SUPPORTS_STANDBY] = bool(sourceControlData)
                    self.globals[K_ROON][K_OUTPUTS][output_id][K_SOURCE_CONTROLS_COUNT] = sourceControlsCount

                elif outputKey == 'volume':
                    for volumeKey, volumeData in outputValue.iteritems():
                        if volumeKey == 'hard_limit_min':
                            self.globals[K_ROON][K_OUTPUTS][output_id][K_VOLUME][K_VOLUME_HARD_LIMIT_MIN] = volumeData
                        elif volumeKey == 'min':
                            self.globals[K_ROON][K_OUTPUTS][output_id][K_VOLUME][K_VOLUME_MIN] = volumeData
                        elif volumeKey == 'is_muted':
                            self.globals[K_ROON][K_OUTPUTS][output_id][K_VOLUME][K_VOLUME_IS_MUTED] = volumeData
                        elif volumeKey == 'max':
                            self.globals[K_ROON][K_OUTPUTS][output_id][K_VOLUME][K_VOLUME_MAX] = volumeData
                        elif volumeKey == 'value':
                            self.globals[K_ROON][K_OUTPUTS][output_id][K_VOLUME][K_VOLUME_VALUE] = volumeData
                        elif volumeKey == 'step':
                            self.globals[K_ROON][K_OUTPUTS][output_id][K_VOLUME][K_VOLUME_STEP] = volumeData
                        elif volumeKey == 'hard_limit_max':
                            self.globals[K_ROON][K_OUTPUTS][output_id][K_VOLUME][K_VOLUME_HARD_LIMIT_MAX] = volumeData
                        elif volumeKey == 'soft_limit':
                            self.globals[K_ROON][K_OUTPUTS][output_id][K_VOLUME][K_VOLUME_SOFT_LIMIT] = volumeData
                        elif volumeKey == 'type':
                            self.globals[K_ROON][K_OUTPUTS][output_id][K_VOLUME][K_VOLUME_TYPE] = volumeData

                elif outputKey == 'can_group_with_output_ids':
                    canGroupCount = 0
                    for can_group_with_output_id in outputValue:
                        canGroupCount += 1
                        self.globals[K_ROON][K_OUTPUTS][output_id][K_CAN_GROUP_WITH_OUTPUT_IDS][canGroupCount] = can_group_with_output_id
                    self.globals[K_ROON][K_OUTPUTS][output_id][K_CAN_GROUP_WITH_OUTPUT_IDS_COUNT] = canGroupCount

            if output_id not in self.globals[K_ROON][K_OUTPUT_ID_TO_DEV_ID]:
                if self.globals[K_CONFIG][K_AUTO_CREATE_DEVICES]:
                    self.auto_create_output_device(output_id)

            if len(self.globals[K_ROON][K_OUTPUTS][output_id][K_SOURCE_CONTROLS]) > 0:
                process_output_return_state = True
            else:
                self.globals[K_ROON][K_OUTPUTS][output_id] = dict()
                self.globals[K_ROON][K_OUTPUTS][output_id][K_SOURCE_CONTROLS] = dict()
                self.globals[K_ROON][K_OUTPUTS][output_id][K_SOURCE_CONTROLS_COUNT] = 0
                self.globals[K_ROON][K_OUTPUTS][output_id][K_VOLUME] = dict()
                self.globals[K_ROON][K_OUTPUTS][output_id][K_CAN_GROUP_WITH_OUTPUT_IDS] = dict()
                if output_id in self.globals[K_ROON][K_OUTPUT_ID_TO_DEV_ID]:
                    self.disconnect_roon_output_device(self.globals[K_ROON][K_OUTPUT_ID_TO_DEV_ID][output_id])
                process_output_return_state = False

        except StandardError as e:
            self.logger.error(u"'process_output' error detected. Line '{0}' has error='{1}'".format(sys.exc_traceback.tb_lineno, e))

        finally:
            return process_output_return_state

    def process_outputs(self, outputs):
        try:
            for output_id, output_data in outputs.iteritems():
                self.process_output(output_id, output_data)
                if self.globals[K_CONFIG][K_PRINT_OUTPUT]:
                    self.print_output(output_id)

        except StandardError as e:
            self.logger.error(u"'process_outputs' error detected. Line {0} has error='{1}'".format(sys.exc_traceback.tb_lineno, e))

    def process_outputs_added(self, event, changed_items):
        try:
            for output_id in changed_items:
                if output_id == '1701b9ea8b0814189098501722daf1427ea9':
                    tempOutputs = self.globals[K_ROON][K_API].outputs
                    self.logger.debug(
                        u"'process_outputs_changed' - ALL OUTPUTS = \n\n{0}\n\n.".format(tempOutputs))

                output_data = copy.deepcopy(self.globals[K_ROON][K_API].output_by_output_id(output_id))
                processOutput_successful = self.process_output(output_id, output_data)
                self.logger.debug(u"'process_outputs_added' - Output '{0}'. Output ID = '{1}'\n{2}"
                                  .format('TEMPORARY DEBUG NAME', output_id, output_data))

                if processOutput_successful:
                    if output_id in self.globals[K_ROON][K_OUTPUT_ID_TO_DEV_ID]:
                        roonOutputDevId = self.globals[K_ROON][K_OUTPUT_ID_TO_DEV_ID][output_id]
                        self.update_roon_output_device(roonOutputDevId, output_id)
                        self.logger.debug(
                            u"'process_outputs_added' - Output '{0}'. Indigo Device = '{1}', Output ID = '{2}'"
                                .format(self.globals[K_ROON][K_OUTPUTS][output_id][K_DISPLAY_NAME],
                                        indigo.devices[roonOutputDevId].name, output_id))
                    else:
                        self.logger.debug(
                            u"'process_outputs_added' - Output '{0}' no matching Indigo device. Output ID = '{1}'"
                                .format(self.globals[K_ROON][K_OUTPUTS][output_id][K_DISPLAY_NAME], output_id))

                        if self.globals[K_CONFIG][K_AUTO_CREATE_DEVICES]:
                            self.auto_create_output_device(output_id)

        except StandardError as e:
            self.logger.error(u"'process_outputs_added' error detected. Line '{0}' has error='{1}'".format(
                sys.exc_traceback.tb_lineno, e))

    def process_outputs_changed(self, event, changed_items):
        try:
            for output_id in changed_items:
                if output_id == '1701b9ea8b0814189098501722daf1427ea9':
                    tempOutputs = self.globals[K_ROON][K_API].outputs
                    self.logger.debug(
                        u"'process_outputs_changed' - ALL OUTPUTS = \n\n{0}\n\n.".format(tempOutputs))

                output_data = copy.deepcopy(self.globals[K_ROON][K_API].output_by_output_id(output_id))
                processOutput_successful = self.process_output(output_id, output_data)

                if processOutput_successful:
                    if output_id in self.globals[K_ROON][K_OUTPUT_ID_TO_DEV_ID]:
                        roonOutputDevId = self.globals[K_ROON][K_OUTPUT_ID_TO_DEV_ID][output_id]
                        self.update_roon_output_device(roonOutputDevId, output_id)
                        self.logger.debug(u"'process_outputs_changed' - Output '{0}'."
                                          u" Indigo Device = '{1}', Output ID = '{2}'\nOutput Data:\n{3}\n"
                                          .format(self.globals[K_ROON][K_OUTPUTS][output_id][K_DISPLAY_NAME], 
                                                  indigo.devices[roonOutputDevId].name, output_id, output_data))
                    else:
                        self.logger.debug(
                            u"'process_outputs_changed' - Output '{0}'. Output ID = '{1}'\n{2}"
                                .format(self.globals[K_ROON][K_OUTPUTS][output_id][K_DISPLAY_NAME],
                                        output_id, output_data))

        except StandardError as e:
            self.logger.error(
                u"'process_outputs_changed' error detected. Line '{0}' has error='{1}'".format(
                    sys.exc_traceback.tb_lineno, e))

    def process_outputs_removed(self, event, changed_items):
        try:
            self.logger.debug(u"'OUTPUT REMOVED' INVOKED")
            self.print_known_outputs_summary("PROCESS OUTPUT REMOVED [START]")

            for output_id in changed_items:
                if output_id in self.globals[K_ROON][K_OUTPUTS]:
                    output_display_name = "Unknown Output"
                    self.logger.debug(
                        u"'OUTPUT REMOVED' - Output:\n{0}".format(self.globals[K_ROON][K_OUTPUTS][output_id]))
                    if K_DISPLAY_NAME in self.globals[K_ROON][K_OUTPUTS][output_id]:
                        output_display_name = self.globals[K_ROON][K_OUTPUTS][output_id][K_DISPLAY_NAME]
                    if output_id in self.globals[K_ROON][K_OUTPUT_ID_TO_DEV_ID]:
                        roon_output_dev_id = self.globals[K_ROON][K_OUTPUT_ID_TO_DEV_ID][output_id]
                        self.disconnect_roon_output_device(roon_output_dev_id)
                        self.logger.debug(u"'OUTPUT REMOVED' - Output '{0}'. Indigo Device = '{1}', Output ID = '{2}'"
                                          .format(output_display_name, indigo.devices[roon_output_dev_id].name,
                                                  output_id))
                    else:
                        self.logger.debug(u"'OUTPUT REMOVED' - Output '{0}' no matching Indigo device."
                                          .format(output_display_name))

                del self.globals[K_ROON][K_OUTPUTS][output_id]

                self.print_known_outputs_summary('PROCESS OUTPUTS REMOVED [OUTPUT REMOVED]')

            else:
                self.logger.debug(
                    u"'OUTPUT REMOVED' - All Output:\n{0}".format(self.globals[K_ROON][K_OUTPUTS]))

        except StandardError as e:
            self.logger.error(
                u"'process_outputs_removed' error detected. Line '{0}' has error='{1}'".format(
                    sys.exc_traceback.tb_lineno, e))

    def process_playback_control(self, invoking_process_name, plugin_action, zone_dev):
        try:
            if zone_dev is None:
                self.logger.error(u"Roon Controller Action '{0}' ignored as no Zone device specified in Action.".format(plugin_action.pluginTypeId))
                return False

            if not zone_dev.states['zone_connected']:
                self.logger.error(u"Roon Controller Action '{0}' ignored as Zone '{1}' is disconnected.".format(plugin_action.pluginTypeId, zone_dev.name))
                return False

            zone_id = zone_dev.states['zone_id']
            if zone_id == '':
                self.logger.error(u"Roon Controller Action '{0}' ignored as Zone '{1}' is not connected to the Roon Core.".format(plugin_action.pluginTypeId, zone_dev.name))
                return False

            self.globals[K_ROON][K_API].playback_control(zone_id, plugin_action.pluginTypeId.lower())

            return True

        except StandardError as err:
            zone_dev_name = "Unknown Device"
            if zone_dev is not None:
                zone_dev_name = zone_dev.name
            self.logger.error(u"'process_playback_control' error detected for device '{0}' while invoked from '{1}'. Line '{2}' has error='{3}'".format(zone_dev_name, invoking_process_name, sys.exc_traceback.tb_lineno, err))

    def process_playback_control_mute(self, plugin_action, zone_dev):
        try:
            if zone_dev is None:
                self.logger.error(u"Roon Controller Action '{0}' ignored as no Zone device specified in Action.".format(plugin_action.pluginTypeId))
                return

            if not zone_dev.states['zone_connected']:
                self.logger.error(u"Roon Controller Action '{0}' ignored as Zone '{1}' is disconnected.".format(plugin_action.pluginTypeId, zone_dev.name))
                return

            zone_id = zone_dev.states['zone_id']
            if zone_id == '':
                self.logger.error(u"Roon Controller Action '{0}' ignored as Zone '{1}' is not connected to the Roon Core.".format(plugin_action.pluginTypeId, zone_dev.name))
                return

            if self.globals[K_ROON][K_ZONES][zone_id][K_OUTPUTS_COUNT] > 0:
                for output_number in self.globals[K_ROON][K_ZONES][zone_id][K_OUTPUTS]:
                    output_id = self.globals[K_ROON][K_ZONES][zone_id][K_OUTPUTS][output_number][K_OUTPUT_ID]

                    toggle = not self.globals[K_ROON][K_OUTPUTS][output_id][K_VOLUME][K_VOLUME_IS_MUTED]

                    self.globals[K_ROON][K_API].mute(output_id, toggle)

        except StandardError as err:
            zone_dev_name = "Unknown Device"
            if zone_dev is not None:
                zone_dev_name = zone_dev.name
            self.logger.error(u"'process_playback_control_mute' error detected for device '{0}'. Line '{1}' has error='{2}'".format(zone_dev_name, sys.exc_traceback.tb_lineno, err))

    def process_playback_control_mute_all(self, plugin_action, zone_dev):
        try:
            for zone_dev in indigo.devices.iter("self"):
                if zone_dev.deviceTypeId == 'roonZone':

                    if not zone_dev.states['zone_connected']:
                        self.logger.debug(u"Roon Controller Action '{0}' ignored as Zone '{1}' is disconnected.".format(plugin_action.pluginTypeId, zone_dev.name))
                        continue

                    zone_id = zone_dev.states['zone_id']
                    if zone_id == '':
                        self.logger.debug(u"Roon Controller Action '{0}' ignored as Zone '{1}' is not connected to the Roon Core.".format(plugin_action.pluginTypeId, zone_dev.name))
                        continue

                    if self.globals[K_ROON][K_ZONES][zone_id][K_OUTPUTS_COUNT] > 0:
                        for output_number in self.globals[K_ROON][K_ZONES][zone_id][K_OUTPUTS]:
                            output_id = self.globals[K_ROON][K_ZONES][zone_id][K_OUTPUTS][output_number][K_OUTPUT_ID]
                            self.globals[K_ROON][K_API].mute(output_id, True)

        except StandardError as err:
            zone_dev_name = "Unknown Device"
            if zone_dev is not None:
                zone_dev_name = zone_dev.name
            self.logger.error(u"'process_playback_control_mute_all' error detected for device '{0}'. Line '{1}' has error='{2}'".format(zone_dev_name, sys.exc_traceback.tb_lineno, err))

    def process_playback_control_next(self, pluginAction, zone_dev):
        try:
            if self.process_playback_control('process_playback_control_next', pluginAction, zone_dev):
                self.logger.info(u"Zone '{0}' advanced to next track.".format(zone_dev.name))

        except StandardError as err:
            zone_dev_name = "Unknown Device"
            if zone_dev is not None:
                zone_dev_name = zone_dev.name
            self.logger.error(u"'process_playback_control_next' error detected for device {0}. Line '{1}' has error='{2}'".format(zone_dev_name, sys.exc_traceback.tb_lineno, err))

    def process_playback_control_pause(self, pluginAction, zone_dev):
        try:
            if self.process_playback_control('process_playback_control_pause', pluginAction, zone_dev):
                self.logger.info(u"Zone '{0}' playback paused.".format(zone_dev.name))

        except StandardError as err:
            zone_dev_name = "Unknown Device"
            if zone_dev is not None:
                zone_dev_name = zone_dev.name
            self.logger.error(u"'process_playback_control_pause' error detected for device '{0}'. Line '{1}' has error='{2}'".format(zone_dev_name, sys.exc_traceback.tb_lineno, err))

    def process_playback_control_play(self, pluginAction, zone_dev):
        try:
            if self.process_playback_control('process_playback_control_play', pluginAction, zone_dev):
                self.logger.info(u"Zone '{0}' playback started.".format(zone_dev.name))

        except StandardError as err:
            zone_dev_name = "Unknown Device"
            if zone_dev is not None:
                zone_dev_name = zone_dev.name
            self.logger.error(u"'process_playback_control_play' error detected for device '{0}'. Line '{1}' has error='{2}'".format(zone_dev_name, sys.exc_traceback.tb_lineno, err))

    def process_playback_control_play_pause(self, pluginAction, zone_dev):
        try:
            if self.process_playback_control('process_playback_control_play_pause', pluginAction, zone_dev):
                self.logger.info(u"Zone '{0}' playback toggled.".format(zone_dev.name))

        except StandardError as err:
            zone_dev_name = "Unknown Device"
            if zone_dev is not None:
                zone_dev_name = zone_dev.name
            self.logger.error(u"'process_playback_control_play_pause' error detected for device '{0}'. Line '{1}' has error='{2}'".format(zone_dev_name, sys.exc_traceback.tb_lineno, err))

    def process_playback_control_previous(self, pluginAction, zone_dev):
        try:
            if self.process_playback_control('process_playback_control_previous', pluginAction, zone_dev):
                self.logger.info(u"Zone '{0}' gone to start of track or previous track.".format(zone_dev.name))

        except StandardError as err:
            zone_dev_name = "Unknown Device"
            if zone_dev is not None:
                zone_dev_name = zone_dev.name
            self.logger.error(u"'process_playback_control_previous' error detected for device '{0}'. Line '{1}' has error='{2}'".format(zone_dev_name, sys.exc_traceback.tb_lineno, err))

    def process_playback_control_stop(self, pluginAction, zone_dev):
        try:
            if self.process_playback_control('process_playback_control_stop', pluginAction, zone_dev):
                self.logger.info(u"Zone '{0}' playback stopped.".format(zone_dev.name))

        except StandardError as err:
            zone_dev_name = "Unknown Device"
            if zone_dev is not None:
                zone_dev_name = zone_dev.name
            self.logger.error(u"'process_playback_control_stop' error detected for device '{0}'. Line '{1}' has error='{2}'".format(zone_dev_name, sys.exc_traceback.tb_lineno, err))

    def process_playback_control_volume_decrease(self, plugin_action, output_dev):
        try:
            if output_dev is None:
                self.logger.error(u"'process_playback_control_volume_decrease' Roon Controller Action {0} ignored as no Output device specified in Action.".format(plugin_action.pluginTypeId))
                return

            if not output_dev.states['output_connected']:
                self.logger.error(u"'process_playback_control_volume_decrease' Roon Controller Action '{0}' ignored as Output '{1}' is disconnected.".format(plugin_action.pluginTypeId, output_dev.name))
                return

            output_id = output_dev.states['output_id']
            if output_id == '':
                self.logger.error(u"'process_playback_control_volume_decrease' Roon Controller Action '{0}' ignored as Output '{1}' is not connected to the Roon Core.".format(plugin_action.pluginTypeId, output_dev.name))
                return

            volume_decrement = -int(plugin_action.props['volumeDecrease'])
            if volume_decrement > -1:
                volume_decrement = -1  # SAFETY CHECK!

            self.globals[K_ROON][K_API].change_volume(output_id, volume_decrement, method='relative_step')

        except StandardError as err:
            output_dev_name = "Unknown Device"
            if output_dev is not None:
                output_dev_name = output_dev.name
            self.logger.error(u"'process_playback_control_volume_increase' error detected for device '{0}'. Line '{1}' has error='{2}'".format(output_dev_name, sys.exc_traceback.tb_lineno, err))

    def process_playback_control_volume_increase(self, plugin_action, output_dev):
        try:
            if output_dev is None:
                self.logger.error(u"'process_playback_control_volume_increase' Roon Controller Action '{0}' ignored as no Output device specified in Action.".format(plugin_action.pluginTypeId))
                return

            # self.logger.error(u"Roon Controller plugin method 'process_playback_control_next' Plugin Action:\n{0}\n".format(plugin_action))

            if not output_dev.states['output_connected']:
                self.logger.error(u"'process_playback_control_volume_increase' Roon Controller Action '{0}' ignored as Output '{1}' is disconnected.".format(plugin_action.pluginTypeId, output_dev.name))
                return

            output_id = output_dev.states['output_id']
            if output_id == '':
                self.logger.error(u"'process_playback_control_volume_increase' Roon Controller Action '{0}' ignored as Output '{1}' is not connected to the Roon Core.".format(plugin_action.pluginTypeId, output_dev.name))
                return

            volume_increment = int(plugin_action.props['volumeIncrease'])
            if volume_increment > 10:
                volume_increment = 1  # SAFETY CHECK!

            self.globals[K_ROON][K_API].change_volume(output_id, volume_increment, method='relative_step')

        except StandardError as err:
            output_dev_name = "Unknown Device"
            if output_dev is not None:
                output_dev_name = output_dev.name
            self.logger.error(u"'process_playback_control_volume_increase' error detected for device '{0}'. Line '{1}' has error='{2}'".format(output_dev_name, sys.exc_traceback.tb_lineno, err))

    def process_playback_control_volume_set(self, plugin_action, output_dev):
        try:
            if output_dev is None:
                self.logger.error(u"'process_playback_control_volume_set' Roon Controller Action '{0}' ignored as no Output device specified in Action.".format(plugin_action.pluginTypeId))
                return

            if not output_dev.states['output_connected']:
                self.logger.error(u"'process_playback_control_volume_set' Roon Controller Action '{0}' ignored as Output '{1}' is disconnected.".format(plugin_action.pluginTypeId, output_dev.name))
                return

            output_id = output_dev.states['output_id']
            if output_id == '':
                self.logger.error(u"'process_playback_control_volume_set' Roon Controller Action '{0}' ignored as Output '{1}' is not connected to the Roon Core.".format(plugin_action.pluginTypeId, output_dev.name))
                return

            volume_level = int(plugin_action.props['volumePercentage'])

            self.globals[K_ROON][K_API].change_volume(output_id, volume_level, method='absolute')

        except StandardError as err:
            output_dev_name = "Unknown Device"
            if output_dev is not None:
                output_dev_name = output_dev.name
            self.logger.error(u"'process_playback_control_volume_set' error detected for device '{0}'. Line '{1}' has error='{2}'".format(output_dev_name, sys.exc_traceback.tb_lineno, err))

    def process_roon_callback_queue(self):
        try:
            self.logger.debug(u"'Roon [SELF] Queue Callback' '{0}': {1}".format(event, changed_items))

        except StandardError as e:
            self.logger.error(u"'process_roon_callback_queue' error detected. Line '{0}' has error='{1}'"
                              .format(sys.exc_traceback.tb_lineno, e))

    def process_roon_callback_state(self, event, changed_items):
        try:

            if event == 'zones_seek_changed':
                self.process_zones_seek_changed(event, changed_items)

            elif event == 'zones_changed':
                self.process_zones_changed(event, changed_items)

            elif event == 'zones_added':
                self.process_zones_added(event, changed_items)

            elif event == 'zones_removed':
                self.process_zones_removed(event, changed_items)

            elif event == 'outputs_changed':
                self.process_outputs_changed(event, changed_items)

            elif event == 'outputs_added':
                self.process_outputs_added(event, changed_items)

            elif event == 'outputs_removed':
                self.process_outputs_removed(event, changed_items)

        except StandardError as e:
            self.logger.error(u"'process_roon_callback_state' error detected. Line '{0}' has error='{1}'"
                              .format(sys.exc_traceback.tb_lineno, e))

    def process_roon_volume_control(self, control_key, event, data):

        try:
            self.logger.error("'process_roon_volume_control' --> control_key: '{0}', event: '{1}' - data: '{2}'"
                              .format(control_key, event, data))
            # just echo back the new value to set it
            # if event == "set_mute":
            #     roonapi.update_volume_control(control_key, mute=data)
            # elif event == "set_volume":
            #     roonapi.update_volume_control(control_key, volume=data)
        except StandardError as e:
            self.logger.error(u"'process_roon_volume_control' error detected. Line '{0}' has error='{1}'"
                              .format(sys.exc_traceback.tb_lineno, e))

    def process_zone(self, zone_id, zoneData):
        try:
            self.globals[K_ROON][K_ZONES][zone_id] = dict()

            self.globals[K_ROON][K_ZONES][zone_id][K_ZONE_ID] = ""
            self.globals[K_ROON][K_ZONES][zone_id][K_QUEUE_ITEMS_REMAINING] = 0
            self.globals[K_ROON][K_ZONES][zone_id][K_QUEUE_TIME_REMAINING] = 0
            self.globals[K_ROON][K_ZONES][zone_id][K_DISPLAY_NAME] = ""
            self.globals[K_ROON][K_ZONES][zone_id][K_SETTINGS] = dict()
            self.globals[K_ROON][K_ZONES][zone_id][K_SETTINGS][K_AUTO_RADIO] = False
            self.globals[K_ROON][K_ZONES][zone_id][K_SETTINGS][K_SHUFFLE] = False
            self.globals[K_ROON][K_ZONES][zone_id][K_SETTINGS][K_LOOP] = u"disabled"
            self.globals[K_ROON][K_ZONES][zone_id][K_ZONE_UNIQUE_IDENTITY_KEY] = ""
            self.globals[K_ROON][K_ZONES][zone_id][K_OUTPUTS] = dict()
            self.globals[K_ROON][K_ZONES][zone_id][K_OUTPUTS_COUNT] = 0
            self.globals[K_ROON][K_ZONES][zone_id][K_NOW_PLAYING] = dict()
            self.globals[K_ROON][K_ZONES][zone_id][K_NOW_PLAYING][K_ARTIST_IMAGE_KEYS] = dict()
            self.globals[K_ROON][K_ZONES][zone_id][K_NOW_PLAYING][K_ARTIST_IMAGE_KEYS_COUNT] = 0
            self.globals[K_ROON][K_ZONES][zone_id][K_NOW_PLAYING][K_IMAGE_KEY] = ""
            self.globals[K_ROON][K_ZONES][zone_id][K_NOW_PLAYING][K_ONE_LINE] = dict()
            self.globals[K_ROON][K_ZONES][zone_id][K_NOW_PLAYING][K_ONE_LINE][K_LINE_1] = ""
            self.globals[K_ROON][K_ZONES][zone_id][K_NOW_PLAYING][K_TWO_LINE] = dict()
            self.globals[K_ROON][K_ZONES][zone_id][K_NOW_PLAYING][K_TWO_LINE][K_LINE_1] = ""
            self.globals[K_ROON][K_ZONES][zone_id][K_NOW_PLAYING][K_TWO_LINE][K_LINE_2] = ""
            self.globals[K_ROON][K_ZONES][zone_id][K_NOW_PLAYING][K_THREE_LINE] = dict()
            self.globals[K_ROON][K_ZONES][zone_id][K_NOW_PLAYING][K_THREE_LINE][K_LINE_1] = ""
            self.globals[K_ROON][K_ZONES][zone_id][K_NOW_PLAYING][K_THREE_LINE][K_LINE_2] = ""
            self.globals[K_ROON][K_ZONES][zone_id][K_NOW_PLAYING][K_THREE_LINE][K_LINE_3] = ""
            self.globals[K_ROON][K_ZONES][zone_id][K_NOW_PLAYING][K_LENGTH] = 0
            self.globals[K_ROON][K_ZONES][zone_id][K_NOW_PLAYING][K_SEEK_POSITION] = 0
            self.globals[K_ROON][K_ZONES][zone_id][K_IS_PREVIOUS_ALLOWED] = False
            self.globals[K_ROON][K_ZONES][zone_id][K_IS_PAUSE_ALLOWED] = False
            self.globals[K_ROON][K_ZONES][zone_id][K_IS_SEEK_ALLOWED] = False
            self.globals[K_ROON][K_ZONES][zone_id][K_STATE] = "stopped"
            self.globals[K_ROON][K_ZONES][zone_id][K_IS_PLAY_ALLOWED] = False
            self.globals[K_ROON][K_ZONES][zone_id][K_IS_NEXT_ALLOWED] = False

            for zoneKey, zoneValue in zoneData.iteritems():

                if zoneKey == 'zone_id':
                    self.globals[K_ROON][K_ZONES][zone_id][K_ZONE_ID] = zoneValue
                if zoneKey == 'queue_items_remaining':
                    self.globals[K_ROON][K_ZONES][zone_id][K_QUEUE_ITEMS_REMAINING] = zoneValue
                elif zoneKey == 'queue_time_remaining':
                    self.globals[K_ROON][K_ZONES][zone_id][K_QUEUE_TIME_REMAINING] = zoneValue
                elif zoneKey == 'display_name':
                    self.globals[K_ROON][K_ZONES][zone_id][K_DISPLAY_NAME] = zoneValue
                elif zoneKey == 'settings':
                    self.globals[K_ROON][K_ZONES][zone_id][K_SETTINGS] = dict()
                    for zoneKey2, zoneValue2 in zoneValue.iteritems():
                        if zoneKey2 == 'auto_radio':
                            self.globals[K_ROON][K_ZONES][zone_id][K_SETTINGS][K_AUTO_RADIO] = bool(zoneValue2)
                        elif zoneKey2 == 'shuffle':
                            self.globals[K_ROON][K_ZONES][zone_id][K_SETTINGS][K_SHUFFLE] = bool(zoneValue2)
                        elif zoneKey2 == 'loop':
                            self.globals[K_ROON][K_ZONES][zone_id][K_SETTINGS][K_LOOP] = zoneValue2
                elif zoneKey == 'outputs':
                    self.globals[K_ROON][K_ZONES][zone_id][K_OUTPUTS] = dict()
                    outputCount = 0
                    outputsList = list()
                    for output in zoneValue:
                        outputCount += 1
                        self.globals[K_ROON][K_ZONES][zone_id][K_OUTPUTS][outputCount] = dict()
                        for outputKey, outputData in output.iteritems():
                            if outputKey == 'output_id':
                                self.globals[K_ROON][K_ZONES][zone_id][K_OUTPUTS][outputCount][K_OUTPUT_ID] = outputData
                                outputsList.append(outputData)
                            elif outputKey == 'display_name':
                                self.globals[K_ROON][K_ZONES][zone_id][K_OUTPUTS][outputCount][K_DISPLAY_NAME] = outputData
                            elif outputKey == 'zone_id':
                                self.globals[K_ROON][K_ZONES][zone_id][K_OUTPUTS][outputCount][K_ZONE_ID] = outputData
                            elif outputKey == 'source_controls':
                                self.globals[K_ROON][K_ZONES][zone_id][K_OUTPUTS][outputCount][K_SOURCE_CONTROLS] = dict()
                                sourceControlsCount = 0
                                for sourceControls in outputData:
                                    sourceControlsCount += 1
                                    self.globals[K_ROON][K_ZONES][zone_id][K_OUTPUTS][outputCount][K_SOURCE_CONTROLS][sourceControlsCount] = dict()
                                    for sourceControlKey, sourceControlData in sourceControls.iteritems():
                                        if sourceControlKey == 'status':
                                            self.globals[K_ROON][K_ZONES][zone_id][K_OUTPUTS][outputCount][K_SOURCE_CONTROLS][sourceControlsCount][K_STATUS] = sourceControlData
                                        elif sourceControlKey == 'display_name':
                                            self.globals[K_ROON][K_ZONES][zone_id][K_OUTPUTS][outputCount][K_SOURCE_CONTROLS][sourceControlsCount][K_DISPLAY_NAME] = sourceControlData
                                        elif sourceControlKey == 'control_key':
                                            self.globals[K_ROON][K_ZONES][zone_id][K_OUTPUTS][outputCount][K_SOURCE_CONTROLS][sourceControlsCount][K_CONTROL_KEY] = sourceControlData
                                        elif sourceControlKey == 'supports_standby':
                                            self.globals[K_ROON][K_ZONES][zone_id][K_OUTPUTS][outputCount][K_SOURCE_CONTROLS][sourceControlsCount][K_SUPPORTS_STANDBY] = bool(sourceControlData)
                                self.globals[K_ROON][K_ZONES][zone_id][K_OUTPUTS][outputCount][K_SOURCE_CONTROLS_COUNT] = sourceControlsCount
                            elif outputKey == 'volume':
                                self.globals[K_ROON][K_ZONES][zone_id][K_OUTPUTS][outputCount][K_VOLUME] = dict()
                                for volumeKey, volumeData in outputData.iteritems():
                                    if volumeKey == 'hard_limit_min':
                                        self.globals[K_ROON][K_ZONES][zone_id][K_OUTPUTS][outputCount][K_VOLUME][K_VOLUME_HARD_LIMIT_MIN] = volumeData
                                    elif volumeKey == 'min':
                                        self.globals[K_ROON][K_ZONES][zone_id][K_OUTPUTS][outputCount][K_VOLUME][K_VOLUME_MIN] = volumeData
                                    elif volumeKey == 'is_muted':
                                        self.globals[K_ROON][K_ZONES][zone_id][K_OUTPUTS][outputCount][K_VOLUME][K_VOLUME_IS_MUTED] = volumeData
                                    elif volumeKey == 'max':
                                        self.globals[K_ROON][K_ZONES][zone_id][K_OUTPUTS][outputCount][K_VOLUME][K_VOLUME_MAX] = volumeData
                                    elif volumeKey == 'value':
                                        self.globals[K_ROON][K_ZONES][zone_id][K_OUTPUTS][outputCount][K_VOLUME][K_VOLUME_VALUE] = volumeData
                                    elif volumeKey == 'step':
                                        self.globals[K_ROON][K_ZONES][zone_id][K_OUTPUTS][outputCount][K_VOLUME][K_VOLUME_STEP] = volumeData
                                    elif volumeKey == 'hard_limit_max':
                                        self.globals[K_ROON][K_ZONES][zone_id][K_OUTPUTS][outputCount][K_VOLUME][K_VOLUME_HARD_LIMIT_MAX] = volumeData
                                    elif volumeKey == 'soft_limit':
                                        self.globals[K_ROON][K_ZONES][zone_id][K_OUTPUTS][outputCount][K_VOLUME][K_VOLUME_SOFT_LIMIT] = volumeData
                                    elif volumeKey == 'type':
                                        self.globals[K_ROON][K_ZONES][zone_id][K_OUTPUTS][outputCount][K_VOLUME][K_VOLUME_TYPE] = volumeData

                            elif outputKey == 'can_group_with_output_ids':
                                self.globals[K_ROON][K_ZONES][zone_id][K_OUTPUTS][outputCount][K_CAN_GROUP_WITH_OUTPUT_IDS] = dict()
                                canGroupCount = 0
                                for can_group_with_output_id in outputData:
                                    canGroupCount += 1
                                    self.globals[K_ROON][K_ZONES][zone_id][K_OUTPUTS][outputCount][K_CAN_GROUP_WITH_OUTPUT_IDS][canGroupCount] = can_group_with_output_id
                                self.globals[K_ROON][K_ZONES][zone_id][K_OUTPUTS][outputCount][K_CAN_GROUP_WITH_OUTPUT_IDS_COUNT] = canGroupCount
                    self.globals[K_ROON][K_ZONES][zone_id][K_OUTPUTS_COUNT] = outputCount
                    outputsList.sort()
                    self.globals[K_ROON][K_ZONES][zone_id][K_ZONE_UNIQUE_IDENTITY_KEY] = self.convert_output_id_list_to_string(outputsList)

                elif zoneKey == 'now_playing':
                    for zoneKey2, zoneValue2 in zoneValue.iteritems():
                        if zoneKey2 == 'artist_image_keys':
                            artistImageCount = 0
                            for artist_image_key in zoneValue2:
                                artistImageCount += 1
                                self.globals[K_ROON][K_ZONES][zone_id][K_NOW_PLAYING][K_ARTIST_IMAGE_KEYS][artistImageCount] = artist_image_key
                            self.globals[K_ROON][K_ZONES][zone_id][K_NOW_PLAYING][K_ARTIST_IMAGE_KEYS_COUNT] = artistImageCount
                        elif zoneKey2 == 'image_key':
                            self.globals[K_ROON][K_ZONES][zone_id][K_NOW_PLAYING][K_IMAGE_KEY] = zoneValue2
                        elif zoneKey2 == 'one_line':
                            self.globals[K_ROON][K_ZONES][zone_id][K_NOW_PLAYING][K_ONE_LINE] = dict()
                            for zoneKey3, zoneValue3 in zoneValue2.iteritems():
                                if zoneKey3 == 'line1':
                                    self.globals[K_ROON][K_ZONES][zone_id][K_NOW_PLAYING][K_ONE_LINE][K_LINE_1] = zoneValue3
                        elif zoneKey2 == 'two_line':
                            self.globals[K_ROON][K_ZONES][zone_id][K_NOW_PLAYING][K_TWO_LINE] = dict()
                            for zoneKey3, zoneValue3 in zoneValue2.iteritems():
                                if zoneKey3 == 'line1':
                                    self.globals[K_ROON][K_ZONES][zone_id][K_NOW_PLAYING][K_TWO_LINE][K_LINE_1] = zoneValue3
                                elif zoneKey3 == 'line2':
                                    self.globals[K_ROON][K_ZONES][zone_id][K_NOW_PLAYING][K_TWO_LINE][K_LINE_2] = zoneValue3
                        elif zoneKey2 == 'three_line':
                            self.globals[K_ROON][K_ZONES][zone_id][K_NOW_PLAYING][K_THREE_LINE] = dict()
                            for zoneKey3, zoneValue3 in zoneValue2.iteritems():
                                if zoneKey3 == 'line1':
                                    self.globals[K_ROON][K_ZONES][zone_id][K_NOW_PLAYING][K_THREE_LINE][K_LINE_1] = zoneValue3
                                elif zoneKey3 == 'line2':
                                    self.globals[K_ROON][K_ZONES][zone_id][K_NOW_PLAYING][K_THREE_LINE][K_LINE_2] = zoneValue3
                                elif zoneKey3 == 'line3':
                                    self.globals[K_ROON][K_ZONES][zone_id][K_NOW_PLAYING][K_THREE_LINE][K_LINE_3] = zoneValue3
                        if zoneKey2 == 'length':
                            self.globals[K_ROON][K_ZONES][zone_id][K_NOW_PLAYING][K_LENGTH] = zoneValue2
                        if zoneKey2 == 'seek_position':
                            if zoneValue2 is None:
                                self.globals[K_ROON][K_ZONES][zone_id][K_NOW_PLAYING][K_SEEK_POSITION] = 0
                            else:
                                self.globals[K_ROON][K_ZONES][zone_id][K_NOW_PLAYING][K_SEEK_POSITION] = zoneValue2

                elif zoneKey == 'is_previous_allowed':
                    self.globals[K_ROON][K_ZONES][zone_id][K_IS_PREVIOUS_ALLOWED] = bool(zoneValue)
                elif zoneKey == 'is_pause_allowed':
                    self.globals[K_ROON][K_ZONES][zone_id][K_IS_PAUSE_ALLOWED] = bool(zoneValue)
                elif zoneKey == 'is_seek_allowed':
                    self.globals[K_ROON][K_ZONES][zone_id][K_IS_SEEK_ALLOWED] = bool(zoneValue)
                elif zoneKey == 'state':
                    self.globals[K_ROON][K_ZONES][zone_id][K_STATE] = zoneValue
                elif zoneKey == 'is_play_allowed':
                    self.globals[K_ROON][K_ZONES][zone_id][K_IS_PLAY_ALLOWED] = bool(zoneValue)
                elif zoneKey == 'is_next_allowed':
                    self.globals[K_ROON][K_ZONES][zone_id][K_IS_NEXT_ALLOWED] = bool(zoneValue)

            # ### SPECIAL ANNOUCEMENT CODE - START ####
            if self.globals[K_ROON][K_ZONES][zone_id][K_NOW_PLAYING][K_THREE_LINE][K_LINE_1] != '':
                zone_state = self.globals[K_ROON][K_ZONES][zone_id][K_STATE]
                self.logger.debug(u"STC. STATE = {0}".format(zone_state))

                if zone_state == u"playing":
                    announcement_track = self.globals[K_ROON][K_ZONES][zone_id][K_NOW_PLAYING][K_THREE_LINE][K_LINE_1]
                    work_artist = self.globals[K_ROON][K_ZONES][zone_id][K_NOW_PLAYING][K_THREE_LINE][K_LINE_2]
                    work_artist = work_artist.replace(' / Various Artists', '')
                    work_artist = work_artist.replace(' / ', ' and ')
                    work_artist = work_artist.replace(' & ', ' and ')
                    work_artist = work_artist.replace(', Jr.', ' junior')
                    announcement_artist = work_artist
                    announcement_album = self.globals[K_ROON][K_ZONES][zone_id][K_NOW_PLAYING][K_THREE_LINE][K_LINE_3]
                    work_announcement = (u"Now playing {0}".format(announcement_track))
                    if announcement_artist != '':
                        work_announcement = (u"{0}, by {1}".format(work_announcement, announcement_artist))
                    if announcement_album != '':
                        work_announcement = (u"{0}, from the album, {1}".format(work_announcement, announcement_album))
                    announcement = work_announcement.replace(' & ', ' and ')
                else:
                    announcement = ""

                self.logger.debug(u"STC. Announcement = 0".format(announcement))

                self.logger.debug(u"STC. OUTPUT ID TO DEV ID = {0}".format(self.globals[K_ROON][K_OUTPUT_ID_TO_DEV_ID]))

                for key, output in self.globals[K_ROON][K_ZONES][zone_id][K_OUTPUTS].iteritems():
                    self.logger.debug(u"STC. Key = {0}, Output ID = {1}".format(key, output))
                    if 'output_id' in output:
                        roonOutputDevId = self.globals[K_ROON][K_OUTPUT_ID_TO_DEV_ID][output[K_OUTPUT_ID]]
                        self.logger.debug(u"STC. ROONOUTPUTDEVID = {0}".format(roonOutputDevId))

                        roonOutputDev = indigo.devices[roonOutputDevId]
                        if roonOutputDev.enabled:
                            nowPlayingVarId = int(roonOutputDev.pluginProps.get('nowPlayingVarId', 0))
                            self.logger.debug(u"STC. INDIGO OUTPUT DEV [{0}]: NOWPLAYINGVARID = {1}"
                                              .format(roonOutputDev.name, nowPlayingVarId))
                            if nowPlayingVarId != 0:
                                indigo.variable.updateValue(nowPlayingVarId, value=announcement)

            # ### SPECIAL ANNOUCEMENT CODE - END ####

            if self.globals[K_ROON][K_ZONES][zone_id][K_ZONE_ID] != '' and self.globals[K_ROON][K_ZONES][zone_id][K_ZONE_UNIQUE_IDENTITY_KEY] != '':
                self.globals[K_ROON][K_ZONE_UNIQUE_IDENTITY_KEY_TO_ZONE_ID][self.globals[K_ROON][K_ZONES][zone_id][K_ZONE_UNIQUE_IDENTITY_KEY]] = self.globals[K_ROON][K_ZONES][zone_id][K_ZONE_ID]

                if self.globals[K_ROON][K_ZONES][zone_id][K_ZONE_UNIQUE_IDENTITY_KEY] not in self.globals[K_ROON][K_ZONE_UNIQUE_IDENTITY_KEY_TO_DEV_ID]:
                    if self.globals[K_CONFIG][K_AUTO_CREATE_DEVICES]:
                        self.auto_create_zone_device(zone_id, self.globals[K_ROON][K_ZONES][zone_id][K_ZONE_UNIQUE_IDENTITY_KEY])

            else:
                self.logger.error(u"'process_zone' unable to set up 'zoneUniqueIdentityKeyToZoneId'"
                                  " entry: Zone_id = '{0}', zone_unique_identity_key = '{1}'"
                                  .format(zone_id, self.globals[K_ROON][K_ZONES][zone_id][K_ZONE_UNIQUE_IDENTITY_KEY]))

        except StandardError as e:
            self.logger.error(u"'process_zone' error detected. Line '{0}' has error='{1}'"
                              .format(sys.exc_traceback.tb_lineno, e))

    def process_zones(self, zones):
        try:
            for zone_id, zoneData in zones.iteritems():
                self.process_zone(zone_id, zoneData)
                if self.globals[K_CONFIG][K_PRINT_ZONE]:
                    self.print_zone(zone_id)

        except StandardError as e:
            self.logger.error(u"'process_zones' error detected. Line '{0}' has error='{1}'"
                              .format(sys.exc_traceback.tb_lineno, e))

    def process_zones_added(self, event, changed_items):
        try:
            # self.print_known_zones_summary('PROCESS ZONES ADDED')

            for zone_id in changed_items:
                zoneData = copy.deepcopy(self.globals[K_ROON][K_API].zone_by_zone_id(zone_id))
                self.process_zone(zone_id, zoneData)
                zoneUniqueIdentityKey = self.globals[K_ROON][K_ZONES][zone_id][K_ZONE_UNIQUE_IDENTITY_KEY]
                self.logger.debug(u"'process_zones_added' - Zone '{0}'. Zone ID = '{1}', "
                                  u"Unique ID = '{2}'\nZoneData:\n{3}\n"
                                  .format(self.globals[K_ROON][K_ZONES][zone_id][K_DISPLAY_NAME],
                                          zone_id, zoneUniqueIdentityKey, zoneData))

                if zoneUniqueIdentityKey in self.globals[K_ROON][K_ZONE_UNIQUE_IDENTITY_KEY_TO_DEV_ID]:
                    roonZoneDevId = self.globals[K_ROON][K_ZONE_UNIQUE_IDENTITY_KEY_TO_DEV_ID][zoneUniqueIdentityKey]
                    self.update_roon_zone_device(roonZoneDevId, zone_id)
                    self.logger.debug(u"'process_zones_added' - Zone '{0}'. Indigo Device = '{1}', "
                                      u"Zone ID = '{2}', Unique ID = '{3}'"
                                      .format(self.globals[K_ROON][K_ZONES][zone_id][K_DISPLAY_NAME],
                                              indigo.devices[roonZoneDevId].name, zone_id, zoneUniqueIdentityKey))
                else:
                    self.logger.debug(u"'process_zones_added' - Zone '{0}' no matching Indigo device."
                                      u" Zone ID = '{1}', Unique ID = '{2}'"
                                      .format(self.globals[K_ROON][K_ZONES][zone_id][K_DISPLAY_NAME],
                                              zone_id, zoneUniqueIdentityKey))

                    if self.globals[K_CONFIG][K_AUTO_CREATE_DEVICES]:
                        self.auto_create_zone_device(zone_id, zoneUniqueIdentityKey)

        except StandardError as e:
            self.logger.error(u"'process_zones_added' error detected. Line '{0}' has error='{1}'"
                              .format(sys.exc_traceback.tb_lineno, e))

    def process_zones_changed(self, event, changed_items):
        try:
            # self.print_known_zones_summary('PROCESS ZONES CHANGED')

            for zone_id in changed_items:

                zoneData = copy.deepcopy(self.globals[K_ROON][K_API].zone_by_zone_id(zone_id))
                self.process_zone(zone_id, zoneData)

                zoneUniqueIdentityKey = self.globals[K_ROON][K_ZONES][zone_id][K_ZONE_UNIQUE_IDENTITY_KEY]
                if zoneUniqueIdentityKey in self.globals[K_ROON][K_ZONE_UNIQUE_IDENTITY_KEY_TO_DEV_ID]:
                    roonZoneDevId = self.globals[K_ROON][K_ZONE_UNIQUE_IDENTITY_KEY_TO_DEV_ID][zoneUniqueIdentityKey]
                    self.update_roon_zone_device(roonZoneDevId, zone_id)
                    self.logger.debug(u"'ZONE CHANGED' - Zone '{0}'. Indigo Device = '{1}', Unique ID = '{2}'"
                                      .format(self.globals[K_ROON][K_ZONES][zone_id][K_DISPLAY_NAME],
                                              indigo.devices[roonZoneDevId].name, zoneUniqueIdentityKey))
                else:
                    self.logger.debug(u"'ZONE CHANGED' - Zone '{0}' no matching Indigo device. Unique ID = '{1}'"
                                      .format(self.globals[K_ROON][K_ZONES][zone_id][K_DISPLAY_NAME],
                                              zoneUniqueIdentityKey))

        except StandardError as e:
            self.logger.error(u"'process_zones_changed' error detected. Line '{0}' has error='{1}'"
                              .format(sys.exc_traceback.tb_lineno, e))

    def process_zones_removed(self, event, changed_items):
        try:
            self.logger.debug(u"'ZONE REMOVED' INVOKED")
            # self.print_known_zones_summary('PROCESS ZONES REMOVED [START]')

            for zone_id in changed_items:
                zone_display_name = "Unknown Zone"
                zone_unique_identity_key = "None"
                if zone_id in self.globals[K_ROON][K_ZONES]:
                    self.logger.debug(
                        u"'process_zones_removed' - Zone:\n{0}".format(self.globals[K_ROON][K_ZONES][zone_id]))

                    if K_DISPLAY_NAME in self.globals[K_ROON][K_ZONES][zone_id]:
                        zone_display_name = self.globals[K_ROON][K_ZONES][zone_id][K_DISPLAY_NAME]
                    if K_ZONE_UNIQUE_IDENTITY_KEY in self.globals[K_ROON][K_ZONES][zone_id]:
                        zone_unique_identity_key = self.globals[K_ROON][K_ZONES][zone_id][K_ZONE_UNIQUE_IDENTITY_KEY]
                        if zone_unique_identity_key in self.globals[K_ROON][K_ZONE_UNIQUE_IDENTITY_KEY_TO_DEV_ID]:
                            roonZoneDevId = self.globals[K_ROON][K_ZONE_UNIQUE_IDENTITY_KEY_TO_DEV_ID][
                                zone_unique_identity_key]
                            self.disconnect_roon_zone_device(roonZoneDevId)
                            self.logger.debug(
                                u"'process_zones_removed' - Zone '{0}'. Indigo Device = '{1}', Zone ID = '{2}',"
                                u" Unique ID = '{3}'"
                                    .format(self.globals[K_ROON][K_ZONES][zone_id][K_DISPLAY_NAME],
                                            indigo.devices[roonZoneDevId].name, zone_id, zone_unique_identity_key))
                        else:
                            self.logger.debug(
                                u"'process_zones_removed' - Zone '{0}' no matching Indigo device. Unique ID = '{1}'"
                                    .format(zone_display_name, zone_unique_identity_key))
                    else:
                        self.logger.debug(
                            u"'process_zones_removed' - Zone '{0}', Zone ID = '{1}' no matching Indigo device."
                            u" Unique ID = '{2}'".format(zone_display_name, zone_id, zone_unique_identity_key))

                    del self.globals[K_ROON][K_ZONES][zone_id]

                    # self.print_known_zones_summary('PROCESS ZONES REMOVED [ZONE REMOVED]')

                else:
                    self.logger.debug(u"'process_zones_removed' - All Zones:\n{0}"
                                      .format(self.globals[K_ROON][K_ZONES]))

                self.logger.debug(u"'process_zones_removed' - Zone '{0}'. Zone ID =  '{1}', Unique ID = '{2}'"
                                  .format(zone_display_name, zone_id, zone_unique_identity_key))

        except StandardError as e:
            self.logger.error(u"'process_zones_removed' error detected. Line '{0}' has error='{1}'".format(
                sys.exc_traceback.tb_lineno, e))

    def process_zones_seek_changed(self, event, changed_items):
        zoneData = None
        try:
            for zone_id in changed_items:
                zoneData = copy.deepcopy(self.globals[K_ROON][K_API].zone_by_zone_id(zone_id))

                self.globals[K_ROON][K_ZONES][zone_id][K_QUEUE_ITEMS_REMAINING] = zoneData['queue_items_remaining']
                self.globals[K_ROON][K_ZONES][zone_id][K_QUEUE_TIME_REMAINING] = zoneData['queue_time_remaining']
                if 'seek_position' in zoneData:
                    self.globals[K_ROON][K_ZONES][zone_id][K_SEEK_POSITION] = zoneData['seek_position']
                    if self.globals[K_ROON][K_ZONES][zone_id][K_SEEK_POSITION] is None:
                        self.globals[K_ROON][K_ZONES][zone_id][K_SEEK_POSITION] = 0
                        self.globals[K_ROON][K_ZONES][zone_id][K_REMAINING] = 0
                    else:
                        if 'now_playing' in zoneData and 'length' in zoneData['now_playing']:
                            self.globals[K_ROON][K_ZONES][zone_id][K_REMAINING] = int(zoneData['now_playing']['length']) - int(self.globals[K_ROON][K_ZONES][zone_id][K_SEEK_POSITION])
                        else:
                            self.globals[K_ROON][K_ZONES][zone_id][K_REMAINING] = 0
                else:
                    self.globals[K_ROON][K_ZONES][zone_id][K_SEEK_POSITION] = 0
                    self.globals[K_ROON][K_ZONES][zone_id][K_REMAINING] = 0

                self.globals[K_ROON][K_ZONES][zone_id][K_STATE] = zoneData.get('state', '-stopped-')

                if K_ZONE_UNIQUE_IDENTITY_KEY in self.globals[K_ROON][K_ZONES][zone_id]:
                    zone_unique_identity_key = self.globals[K_ROON][K_ZONES][zone_id][K_ZONE_UNIQUE_IDENTITY_KEY]
                else:
                    zone_unique_identity_key = "NONE"
                if zone_unique_identity_key in self.globals[K_ROON][K_ZONE_UNIQUE_IDENTITY_KEY_TO_DEV_ID] and zone_unique_identity_key != 'NONE':
                    roonZoneDevId = self.globals[K_ROON][K_ZONE_UNIQUE_IDENTITY_KEY_TO_DEV_ID][zone_unique_identity_key]

                    ui_queue_time_remaining = self.ui_time(self.globals[K_ROON][K_ZONES][zone_id][K_QUEUE_TIME_REMAINING])
                    ui_seek_position = self.ui_time(self.globals[K_ROON][K_ZONES][zone_id][K_SEEK_POSITION])
                    ui_remaining = self.ui_time(self.globals[K_ROON][K_ZONES][zone_id][K_REMAINING])

                    zone_dev = indigo.devices[roonZoneDevId]
                    key_value_list = [
                        {'key': 'queue_items_remaining', 'value': self.globals[K_ROON][K_ZONES][zone_id][K_QUEUE_ITEMS_REMAINING]},
                        {'key': 'queue_time_remaining', 'value': self.globals[K_ROON][K_ZONES][zone_id][K_QUEUE_TIME_REMAINING]},
                        {'key': 'seek_position', 'value': self.globals[K_ROON][K_ZONES][zone_id][K_SEEK_POSITION]},
                        {'key': 'remaining', 'value': self.globals[K_ROON][K_ZONES][zone_id][K_REMAINING]},
                        {'key': 'state', 'value': self.globals[K_ROON][K_ZONES][zone_id][K_STATE]},
                        {'key': 'ui_queue_time_remaining', 'value': ui_queue_time_remaining},
                        {'key': 'ui_seek_position', 'value': ui_seek_position},
                        {'key': 'ui_remaining', 'value': ui_remaining}
                    ]

                    if zone_dev.states['state'] != self.globals[K_ROON][K_ZONES][zone_id][K_STATE]:
                        key_value_list.append({'key': 'state', 'value': self.globals[K_ROON][K_ZONES][zone_id][K_STATE]})
                        if self.globals[K_ROON][K_ZONES][zone_id][K_STATE] == 'playing':
                            zone_dev.updateStateImageOnServer(indigo.kStateImageSel.AvPlaying)
                        elif self.globals[K_ROON][K_ZONES][zone_id][K_STATE] == 'paused':
                            zone_dev.updateStateImageOnServer(indigo.kStateImageSel.AvPaused)
                        else:
                            zone_dev.updateStateImageOnServer(indigo.kStateImageSel.AvStopped)
                    if zone_dev.states['zone_status'] != self.globals[K_ROON][K_ZONES][zone_id][K_STATE]:
                        key_value_list.append({'key': 'zone_status', 'value': self.globals[K_ROON][K_ZONES][zone_id][K_STATE]})

                    zone_dev.updateStatesOnServer(key_value_list)

        except StandardError as e:
            self.logger.error(u"'process_zones_seek_changed' error detected."
                              u" Line '{0}' has error='{1}'\nZoneData:\n{2}\n"
                              .format(sys.exc_traceback.tb_lineno, e, zoneData))

    def roon_output_id_selected(self, values_dict, type_id, devId):
        try:
            output_id = values_dict.get('roonOutputId', '-')
            if output_id != "-":
                values_dict["roonOutputId"] = values_dict.get("roonOutputId", "**INVALID**")
                values_dict["roonOutputIdUi"] = output_id
            else:
                values_dict["roonOutputIdUi"] = "** INVALID **"

        except StandardError as err:
            self.logger.error(u"'roon_output_id_selected' error detected for device '{0}']. Line '{1}' has error='{2}'"
                              .format(indigo.devices[devId].name, sys.exc_traceback.tb_lineno, err))

    def roon_zone_unique_identity_key_selected(self, values_dict, type_id, devId):
        try:
            zone_unique_identity_key = values_dict.get('roonZoneUniqueIdentityKey', '-')
            if zone_unique_identity_key != '-':
                values_dict['roonZoneUniqueIdentityKeyUi'] = zone_unique_identity_key
            else:
                values_dict['roonZoneUniqueIdentityKeyUi'] = "** INVALID **"

            return values_dict

        except StandardError as err:
            self.logger.error(u"'roon_zone_unique_identity_key_selected' error detected. Line '{0}' has error='{1}'"
                              .format(indigo.devices[devId].name, sys.exc_traceback.tb_lineno, err))

    def roon_zones_selection(self, values_dict, type_id, zone_dev_id):
        try:
            self.logger.error(u"'roon_zones_selection' values_dict:\n{0}\n".format(values_dict))

            return values_dict

        except StandardError as err:
            self.logger.error(u"'roon_zones_selection' error detected. Line '{0}' has error='{1}'"
                              .format(sys.exc_traceback.tb_lineno, err))

    def supply_available_roon_outputs_list(self, filter, values_dict, type_id, output_dev_id):
        try:
            roonOutputToGroupToName = indigo.devices[output_dev_id].name
            values_dict["roonOutputToGroupTo"] = roonOutputToGroupToName

            available_roon_outputs_devices_list = list()

            for output_dev in indigo.devices:
                if output_dev.deviceTypeId == 'roonOutput' and output_dev.id != output_dev_id and output_dev.states['output_connected']:

                    output_dev_plugin_props = output_dev.pluginProps
                    output_id = output_dev_plugin_props.get('roonOutputId', '')

                    available_roon_outputs_devices_list.append((output_id, output_dev.name))

            def getRoonOutputName(roonOutputNameItem):
                return roonOutputNameItem[1]

            return sorted(available_roon_outputs_devices_list, key=getRoonOutputName)

        except StandardError as err:
            self.logger.error(u"'supply_available_roon_outputs_list' error detected. Line {0} has error='{1}'"
                              .format(sys.exc_traceback.tb_lineno, err))

    def ui_time(self, seconds):
        try:
            m, s = divmod(seconds, 60)
            h, m = divmod(m, 60)
            if h == 0:
                return u"{:d}:{:02d}".format(m, s)
            else:
                return u"{:d}:{:02d}:{:02d}".format(h, m, s)

        except StandardError as e:
            self.logger.error(u"'ui_time' error detected. Line '{0}' has error='{1}'".format(sys.exc_traceback.tb_lineno, e))

    def update_roon_output_device(self, roonOutputDevId, output_id):
        output_dev = indigo.devices[roonOutputDevId]

        try:
            auto_name_new_roon_output = bool(output_dev.pluginProps.get('autoNameNewRoonOutput', True))
            if auto_name_new_roon_output and output_dev.name[0:10] == 'new device':

                output_name = u"{0}".format(self.globals[K_ROON][K_OUTPUTS][output_id][K_DISPLAY_NAME])
                new_device_name = u"Roon Output - {0}".format(output_name)

                try:
                    output_dev.pluginProps.update({'roonOutputName': output_name})
                    output_dev.replacePluginPropsOnServer(output_dev.pluginProps)

                    new_device_name = u"Roon Output - {0}".format(output_name)

                    self.logger.debug(u"'update_roon_ouput_device' [Auto-name - New Device];"
                                      u" Debug Info of rename Roon Output from '{0}' to '{1}'"
                                      .format(output_dev.name, new_device_name))

                    output_dev.name = new_device_name
                    output_dev.replaceOnServer()
                except StandardError as err:
                    self.logger.error(u"'update_roon_output_device' [Auto-name];"
                                      u" Unable to rename Roon Output from '{0}' to '{1}'. Line '{2}' has error='{3}'"
                                      .format(output_dev.name, new_device_name, sys.exc_traceback.tb_lineno, err))

            if 1 in self.globals[K_ROON][K_OUTPUTS][output_id][K_CAN_GROUP_WITH_OUTPUT_IDS]:
                can_group_with_output_id_1 = self.globals[K_ROON][K_OUTPUTS][output_id][K_CAN_GROUP_WITH_OUTPUT_IDS][1]
            else:
                can_group_with_output_id_1 = ""
            if 2 in self.globals[K_ROON][K_OUTPUTS][output_id][K_CAN_GROUP_WITH_OUTPUT_IDS]:
                can_group_with_output_id_2 = self.globals[K_ROON][K_OUTPUTS][output_id][K_CAN_GROUP_WITH_OUTPUT_IDS][2]
            else:
                can_group_with_output_id_2 = ""
            if 3 in self.globals[K_ROON][K_OUTPUTS][output_id][K_CAN_GROUP_WITH_OUTPUT_IDS]:
                can_group_with_output_id_3 = self.globals[K_ROON][K_OUTPUTS][output_id][K_CAN_GROUP_WITH_OUTPUT_IDS][3]
            else:
                can_group_with_output_id_3 = ""
            if 4 in self.globals[K_ROON][K_OUTPUTS][output_id][K_CAN_GROUP_WITH_OUTPUT_IDS]:
                can_group_with_output_id_4 = self.globals[K_ROON][K_OUTPUTS][output_id][K_CAN_GROUP_WITH_OUTPUT_IDS][4]
            else:
                can_group_with_output_id_4 = ""
            if 5 in self.globals[K_ROON][K_OUTPUTS][output_id][K_CAN_GROUP_WITH_OUTPUT_IDS]:
                can_group_with_output_id_5 = self.globals[K_ROON][K_OUTPUTS][output_id][K_CAN_GROUP_WITH_OUTPUT_IDS][5]
            else:
                can_group_with_output_id_5 = ""

            key_value_list = list()
            if not output_dev.states['output_connected']:
                key_value_list.append({'key': 'output_connected', 'value': True})
            if output_dev.states['output_status'] != 'connected':
                key_value_list.append({'key': 'output_status', 'value': 'connected'})
            if output_dev.states['output_id'] != self.globals[K_ROON][K_OUTPUTS][output_id][K_OUTPUT_ID]:
                key_value_list.append({'key': 'output_id', 'value': self.globals[K_ROON][K_OUTPUTS][output_id][K_OUTPUT_ID]})
            if output_dev.states['display_name'] != self.globals[K_ROON][K_OUTPUTS][output_id][K_DISPLAY_NAME]:
                if self.globals[K_ROON][K_OUTPUTS][output_id][K_DISPLAY_NAME] != '':  # < TEST LEAVING DISPLAY NAME UNALTERED
                    key_value_list.append({'key': 'display_name', 'value': self.globals[K_ROON][K_OUTPUTS][output_id][K_DISPLAY_NAME]})

            if 'source_controls' in self.globals[K_ROON][K_OUTPUTS][output_id] and self.globals[K_ROON][K_OUTPUTS][output_id][K_SOURCE_CONTROLS_COUNT] > 0:
                if output_dev.states['source_control_1_status'] != self.globals[K_ROON][K_OUTPUTS][output_id][K_SOURCE_CONTROLS][1][K_STATUS]:
                    key_value_list.append({'key': 'source_control_1_status', 'value': self.globals[K_ROON][K_OUTPUTS][output_id][K_SOURCE_CONTROLS][1][K_STATUS]})
                if output_dev.states['source_control_1_display_name'] != self.globals[K_ROON][K_OUTPUTS][output_id][K_SOURCE_CONTROLS][1][K_DISPLAY_NAME]:
                    key_value_list.append({'key': 'source_control_1_display_name', 'value': self.globals[K_ROON][K_OUTPUTS][output_id][K_SOURCE_CONTROLS][1][K_DISPLAY_NAME]})
                if output_dev.states['source_control_1_control_key'] != self.globals[K_ROON][K_OUTPUTS][output_id][K_SOURCE_CONTROLS][1][K_CONTROL_KEY]:
                    key_value_list.append({'key': 'source_control_1_control_key', 'value': self.globals[K_ROON][K_OUTPUTS][output_id][K_SOURCE_CONTROLS][1][K_CONTROL_KEY]})
                if output_dev.states['source_control_1_control_key'] != self.globals[K_ROON][K_OUTPUTS][output_id][K_SOURCE_CONTROLS][1][K_CONTROL_KEY]:
                    key_value_list.append({'key': 'source_control_1_control_key', 'value': self.globals[K_ROON][K_OUTPUTS][output_id][K_SOURCE_CONTROLS][1][K_CONTROL_KEY]})
                if output_dev.states['source_control_1_supports_standby'] != self.globals[K_ROON][K_OUTPUTS][output_id][K_SOURCE_CONTROLS][1][K_SUPPORTS_STANDBY]:
                    key_value_list.append({'key': 'source_control_1_supports_standby', 'value': self.globals[K_ROON][K_OUTPUTS][output_id][K_SOURCE_CONTROLS][1][K_SUPPORTS_STANDBY]})
            else:
                    key_value_list.append({'key': 'source_control_1_status', 'value': ''})
                    key_value_list.append({'key': 'source_control_1_display_name', 'value': ''})
                    key_value_list.append({'key': 'source_control_1_control_key', 'value': ''})
                    key_value_list.append({'key': 'source_control_1_control_key', 'value': ''})
                    key_value_list.append({'key': 'source_control_1_supports_standby', 'value': False})

            if 'volume' in self.globals[K_ROON][K_OUTPUTS][output_id] and len(self.globals[K_ROON][K_OUTPUTS][output_id][K_VOLUME]) > 0:
                if output_dev.states['volume_hard_limit_min'] != self.globals[K_ROON][K_OUTPUTS][output_id][K_VOLUME][K_VOLUME_HARD_LIMIT_MIN]:
                    key_value_list.append({'key': 'volume_hard_limit_min', 'value': self.globals[K_ROON][K_OUTPUTS][output_id][K_VOLUME][K_VOLUME_HARD_LIMIT_MIN]})
                if output_dev.states['volume_min'] != self.globals[K_ROON][K_OUTPUTS][output_id][K_VOLUME][K_VOLUME_MIN]:
                    key_value_list.append({'key': 'volume_min', 'value': self.globals[K_ROON][K_OUTPUTS][output_id][K_VOLUME][K_VOLUME_MIN]})
                if output_dev.states['volume_is_muted'] != self.globals[K_ROON][K_OUTPUTS][output_id][K_VOLUME][K_VOLUME_IS_MUTED]:
                    key_value_list.append({'key': 'volume_is_muted', 'value': self.globals[K_ROON][K_OUTPUTS][output_id][K_VOLUME][K_VOLUME_IS_MUTED]})
                if output_dev.states['volume_max'] != self.globals[K_ROON][K_OUTPUTS][output_id][K_VOLUME][K_VOLUME_MAX]:
                    key_value_list.append({'key': 'volume_max', 'value': self.globals[K_ROON][K_OUTPUTS][output_id][K_VOLUME][K_VOLUME_MAX]})
                if output_dev.states['volume_value'] != self.globals[K_ROON][K_OUTPUTS][output_id][K_VOLUME][K_VOLUME_VALUE]:
                    key_value_list.append({'key': 'volume_value', 'value': self.globals[K_ROON][K_OUTPUTS][output_id][K_VOLUME][K_VOLUME_VALUE]})
                if output_dev.states['volume_step'] != self.globals[K_ROON][K_OUTPUTS][output_id][K_VOLUME][K_VOLUME_STEP]:
                    key_value_list.append({'key': 'volume_step', 'value': self.globals[K_ROON][K_OUTPUTS][output_id][K_VOLUME][K_VOLUME_STEP]})
                if output_dev.states['volume_hard_limit_max'] != self.globals[K_ROON][K_OUTPUTS][output_id][K_VOLUME][K_VOLUME_HARD_LIMIT_MAX]:
                    key_value_list.append({'key': 'volume_hard_limit_max', 'value': self.globals[K_ROON][K_OUTPUTS][output_id][K_VOLUME][K_VOLUME_HARD_LIMIT_MAX]})
                if output_dev.states['volume_soft_limit'] != self.globals[K_ROON][K_OUTPUTS][output_id][K_VOLUME][K_VOLUME_SOFT_LIMIT]:
                    key_value_list.append({'key': 'volume_soft_limit', 'value': self.globals[K_ROON][K_OUTPUTS][output_id][K_VOLUME][K_VOLUME_SOFT_LIMIT]})
                if output_dev.states['volume_type'] != self.globals[K_ROON][K_OUTPUTS][output_id][K_VOLUME][K_VOLUME_TYPE]:
                    key_value_list.append({'key': 'volume_type', 'value': self.globals[K_ROON][K_OUTPUTS][output_id][K_VOLUME][K_VOLUME_TYPE]})
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
            self.logger.error(u"'update_roon_output_device' error detected for device '{0}'. Line '{1}' has error='{2}'"
                              .format(output_dev.name, sys.exc_traceback.tb_lineno, err))

    def update_roon_zone_device(self, roonZoneDevId, zone_id):
        new_device_name = ""
        zone_dev = indigo.devices[roonZoneDevId]

        try:
            auto_name_new_roon_zone = bool(zone_dev.pluginProps.get('autoNameNewRoonZone', True))
            if auto_name_new_roon_zone and zone_dev.name[0:10] == 'new device':

                zone_name = u"{0}".format(self.globals[K_ROON][K_ZONES][zone_id][K_DISPLAY_NAME])
                new_device_name = u"Roon Zone - {0}".format(zone_name)

                try:
                    zone_dev.pluginProps.update({'roonZoneName': zone_name})
                    zone_dev.replacePluginPropsOnServer(zone_dev.pluginProps)

                    outputCount = self.globals[K_ROON][K_ZONES][zone_id][K_OUTPUTS_COUNT]
                    if outputCount == 0:
                        new_device_name = u"Roon Zone - {0}".format(zone_name)
                    else:
                        temp_zone_name = self.globals[K_ROON][K_ZONES][zone_id][K_OUTPUTS][1][K_DISPLAY_NAME]
                        for i in range(2, outputCount + 1):
                            temp_zone_name = "{0} + {1}".format(temp_zone_name, self.globals[K_ROON][K_ZONES][zone_id][K_OUTPUTS][i][K_DISPLAY_NAME])
                        new_device_name = u"Roon Zone - {0}".format(temp_zone_name)

                    self.logger.debug(u"'update_roon_zone_device' [Auto-name - New Device];"
                                      u" Debug Info of rename Roon Zone from '{0}' to '{1}'"
                                      .format(zone_dev.name, new_device_name))

                    zone_dev.name = new_device_name
                    zone_dev.replaceOnServer()
                except StandardError as err:
                    self.logger.error(u"'update_roon_zone_device' [Auto-name];"
                                      u" Unable to rename Roon Zone from '{0}' to '{1}'. Line '{2}' has error='{3}'"
                                      .format(zone_dev.name, new_device_name, sys.exc_traceback.tb_lineno, err))

            # Only check for a roon zone device dynamic rename if a grouped zone
            if self.globals[K_ROON][K_ZONES][zone_id][K_OUTPUTS_COUNT] > 1:
                dynamic_rename_check_required = bool(zone_dev.pluginProps.get('dynamicGroupedZoneRename', False))
                if dynamic_rename_check_required:   # True if Dynamic Rename Check Required
                    try:
                        outputCount = self.globals[K_ROON][K_ZONES][zone_id][K_OUTPUTS_COUNT]
                        if outputCount > 0:
                            new_zone_name = self.globals[K_ROON][K_ZONES][zone_id][K_OUTPUTS][1][K_DISPLAY_NAME]
                            for i in range(2, outputCount + 1):
                                new_zone_name = "{0} + {1}".format(new_zone_name, self.globals[K_ROON][K_ZONES][zone_id][K_OUTPUTS][i][K_DISPLAY_NAME])
                            new_device_name = u"Roon Zone - {0}".format(new_zone_name)

                            old_zone_name = zone_dev.pluginProps.get('roonZoneName', '-')  # e.g. 'Study + Dining Room'

                            if new_device_name != old_zone_name:  # e.g. 'Study + Kitchen' != 'Study + Dining Room'
                                zone_dev_props = zone_dev.pluginProps
                                zone_dev_props['roonZoneName'] = new_zone_name
                                zone_dev.replacePluginPropsOnServer(zone_dev_props)

                            if new_device_name != zone_dev.name:  # e.g. 'Roon Zone - Study + Kitchen'
                                zone_dev.name = new_device_name
                                zone_dev.replaceOnServer()

                    except StandardError as err:
                        self.logger.error(u"'update_roon_zone_device' [Dynamic Rename];"
                                          u" Unable to rename Roon Zone from '{0}' to '{1}'. Line '{2}' has error='{3}'"
                                          .format(originalZoneDevName, new_device_name,
                                                  sys.exc_traceback.tb_lineno, err))

            if 1 in self.globals[K_ROON][K_ZONES][zone_id][K_OUTPUTS]:
                output_id_1 = self.globals[K_ROON][K_ZONES][zone_id][K_OUTPUTS][1][K_OUTPUT_ID]
            else:
                output_id_1 = ""
            if 2 in self.globals[K_ROON][K_ZONES][zone_id][K_OUTPUTS]:
                output_id_2 = self.globals[K_ROON][K_ZONES][zone_id][K_OUTPUTS][2][K_OUTPUT_ID]
            else:
                output_id_2 = ""
            if 3 in self.globals[K_ROON][K_ZONES][zone_id][K_OUTPUTS]:
                output_id_3 = self.globals[K_ROON][K_ZONES][zone_id][K_OUTPUTS][3][K_OUTPUT_ID]
            else:
                output_id_3 = ""
            if 4 in self.globals[K_ROON][K_ZONES][zone_id][K_OUTPUTS]:
                output_id_4 = self.globals[K_ROON][K_ZONES][zone_id][K_OUTPUTS][4][K_OUTPUT_ID]
            else:
                output_id_4 = ""
            if 5 in self.globals[K_ROON][K_ZONES][zone_id][K_OUTPUTS]:
                output_id_5 = self.globals[K_ROON][K_ZONES][zone_id][K_OUTPUTS][5][K_OUTPUT_ID]
            else:
                output_id_5 = ""

            if 1 in self.globals[K_ROON][K_ZONES][zone_id][K_NOW_PLAYING][K_ARTIST_IMAGE_KEYS]:
                artist_image_key_1 = self.globals[K_ROON][K_ZONES][zone_id][K_NOW_PLAYING][K_ARTIST_IMAGE_KEYS][1]
            else:
                artist_image_key_1 = ""
            self.process_image(ARTIST, '1', zone_dev, artist_image_key_1)

            if 2 in self.globals[K_ROON][K_ZONES][zone_id][K_NOW_PLAYING][K_ARTIST_IMAGE_KEYS]:
                artist_image_key_2 = self.globals[K_ROON][K_ZONES][zone_id][K_NOW_PLAYING][K_ARTIST_IMAGE_KEYS][2]
            else:
                artist_image_key_2 = ""
            self.process_image(ARTIST, '2', zone_dev, artist_image_key_2)

            if 3 in self.globals[K_ROON][K_ZONES][zone_id][K_NOW_PLAYING][K_ARTIST_IMAGE_KEYS]:
                artist_image_key_3 = self.globals[K_ROON][K_ZONES][zone_id][K_NOW_PLAYING][K_ARTIST_IMAGE_KEYS][3]
            else:
                artist_image_key_3 = ""
            self.process_image(ARTIST, '3', zone_dev, artist_image_key_3)

            if 4 in self.globals[K_ROON][K_ZONES][zone_id][K_NOW_PLAYING][K_ARTIST_IMAGE_KEYS]:
                artist_image_key_4 = self.globals[K_ROON][K_ZONES][zone_id][K_NOW_PLAYING][K_ARTIST_IMAGE_KEYS][4]
            else:
                artist_image_key_4 = ""
            self.process_image(ARTIST, '4', zone_dev, artist_image_key_4)

            if 5 in self.globals[K_ROON][K_ZONES][zone_id][K_NOW_PLAYING][K_ARTIST_IMAGE_KEYS]:
                artist_image_key_5 = self.globals[K_ROON][K_ZONES][zone_id][K_NOW_PLAYING][K_ARTIST_IMAGE_KEYS][5]
            else:
                artist_image_key_5 = ""
            self.process_image(ARTIST, '5', zone_dev, artist_image_key_5)

            self.process_image(ALBUM, '', zone_dev, self.globals[K_ROON][K_ZONES][zone_id][K_NOW_PLAYING][K_IMAGE_KEY])

            zone_status = "stopped"
            if self.globals[K_ROON][K_ZONES][zone_id][K_STATE] == 'playing':
                zone_dev.updateStateImageOnServer(indigo.kStateImageSel.AvPlaying)
                zone_status = "playing"
            elif self.globals[K_ROON][K_ZONES][zone_id][K_STATE] == 'paused':
                zone_dev.updateStateImageOnServer(indigo.kStateImageSel.AvPaused)
                zone_status = "Paused"
            else:
                zone_dev.updateStateImageOnServer(indigo.kStateImageSel.AvStopped)

            key_value_list = list()

            if not zone_dev.states['zone_connected']:
                key_value_list.append({'key': 'zone_connected', 'value': True})

            if zone_dev.states['zone_status'] != zone_status:
                key_value_list.append({'key': 'zone_status', 'value': zone_status})

            if zone_dev.states['zone_id'] != self.globals[K_ROON][K_ZONES][zone_id][K_ZONE_ID]:
                key_value_list.append({'key': 'zone_id', 'value': self.globals[K_ROON][K_ZONES][zone_id][K_ZONE_ID]})

            if zone_dev.states['display_name'] != self.globals[K_ROON][K_ZONES][zone_id][K_DISPLAY_NAME]:
                key_value_list.append({'key': 'display_name', 'value': self.globals[K_ROON][K_ZONES][zone_id][K_DISPLAY_NAME]})

            if zone_dev.states['auto_radio'] != self.globals[K_ROON][K_ZONES][zone_id][K_SETTINGS][K_AUTO_RADIO]:
                key_value_list.append({'key': 'auto_radio', 'value': self.globals[K_ROON][K_ZONES][zone_id][K_SETTINGS][K_AUTO_RADIO]})

            if zone_dev.states['shuffle'] != self.globals[K_ROON][K_ZONES][zone_id][K_SETTINGS][K_SHUFFLE]:
                key_value_list.append({'key': 'shuffle', 'value': self.globals[K_ROON][K_ZONES][zone_id][K_SETTINGS][K_SHUFFLE]})

            if zone_dev.states['loop'] != self.globals[K_ROON][K_ZONES][zone_id][K_SETTINGS][K_LOOP]:
                key_value_list.append({'key': 'loop', 'value': self.globals[K_ROON][K_ZONES][zone_id][K_SETTINGS][K_LOOP]})

            if zone_dev.states['number_of_outputs'] != self.globals[K_ROON][K_ZONES][zone_id][K_OUTPUTS_COUNT]:
                key_value_list.append({'key': 'number_of_outputs', 'value': self.globals[K_ROON][K_ZONES][zone_id][K_OUTPUTS_COUNT]})

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

            if zone_dev.states['number_of_artist_image_keys'] != self.globals[K_ROON][K_ZONES][zone_id][K_NOW_PLAYING][K_ARTIST_IMAGE_KEYS_COUNT]:
                key_value_list.append({'key': 'number_of_artist_image_keys', 'value': self.globals[K_ROON][K_ZONES][zone_id][K_NOW_PLAYING][K_ARTIST_IMAGE_KEYS_COUNT]})

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

            if zone_dev.states['image_key'] != self.globals[K_ROON][K_ZONES][zone_id][K_NOW_PLAYING][K_IMAGE_KEY]:
                key_value_list.append({'key': 'image_key', 'value': self.globals[K_ROON][K_ZONES][zone_id][K_NOW_PLAYING][K_IMAGE_KEY]})

            if zone_dev.states['one_line_1'] != self.globals[K_ROON][K_ZONES][zone_id][K_NOW_PLAYING][K_ONE_LINE][K_LINE_1]:
                key_value_list.append({'key': 'one_line_1', 'value': self.globals[K_ROON][K_ZONES][zone_id][K_NOW_PLAYING][K_ONE_LINE][K_LINE_1]})

            if zone_dev.states['two_line_1'] != self.globals[K_ROON][K_ZONES][zone_id][K_NOW_PLAYING][K_TWO_LINE][K_LINE_1]:
                key_value_list.append({'key': 'two_line_1', 'value': self.globals[K_ROON][K_ZONES][zone_id][K_NOW_PLAYING][K_TWO_LINE][K_LINE_1]})

            if zone_dev.states['two_line_2'] != self.globals[K_ROON][K_ZONES][zone_id][K_NOW_PLAYING][K_TWO_LINE][K_LINE_2]:
                key_value_list.append({'key': 'two_line_2', 'value': self.globals[K_ROON][K_ZONES][zone_id][K_NOW_PLAYING][K_TWO_LINE][K_LINE_2]})

            if zone_dev.states['three_line_1'] != self.globals[K_ROON][K_ZONES][zone_id][K_NOW_PLAYING][K_THREE_LINE][K_LINE_1]:
                key_value_list.append({'key': 'three_line_1', 'value': self.globals[K_ROON][K_ZONES][zone_id][K_NOW_PLAYING][K_THREE_LINE][K_LINE_1]})

            if zone_dev.states['three_line_2'] != self.globals[K_ROON][K_ZONES][zone_id][K_NOW_PLAYING][K_THREE_LINE][K_LINE_2]:
                key_value_list.append({'key': 'three_line_2', 'value': self.globals[K_ROON][K_ZONES][zone_id][K_NOW_PLAYING][K_THREE_LINE][K_LINE_2]})

            if zone_dev.states['three_line_3'] != self.globals[K_ROON][K_ZONES][zone_id][K_NOW_PLAYING][K_THREE_LINE][K_LINE_3]:
                key_value_list.append({'key': 'three_line_3', 'value': self.globals[K_ROON][K_ZONES][zone_id][K_NOW_PLAYING][K_THREE_LINE][K_LINE_3]})

            if zone_dev.states['length'] != self.globals[K_ROON][K_ZONES][zone_id][K_NOW_PLAYING][K_LENGTH]:
                key_value_list.append({'key': 'length', 'value': self.globals[K_ROON][K_ZONES][zone_id][K_NOW_PLAYING][K_LENGTH]})
                ui_length = self.ui_time(self.globals[K_ROON][K_ZONES][zone_id][K_NOW_PLAYING][K_LENGTH])
                key_value_list.append({'key': 'ui_length', 'value': ui_length})

            if zone_dev.states['seek_position'] != self.globals[K_ROON][K_ZONES][zone_id][K_NOW_PLAYING][K_SEEK_POSITION]:
                key_value_list.append({'key': 'seek_position', 'value': self.globals[K_ROON][K_ZONES][zone_id][K_NOW_PLAYING][K_SEEK_POSITION]})

            if zone_dev.states['remaining'] != 0:
                key_value_list.append({'key': 'remaining', 'value': 0})
                key_value_list.append({'key': 'ui_remaining', 'value': '0:00'})

            if zone_dev.states['is_previous_allowed'] != self.globals[K_ROON][K_ZONES][zone_id][K_IS_PREVIOUS_ALLOWED]:
                key_value_list.append({'key': 'is_previous_allowed', 'value': self.globals[K_ROON][K_ZONES][zone_id][K_IS_PREVIOUS_ALLOWED]})

            if zone_dev.states['is_pause_allowed'] != self.globals[K_ROON][K_ZONES][zone_id][K_IS_PAUSE_ALLOWED]:
                key_value_list.append({'key': 'is_pause_allowed', 'value': self.globals[K_ROON][K_ZONES][zone_id][K_IS_PAUSE_ALLOWED]})

            if zone_dev.states['is_seek_allowed'] != self.globals[K_ROON][K_ZONES][zone_id][K_IS_SEEK_ALLOWED]:
                key_value_list.append({'key': 'is_seek_allowed', 'value': self.globals[K_ROON][K_ZONES][zone_id][K_IS_SEEK_ALLOWED]})

            if zone_dev.states['state'] != self.globals[K_ROON][K_ZONES][zone_id][K_STATE]:
                key_value_list.append({'key': 'state', 'value': self.globals[K_ROON][K_ZONES][zone_id][K_STATE]})

            if zone_dev.states['is_play_allowed'] != self.globals[K_ROON][K_ZONES][zone_id][K_IS_PLAY_ALLOWED]:
                key_value_list.append({'key': 'is_play_allowed', 'value': self.globals[K_ROON][K_ZONES][zone_id][K_IS_PLAY_ALLOWED]})

            if zone_dev.states['is_next_allowed'] != self.globals[K_ROON][K_ZONES][zone_id][K_IS_NEXT_ALLOWED]:
                key_value_list.append({'key': 'is_next_allowed', 'value': self.globals[K_ROON][K_ZONES][zone_id][K_IS_NEXT_ALLOWED]})

            if len(key_value_list) > 0:
                zone_dev.updateStatesOnServer(key_value_list)

        except StandardError as err:
            self.logger.error(u"'update_roon_zone_device' error detected for device '{0}'. Line '{1}' has error='{2}'"
                              .format(zone_dev.name, sys.exc_traceback.tb_lineno, err))
